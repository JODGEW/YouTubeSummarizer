"""YouTube metadata and audio download, via yt-dlp.

Only the audio stream is fetched. Nothing downstream looks at the picture, and
the audio track is a small fraction of the size of a full video download.
"""

import re
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

from errors import PipelineError

_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def parse_video_id(url: str) -> str:
    """Return the 11-character video id, or explain why the URL is unusable."""
    url = (url or "").strip()
    if not url:
        raise PipelineError("bad_request", "Please enter a YouTube video URL.", 400)
    if "://" not in url:
        url = f"https://{url}"

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        raise PipelineError(
            "not_youtube",
            "That does not look like a YouTube link. Please paste a URL from youtube.com.",
            400,
        )

    candidate = ""
    if host.endswith("youtu.be"):
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        candidate = (parse_qs(parsed.query).get("v") or [""])[0]
    else:
        for prefix in ("/shorts/", "/embed/", "/live/", "/v/"):
            if parsed.path.startswith(prefix):
                candidate = parsed.path[len(prefix):].split("/")[0]
                break

    if not _VIDEO_ID.match(candidate):
        raise PipelineError(
            "not_youtube",
            "That YouTube link does not contain a video id. Please copy the URL "
            "straight from the address bar of the video.",
            400,
        )
    return candidate


def _classify(message: str) -> PipelineError:
    lowered = message.lower()
    if "age" in lowered and ("confirm" in lowered or "restrict" in lowered):
        return PipelineError(
            "age_restricted",
            "This video is age-restricted, so YouTube will not let the app watch "
            "it without a signed-in account.",
            403,
        )
    if "private video" in lowered or "members-only" in lowered or "join this channel" in lowered:
        return PipelineError(
            "unavailable",
            "This video is private or restricted to channel members, so it cannot "
            "be summarized.",
            403,
        )
    if "unavailable" in lowered or "removed" in lowered or "does not exist" in lowered:
        return PipelineError(
            "unavailable",
            "This video is unavailable. It may have been removed or blocked in "
            "this region.",
            404,
        )
    if "sign in" in lowered or "bot" in lowered:
        return PipelineError(
            "unavailable",
            "YouTube asked the app to sign in before serving this video, so it "
            "cannot be downloaded right now.",
            403,
        )
    return PipelineError(
        "unavailable", "This video could not be read from YouTube.", 502
    )


def _run(opts: dict, url: str, download: bool):
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError, ExtractorError

    base = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
    }
    base.update(opts)
    try:
        with YoutubeDL(base) as ydl:
            return ydl.extract_info(url, download=download)
    except (DownloadError, ExtractorError) as exc:
        raise _classify(str(exc)) from exc


def fetch_metadata(url: str) -> dict:
    info = _run({"skip_download": True}, url, download=False)
    if not info:
        raise PipelineError("unavailable", "This video could not be read from YouTube.", 502)
    return {
        "video_id": info.get("id") or parse_video_id(url),
        "title": info.get("title") or "Untitled video",
        "duration_sec": info.get("duration"),
    }


def download_audio(
    url: str,
    dest_dir: Path,
    on_progress: Optional[Callable[[float], None]] = None,
) -> Path:
    """Download the best audio-only stream into dest_dir and return its path.

    No ffmpeg post-processing: the container YouTube serves (usually m4a or
    webm) is already accepted by the speech-recognition step, and requiring
    ffmpeg just to rewrap it would make it a hard dependency.
    """

    def hook(status: dict) -> None:
        if not on_progress or status.get("status") != "downloading":
            return
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        done = status.get("downloaded_bytes") or 0
        if total:
            on_progress(min(1.0, done / total))

    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(dest_dir / "audio.%(ext)s"),
        "progress_hooks": [hook] if on_progress else [],
    }
    info = _run(opts, url, download=True)

    downloaded = sorted(p for p in dest_dir.iterdir() if p.is_file())
    if not downloaded:
        raise PipelineError(
            "no_audio", "No audio track could be downloaded for this video.", 502
        )
    # requested_downloads carries the real path when yt-dlp renames the file.
    requested = (info or {}).get("requested_downloads") or []
    if requested and requested[0].get("filepath"):
        path = Path(requested[0]["filepath"])
        if path.exists():
            return path
    return downloaded[0]
