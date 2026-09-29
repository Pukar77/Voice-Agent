# Voice-Agent

**Talk to your knowledge base: you ask out loud, it answers out loud.**

A voice-first RAG assistant for the *Apex Global Technologies* enterprise
knowledge base. Speech is transcribed in real time by AssemblyAI, answered
from a Qdrant vector store via Groq, and spoken back with edge-tts — either
in your terminal as a CLI agent, or in the browser through a React web app
over WebSockets. A plain-text composer runs through the same RAG pipeline
for times when you cannot (or would rather not) speak.

---

## Features

- **Full-duplex voice loop** — speak, get transcribed live (partial
  transcripts stream in), hear the answer streamed back as audio chunks.
- **Two frontends, one pipeline** — a terminal agent (`agent.py`) and a
  browser app share the same STT → RAG → TTS core.
- **Streaming everywhere** — TTS audio is played/forwarded chunk by chunk
  as edge-tts produces it, so replies start before synthesis finishes.
- **Echo protection** — the microphone is muted while the agent speaks,
  with a short delay before listening resumes, so it never transcribes its
  own voice. (No barge-in: the agent always finishes its sentence.)
- **Text fallback** — the web UI's composer hits `POST /ask`, the same
  retrieval + LLM path the voice loop uses.
- **Keys stay server-side** — AssemblyAI and Groq credentials never reach
  the browser; it only ever sees transcripts and audio.
- **Warm cache** — the embedding model loads and Qdrant is probed at
  startup, not on the user's first question.

---

## Architecture

```
                        ┌──────────────────────────────────────────┐
   microphone (16 kHz)  │              backend/voice-agent         │
  ┌─────────────────┐   │                                          │
  │ STT/stt.py       │──▶│ AssemblyAI realtime transcription       │
  │ (AssemblyAI)     │   │            │ final transcript           │
  └─────────────────┘   │            ▼                             │
                        │ RAG/chains.py  Qdrant top-5 + Groq LLM   │
  ┌─────────────────┐   │            │ answer                      │
  │ TTS/tts.py       │◀──│            ▼                             │
  │ (edge-tts)       │   │ TTS streams mp3 chunks                  │
  └─────────────────┘   │                                          │
                        │  agent.py         the CLI voice loop     │
                        │  RAG/main.py      FastAPI HTTP + WS API  │
                        └──────────────┬───────────────────────────┘
                                       │  WS /ws/voice · POST /ask
                                       ▼
                        ┌──────────────────────────────────────────┐
                        │ frontend/  React + Vite                  │
                        │   mic bytes in · transcripts + audio out │
                        └──────────────────────────────────────────┘
```

**Ingestion (run once):** PDF → `document_loader.py` extracts TXT →
`vector_store.py` splits it (1000 chars, 200 overlap) →
`sentence-transformers/all-MiniLM-L6-v2` embeddings → Qdrant collection
`chunks for voice agent`.

**Retrieval:** each question is embedded the same way, top-5 similar
chunks are fetched, and Groq (`openai/gpt-oss-120b` by default,
temperature 0.2) answers strictly from that context — saying so when the
answer is not in the knowledge base.

### Tech stack

| Layer | Choice |
| --- | --- |
| STT | AssemblyAI realtime streaming (`universal-3-6-pro`), PCM16 16 kHz mono |
| Vector store | Qdrant + LangChain, HuggingFace `all-MiniLM-L6-v2` embeddings |
| LLM | Groq via `langchain_groq` (default `openai/gpt-oss-120b`) |
| TTS | edge-tts (`en-US-AndrewNeural`), streamed |
| Backend | FastAPI + Uvicorn (HTTP + WebSocket) |
| Frontend | React 19 + Vite 8 |
| CLI capture | PyAudio |

---

## Prerequisites

- **Python 3.10+** (developed on 3.13)
- **Node.js 18+**
- **Docker** (for Qdrant) — or any Qdrant instance you already run
- **ffmpeg** (`ffplay` on PATH) — optional, only for CLI audio playback;
  without it the CLI writes `TTS/agent_response.mp3` instead of speaking
- Microphone + speakers (or headphones — recommended)

---

## Getting started

### 1. Install the backend

```bash
python -m venv myenv
source myenv/bin/activate          # Windows: myenv\Scripts\activate
pip install -r requirements.txt
```

> PyAudio needs the PortAudio library on Linux
> (`apt install portaudio19-dev`); on Windows/macOS pip wheels usually
> install cleanly.

### 2. Configure secrets

Create a `.env` file **at the repo root** (it is git-ignored):

```dotenv
ASSEMBLYAI_API_KEY=...      # required  – realtime transcription
GROQ_API_KEY=...            # required  – LLM answers
QDRANT_URL=http://localhost:6333

GROQ_MODEL=openai/gpt-oss-120b   # optional, this is the default
ELEVENLABS_API_KEY=...          # optional, currently unused
```

### 3. Start Qdrant

```bash
docker run -p 6333:6333 -v ./qdrant_storage:/qdrant/storage qdrant/qdrant
```

### 4. Ingest the knowledge base (once)

```bash
cd backend/voice-agent
python RAG/vector_store.py
```

Re-running is safe: the collection is rebuilt from
`RAG/Apex_Global_Technologies_Enterprise_Knowledge_Base.txt` every time
(`force_recreate=True`). Swap in your own PDF/TXT pair to change the
knowledge base.

---

## Usage

### CLI voice agent

```bash
cd backend/voice-agent
python agent.py
```

Ask out loud; answers print to the terminal and play through the
speakers. The mic is muted while it speaks — use headphones to avoid
speaker bleed in a loud room. `Ctrl+C` to quit.

### Web app

Two processes — backend first:

```bash
# terminal 1
cd backend/voice-agent
python -m RAG.main                    # http://localhost:8000

# terminal 2
cd frontend
npm install
npm run dev                           # http://localhost:5173
```

Open **http://localhost:5173**, press the microphone button, allow mic
access, and talk. The text box at the bottom is the no-audio fallback —
same RAG pipeline, typed instead of spoken.

### Standalone demos

```bash
python -m STT.stt      # transcripts only, no answering — good for tuning the mic
python -m TTS.tts      # speaks a fixed sentence
python RAG/document_loader.py   # PDF → TXT extraction
```

---

## Configuration

### Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `ASSEMBLYAI_API_KEY` | yes | Realtime transcription |
| `GROQ_API_KEY` | yes | LLM answers |
| `QDRANT_URL` | yes | Qdrant endpoint, e.g. `http://localhost:6333` |
| `GROQ_MODEL` | no | Groq model id (default `openai/gpt-oss-120b`) |
| `ELEVENLABS_API_KEY` | no | Reserved, not used yet |
| `HOST` / `PORT` | no | Backend bind address (default `0.0.0.0:8000`) |
| `ALLOW_ORIGINS` | no | Comma-separated CORS origins (see below) |
| `VITE_BACKEND` | no | Where the Vite proxy sends `/ask`, `/health`, `/ws` |

### CORS

Allowed origins come from `ALLOW_ORIGINS`, defaulting to
`http://localhost:5173,http://127.0.0.1:5173`. The Vite dev server proxies
`/ask`, `/health` and `/ws` to the backend, so **no CORS is needed in
dev**. For a real deployment:

```bash
ALLOW_ORIGINS=https://myapp.example.com python -m RAG.main
```

---

## HTTP API

Base URL: `http://localhost:8000`

| Endpoint | Request | Response |
| --- | --- | --- |
| `GET /health` | — | `{"status": "ok"}` |
| `POST /ask` | `{"question": "..."}` | `{"answer": "..."}` |

`POST /ask` returns `400` for an empty question and `500` with the error
message if retrieval or generation fails.

### WebSocket `/ws/voice`

**Client → server**

| Message | Meaning |
| --- | --- |
| binary frame | Int16LE, 16 kHz, mono microphone audio |
| `{"type": "start"}` | open the AssemblyAI session |
| `{"type": "stop"}` | stop listening |

**Server → client**

| Message | Meaning |
| --- | --- |
| `{"type":"ready","sample_rate":16000}` | session open, start sending audio |
| `{"type":"state","value":"idle\|connecting\|listening\|thinking\|speaking"}` | agent state |
| `{"type":"partial","text":"..."}` | live transcript while you speak |
| `{"type":"final","text":"..."}` | your finished question |
| `{"type":"answer","text":"..."}` | the full answer, for the chat log |
| `{"type":"audio","data":"<base64>"}` | mp3 chunk, plays in arrival order |
| `{"type":"audio_end"}` | last chunk sent — client may close its stream |
| `{"type":"error","message":"..."}` | something went wrong |

Frames received while `thinking`/`speaking` are dropped (v1 has no
barge-in). The browser never sees the AssemblyAI or Groq keys.

---

## Project structure

```
.
├── .env                        # secrets (git-ignored, you create this)
├── requirements.txt
├── backend/
│   ├── qdrant_storage/         # Qdrant data (docker volume)
│   └── voice-agent/
│       ├── agent.py            # the CLI voice loop
│       ├── STT/
│       │   └── stt.py          # TranscriptionSession + MicrophoneListener
│       ├── RAG/
│       │   ├── chains.py       # ask() / preload() / build_answer(), the LLM prompt
│       │   ├── document_loader.py  # PDF → TXT
│       │   ├── vector_store.py # TXT → chunks → embeddings → Qdrant (ingest)
│       │   ├── retreival.py    # cached vectorstore + retriever
│       │   ├── main.py         # FastAPI: POST /ask + WS /ws/voice
│       │   └── *.pdf / *.txt   # the knowledge base
│       └── TTS/
│           └── tts.py          # speak() / synthesize_stream() / save()
└── frontend/
    ├── src/
    │   ├── App.jsx             # layout, captions, status
    │   ├── hooks/useVoiceAgent.js  # the client-side state machine
    │   ├── audio/capture.js    # mic → 16 kHz PCM frames
    │   ├── audio/player.js     # ordered mp3 chunk playback
    │   └── components/         # VoiceOrb, Transcript, Composer, Controls, …
    ├── smoke.mjs               # server-renders the UI to catch render errors
    └── player-check.mjs        # exercises the audio state machine with stubs
```

---

## Checks

```bash
cd frontend
node smoke.mjs          # renders the UI outside the browser
node player-check.mjs   # playback state machine, stubbed browser APIs
npm run build           # production build
```

`smoke.mjs` catches render errors a plain `vite build` cannot see.

---

## Troubleshooting

**Port 8000 already in use.** An older instance is still holding the
port — the browser is talking to *that* one, so backend edits look like
they did nothing. `python -m RAG.main` detects this and prints
instructions; a bare `uvicorn RAG.main:app` fails with
`WinError 10048` / `EADDRINUSE` instead. Stop the old process:

```bash
# Windows
netstat -ano | findstr :8000
taskkill /F /PID <pid>

# macOS/Linux
lsof -ti tcp:8000 | xargs kill
```

…or listen elsewhere and point the frontend at it:

```bash
PORT=8001 python -m RAG.main
VITE_BACKEND=http://localhost:8001 npm run dev
```

**"Qdrant collection does not exist."** Qdrant is not running or the
knowledge base was never ingested — see steps 3–4 above.

**`ASSEMBLYAI_API_KEY is missing / rejected`.** The key is checked
against the REST API up front (the realtime socket only reports a bad key
as a generic "Unauthorized Connection"). Create a fresh key at
<https://www.assemblyai.com/dashboard/> and update `.env`.

**First run is slow.** The embedding model downloads and loads on first
use; both the CLI and the server preload it at startup so the first
question is fast.

**No sound from the CLI.** Check `ffplay` is on PATH — without it the
agent writes `backend/voice-agent/TTS/agent_response.mp3` instead of
playing. Headphones also isolate the mic from the speakers.

**Transcribing its own voice.** Use headphones. The mic is muted during
playback plus a 0.35 s cool-down, but speaker bleed can still leak past
that in a loud room.

---

## Security notes

- `.env` is git-ignored — never commit it.
- The browser only ever receives transcripts, states and audio; API keys
  stay on the server.
- Lock down `ALLOW_ORIGINS` before deploying beyond localhost.
