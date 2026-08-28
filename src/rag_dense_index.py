# RAG_DENSE_INDEX_V1

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import numpy as np

from src.rag_document_model import (
    GROUNDING_EXCLUDE,
    GROUNDING_LIVE_ONLY,
    RagChunkCandidate,
)


@dataclass(frozen=True)
class DenseIndexRecord:

    chunk_id: str
    doc_id: str

    source_kind: str
    bank_name: str
    document_title: str

    section_type: str
    section_heading: str

    grounding_policy: str

    embedding_text: str
    evidence_text: str

    source_url: str
    checked_at: str | None

    metadata: dict


@dataclass(frozen=True)
class DenseSearchHit:

    rank: int
    score: float
    record: DenseIndexRecord


def chunk_is_dense_eligible(
    chunk: RagChunkCandidate,
) -> bool:

    if not str(
        chunk.text or ""
    ).strip():
        return False

    if chunk.grounding_policy in {
        GROUNDING_EXCLUDE,
        GROUNDING_LIVE_ONLY,
    }:
        return False

    return True


def embedding_text_for_chunk(
    chunk: RagChunkCandidate,
) -> str:

    parts = []

    if chunk.bank_name:
        parts.append(
            f"Banka: {chunk.bank_name}"
        )

    if chunk.document_title:
        parts.append(
            f"Belge: {chunk.document_title}"
        )

    if chunk.section_heading:
        parts.append(
            f"B?l?m: {chunk.section_heading}"
        )

    parts.append(
        chunk.text
    )

    return "\n".join(
        part
        for part in parts
        if str(
            part or ""
        ).strip()
    )


def build_dense_records(
    chunks: Iterable[
        RagChunkCandidate
    ],
) -> list[DenseIndexRecord]:

    records = []

    for chunk in chunks:

        if not chunk_is_dense_eligible(
            chunk
        ):
            continue

        records.append(
            DenseIndexRecord(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                source_kind=(
                    chunk.source_kind
                ),
                bank_name=(
                    chunk.bank_name
                ),
                document_title=(
                    chunk.document_title
                ),
                section_type=(
                    chunk.section_type
                ),
                section_heading=(
                    chunk.section_heading
                ),
                grounding_policy=(
                    chunk.grounding_policy
                ),
                embedding_text=(
                    embedding_text_for_chunk(
                        chunk
                    )
                ),
                evidence_text=(
                    chunk.text
                ),
                source_url=(
                    chunk.source_url
                ),
                checked_at=(
                    chunk.checked_at
                ),
                metadata=dict(
                    chunk.metadata
                ),
            )
        )

    return records


def _normalized_matrix(
    values,
) -> np.ndarray:

    matrix = np.asarray(
        values,
        dtype=np.float32,
    )

    if matrix.ndim != 2:
        raise ValueError(
            "Dense vectors must be "
            "a 2D matrix."
        )

    if matrix.shape[0] == 0:
        return matrix

    if not np.isfinite(
        matrix
    ).all():
        raise ValueError(
            "Dense vectors contain "
            "NaN or Inf."
        )

    norms = np.linalg.norm(
        matrix,
        axis=1,
        keepdims=True,
    )

    if np.any(
        norms == 0
    ):
        raise ValueError(
            "Dense vector cannot "
            "have zero norm."
        )

    return (
        matrix
        / norms
    )


class DenseIndex:

    def __init__(
        self,
        *,
        records: Sequence[
            DenseIndexRecord
        ],
        matrix,
    ):

        self.records = tuple(
            records
        )

        self.matrix = (
            _normalized_matrix(
                matrix
            )
        )

        if (
            self.matrix.shape[0]
            != len(self.records)
        ):
            raise ValueError(
                "Dense vector count "
                "does not match records."
            )

    @classmethod
    def build(
        cls,
        chunks: Iterable[
            RagChunkCandidate
        ],
        *,
        embed_documents: Callable[
            [Sequence[str]],
            object,
        ],
    ) -> "DenseIndex":

        records = build_dense_records(
            chunks
        )

        if not records:

            return cls(
                records=[],
                matrix=np.empty(
                    (
                        0,
                        0,
                    ),
                    dtype=np.float32,
                ),
            )

        texts = [
            record.embedding_text
            for record in records
        ]

        vectors = embed_documents(
            texts
        )

        return cls(
            records=records,
            matrix=vectors,
        )

    @property
    def dimension(
        self,
    ) -> int:

        if self.matrix.ndim != 2:
            return 0

        if self.matrix.shape[0] == 0:
            return 0

        return int(
            self.matrix.shape[1]
        )

    def search(
        self,
        query: str,
        *,
        embed_queries: Callable[
            [Sequence[str]],
            object,
        ],
        top_k: int = 5,
        predicate=None,
    ) -> list[DenseSearchHit]:

        if not self.records:
            return []

        query_text = str(
            query or ""
        ).strip()

        if not query_text:
            return []

        query_matrix = (
            _normalized_matrix(
                embed_queries(
                    [query_text]
                )
            )
        )

        if query_matrix.shape[0] != 1:
            raise ValueError(
                "Query backend must "
                "return one vector."
            )

        if (
            query_matrix.shape[1]
            != self.matrix.shape[1]
        ):
            raise ValueError(
                "Query/index dimension "
                "mismatch."
            )

        scores = (
            self.matrix
            @ query_matrix[0]
        )

        candidates = []

        for index, score in enumerate(
            scores
        ):

            record = self.records[
                index
            ]

            if (
                predicate is not None
                and not predicate(
                    record
                )
            ):
                continue

            candidates.append(
                (
                    float(score),
                    record,
                )
            )

        candidates.sort(
            key=lambda item: (
                item[0],
                item[1].chunk_id,
            ),
            reverse=True,
        )

        limit = max(
            1,
            int(top_k),
        )

        return [
            DenseSearchHit(
                rank=rank,
                score=score,
                record=record,
            )
            for rank, (
                score,
                record,
            )
            in enumerate(
                candidates[:limit],
                start=1,
            )
        ]
