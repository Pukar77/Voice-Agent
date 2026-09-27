import asyncio
import edge_tts

TEXT = "Hello Usha! K gardai ho???"
VOICE = "en-US-AndrewNeural"
OUTPUT_FILE = "agent_response.mp3"

async def stream_audio():
    communicate = edge_tts.Communicate(TEXT, VOICE)
    
    # Open file to write binary audio chunks as they stream in
    with open(OUTPUT_FILE, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
                print(f"Received audio chunk of size: {len(chunk['data'])} bytes")

    print(f"\nFinished streaming. Audio saved to {OUTPUT_FILE}")

asyncio.run(stream_audio())