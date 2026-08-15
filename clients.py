"""Lazily built API clients, so a missing key fails with a clear message."""

import threading

import config
from errors import PipelineError

_lock = threading.Lock()
_openai_client = None
_translate_client = None


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        with _lock:
            if _openai_client is None:
                if not config.OPENAI_API_KEY:
                    raise PipelineError(
                        "internal",
                        "The server is missing its OpenAI API key, so speech "
                        "recognition, summaries and audio are unavailable.",
                    )
                from openai import OpenAI

                _openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _openai_client


def get_translate_client():
    global _translate_client
    if _translate_client is None:
        with _lock:
            if _translate_client is None:
                if not config.GOOGLE_CREDENTIALS:
                    raise PipelineError(
                        "translation_failed",
                        "The server is missing its Google Cloud credentials, so "
                        "translation is unavailable.",
                    )
                from google.cloud import translate_v2

                _translate_client = translate_v2.Client()
    return _translate_client
