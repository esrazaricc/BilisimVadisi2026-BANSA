# RAG_MATERIALIZER_V1

from __future__ import annotations

from dataclasses import (
    asdict,
    dataclass,
)

from datetime import (
    datetime,
    timezone,
)

from hashlib import sha256

import json

from pathlib import Path
from typing import Iterable


from src.rag_corpus_builder import (
    build_structure_chunks,
    finish_semantic_chunks,
)

from src.rag_document_model import (
    RagChunkCandidate,
    RagDocument,
)


@dataclass(frozen=True)
class RagCorpusManifest:

    corpus_hash: str

    document_count: int
    chunk_count: int

    semantic_chunk_count: int
    live_only_chunk_count: int
    grounding_limited_document_count: int

    model_name: str

    created_at: str


def materialize_rag_chunks(
    documents: Iterable[
        RagDocument
    ],
    *,
    embed_texts,
    semantic_split_threshold: int = 1800,
    min_chars: int = 350,
    max_chars: int = 1400,
    context_radius: int = 1,
    breakpoint_percentile: float = 80.0,
) -> list[RagChunkCandidate]:

    documents = list(
        documents
    )

    structural = (
        build_structure_chunks(
            documents,
            semantic_split_threshold=(
                semantic_split_threshold
            ),
        )
    )

    final_chunks = (
        finish_semantic_chunks(
            structural,
            embed_texts=embed_texts,
            min_chars=min_chars,
            max_chars=max_chars,
            context_radius=context_radius,
            breakpoint_percentile=(
                breakpoint_percentile
            ),
        )
    )

    ids = [
        chunk.chunk_id
        for chunk in final_chunks
    ]

    if len(ids) != len(
        set(ids)
    ):
        raise RuntimeError(
            "Duplicate RAG chunk_id detected."
        )

    if any(
        chunk.requires_semantic_split
        for chunk in final_chunks
    ):
        raise RuntimeError(
            "Unfinished semantic chunk "
            "remains in materialized corpus."
        )

    return final_chunks


def corpus_hash(
    chunks: Iterable[
        RagChunkCandidate
    ],
) -> str:

    identifiers = sorted(
        chunk.chunk_id
        for chunk in chunks
    )

    payload = "\n".join(
        identifiers
    )

    return sha256(
        payload.encode(
            "utf-8"
        )
    ).hexdigest()


def build_manifest(
    documents: Iterable[
        RagDocument
    ],
    chunks: Iterable[
        RagChunkCandidate
    ],
    *,
    model_name: str,
) -> RagCorpusManifest:

    documents = list(
        documents
    )

    chunks = list(
        chunks
    )

    return RagCorpusManifest(
        corpus_hash=corpus_hash(
            chunks
        ),
        document_count=len(
            documents
        ),
        chunk_count=len(
            chunks
        ),
        semantic_chunk_count=sum(
            1
            for chunk in chunks
            if chunk.metadata.get(
                "semantic_split"
            )
        ),
        live_only_chunk_count=sum(
            1
            for chunk in chunks
            if chunk.grounding_policy
            == "live_only"
        ),
        grounding_limited_document_count=sum(
            1
            for document in documents
            if document.metadata.get(
                "grounding_limited"
            )
        ),
        model_name=str(
            model_name
        ),
        created_at=(
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    )


def write_materialized_corpus(
    chunks: Iterable[
        RagChunkCandidate
    ],
    manifest: RagCorpusManifest,
    *,
    chunks_path,
    manifest_path,
) -> None:

    chunks = list(
        chunks
    )

    chunks_path = Path(
        chunks_path
    )

    manifest_path = Path(
        manifest_path
    )

    chunks_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    chunk_temp = (
        chunks_path.with_suffix(
            chunks_path.suffix
            + ".tmp"
        )
    )

    manifest_temp = (
        manifest_path.with_suffix(
            manifest_path.suffix
            + ".tmp"
        )
    )

    with chunk_temp.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:

        for chunk in chunks:

            handle.write(
                json.dumps(
                    asdict(
                        chunk
                    ),
                    ensure_ascii=False,
                    default=str,
                    sort_keys=True,
                )
            )

            handle.write(
                "\n"
            )

    manifest_temp.write_text(
        json.dumps(
            asdict(
                manifest
            ),
            ensure_ascii=False,
            default=str,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    chunk_temp.replace(
        chunks_path
    )

    manifest_temp.replace(
        manifest_path
    )
