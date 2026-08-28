import json

import numpy as np


from src.rag_bm25_index import (
    BM25Index,
)

from src.rag_dense_index import (
    DenseIndex,
)

from src.rag_dense_store import (
    load_dense_index,
    save_dense_index,
)

from src.rag_document_model import (
    RagChunkCandidate,
)

from src.rag_rrf import (
    hybrid_search,
    reciprocal_rank_fusion,
)


def make_chunk(
    chunk_id,
    title,
    text,
):

    return RagChunkCandidate(
        chunk_id=chunk_id,
        doc_id="doc-" + chunk_id,
        ordinal=0,
        section_type="body",
        section_heading="",
        text=text,
        retrieval_start=0,
        retrieval_end=len(text),
        grounding_policy="allow",
        requires_semantic_split=False,
        source_kind="campaign",
        bank_name="Banka",
        document_title=title,
        source_url="https://example.com",
        checked_at="2026-08-21",
        metadata={},
    )


def fake_documents(
    texts,
):

    vectors = []

    for text in texts:

        lowered = text.lower()

        if "parafpara" in lowered:
            vectors.append(
                [1.0, 0.0, 0.0]
            )

        elif "ucak" in lowered:
            vectors.append(
                [0.8, 0.2, 0.0]
            )

        else:
            vectors.append(
                [0.0, 0.0, 1.0]
            )

    return np.asarray(
        vectors,
        dtype=np.float32,
    )


def fake_queries(
    texts,
):

    return np.asarray(
        [
            [1.0, 0.0, 0.0]
            for _ in texts
        ],
        dtype=np.float32,
    )


def test_dense_store_roundtrip(
    tmp_path,
):

    chunks = [
        make_chunk(
            "a",
            "ParafPara Kampanyasi",
            "Ucak bileti ParafPara.",
        ),
        make_chunk(
            "b",
            "Diger Kampanya",
            "Baska kampanya.",
        ),
    ]

    index = DenseIndex.build(
        chunks,
        embed_documents=(
            fake_documents
        ),
    )

    vectors = (
        tmp_path
        / "vectors.npy"
    )

    manifest = (
        tmp_path
        / "manifest.json"
    )

    saved = save_dense_index(
        index,
        corpus_hash="abc",
        model_name="fake",
        vectors_path=vectors,
        manifest_path=manifest,
    )

    loaded, loaded_manifest = (
        load_dense_index(
            chunks,
            vectors_path=vectors,
            manifest_path=manifest,
            expected_corpus_hash="abc",
            expected_model_name="fake",
        )
    )

    assert saved.record_count == 2

    assert (
        loaded_manifest.record_count
        == 2
    )

    assert (
        loaded.matrix.shape
        == (2, 3)
    )


def test_rrf_rewards_cross_lane_hits():

    chunks = [
        make_chunk(
            "a",
            "ParafPara",
            "Ucak bileti ParafPara.",
        ),
        make_chunk(
            "b",
            "Ucak Kampanyasi",
            "Ucak bileti kampanyasi.",
        ),
    ]

    dense = DenseIndex.build(
        chunks,
        embed_documents=(
            fake_documents
        ),
    )

    bm25 = BM25Index.build(
        chunks
    )

    dense_hits = dense.search(
        "ParafPara ucak",
        embed_queries=(
            fake_queries
        ),
        top_k=2,
    )

    bm25_hits = bm25.search(
        "ParafPara ucak",
        top_k=2,
    )

    fused = reciprocal_rank_fusion(
        dense_hits=dense_hits,
        bm25_hits=bm25_hits,
        top_k=2,
    )

    assert fused

    assert (
        fused[0]
        .record
        .chunk_id
        == "a"
    )

    assert (
        fused[0].dense_rank
        is not None
    )

    assert (
        fused[0].bm25_rank
        is not None
    )


def test_hybrid_search():

    chunks = [
        make_chunk(
            "education",
            "Egitim Finansmani",
            "Egitim masraflari 12 ay.",
        ),
        make_chunk(
            "campaign",
            "Kart Kampanyasi",
            "Kart harcamalarina odul.",
        ),
    ]

    def embed_docs(texts):

        return np.asarray(
            [
                (
                    [1.0, 0.0]
                    if "Egitim" in text
                    else [0.0, 1.0]
                )
                for text in texts
            ],
            dtype=np.float32,
        )

    def embed_query(texts):

        return np.asarray(
            [
                [1.0, 0.0]
                for _ in texts
            ],
            dtype=np.float32,
        )

    dense = DenseIndex.build(
        chunks,
        embed_documents=embed_docs,
    )

    bm25 = BM25Index.build(
        chunks
    )

    hits = hybrid_search(
        "Egitim masraflari",
        dense_index=dense,
        bm25_index=bm25,
        embed_queries=embed_query,
        source_top_k=5,
        final_top_k=5,
    )

    assert hits

    assert (
        hits[0]
        .record
        .chunk_id
        == "education"
    )
