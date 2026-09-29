"""
Step 1 - Speech to Text.

Streams audio to AssemblyAI and reports each completed turn.

Two layers:

    TranscriptionSession   the AssemblyAI connection itself. It does not care
                           where the audio comes from: it just takes PCM16
                           frames. Shared by the CLI (microphone) and the
                           voice server (websocket).
    MicrophoneListener     the CLI wrapper: opens the mic and pushes frames
                           into a session.

Public API:
    listener = MicrophoneListener(on_final_transcript=my_callback)
    listener.start()   # returns immediately, mic capture runs on a thread
    listener.pause()   # stop sending audio, e.g. while the agent is speaking
    listener.resume()
    listener.stop()

Demo:
    python -m STT.stt
"""

import os
import threading
import time

import pyaudio
import requests
from dotenv import load_dotenv
from assemblyai.streaming.v3 import (
    BeginEvent,
    Encoding,
    RealTimeError,
    RealTimeEvents,
    RealTimeParameters,
    RealTimeTranscriber,
    RealTimeTranscriberOptions,
    TurnEvent,
)

load_dotenv()


# Audio recording configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024

SPEECH_MODEL = "universal-3-6-pro"
TERMINATE_TIMEOUT = 30.0

API_BASE = "https://api.assemblyai.com"

# Opening the websocket sometimes fails with a transient TLS/network timeout
# ("_ssl.c: The handshake operation timed out"), so the connect is retried
# with a growing delay before giving up.
CONNECT_ATTEMPTS = 3
CONNECT_BACKOFF = 2.0

# How long to keep the mic muted after playback stops, so the tail of the
# agent's own voice is not picked up as a new question.
RESUME_DELAY = 0.35


class TranscriptionAuthError(RuntimeError):
    """The AssemblyAI API key is missing or was rejected."""


def verify_api_key():
    """
    Fail fast, with a readable message, when the AssemblyAI key is unusable.

    The realtime websocket only reports a bad key after connecting, as a
    generic "Unauthorized Connection" error, so the key is checked up front
    against the REST API.
    """

    api_key = os.getenv("ASSEMBLYAI_API_KEY")

    if not api_key:
        raise TranscriptionAuthError(
            "ASSEMBLYAI_API_KEY is missing from .env - cannot listen."
        )

    try:
        response = requests.get(
            f"{API_BASE}/v2/transcript",
            params={"limit": 1},
            headers={"Authorization": api_key},
            timeout=15,
        )
    except requests.RequestException as exc:
        # A network problem must not block the agent: the realtime
        # connection is retried below and will surface any real failure.
        print(f"Warning: could not pre-check the AssemblyAI key ({exc}).")
        return

    if response.status_code in (401, 403):
        raise TranscriptionAuthError(
            f"AssemblyAI rejected ASSEMBLYAI_API_KEY (HTTP {response.status_code}). "
            "Create a new key at https://www.assemblyai.com/dashboard/ and "
            "update ASSEMBLYAI_API_KEY in .env"
        )


class TranscriptionSession:
    """
    One AssemblyAI realtime session, fed by whichever component has audio.

    AssemblyAI calls back on its own thread, so every handler here returns
    fast and just forwards to the callbacks given at construction time.

    Threading: `stream()` and `stop()` may be called from a different thread
    than `start()`. A lock keeps a frame from being sent on a client that is
    being torn down.
    """

    def __init__(self, on_final_transcript, on_partial=None, on_error=None,
                 on_begin=None):
        self.on_final_transcript = on_final_transcript
        self.on_partial = on_partial or (lambda text: None)
        self.on_error = on_error or (lambda error: None)
        self.on_begin = on_begin or (lambda event: None)

        self._paused = threading.Event()
        self._client = None
        self._lock = threading.Lock()

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def start(self):
        """Connect to AssemblyAI. Call once, from the owning thread."""

        verify_api_key()

        parameters = RealTimeParameters(
            speech_model=SPEECH_MODEL,
            encoding=Encoding.pcm_s16le,
            sample_rate=RATE,
        )

        for attempt in range(1, CONNECT_ATTEMPTS + 1):
            client = RealTimeTranscriber(
                RealTimeTranscriberOptions(terminate_timeout=TERMINATE_TIMEOUT),
                api_key=os.getenv("ASSEMBLYAI_API_KEY"),
            )
            client.on(RealTimeEvents.Begin, self._on_begin)
            client.on(RealTimeEvents.Turn, self._on_turn)
            client.on(RealTimeEvents.Error, self._on_error)

            try:
                client.connect(parameters)
            except Exception as exc:
                try:
                    client.disconnect(terminate=True)
                except Exception:
                    pass

                print(
                    f"\nConnection failed (attempt {attempt}/{CONNECT_ATTEMPTS}): {exc}"
                )

                if attempt == CONNECT_ATTEMPTS:
                    raise RuntimeError(
                        f"Could not open the AssemblyAI stream after "
                        f"{CONNECT_ATTEMPTS} attempts: {exc}"
                    ) from exc

                time.sleep(CONNECT_BACKOFF * attempt)
                continue

            with self._lock:
                self._client = client
            break

    def stop(self):
        """Close the session. Frames sent afterwards are ignored."""

        self._paused.clear()

        with self._lock:
            client, self._client = self._client, None

        if client is not None:
            try:
                client.disconnect(terminate=True)
            except Exception:
                pass

    @property
    def started(self):
        with self._lock:
            return self._client is not None

    # ---------------------------------------------------------------
    # Audio in
    # ---------------------------------------------------------------

    def stream(self, data):
        """
        Forward one chunk of PCM16 audio (little-endian, 16 kHz, mono).

        Chunks are dropped while paused, which is how the agent avoids
        transcribing its own voice.
        """

        if not data or self._paused.is_set():
            return

        with self._lock:
            if self._client is None:
                return
            self._client.stream(data)

    # ---------------------------------------------------------------
    # Mute control
    # ---------------------------------------------------------------

    def pause(self):
        """
        Stop sending audio upstream. Use this while the agent is speaking,
        otherwise the microphone hears the answer and transcribes it.
        """
        self._paused.set()

    def resume(self, delay=RESUME_DELAY):
        """Unmute, optionally after a short delay for the speaker to go quiet."""
        self._paused.clear()
        if delay:
            time.sleep(delay)

    @property
    def paused(self):
        return self._paused.is_set()

    # ---------------------------------------------------------------
    # AssemblyAI event handlers (run on AssemblyAI's thread)
    # ---------------------------------------------------------------

    def _on_begin(self, client, event):
        self.on_begin(event)

    def _on_turn(self, client, event):
        transcript = (event.transcript or "").strip()
        if not transcript:
            return

        if event.end_of_turn:
            # The user has finished speaking: this is the text to answer.
            self.on_final_transcript(transcript)
        else:
            self.on_partial(transcript)

    def _on_error(self, client, error):
        self.on_error(error)


class MicrophoneListener:
    """
    Streams mic audio to AssemblyAI and hands finished transcripts to a
    callback.

    AssemblyAI delivers events on its own background thread, so the callback
    must return quickly: queue the text, do the slow work elsewhere.
    """

    def __init__(self, on_final_transcript, on_partial=None, on_error=None):
        self.on_error = on_error or (lambda error: None)

        self.session = TranscriptionSession(
            on_final_transcript=on_final_transcript,
            on_partial=on_partial,
            on_error=self.on_error,
            on_begin=self._on_begin,
        )

        self._stopping = threading.Event()

        self._audio = None
        self._mic_stream = None
        self._pump_thread = None

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def start(self):
        """Connect to AssemblyAI, open the mic, start capture."""

        self.session.start()

        self._audio = pyaudio.PyAudio()
        self._mic_stream = self._audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )

        self._pump_thread = threading.Thread(
            target=self._pump, name="mic-capture", daemon=True
        )
        self._pump_thread.start()

    def stop(self):
        """Stop capture and close the session."""

        self._stopping.set()

        if self._pump_thread:
            self._pump_thread.join(timeout=2.0)
            self._pump_thread = None

        if self._mic_stream:
            self._mic_stream.stop_stream()
            self._mic_stream.close()
            self._mic_stream = None

        if self._audio:
            self._audio.terminate()
            self._audio = None

        self.session.stop()

    # ---------------------------------------------------------------
    # Mute control
    # ---------------------------------------------------------------

    def pause(self):
        """Stop sending mic audio upstream, e.g. while the agent speaks."""
        self.session.pause()

    def resume(self):
        """Unmute after a short delay, once the speaker has gone quiet."""
        self.session.resume()

    @property
    def paused(self):
        return self.session.paused

    # ---------------------------------------------------------------
    # Audio pump
    # ---------------------------------------------------------------

    def _pump(self):
        """
        Read PCM frames and forward them to AssemblyAI.

        Runs on its own thread: this loop can only be as responsive as the
        websocket, so nothing slow may happen inside it.
        """
        try:
            while not self._stopping.is_set():
                if self.session.paused:
                    time.sleep(0.02)
                    continue

                data = self._mic_stream.read(CHUNK, exception_on_overflow=False)

                # Re-check: a pause may have started while we were reading.
                if self.session.paused:
                    continue

                self.session.stream(data)

        except Exception as exc:
            self.on_error(exc)

    # ---------------------------------------------------------------

    def _on_begin(self, event):
        print(f"Session started: {event.id}")
        print("Microphone connected. Speak now...")


def main():
    """Print transcripts only, no answering. Useful for tuning the mic."""

    listener = MicrophoneListener(
        on_final_transcript=lambda text: print(f"You said: {text}"),
        on_partial=lambda text: print(f"User speaking... {text}", end="\r"),
        on_error=lambda error: print(f"Error: {error}"),
    )

    listener.start()

    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping stream...")
    finally:
        listener.stop()


if __name__ == "__main__":
    main()
