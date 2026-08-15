"""Translation through Google Cloud Translate v2."""

import html

import config
from clients import get_translate_client
from errors import PipelineError
from textutil import split_into_chunks


def detect_language(text: str) -> str:
    """Best-effort source language; "unknown" if detection fails."""
    try:
        result = get_translate_client().detect_language(text[:2000])
    except PipelineError:
        raise
    except Exception:
        return "unknown"
    if isinstance(result, list):
        result = result[0] if result else {}
    return result.get("language", "unknown")


def translate_text(text: str, target_language: str, source_language: str = "") -> str:
    """Translate text, or return it untouched when it is already in the target
    language. Google is billed per character, so skipping that case matters."""
    text = (text or "").strip()
    if not text:
        raise PipelineError("translation_failed", "There is no text to translate.")
    if not target_language:
        return text

    known_source = source_language or detect_language(text)
    if known_source.split("-")[0].lower() == target_language.split("-")[0].lower():
        return text

    client = get_translate_client()
    pieces = []
    for chunk in split_into_chunks(text, config.TRANSLATE_CHUNK_CHARS):
        try:
            result = client.translate(
                chunk,
                target_language=target_language,
                # Without this Google returns HTML and escapes quotes as &#39;.
                format_="text",
                source_language=known_source if known_source != "unknown" else None,
            )
        except Exception as exc:
            raise PipelineError(
                "translation_failed",
                "The text could not be translated. Please try again in a moment.",
            ) from exc
        if isinstance(result, list):
            result = result[0] if result else {}
        pieces.append(html.unescape(result.get("translatedText", "")))

    translated = " ".join(p for p in pieces if p).strip()
    return translated or text
