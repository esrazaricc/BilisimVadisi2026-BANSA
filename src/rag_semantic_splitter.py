# RAG_SEMANTIC_SPLITTER_V1

from __future__ import annotations

from dataclasses import replace
import math
import re
from typing import Callable, Iterable, Sequence

from src.rag_document_model import (
    RagChunkCandidate,
    stable_rag_id,
)


Embedding = Sequence[float]

EmbeddingFunction = Callable[
    [list[str]],
    Sequence[Embedding],
]


_SENTENCE_BOUNDARY = re.compile(
    r"(?<=[.!?])\s+"
)


def split_sentences(
    text: str,
) -> list[str]:

    value = re.sub(
        r"\s+",
        " ",
        str(text or ""),
    ).strip()

    if not value:
        return []

    sentences = [
        item.strip()
        for item in _SENTENCE_BOUNDARY.split(
            value
        )
        if item.strip()
    ]

    return sentences or [value]


def cosine_similarity(
    left: Embedding,
    right: Embedding,
) -> float:

    if len(left) != len(right):
        raise ValueError(
            "Embedding dimensions do not match."
        )

    if len(left) == 0:
        raise ValueError(
            "Embedding cannot be empty."
        )

    dot = sum(
        float(a) * float(b)
        for a, b in zip(
            left,
            right,
        )
    )

    left_norm = math.sqrt(
        sum(
            float(value) ** 2
            for value in left
        )
    )

    right_norm = math.sqrt(
        sum(
            float(value) ** 2
            for value in right
        )
    )

    if (
        left_norm == 0
        or right_norm == 0
    ):
        return 0.0

    return dot / (
        left_norm
        * right_norm
    )


def cosine_distance(
    left: Embedding,
    right: Embedding,
) -> float:

    return 1.0 - cosine_similarity(
        left,
        right,
    )


def percentile(
    values: Sequence[float],
    percentage: float,
) -> float:

    if not values:
        return 1.0

    ordered = sorted(
        float(value)
        for value in values
    )

    pct = min(
        100.0,
        max(
            0.0,
            float(percentage),
        ),
    )

    position = (
        len(ordered) - 1
    ) * pct / 100.0

    lower = math.floor(
        position
    )

    upper = math.ceil(
        position
    )

    if lower == upper:
        return ordered[lower]

    fraction = (
        position - lower
    )

    return (
        ordered[lower]
        * (
            1.0 - fraction
        )
        + ordered[upper]
        * fraction
    )


def _window_text(
    sentences: Sequence[str],
    index: int,
    radius: int,
) -> str:

    start = max(
        0,
        index - radius,
    )

    end = min(
        len(sentences),
        index + radius + 1,
    )

    return " ".join(
        sentences[start:end]
    )


def _candidate_breaks(
    sentences: Sequence[str],
    embeddings: Sequence[Embedding],
    *,
    breakpoint_percentile: float,
) -> set[int]:

    if len(sentences) <= 1:
        return set()

    distances = []

    for index in range(
        len(sentences) - 1
    ):

        distances.append(
            cosine_distance(
                embeddings[index],
                embeddings[index + 1],
            )
        )

    threshold = percentile(
        distances,
        breakpoint_percentile,
    )

    return {
        index + 1
        for index, distance
        in enumerate(distances)
        if distance >= threshold
    }


def _merge_sentences(
    sentences: Sequence[str],
    break_before: set[int],
    *,
    min_chars: int,
    max_chars: int,
) -> list[str]:

    chunks: list[str] = []
    current: list[str] = []

    def current_text() -> str:
        return " ".join(
            current
        ).strip()

    for index, sentence in enumerate(
        sentences
    ):

        should_break = (
            index in break_before
            and bool(current)
            and len(
                current_text()
            ) >= min_chars
        )

        if should_break:

            chunks.append(
                current_text()
            )

            current = []

        candidate = (
            " ".join(
                [
                    *current,
                    sentence,
                ]
            )
            .strip()
        )

        if (
            current
            and len(candidate)
            > max_chars
        ):

            chunks.append(
                current_text()
            )

            current = [
                sentence
            ]

        else:

            current.append(
                sentence
            )

    if current:

        chunks.append(
            current_text()
        )

    # Avoid a tiny trailing fragment.
    if (
        len(chunks) >= 2
        and len(chunks[-1])
        < min_chars
    ):

        merged = (
            chunks[-2]
            + " "
            + chunks[-1]
        ).strip()

        if len(merged) <= max_chars:
            chunks[-2:] = [
                merged
            ]

    return chunks


def semantic_split_chunk(
    chunk: RagChunkCandidate,
    *,
    embed_texts: EmbeddingFunction,
    min_chars: int = 350,
    max_chars: int = 1400,
    context_radius: int = 1,
    breakpoint_percentile: float = 80.0,
) -> list[RagChunkCandidate]:

    if not chunk.requires_semantic_split:
        return [chunk]

    sentences = split_sentences(
        chunk.text
    )

    if len(sentences) <= 1:
        return [
            replace(
                chunk,
                requires_semantic_split=False,
            )
        ]

    windows = [
        _window_text(
            sentences,
            index,
            context_radius,
        )
        for index in range(
            len(sentences)
        )
    ]

    embeddings = list(
        embed_texts(
            windows
        )
    )

    if len(embeddings) != len(
        sentences
    ):
        raise ValueError(
            "Embedding backend returned "
            "unexpected vector count."
        )

    breaks = _candidate_breaks(
        sentences,
        embeddings,
        breakpoint_percentile=(
            breakpoint_percentile
        ),
    )

    pieces = _merge_sentences(
        sentences,
        breaks,
        min_chars=int(
            min_chars
        ),
        max_chars=int(
            max_chars
        ),
    )

    if len(pieces) == 1:

        return [
            replace(
                chunk,
                requires_semantic_split=False,
            )
        ]

    results: list[
        RagChunkCandidate
    ] = []

    cursor = 0

    for local_index, text in enumerate(
        pieces
    ):

        local_start = chunk.text.find(
            text,
            cursor,
        )

        if local_start < 0:
            raise ValueError(
                "Semantic child text "
                "could not be mapped "
                "back to parent chunk."
            )

        local_end = (
            local_start
            + len(text)
        )

        cursor = local_end

        chunk_id = stable_rag_id(
            chunk.chunk_id,
            "semantic",
            local_index,
            text,
        )

        metadata = {
            **chunk.metadata,
            "parent_chunk_id":
                chunk.chunk_id,
            "semantic_split":
                True,
            "semantic_index":
                local_index,
        }

        results.append(
            replace(
                chunk,
                chunk_id=chunk_id,
                ordinal=(
                    chunk.ordinal
                    * 1000
                    + local_index
                ),
                text=text,
                retrieval_start=(
                    chunk.retrieval_start
                    + local_start
                ),
                retrieval_end=(
                    chunk.retrieval_start
                    + local_end
                ),
                requires_semantic_split=False,
                metadata=metadata,
            )
        )

    return results


def semantic_split_chunks(
    chunks: Iterable[
        RagChunkCandidate
    ],
    *,
    embed_texts: EmbeddingFunction,
    min_chars: int = 350,
    max_chars: int = 1400,
    context_radius: int = 1,
    breakpoint_percentile: float = 80.0,
) -> list[RagChunkCandidate]:

    output: list[
        RagChunkCandidate
    ] = []

    for chunk in chunks:

        output.extend(
            semantic_split_chunk(
                chunk,
                embed_texts=embed_texts,
                min_chars=min_chars,
                max_chars=max_chars,
                context_radius=(
                    context_radius
                ),
                breakpoint_percentile=(
                    breakpoint_percentile
                ),
            )
        )

    return output
