"""
Step 1 - Speech to Text.

Streams microphone audio to AssemblyAI and reports each completed turn.

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

# How long to keep the mic muted after playback stops, so the tail of the
# agent's own voice is not picked up as a new question.
RESUME_DELAY = 0.35


class MicrophoneListener:
    """
    Streams mic audio to AssemblyAI and hands finished transcripts to a
    callback.

    AssemblyAI delivers events on its own background thread, so the callback
    must return quickly: queue the text, do the slow work elsewhere.
    """

    def __init__(self, on_final_transcript, on_partial=None, on_error=None):
        self.on_final_transcript = on_final_transcript
        self.on_partial = on_partial or (lambda text: None)
        self.on_error = on_error or (lambda error: None)

        self._paused = threading.Event()
        self._stopping = threading.Event()

        self._client = None
        self._audio = None
        self._mic_stream = None
        self._pump_thread = None

    # ---------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------

    def start(self):
        """Connect to AssemblyAI, open the mic, start capture."""

        self._client = RealTimeTranscriber(
            RealTimeTranscriberOptions(terminate_timeout=TERMINATE_TIMEOUT),
            api_key=os.getenv("ASSEMBLYAI_API_KEY"),
        )

        self._client.on(RealTimeEvents.Begin, self._on_begin)
        self._client.on(RealTimeEvents.Turn, self._on_turn)
        self._client.on(RealTimeEvents.Error, self._on_error)

        # For raw mic audio, specify PCM encoding and sample rate
        self._client.connect(
            RealTimeParameters(
                speech_model=SPEECH_MODEL,
                encoding=Encoding.pcm_s16le,
                sample_rate=RATE,
            )
        )

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
        self._paused.clear()

        if self._pump_thread:
            self._pump_thread.join(timeout=2.0)

        if self._mic_stream:
            self._mic_stream.stop_stream()
            self._mic_stream.close()
            self._mic_stream = None

        if self._audio:
            self._audio.terminate()
            self._audio = None

        if self._client:
            self._client.disconnect(terminate=True)
            self._client = None

    # ---------------------------------------------------------------
    # Mute control
    # ---------------------------------------------------------------

    def pause(self):
        """
        Stop sending mic audio upstream. Use this while the agent is speaking,
        otherwise the microphone hears the answer and transcribes it.
        """
        self._paused.set()

    def resume(self):
        """Unmute after a short delay, once the speaker has gone quiet."""
        self._paused.clear()
        time.sleep(RESUME_DELAY)

    @property
    def paused(self):
        return self._paused.is_set()

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
                if self._paused.is_set():
                    time.sleep(0.02)
                    continue

                data = self._mic_stream.read(CHUNK, exception_on_overflow=False)

                # Re-check: a pause may have started while we were reading.
                if self._paused.is_set():
                    continue

                self._client.stream(data)

        except Exception as exc:
            self.on_error(exc)

    # ---------------------------------------------------------------
    # AssemblyAI event handlers
    # ---------------------------------------------------------------

    def _on_begin(self, client, event):
        print(f"Session started: {event.id}")
        print("Microphone connected. Speak now...")

    def _on_turn(self, client, event):
        transcript = (event.transcript or "").strip()
        if not transcript:
            return

        if event.end_of_turn:
            # The user has finished speaking: this is the text to answer.
            print(f"\n[FINAL USER INPUT]: {transcript}\n")
            self.on_final_transcript(transcript)
        else:
            self.on_partial(transcript)

    def _on_error(self, client, error):
        self.on_error(error)


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
