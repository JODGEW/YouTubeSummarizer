"""Runtime configuration, read from the environment.

Nothing secret is stored in the repo. Copy .env.example to .env (loaded
automatically at startup) or export the variables yourself.
"""

import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Load .env before anything below reads the environment. python-dotenv is a
# convenience, so a missing package is not an error.
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# Where downloads, generated speech and other per-job scratch files live.
RUNTIME_DIR = Path(os.getenv("RUNTIME_DIR", BASE_DIR / "runtime"))
MEDIA_DIR = RUNTIME_DIR / "media"
WORK_DIR = RUNTIME_DIR / "work"

# --- Credentials -----------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Google's client library reads GOOGLE_APPLICATION_CREDENTIALS from the
# environment itself, and fails with an opaque error if it points nowhere. A
# path that does not exist (a leftover placeholder, a moved key) is treated as
# unset so the JSON/ default can take over.
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if GOOGLE_CREDENTIALS and not Path(GOOGLE_CREDENTIALS).is_file():
    GOOGLE_CREDENTIALS = None
    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
if not GOOGLE_CREDENTIALS:
    _default_key = BASE_DIR / "JSON" / "google_key.json"
    if _default_key.is_file():
        GOOGLE_CREDENTIALS = str(_default_key)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_CREDENTIALS

# --- Models ----------------------------------------------------------------
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "gpt-4o-mini")
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")
TTS_VOICE = os.getenv("TTS_VOICE", "nova")

# "openai" uses the hosted Whisper endpoint (no local model, no torch).
# "local" uses faster-whisper on this machine; see requirements-local-asr.txt.
ASR_BACKEND = os.getenv("ASR_BACKEND", "openai").lower()
ASR_MODEL = os.getenv("ASR_MODEL", "whisper-1")
LOCAL_ASR_MODEL = os.getenv("LOCAL_ASR_MODEL", "base")

# --- Limits ----------------------------------------------------------------
# Hosted Whisper rejects uploads above 25 MB; leave headroom for chunking.
ASR_UPLOAD_LIMIT_BYTES = int(os.getenv("ASR_UPLOAD_LIMIT_BYTES", 24 * 1024 * 1024))
ASR_CHUNK_SECONDS = int(os.getenv("ASR_CHUNK_SECONDS", 600))
# Refuse absurdly long videos rather than burning minutes discovering it.
MAX_VIDEO_SECONDS = int(os.getenv("MAX_VIDEO_SECONDS", 3 * 60 * 60))
# Text-to-speech is billed per character; skip it past this length.
TTS_MAX_CHARS = int(os.getenv("TTS_MAX_CHARS", 20000))
# A single Translate v2 request cannot take unbounded text.
TRANSLATE_CHUNK_CHARS = int(os.getenv("TRANSLATE_CHUNK_CHARS", 20000))

# --- Jobs ------------------------------------------------------------------
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", 2))
JOB_TTL_SECONDS = int(os.getenv("JOB_TTL_SECONDS", 60 * 60))

FFMPEG = shutil.which(os.getenv("FFMPEG_BINARY", "ffmpeg"))
HAS_FFMPEG = FFMPEG is not None


def ensure_dirs() -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
