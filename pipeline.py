"""The end-to-end job: YouTube URL in, translated text and audio out."""

import shutil
import tempfile
from pathlib import Path
from typing import Callable

import config
import download
import summarize as summarizer
import transcribe
import translate as translator
import tts
from errors import PipelineError
from jobs import Job


def _progress_range(job: Job, low: int, high: int) -> Callable[[float], None]:
    """Map a step's own 0..1 progress onto a slice of the overall bar."""
    return lambda fraction: job.set_progress(low + (high - low) * max(0.0, min(1.0, fraction)))


def _get_transcript(job: Job, video_url: str, video_id: str, language: str,
                    work_dir: Path, notes: list[str]) -> tuple[str, str, str]:
    """Return (text, source, source_language). Captions when YouTube has them,
    speech recognition otherwise. The source language is a hint for the
    translation step and may be empty when it is not known."""
    job.set_stage("fetching_captions", 12)
    captions = transcribe.fetch_captions(video_id, [language, "en"])
    if captions:
        known = captions["language"]
        return captions["text"], "captions", "" if known == "unknown" else known

    notes.append(
        "This video has no caption track, so the audio was transcribed automatically."
    )
    job.set_stage("downloading_audio", 15)
    audio_path = download.download_audio(
        video_url, work_dir, on_progress=_progress_range(job, 15, 45)
    )

    job.set_stage("transcribing", 45)
    text = transcribe.transcribe_audio(
        audio_path, work_dir, on_progress=_progress_range(job, 45, 70)
    )
    return text, "whisper", ""


def run(job: Job, video_url: str, mode: str, language: str) -> dict:
    config.ensure_dirs()
    notes: list[str] = []
    work_dir = Path(tempfile.mkdtemp(dir=config.WORK_DIR))

    try:
        job.set_stage("fetching_metadata", 5)
        meta = download.fetch_metadata(video_url)
        duration = meta.get("duration_sec")
        if duration and duration > config.MAX_VIDEO_SECONDS:
            hours = config.MAX_VIDEO_SECONDS / 3600
            raise PipelineError(
                "unavailable",
                f"This video is longer than the {hours:.0f} hour limit this app "
                "will process.",
                400,
            )

        text, source, source_language = _get_transcript(
            job, video_url, meta["video_id"], language, work_dir, notes
        )

        if mode == "summarize":
            job.set_stage("summarizing", 70)
            text = summarizer.summarize(text, on_progress=_progress_range(job, 70, 85))

        job.set_stage("translating", 88)
        text = translator.translate_text(text, language, source_language)

        audio_url = None
        if len(text) <= config.TTS_MAX_CHARS:
            job.set_stage("synthesizing_audio", 92)
            audio_url = f"/media/{tts.synthesize(text, work_dir).name}"
        else:
            notes.append(
                "The text is too long to read aloud, so no audio was generated."
            )

        return {
            "title": meta["title"],
            "video_id": meta["video_id"],
            "embed_url": f"https://www.youtube.com/embed/{meta['video_id']}",
            "text": text,
            "audio_url": audio_url,
            "transcript_source": source,
            "language": language,
            "duration_sec": duration,
            "notes": notes,
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
