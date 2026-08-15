"""Small text helpers shared by the transcription, summary and speech steps."""

import re

_WHITESPACE = re.compile(r"\s+")
# Caption tracks are littered with these sound tags.
_SOUND_TAG = re.compile(r"[\[(](?:music|applause|laughter|inaudible)[^\])]*[\])]", re.I)
# Split after ., ?, ! or the CJK equivalents when followed by a space or EOL.
_SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s+")


def normalize(text: str) -> str:
    text = _SOUND_TAG.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def split_into_chunks(text: str, max_chars: int) -> list[str]:
    """Break text into pieces of at most max_chars, preferring sentence ends.

    A sentence longer than max_chars is split mid-sentence rather than being
    emitted oversized, since every caller here has a hard upstream limit.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(text):
        if not sentence:
            continue
        while len(sentence) > max_chars:
            room = max_chars - len(current) - (1 if current else 0)
            if room > 0:
                head, sentence = sentence[:room], sentence[room:]
                current = f"{current} {head}".strip()
            chunks.append(current)
            current = ""
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current = f"{current} {sentence}"
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks
