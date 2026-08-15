"""Text to speech, written to a file the web app can serve."""

import subprocess
import uuid
from pathlib import Path

import config
from clients import get_openai_client
from errors import PipelineError
from textutil import split_into_chunks

# The speech endpoint rejects input longer than 4096 characters.
CHUNK_CHARS = 3800


def _join(parts: list[bytes], destination: Path, work_dir: Path) -> None:
    if len(parts) == 1:
        destination.write_bytes(parts[0])
        return

    if not config.HAS_FFMPEG:
        # Concatenated MP3 frames play back fine; the joins are just not
        # sample-accurate, which is inaudible in speech.
        destination.write_bytes(b"".join(parts))
        return

    pieces = []
    for index, blob in enumerate(parts):
        piece = work_dir / f"speech{index:03d}.mp3"
        piece.write_bytes(blob)
        pieces.append(piece)

    listing = work_dir / "speech.txt"
    listing.write_text("\n".join(f"file '{p.as_posix()}'" for p in pieces))
    subprocess.run(
        [config.FFMPEG, "-nostdin", "-y", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-c", "copy", str(destination)],
        check=True, capture_output=True,
    )


def synthesize(text: str, work_dir: Path) -> Path:
    """Render text to an mp3 in the media directory and return its path."""
    text = (text or "").strip()
    if not text:
        raise PipelineError("internal", "There is no text to read aloud.")

    client = get_openai_client()
    chunks = split_into_chunks(text, CHUNK_CHARS)
    try:
        parts = [
            client.audio.speech.create(
                model=config.TTS_MODEL, voice=config.TTS_VOICE, input=chunk
            ).content
            for chunk in chunks
        ]
    except Exception as exc:
        raise PipelineError(
            "internal", "The audio version could not be generated."
        ) from exc

    config.ensure_dirs()
    destination = config.MEDIA_DIR / f"{uuid.uuid4().hex}.mp3"
    _join(parts, destination, work_dir)
    return destination
