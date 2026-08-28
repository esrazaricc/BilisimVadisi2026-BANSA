# RAG_DENSE_STORE_V1

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

import numpy as np


from src.rag_dense_index import (
    DenseIndex,
    build_dense_records,
)

from src.rag_document_model import (
    RagChunkCandidate,
)


@dataclass(frozen=True)
class DenseIndexManifest:

    corpus_hash: str
    model_name: str

    record_count: int
    dimension: int

    ordered_chunk_hash: str

    created_at: str


def load_chunks_jsonl(
    path,
) -> list[RagChunkCandidate]:

    path = Path(
        path
    )

    if not path.exists():

        raise RuntimeError(
            f"RAG chunks file "
            f"does not exist: {path}"
        )

    chunks = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:

        for line_number, line in enumerate(
            handle,
            start=1,
        ):

            value = line.strip()

            if not value:
                continue

            try:

                payload = json.loads(
                    value
                )

                chunk = (
                    RagChunkCandidate(
                        **payload
                    )
                )

            except Exception as exc:

                raise RuntimeError(
                    "Invalid RAG chunk JSON "
                    f"at line {line_number}."
                ) from exc

            chunks.append(
                chunk
            )

    ids = [
        chunk.chunk_id
        for chunk in chunks
    ]

    if len(ids) != len(
        set(ids)
    ):

        raise RuntimeError(
            "Duplicate chunk IDs "
            "inside materialized corpus."
        )

    return chunks


def ordered_chunk_hash(
    records,
) -> str:

    payload = "\n".join(
        record.chunk_id
        for record in records
    )

    return sha256(
        payload.encode(
            "utf-8"
        )
    ).hexdigest()


def build_dense_index(
    chunks,
    *,
    embed_documents,
) -> DenseIndex:

    return DenseIndex.build(
        chunks,
        embed_documents=(
            embed_documents
        ),
    )


def save_dense_index(
    index: DenseIndex,
    *,
    corpus_hash: str,
    model_name: str,
    vectors_path,
    manifest_path,
) -> DenseIndexManifest:

    vectors_path = Path(
        vectors_path
    )

    manifest_path = Path(
        manifest_path
    )

    vectors_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest = DenseIndexManifest(
        corpus_hash=str(
            corpus_hash
        ),
        model_name=str(
            model_name
        ),
        record_count=len(
            index.records
        ),
        dimension=(
            index.dimension
        ),
        ordered_chunk_hash=(
            ordered_chunk_hash(
                index.records
            )
        ),
        created_at=(
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    )

    vector_temp = (
        vectors_path.with_name(
            vectors_path.name
            + ".tmp"
        )
    )

    manifest_temp = (
        manifest_path.with_name(
            manifest_path.name
            + ".tmp"
        )
    )

    with vector_temp.open(
        "wb",
    ) as handle:

        np.save(
            handle,
            np.asarray(
                index.matrix,
                dtype=np.float32,
            ),
            allow_pickle=False,
        )

    manifest_temp.write_text(
        json.dumps(
            asdict(
                manifest
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    vector_temp.replace(
        vectors_path
    )

    manifest_temp.replace(
        manifest_path
    )

    return manifest


def load_dense_index(
    chunks,
    *,
    vectors_path,
    manifest_path,
    expected_corpus_hash: str | None = None,
    expected_model_name: str | None = None,
) -> tuple[
    DenseIndex,
    DenseIndexManifest,
]:

    vectors_path = Path(
        vectors_path
    )

    manifest_path = Path(
        manifest_path
    )

    if not vectors_path.exists():

        raise RuntimeError(
            "Dense vector file "
            "does not exist."
        )

    if not manifest_path.exists():

        raise RuntimeError(
            "Dense manifest file "
            "does not exist."
        )

    payload = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    manifest = DenseIndexManifest(
        **payload
    )

    if (
        expected_corpus_hash
        is not None
        and manifest.corpus_hash
        != str(
            expected_corpus_hash
        )
    ):

        raise RuntimeError(
            "Dense index corpus hash "
            "does not match RAG corpus."
        )

    if (
        expected_model_name
        is not None
        and manifest.model_name
        != str(
            expected_model_name
        )
    ):

        raise RuntimeError(
            "Dense index model "
            "does not match expected model."
        )

    records = build_dense_records(
        chunks
    )

    current_hash = (
        ordered_chunk_hash(
            records
        )
    )

    if current_hash != (
        manifest.ordered_chunk_hash
    ):

        raise RuntimeError(
            "Dense record order/hash "
            "does not match manifest."
        )

    if len(records) != (
        manifest.record_count
    ):

        raise RuntimeError(
            "Dense record count "
            "does not match manifest."
        )

    matrix = np.load(
        vectors_path,
        allow_pickle=False,
    )

    if matrix.ndim != 2:

        raise RuntimeError(
            "Dense vector matrix "
            "must be 2D."
        )

    if matrix.shape[0] != (
        manifest.record_count
    ):

        raise RuntimeError(
            "Dense matrix row count "
            "does not match manifest."
        )

    if matrix.shape[1] != (
        manifest.dimension
    ):

        raise RuntimeError(
            "Dense matrix dimension "
            "does not match manifest."
        )

    index = DenseIndex(
        records=records,
        matrix=matrix,
    )

    return (
        index,
        manifest,
    )
