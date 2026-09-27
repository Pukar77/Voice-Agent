import os
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
    TerminationEvent,
    TurnEvent,
)

load_dotenv()




# Audio recording configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024

def on_begin(client: RealTimeTranscriber, event: BeginEvent):
    print(f"Session started: {event.id}")
    print("Microphone connected. Speak now...")

def on_turn(client: RealTimeTranscriber, event: TurnEvent):
    if event.transcript:
        print(f"User said: {event.transcript}")

def on_error(client: RealTimeTranscriber, error: RealTimeError):
    print(f"Error: {error}")

def on_turn(client: RealTimeTranscriber, event: TurnEvent):
    # Only print and process when the user HAS FINISHED speaking their turn
    if event.end_of_turn and event.transcript:
        print(f"\n[FINAL USER INPUT]: {event.transcript}\n")
        
        # ---> THIS IS WHERE YOU CALL YOUR LLM AND TOOLS <---
        # response = call_llm_and_tools(event.transcript)
        
    elif event.transcript:
        # (Optional) Print partials on a single re-written line for live UI feed
        print(f"User speaking... {event.transcript}", end="\r")

def main():
    client = RealTimeTranscriber(
        RealTimeTranscriberOptions(terminate_timeout=30.0),
        api_key=os.getenv("ASSEMBLYAI_API_KEY"),
    )

    client.on(RealTimeEvents.Begin, on_begin)
    client.on(RealTimeEvents.Turn, on_turn)
    client.on(RealTimeEvents.Error, on_error)

    # For raw mic audio, specify PCM encoding and sample rate
    client.connect(
        RealTimeParameters(speech_model="universal-3-6-pro", encoding=Encoding.pcm_s16le, sample_rate=RATE)
    )

    # Initialize PyAudio stream
    audio = pyaudio.PyAudio()
    mic_stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    try:
        while True:
            # Read raw PCM bytes from mic and send directly to WebSocket
            data = mic_stream.read(CHUNK, exception_on_overflow=False)
            client.stream(data)
    except KeyboardInterrupt:
        print("\nStopping stream...")
    finally:
        mic_stream.stop_stream()
        mic_stream.close()
        audio.terminate()
        client.disconnect(terminate=True)

if __name__ == "__main__":
    main()