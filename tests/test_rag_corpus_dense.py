import numpy as np
import pandas as pd

from src.rag_corpus_builder import (
    build_campaign_documents,
    build_standard_product_documents,
)

from src.rag_dense_index import (
    DenseIndex,
    build_dense_records,
)

from src.rag_document_model import (
    GROUNDING_LIVE_ONLY,
    RagChunkCandidate,
)


def test_product_document_uses_clean_text():

    frame = pd.DataFrame(
        [
            {
                "id": 1,
                "bank_name": "Banka A",
                "product_family_key":
                    "ihtiyac_finansmani",
                "product_family":
                    "Ihtiyac Finansmani",
                "product_name":
                    "Egitim Finansmani",
                "scope": "bireysel",
                "source_url":
                    "https://example.com/p",
                "source_page":
                    "Egitim Finansmani",
                "clean_text":
                    "Resmi urun metni.",
                "last_checked_at":
                    "2026-08-21",
                "maximum_maturity_months":
                    12,
            }
        ]
    )

    docs = (
        build_standard_product_documents(
            frame
        )
    )

    assert len(docs) == 1
    assert (
        docs[0].text
        == "Resmi urun metni."
    )
    assert (
        docs[0].metadata[
            "text_origin"
        ]
        == "official_clean_text"
    )


def test_empty_product_text_has_limited_fallback():

    frame = pd.DataFrame(
        [
            {
                "id": 2,
                "bank_name": "Banka B",
                "product_family_key":
                    "ihtiyac_finansmani",
                "product_family":
                    "Ihtiyac Finansmani",
                "product_name":
                    "Bireysel Finansman",
                "scope": "bireysel",
                "source_url":
                    "https://example.com/p2",
                "source_page":
                    "Bireysel Finansman",
                "clean_text": "",
                "last_checked_at":
                    "2026-08-21",
            }
        ]
    )

    docs = (
        build_standard_product_documents(
            frame
        )
    )

    assert len(docs) == 1

    assert (
        "Bireysel Finansman"
        in docs[0].text
    )

    assert (
        docs[0].metadata[
            "grounding_limited"
        ]
        is True
    )


def test_campaign_active_filter():

    frame = pd.DataFrame(
        [
            {
                "id": 1,
                "bank_name": "Banka A",
                "campaign_name":
                    "Aktif Kampanya",
                "campaign_type":
                    "points_campaign",
                "campaign_conditions":
                    "Aktif kosullar.",
                "source_url":
                    "https://example.com/a",
                "is_active": 1.0,
                "created_at":
                    "2026-08-21",
            },
            {
                "id": 2,
                "bank_name": "Banka A",
                "campaign_name":
                    "Pasif Kampanya",
                "campaign_type":
                    "points_campaign",
                "campaign_conditions":
                    "Pasif kosullar.",
                "source_url":
                    "https://example.com/b",
                "is_active": 0.0,
                "created_at":
                    "2026-08-21",
            },
        ]
    )

    docs = build_campaign_documents(
        frame,
        active_only=True,
    )

    assert len(docs) == 1
    assert (
        docs[0].title
        == "Aktif Kampanya"
    )


def make_chunk(
    *,
    chunk_id,
    title,
    text,
    policy="allow",
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
        grounding_policy=policy,
        requires_semantic_split=False,
        source_kind="standard_product",
        bank_name="Banka",
        document_title=title,
        source_url="https://example.com",
        checked_at="2026-08-21",
        metadata={},
    )


def test_live_only_is_not_dense_indexed():

    chunks = [
        make_chunk(
            chunk_id="a",
            title="Urun",
            text="Normal bilgi",
        ),
        make_chunk(
            chunk_id="b",
            title="Hesaplama",
            text="Aylik oran yuzde sifir",
            policy=GROUNDING_LIVE_ONLY,
        ),
    ]

    records = build_dense_records(
        chunks
    )

    assert len(records) == 1
    assert records[0].chunk_id == "a"


def test_embedding_text_contains_document_context():

    chunk = make_chunk(
        chunk_id="x",
        title="Egitim Finansmani",
        text="12 aya kadar vade.",
    )

    record = build_dense_records(
        [chunk]
    )[0]

    assert (
        "Egitim Finansmani"
        in record.embedding_text
    )

    assert (
        record.evidence_text
        == "12 aya kadar vade."
    )


def fake_embed_documents(
    texts,
):

    vectors = []

    for text in texts:

        lowered = text.lower()

        if "egitim" in lowered:
            vectors.append(
                [1.0, 0.0, 0.0]
            )

        elif "tasit" in lowered:
            vectors.append(
                [0.0, 1.0, 0.0]
            )

        else:
            vectors.append(
                [0.0, 0.0, 1.0]
            )

    return np.asarray(
        vectors,
        dtype=np.float32,
    )


def fake_embed_queries(
    texts,
):

    return np.asarray(
        [
            [1.0, 0.0, 0.0]
            for _ in texts
        ],
        dtype=np.float32,
    )


def test_dense_index_ranks_relevant_document():

    chunks = [
        make_chunk(
            chunk_id="education",
            title="Egitim Finansmani",
            text="Egitim giderleri.",
        ),
        make_chunk(
            chunk_id="vehicle",
            title="Tasit Finansmani",
            text="Arac alimlari.",
        ),
    ]

    index = DenseIndex.build(
        chunks,
        embed_documents=(
            fake_embed_documents
        ),
    )

    hits = index.search(
        "Egitim masrafi",
        embed_queries=(
            fake_embed_queries
        ),
        top_k=2,
    )

    assert len(hits) == 2

    assert (
        hits[0]
        .record
        .chunk_id
        == "education"
    )

    assert hits[0].rank == 1


def test_dense_index_predicate():

    chunks = [
        make_chunk(
            chunk_id="one",
            title="Egitim Finansmani",
            text="Egitim giderleri.",
        ),
        make_chunk(
            chunk_id="two",
            title="Egitim Finansmani",
            text="Diger egitim bilgisi.",
        ),
    ]

    index = DenseIndex.build(
        chunks,
        embed_documents=(
            fake_embed_documents
        ),
    )

    hits = index.search(
        "Egitim",
        embed_queries=(
            fake_embed_queries
        ),
        predicate=lambda record: (
            record.chunk_id == "two"
        ),
    )

    assert len(hits) == 1
    assert (
        hits[0].record.chunk_id
        == "two"
    )
