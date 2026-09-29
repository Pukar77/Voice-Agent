"""
RAG API - the HTTP/WebSocket surface a frontend talks to.

    GET  /health      is the server alive
    POST /ask         text question -> text answer (no audio)
    WS   /ws/voice    the voice loop: mic bytes in, transcripts + audio out

Run:

    python -m RAG.main          # http://localhost:8000
"""

import asyncio
import base64
import json
import os
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from RAG.chains import ask as rag_ask, build_answer, preload
from RAG.retreival import get_vectorstore
from STT.stt import RATE, TranscriptionSession
from TTS.tts import DEFAULT_VOICE, synthesize_stream

# The CLI already knows how to make an answer speakable (markdown, links and
# emoji out); the browser plays edge-tts output, so it needs the same cleanup.
from agent import spoken

# Origins the browser may connect from. Override for a real deployment:
#   ALLOW_ORIGINS=https://myapp.example.com python -m RAG.main
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

# Pause between "answer fully played" and "listen again", so the tail of the
# agent's own voice cannot be picked up as a new question.
LISTEN_AGAIN_DELAY = 0.35

# Where the server listens. Override when the port is already taken:
#   PORT=8001 python -m RAG.main
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))


# ---------------------------------------------------------
# Voice session
# ---------------------------------------------------------

class VoiceSocket:
    """
    One browser connection: mic bytes -> AssemblyAI -> RAG -> TTS -> browser.

    Three loops are involved:

      receive  lives in the endpoint itself; it reads frames and commands
      send     is the *only* writer of the socket (concurrent sends are not
               allowed), draining a queue that any thread may add to
      answer   processes one question at a time: ask(), then stream TTS

    AssemblyAI calls back from its own thread, which is why everything it
    produces goes through `_emit()` -> `loop.call_soon_threadsafe()`.
    """

    def __init__(self, ws: WebSocket):
        self._ws = ws
        self._loop = asyncio.get_running_loop()

        self._outgoing: asyncio.Queue = asyncio.Queue()
        self._turns: asyncio.Queue = asyncio.Queue()

        self._session: TranscriptionSession | None = None
        self._state = "connecting"
        self._closed = False

        self._sender = self._loop.create_task(self._send_loop())
        self._answerer = self._loop.create_task(self._answer_loop())

    # -----------------------------------------------------------
    # Outgoing messages
    # -----------------------------------------------------------

    def _emit(self, message: dict):
        """Queue a JSON message. Safe from any thread."""

        if self._closed:
            return

        payload = json.dumps(message, ensure_ascii=False)

        try:
            self._loop.call_soon_threadsafe(self._outgoing.put_nowait, payload)
        except RuntimeError:
            pass  # event loop already closed

    def _set_state(self, value: str):
        self._state = value
        self._emit({"type": "state", "value": value})

    async def _send_loop(self):
        """The single writer of this websocket."""

        while True:
            payload = await self._outgoing.get()

            try:
                await self._ws.send_text(payload)
            except Exception:
                # Peer went away; the receive loop performs the cleanup.
                return

    # -----------------------------------------------------------
    # Transcription callbacks (AssemblyAI's thread)
    # -----------------------------------------------------------

    def _on_final(self, text: str):
        # Stop listening immediately: the turn is complete, and while we
        # think and speak nothing else may be transcribed.
        if self._session is not None:
            self._session.pause()

        try:
            self._loop.call_soon_threadsafe(self._turns.put_nowait, text)
        except RuntimeError:
            pass

    # -----------------------------------------------------------
    # Answer loop
    # -----------------------------------------------------------

    async def _answer_loop(self):
        while True:
            question = await self._turns.get()

            try:
                await self._answer(question)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._emit({"type": "error", "message": str(exc)})
                await self._listen_again()

    async def _answer(self, question: str):
        self._emit({"type": "final", "text": question})
        self._set_state("thinking")

        answer = await asyncio.to_thread(rag_ask, question)

        # The full text feeds the chat UI; the spoken version feeds the TTS.
        self._emit({"type": "answer", "text": answer})
        self._set_state("speaking")

        # Any failure from here on reaches `_answer_loop`, which reports it
        # and unmutes the transcriber - so no lock to release on error paths.
        async for chunk in synthesize_stream(spoken(answer), DEFAULT_VOICE):
            if self._closed:
                return
            self._emit(
                {"type": "audio", "data": base64.b64encode(chunk).decode("ascii")}
            )

        # Everything for this reply is already on the wire, in order, so the
        # client may close its media stream and let the tail play out.
        self._emit({"type": "audio_end"})

        await self._listen_again()

    async def _listen_again(self):
        """Unmute the transcriber once the reply has faded out."""

        session = self._session

        if session is not None:
            await asyncio.sleep(LISTEN_AGAIN_DELAY)
            session.resume(delay=0)

        if not self._closed:
            self._set_state("listening")

    # -----------------------------------------------------------
    # Incoming messages
    # -----------------------------------------------------------

    def feed(self, data: bytes):
        """
        One frame of microphone audio.

        Frames are dropped while thinking/speaking: v1 has no barge-in, so
        the agent always gets to finish its sentence.
        """

        session = self._session

        if session is None or self._state != "listening":
            return

        try:
            session.stream(data)
        except Exception as exc:
            self._emit({"type": "error", "message": str(exc)})

    async def handle_command(self, text: str):
        try:
            command = json.loads(text)
        except ValueError:
            self._emit({"type": "error", "message": "Commands must be JSON."})
            return

        kind = command.get("type") if isinstance(command, dict) else None

        if kind == "start":
            await self.start()
        elif kind == "stop":
            self._set_state("idle")
        else:
            self._emit({"type": "error", "message": f"Unknown command: {kind!r}"})

    async def start(self):
        """Open the AssemblyAI session. Connects off-loop; it can take seconds."""

        if self._session is not None:
            return

        self._set_state("connecting")

        session = TranscriptionSession(
            on_final_transcript=self._on_final,
            on_partial=lambda text: self._emit({"type": "partial", "text": text}),
            on_error=lambda error: self._emit(
                {"type": "error", "message": str(error)}
            ),
        )

        try:
            await asyncio.to_thread(session.start)
        except Exception as exc:
            self._emit({"type": "error", "message": str(exc)})
            self._set_state("idle")
            return

        self._session = session

        self._emit({"type": "ready", "sample_rate": RATE})
        self._set_state("listening")

    # -----------------------------------------------------------
    # Teardown
    # -----------------------------------------------------------

    async def close(self):
        if self._closed:
            return

        self._closed = True

        for task in (self._sender, self._answerer):
            if task is not None:
                task.cancel()

        session, self._session = self._session, None

        if session is not None:
            try:
                await asyncio.to_thread(session.stop)
            except Exception:
                pass


# ---------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the embedding model and confirm Qdrant answers before any request
    # arrives, so the first question is not the one that pays the warm-up.
    print("Loading knowledge base ...")

    try:
        await asyncio.to_thread(preload)
    except Exception as exc:
        print(f"\nCould not open the knowledge base: {exc}")
        print("Is Qdrant running and has the knowledge base been ingested?")
        print("  docker run -p 6333:6333 -v ./qdrant_storage:/qdrant/storage qdrant/qdrant")
        print("  python RAG/vector_store.py")

    yield


app = FastAPI(title="RAG API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------

class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str


# ---------------------------------------------------------
# Health Check API
# ---------------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }


# ---------------------------------------------------------
# Ask API
# ---------------------------------------------------------

@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):

    # Remove leading/trailing spaces
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question is required."
        )

    try:
        # -------------------------------------------------
        # 1. Connect to Qdrant
        # -------------------------------------------------

        vectorstore = get_vectorstore()

        # -------------------------------------------------
        # 2. Search Qdrant for relevant chunks
        # -------------------------------------------------

        docs = vectorstore.similarity_search(
            question,
            k=5
        )

        # -------------------------------------------------
        # 3. Send retrieved documents + question to LLM
        # -------------------------------------------------

        answer = build_answer(
            question=question,
            docs=docs
        )

        # -------------------------------------------------
        # 4. Return response
        # -------------------------------------------------

        return AskResponse(
            answer=answer
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


# ---------------------------------------------------------
# Voice WebSocket
# ---------------------------------------------------------

@app.websocket("/ws/voice")
async def voice_socket(ws: WebSocket):
    await ws.accept()

    session = VoiceSocket(ws)

    try:
        while True:
            message = await ws.receive()

            if message.get("type") == "websocket.disconnect":
                break

            data = message.get("bytes")
            if data is not None:
                session.feed(data)
                continue

            text = message.get("text")
            if text is not None:
                await session.handle_command(text)

    except WebSocketDisconnect:
        pass
    finally:
        await session.close()


# ---------------------------------------------------------
# Run Application
# ---------------------------------------------------------

def _port_taken(host, port):
    """
    Is something already listening on `host:port`?

    Probed by connecting, not by binding: on Windows SO_REUSEADDR lets a
    second bind succeed, which would hide the clash until uvicorn dies with
    WinError 10048.
    """

    target = "127.0.0.1" if host in ("0.0.0.0", "::") else host

    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((target, port)) == 0


def _explain_port_clash(port):
    """Turn WinError 10048 / EADDRINUSE into something actionable."""

    print(f"\nPort {port} is already in use - another voice server is running.")
    print("The new process cannot take the port, and the browser keeps talking")
    print("to the first one, so backend edits look like they did nothing.")
    print("Stop the old process first:\n")
    print(f"    Windows    netstat -ano | findstr :{port}")
    print("               taskkill /F /PID <pid>")
    print(f"    macOS/Linux  lsof -ti tcp:{port} | xargs kill\n")
    print(f"Or listen somewhere else:  PORT={port + 1} python -m RAG.main")
    print(f"  (then point the frontend at it: VITE_BACKEND=http://localhost:{port + 1})\n")


def main():
    import uvicorn

    if _port_taken(HOST, PORT):
        _explain_port_clash(PORT)
        raise SystemExit(1)

    uvicorn.run(
        "RAG.main:app",
        host=HOST,
        port=PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
