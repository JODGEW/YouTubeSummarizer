"""Summify — transcribe, summarize and translate YouTube videos.

Processing a video takes minutes, so the browser submits a job and polls for
its status rather than holding a request open.
"""

import os
import re

from flask import Flask, jsonify, render_template, request, send_from_directory

import config
import download
import pipeline
from errors import PipelineError
from jobs import JobStore

MODES = {"transcribe", "summarize"}
LANGUAGES = {
    "en", "es", "hi", "zh", "tl", "ko",
    "vi", "ar", "fr", "ru", "pt", "de", "pl", "it",
}
MEDIA_NAME = re.compile(r"^[0-9a-f]{32}\.mp3$")

app = Flask(__name__, template_folder="Front_end")
config.ensure_dirs()
store = JobStore(config.MAX_CONCURRENT_JOBS, config.JOB_TTL_SECONDS)


def _error(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


@app.route("/")
def index():
    return render_template("app.html")


@app.route("/api/summarize", methods=["POST"])
def create_job():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error("bad_request", "The request body must be JSON.", 400)

    video_url = (payload.get("video_url") or "").strip()
    mode = (payload.get("mode") or "").strip().lower()
    language = (payload.get("language") or "").strip().lower()

    if mode not in MODES:
        return _error("bad_request", "Please choose Transcribe or Summarize.", 400)
    if language not in LANGUAGES:
        return _error("bad_request", "Please choose a language from the list.", 400)

    try:
        # Reject a bad URL now, while there is still a request to answer.
        download.parse_video_id(video_url)
    except PipelineError as exc:
        return _error(exc.code, exc.message, exc.http_status)

    job = store.submit(
        lambda job: pipeline.run(job, video_url=video_url, mode=mode, language=language)
    )
    return jsonify({"job_id": job.id}), 202


@app.route("/api/jobs/<job_id>")
def job_status(job_id: str):
    job = store.get(job_id)
    if job is None:
        return _error(
            "not_found",
            "This job is no longer available. It may have expired — please try again.",
            404,
        )
    return jsonify(job.snapshot())


@app.route("/media/<filename>")
def media(filename: str):
    # Only generated speech files are servable. Serving the app directory (as
    # an earlier version did) would have exposed credentials and source.
    if not MEDIA_NAME.match(filename):
        return _error("not_found", "That audio file does not exist.", 404)
    return send_from_directory(config.MEDIA_DIR, filename, mimetype="audio/mpeg")


if __name__ == "__main__":
    # Debug mode exposes an interactive console, so it stays opt-in and off by
    # default even when running locally.
    debug = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", 5000)),
        debug=debug,
    )
