# RAG_EVIDENCE_PACK_V1

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class EvidenceItem:

    evidence_id: str

    chunk_id: str
    doc_id: str

    source_kind: str

    bank_name: str
    document_title: str

    section_type: str
    section_heading: str

    evidence_text: str

    source_url: str
    checked_at: str | None

    grounding_policy: str
    grounding_limited: bool

    rerank_rank: int
    rerank_score: float

    rrf_rank: int
    rrf_score: float

    dense_rank: int | None
    dense_score: float | None

    bm25_rank: int | None
    bm25_score: float | None

    metadata: dict


@dataclass(frozen=True)
class EvidencePack:

    query: str

    items: tuple[
        EvidenceItem,
        ...
    ]

    source_count: int
    document_count: int


def evidence_item_from_reranked_hit(
    hit,
    *,
    evidence_id: str,
) -> EvidenceItem:

    record = hit.record

    metadata = dict(
        record.metadata or {}
    )

    return EvidenceItem(
        evidence_id=str(
            evidence_id
        ),
        chunk_id=str(
            record.chunk_id
        ),
        doc_id=str(
            record.doc_id
        ),
        source_kind=str(
            record.source_kind
        ),
        bank_name=str(
            record.bank_name or ""
        ),
        document_title=str(
            record.document_title or ""
        ),
        section_type=str(
            record.section_type or ""
        ),
        section_heading=str(
            record.section_heading or ""
        ),
        evidence_text=str(
            record.evidence_text or ""
        ).strip(),
        source_url=str(
            record.source_url or ""
        ).strip(),
        checked_at=(
            None
            if record.checked_at is None
            else str(
                record.checked_at
            )
        ),
        grounding_policy=str(
            record.grounding_policy or ""
        ),
        grounding_limited=bool(
            metadata.get(
                "grounding_limited",
                False,
            )
        ),
        rerank_rank=int(
            hit.rank
        ),
        rerank_score=float(
            hit.rerank_score
        ),
        rrf_rank=int(
            hit.rrf_rank
        ),
        rrf_score=float(
            hit.rrf_score
        ),
        dense_rank=(
            None
            if hit.dense_rank is None
            else int(
                hit.dense_rank
            )
        ),
        dense_score=(
            None
            if hit.dense_score is None
            else float(
                hit.dense_score
            )
        ),
        bm25_rank=(
            None
            if hit.bm25_rank is None
            else int(
                hit.bm25_rank
            )
        ),
        bm25_score=(
            None
            if hit.bm25_score is None
            else float(
                hit.bm25_score
            )
        ),
        metadata=metadata,
    )


def build_evidence_pack(
    query: str,
    reranked_hits: Iterable,
    *,
    max_items: int = 6,
    max_per_document: int = 2,
) -> EvidencePack:

    max_items = max(
        1,
        int(max_items),
    )

    max_per_document = max(
        1,
        int(max_per_document),
    )

    items = []

    seen_chunks = set()

    document_counts = {}

    for hit in reranked_hits:

        record = hit.record

        chunk_id = str(
            record.chunk_id
        )

        doc_id = str(
            record.doc_id
        )

        if chunk_id in seen_chunks:
            continue

        current_count = (
            document_counts.get(
                doc_id,
                0,
            )
        )

        if (
            current_count
            >= max_per_document
        ):
            continue

        evidence_text = str(
            record.evidence_text or ""
        ).strip()

        source_url = str(
            record.source_url or ""
        ).strip()

        if not evidence_text:
            continue

        if not source_url:
            continue

        item = (
            evidence_item_from_reranked_hit(
                hit,
                evidence_id=(
                    f"E{len(items) + 1}"
                ),
            )
        )

        items.append(
            item
        )

        seen_chunks.add(
            chunk_id
        )

        document_counts[
            doc_id
        ] = (
            current_count
            + 1
        )

        if len(items) >= max_items:
            break

    source_urls = {
        item.source_url
        for item in items
        if item.source_url
    }

    documents = {
        item.doc_id
        for item in items
    }

    return EvidencePack(
        query=str(
            query or ""
        ).strip(),
        items=tuple(
            items
        ),
        source_count=len(
            source_urls
        ),
        document_count=len(
            documents
        ),
    )
