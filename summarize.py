"""Summarizing a transcript with an OpenAI chat model.

Long transcripts are summarized in pieces and those summaries are summarized
again, so the whole video is represented instead of the first few minutes.
"""

from typing import Callable, Optional

import config
from clients import get_openai_client
from errors import PipelineError
from textutil import split_into_chunks

# Roughly 4k tokens of transcript per request, well inside any model's window.
CHUNK_CHARS = 14000

_SYSTEM = (
    "You summarize transcripts of videos. Write clear, factual prose in the "
    "same language as the transcript. Never invent details that are not in the "
    "transcript, and do not mention the transcript or these instructions."
)


def _complete(prompt: str) -> str:
    client = get_openai_client()
    try:
        response = client.chat.completions.create(
            model=config.SUMMARY_MODEL,
            temperature=0.3,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        raise PipelineError(
            "summarization_failed",
            "The summary could not be generated. Please try again in a moment.",
        ) from exc

    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise PipelineError(
            "summarization_failed", "The summary came back empty. Please try again."
        )
    return text


def summarize(
    transcript: str,
    on_progress: Optional[Callable[[float], None]] = None,
) -> str:
    if not transcript.strip():
        raise PipelineError("summarization_failed", "There is no transcript to summarize.")

    chunks = split_into_chunks(transcript, CHUNK_CHARS)

    if len(chunks) == 1:
        summary = _complete(
            "Summarize this video transcript in a few short paragraphs, covering "
            "the main points in the order they are made.\n\n" + chunks[0]
        )
        if on_progress:
            on_progress(1.0)
        return summary

    partials = []
    for index, chunk in enumerate(chunks):
        partials.append(
            _complete(
                f"This is part {index + 1} of {len(chunks)} of a video transcript. "
                "Summarize just this part, keeping every distinct point.\n\n" + chunk
            )
        )
        if on_progress:
            # Reserve the last tenth for the combining pass.
            on_progress(0.9 * (index + 1) / len(chunks))

    combined = "\n\n".join(
        f"Part {i + 1}: {text}" for i, text in enumerate(partials)
    )
    summary = _complete(
        "These are ordered partial summaries of one video. Merge them into a "
        "single coherent summary of a few short paragraphs, without repeating "
        "points or referring to the parts.\n\n" + combined
    )
    if on_progress:
        on_progress(1.0)
    return summary
