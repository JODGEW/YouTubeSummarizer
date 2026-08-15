"""Getting text out of a video.

Two sources, cheapest first:

1. The caption track YouTube already has. Free, instant, and usually more
   accurate than anything we could run ourselves.
2. Speech recognition over the downloaded audio, when there are no captions.
"""

import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

import config
from clients import get_openai_client
from errors import PipelineError
from textutil import normalize

_local_model = None
_local_model_lock = threading.Lock()


# --- 1. YouTube's own captions --------------------------------------------

def fetch_captions(video_id: str, preferred_languages: list[str]) -> Optional[dict]:
    """Return {"text", "language"} from YouTube's captions, or None if there
    are none to be had. A caption lookup failing is never fatal: the caller
    falls back to speech recognition."""
    from youtube_transcript_api import YouTubeTranscriptApi

    try:
        listing = YouTubeTranscriptApi().list(video_id)
    except Exception:
        return None

    transcript = None
    for finder in ("find_manually_created_transcript", "find_generated_transcript"):
        try:
            transcript = getattr(listing, finder)(preferred_languages)
            break
        except Exception:
            continue
    if transcript is None:
        try:
            transcript = next(iter(listing))
        except (StopIteration, TypeError):
            return None

    try:
        snippets = transcript.fetch().to_raw_data()
    except Exception:
        return None

    text = normalize(" ".join(s.get("text", "") for s in snippets))
    if not text:
        return None
    return {"text": text, "language": getattr(transcript, "language_code", "unknown")}


# --- 2. Speech recognition -------------------------------------------------

def _shrink_for_upload(path: Path, work_dir: Path) -> list[Path]:
    """Return audio files that each fit within the upload limit.

    Without ffmpeg we can only pass the original file through, so an
    oversized file becomes an actionable error rather than a failed upload.
    """
    if path.stat().st_size <= config.ASR_UPLOAD_LIMIT_BYTES:
        return [path]

    if not config.HAS_FFMPEG:
        raise PipelineError(
            "transcription_failed",
            "This video's audio is too large to transcribe without ffmpeg "
            "installed on the server. Install ffmpeg, or try a video that has "
            "YouTube captions.",
        )

    # 16 kHz mono at 32 kbps is plenty for speech recognition and roughly
    # 14 MB per hour, which brings almost every video under the limit.
    compressed = work_dir / "asr.mp3"
    subprocess.run(
        [config.FFMPEG, "-nostdin", "-y", "-i", str(path),
         "-ac", "1", "-ar", "16000", "-b:a", "32k", str(compressed)],
        check=True, capture_output=True,
    )
    if compressed.stat().st_size <= config.ASR_UPLOAD_LIMIT_BYTES:
        return [compressed]

    split_dir = work_dir / "chunks"
    split_dir.mkdir(exist_ok=True)
    subprocess.run(
        [config.FFMPEG, "-nostdin", "-y", "-i", str(compressed),
         "-f", "segment", "-segment_time", str(config.ASR_CHUNK_SECONDS),
         "-c", "copy", str(split_dir / "part%03d.mp3")],
        check=True, capture_output=True,
    )
    parts = sorted(split_dir.glob("part*.mp3"))
    if not parts:
        raise PipelineError(
            "transcription_failed", "The audio could not be prepared for transcription."
        )
    return parts


def _transcribe_hosted(parts: list[Path], on_progress: Optional[Callable[[float], None]]) -> str:
    client = get_openai_client()
    pieces = []
    for index, part in enumerate(parts):
        with part.open("rb") as handle:
            response = client.audio.transcriptions.create(
                model=config.ASR_MODEL, file=handle
            )
        pieces.append((getattr(response, "text", "") or "").strip())
        if on_progress:
            on_progress((index + 1) / len(parts))
    return " ".join(p for p in pieces if p)


def _get_local_model():
    global _local_model
    if _local_model is None:
        with _local_model_lock:
            if _local_model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:
                    raise PipelineError(
                        "transcription_failed",
                        "Local speech recognition is selected but faster-whisper "
                        "is not installed on the server.",
                    ) from exc
                _local_model = WhisperModel(
                    config.LOCAL_ASR_MODEL, device="auto", compute_type="int8"
                )
    return _local_model


def _transcribe_local(parts: list[Path], on_progress: Optional[Callable[[float], None]]) -> str:
    model = _get_local_model()
    pieces = []
    for index, part in enumerate(parts):
        segments, _info = model.transcribe(str(part))
        pieces.append(" ".join(segment.text.strip() for segment in segments).strip())
        if on_progress:
            on_progress((index + 1) / len(parts))
    return " ".join(p for p in pieces if p)


def transcribe_audio(
    path: Path,
    work_dir: Path,
    on_progress: Optional[Callable[[float], None]] = None,
) -> str:
    """Transcribe an audio file with the configured backend."""
    parts = _shrink_for_upload(path, work_dir)
    if config.ASR_BACKEND == "local":
        text = _transcribe_local(parts, on_progress)
    else:
        text = _transcribe_hosted(parts, on_progress)

    text = normalize(text)
    if not text:
        raise PipelineError(
            "transcription_failed",
            "No speech could be recognised in this video's audio.",
        )
    return text
