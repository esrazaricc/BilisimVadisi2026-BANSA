# RAG_DOCUMENT_MODEL_V1

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


SOURCE_KIND_CAMPAIGN = "campaign"
SOURCE_KIND_PRODUCT = "standard_product"


GROUNDING_ALLOW = "allow"
GROUNDING_STRUCTURED_PREFERRED = "structured_preferred"
GROUNDING_LIVE_ONLY = "live_only"
GROUNDING_EXCLUDE = "exclude"


def stable_rag_id(
    *parts: object,
) -> str:

    material = "\x1f".join(
        str(part or "").strip()
        for part in parts
    )

    return sha256(
        material.encode("utf-8")
    ).hexdigest()[:24]


def source_text_hash(
    text: str,
) -> str:

    return sha256(
        str(text or "").encode(
            "utf-8"
        )
    ).hexdigest()


@dataclass(frozen=True)
class RagDocument:

    doc_id: str
    source_kind: str
    source_id: str
    bank_name: str
    title: str
    text: str
    source_url: str
    checked_at: str | None = None
    source_hash: str = ""
    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class RagChunkCandidate:

    chunk_id: str
    doc_id: str

    ordinal: int

    section_type: str
    section_heading: str

    text: str

    retrieval_start: int
    retrieval_end: int

    grounding_policy: str

    requires_semantic_split: bool

    source_kind: str
    bank_name: str
    document_title: str
    source_url: str
    checked_at: str | None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


def build_rag_document(
    *,
    source_kind: str,
    source_id: object,
    bank_name: object,
    title: object,
    text: object,
    source_url: object,
    checked_at: object = None,
    metadata: dict[str, Any] | None = None,
) -> RagDocument:

    source_kind_text = str(
        source_kind or ""
    ).strip()

    source_id_text = str(
        source_id or ""
    ).strip()

    bank_text = str(
        bank_name or ""
    ).strip()

    title_text = str(
        title or ""
    ).strip()

    body_text = str(
        text or ""
    ).strip()

    url_text = str(
        source_url or ""
    ).strip()

    checked_text = (
        None
        if checked_at is None
        else str(checked_at).strip()
        or None
    )

    doc_id = stable_rag_id(
        source_kind_text,
        source_id_text,
        bank_text,
        title_text,
        url_text,
    )

    return RagDocument(
        doc_id=doc_id,
        source_kind=source_kind_text,
        source_id=source_id_text,
        bank_name=bank_text,
        title=title_text,
        text=body_text,
        source_url=url_text,
        checked_at=checked_text,
        source_hash=source_text_hash(
            body_text
        ),
        metadata=dict(
            metadata or {}
        ),
    )
