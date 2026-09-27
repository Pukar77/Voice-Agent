"""
Step 3 - Text to Speech.

Turns the agent's answer into spoken audio.

Public API:
    speak(text)              -> stream the audio to your speakers, block until done
    speak_async(text)        -> awaitable version, for use inside an event loop
    save(text, path)         -> write an mp3 file instead of playing it

Demo:
    python -m TTS.tts
"""

import asyncio
import shutil
import subprocess
from pathlib import Path

import edge_tts

DEFAULT_VOICE = "en-US-AndrewNeural"
DEFAULT_OUTPUT = Path(__file__).with_name("agent_response.mp3")

# ffplay ships with ffmpeg and is the player edge-tts itself uses. When it is
# missing we fall back to writing a file instead of playing it.
_FFPLAY = shutil.which("ffplay")


def _playback_command():
    """Argv for a player that reads mp3 bytes from stdin as they arrive."""
    if not _FFPLAY:
        return None

    return [
        _FFPLAY,
        "-nodisp",      # audio only, no video window
        "-autoexit",    # exit when stdin reaches EOF
        "-loglevel", "quiet",
        "-f", "mp3",
        "-i", "pipe:0",
    ]


async def _pump(text, voice, player):
    """
    Download audio chunks from edge-tts and hand them to `player` as they
    arrive, so the answer starts playing before synthesis has finished.
    """
    communicate = edge_tts.Communicate(text, voice)
    bytes_sent = 0

    async for chunk in communicate.stream():
        if chunk["type"] != "audio":
            continue

        if player is None:
            continue

        try:
            player.stdin.write(chunk["data"])
            player.stdin.flush()
            bytes_sent += len(chunk["data"])
        except (BrokenPipeError, ValueError):
            # The player quit. Stop feeding it but keep the loop alive so we
            # still measure a real synthesis length.
            player = None

    return bytes_sent


async def _save_async(text, path, voice):
    """Write the spoken audio to an mp3 file without playing it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    await edge_tts.Communicate(text, voice).save(str(path))

    return path


async def speak_async(text, voice=DEFAULT_VOICE):
    """
    Play `text` as audio. Returns once playback has finished, so the caller
    can treat this as "the agent is talking right now".
    """
    text = (text or "").strip()
    if not text:
        return

    command = _playback_command()

    if command is None:
        print(f"No audio player (ffplay) on PATH - writing {DEFAULT_OUTPUT.name} instead")
        await _save_async(text, DEFAULT_OUTPUT, voice)
        return

    player = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        await _pump(text, voice, player)
    finally:
        # Closing stdin is what tells ffplay to finish and exit.
        if player.stdin and not player.stdin.closed:
            player.stdin.close()
        player.wait()


def speak(text, voice=DEFAULT_VOICE):
    """Blocking version of speak_async()."""
    asyncio.run(speak_async(text, voice))


def save(text, path=DEFAULT_OUTPUT, voice=DEFAULT_VOICE):
    """Write `text` to an mp3 file and return its path."""
    return asyncio.run(_save_async(text, path, voice))


async def _demo():
    await speak_async(
        "Hello! I am your voice agent. Ask me anything about Apex Global "
        "Technologies and I will answer out loud."
    )


if __name__ == "__main__":
    asyncio.run(_demo())
