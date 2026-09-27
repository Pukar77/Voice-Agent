"""
Voice Agent - talk to your knowledge base.

    speak  ->  AssemblyAI transcribes  ->  Groq + Qdrant answers  ->  edge-tts speaks back

Run from inside the `voice-agent` folder:

    python agent.py

Requirements:
    * ASSEMBLYAI_API_KEY, GROQ_API_KEY, QDRANT_URL in ../.env
    * a Qdrant server on QDRANT_URL, already holding the knowledge base
      (see RAG/vector_store.py to ingest it)
"""

import os
import queue
import re
import sys
import threading

from dotenv import load_dotenv

from RAG.chains import ask, preload
from STT.stt import MicrophoneListener
from TTS.tts import DEFAULT_VOICE, speak

load_dotenv()


# LLM answers and transcripts contain characters the Windows console
# (cp1252) cannot print, which would crash the agent mid-answer.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

_MD_NOISE = re.compile(r"\*\*|__|`+|[*#>|]|~~")
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF"
    "\u2190-\u21FF\uFE0F\u200D]"
)
# Newlines are deliberately absent: they are turned into sentence breaks
# first, and collapsing them here would silently join the two sentences.
_EXOTIC_SPACE = re.compile(r"[ \t\u00a0\u1680\u2000-\u200b\u202f\u205f\u3000]+")
_LIST_MARK = re.compile(r"(?:^|(?<=\.\s))[-*\u2022\u25cf\u00b7]+\s*")


def spoken(answer):
    """
    Make an LLM answer safe to read out loud.

    Edge TTS reads whatever it is given, so markdown, links and emoji have to
    go or the voice starts reciting punctuation.
    """
    text = _MD_NOISE.sub(" ", answer or "")
    text = re.sub(r"https?://\S+", "a link", text)

    text = _EXOTIC_SPACE.sub(" ", text)
    text = re.sub(r"\s*\n+\s*", ". ", text)  # line break -> sentence break
    text = _EMOJI.sub("", text)

    # Tidy the punctuation the substitutions above left behind.
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    text = re.sub(r"([:;])\s*\.", r"\1", text)
    text = _LIST_MARK.sub("", text)

    # Anything left that is not printable (control chars) becomes a space.
    text = "".join(" " if not ch.isprintable() else ch for ch in text)

    return re.sub(r"\s{2,}", " ", text).strip()


class VoiceAgent:
    """
    Wires the three steps together.

    Threads involved:
        mic-capture  reads audio and forwards it to AssemblyAI
        answer-loop  pulls finished questions, then answers them one at a time
        main         just waits, so Ctrl+C can shut everything down

    AssemblyAI calls our transcript callback on its own thread, so that
    callback only queues the text. The RAG call and the audio playback, both
    slow, happen on `answer-loop`.
    """

    def __init__(self, voice=DEFAULT_VOICE):
        self.voice = voice

        self._questions = queue.Queue()
        self._shutdown = threading.Event()

        self._listener = None
        self._worker = None

    # ---------------------------------------------------------------
    # Callbacks
    # ---------------------------------------------------------------

    def _on_final_transcript(self, text):
        """Runs on AssemblyAI's thread: hand the question over, return fast."""
        self._questions.put(text)

    def _on_error(self, error):
        print(f"\nAudio error: {error}")

    # ---------------------------------------------------------------
    # Answer loop
    # ---------------------------------------------------------------

    def _handle(self, question):
        print(f"\n> {question}")
        print("Thinking...")

        try:
            answer = ask(question)
        except Exception as exc:
            print(f"RAG error: {exc}")
            answer = "Sorry, I could not reach my knowledge base just now."

        print(f"< {answer}")

        # Mute the mic for the whole reply, otherwise the agent transcribes
        # its own voice and answers itself.
        listener = self._listener
        if listener is None:  # shut down while we were thinking
            return

        listener.pause()

        try:
            speak(spoken(answer), self.voice)
        except Exception as exc:
            print(f"TTS error: {exc}")
        finally:
            listener.resume()

    def _answer_loop(self):
        while not self._shutdown.is_set():
            try:
                question = self._questions.get(timeout=0.2)
            except queue.Empty:
                continue

            if question is None:  # shutdown sentinel
                break

            self._handle(question)

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def run(self):
        print("Loading knowledge base (first run downloads the embedding model)...")

        try:
            preload()
        except Exception as exc:
            print(f"\nCould not open the knowledge base: {exc}")
            print("Is Qdrant running and has the knowledge base been ingested?")
            print("  docker run -p 6333:6333 -v ./qdrant_storage:/qdrant/storage qdrant/qdrant")
            print("  python RAG/vector_store.py")
            return

        if not os.getenv("ASSEMBLYAI_API_KEY"):
            print("\nASSEMBLYAI_API_KEY is missing from .env - cannot listen.")
            return

        self._worker = threading.Thread(
            target=self._answer_loop, name="answer-loop", daemon=True
        )
        self._worker.start()

        self._listener = MicrophoneListener(
            on_final_transcript=self._on_final_transcript,
            on_error=self._on_error,
        )
        self._listener.start()

        try:
            while not self._shutdown.is_set():
                self._shutdown.wait(0.2)
        except KeyboardInterrupt:
            print("\nGoodbye.")
        finally:
            self.stop()

    def stop(self):
        self._shutdown.set()
        self._questions.put(None)  # wake the answer loop

        if self._listener:
            self._listener.stop()
            self._listener = None

        if self._worker:
            self._worker.join(timeout=2.0)
            self._worker = None


def main():
    VoiceAgent().run()


if __name__ == "__main__":
    main()
