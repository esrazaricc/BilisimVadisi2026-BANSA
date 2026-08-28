import json

import numpy as np


from src.rag_bm25_index import (
    BM25Index,
    lexical_normalize,
    tokenize,
)

from src.rag_document_model import (
    GROUNDING_LIVE_ONLY,
    RagChunkCandidate,
    SOURCE_KIND_CAMPAIGN,
    build_rag_document,
)

from src.rag_materializer import (
    build_manifest,
    materialize_rag_chunks,
    write_materialized_corpus,
)


def make_chunk(
    chunk_id,
    title,
    text,
    *,
    policy="allow",
    source_kind="standard_product",
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
        source_kind=source_kind,
        bank_name="Banka",
        document_title=title,
        source_url="https://example.com",
        checked_at="2026-08-21",
        metadata={},
    )


def test_turkish_lexical_normalization():

    value = lexical_normalize(
        "E\u011fitim \u0130htiya\u00e7 "
        "Finansman\u0131"
    )

    assert (
        "egitim ihtiyac finansmani"
        == value
    )


def test_tokenizer_preserves_numbers():

    assert tokenize(
        "12 ay 5.000 TL"
    ) == [
        "12",
        "ay",
        "5",
        "000",
        "tl",
    ]


def test_bm25_ranks_education():

    chunks = [
        make_chunk(
            "education",
            "Egitim Finansmani",
            (
                "Egitim masraflari "
                "icin 12 ay vade."
            ),
        ),
        make_chunk(
            "vehicle",
            "Tasit Finansmani",
            (
                "Arac satin alimi "
                "icin finansman."
            ),
        ),
    ]

    index = BM25Index.build(
        chunks
    )

    hits = index.search(
        (
            "egitim masraflari "
            "12 ay"
        ),
        top_k=2,
    )

    assert hits
    assert (
        hits[0]
        .record
        .chunk_id
        == "education"
    )


def test_bm25_excludes_live_only():

    chunks = [
        make_chunk(
            "normal",
            "Urun",
            "Normal urun bilgisi.",
        ),
        make_chunk(
            "live",
            "Hesaplama",
            "Aylik kar orani sifir.",
            policy=GROUNDING_LIVE_ONLY,
        ),
    ]

    index = BM25Index.build(
        chunks
    )

    assert len(
        index.records
    ) == 1

    assert (
        index.records[0].chunk_id
        == "normal"
    )


def fake_embed(
    texts,
):

    vectors = []

    for text in texts:

        if "odul" in text.lower():
            vectors.append(
                [1.0, 0.0]
            )
        else:
            vectors.append(
                [0.0, 1.0]
            )

    return np.asarray(
        vectors,
        dtype=np.float32,
    )


def test_materializer_finishes_semantic_chunks():

    document = build_rag_document(
        source_kind=SOURCE_KIND_CAMPAIGN,
        source_id="1",
        bank_name="Banka",
        title="Kampanya",
        text=(
            "Kampanya Kosullari "
            "Ilk alisverise odul verilir. "
            "Belirli harcamalara odul verilir. "
            "Kart sahipleri yararlanabilir. "
            "Iptal edilen islemler dahil degildir. "
            "Iade edilen islemler dahil degildir."
        ),
        source_url="https://example.com",
        checked_at="2026-08-21",
    )

    chunks = materialize_rag_chunks(
        [document],
        embed_texts=fake_embed,
        semantic_split_threshold=50,
        min_chars=30,
        max_chars=100,
        context_radius=0,
        breakpoint_percentile=50,
    )

    assert chunks

    assert all(
        not chunk.requires_semantic_split
        for chunk in chunks
    )


def test_manifest_hash_is_stable():

    chunks = [
        make_chunk(
            "b",
            "B",
            "text b",
        ),
        make_chunk(
            "a",
            "A",
            "text a",
        ),
    ]

    docs = [
        build_rag_document(
            source_kind=SOURCE_KIND_CAMPAIGN,
            source_id="1",
            bank_name="Banka",
            title="Kampanya",
            text="Kosullar.",
            source_url="https://example.com",
            checked_at="2026-08-21",
        )
    ]

    first = build_manifest(
        docs,
        chunks,
        model_name="model",
    )

    second = build_manifest(
        docs,
        list(reversed(chunks)),
        model_name="model",
    )

    assert (
        first.corpus_hash
        == second.corpus_hash
    )


def test_materialized_jsonl_roundtrip(
    tmp_path,
):

    chunks = [
        make_chunk(
            "a",
            "A",
            "Evidence text",
        )
    ]

    docs = [
        build_rag_document(
            source_kind=SOURCE_KIND_CAMPAIGN,
            source_id="1",
            bank_name="Banka",
            title="Kampanya",
            text="Evidence text",
            source_url="https://example.com",
            checked_at="2026-08-21",
        )
    ]

    manifest = build_manifest(
        docs,
        chunks,
        model_name="model",
    )

    chunks_path = (
        tmp_path
        / "chunks.jsonl"
    )

    manifest_path = (
        tmp_path
        / "manifest.json"
    )

    write_materialized_corpus(
        chunks,
        manifest,
        chunks_path=chunks_path,
        manifest_path=manifest_path,
    )

    lines = (
        chunks_path.read_text(
            encoding="utf-8"
        )
        .splitlines()
    )

    assert len(lines) == 1

    payload = json.loads(
        lines[0]
    )

    assert (
        payload["chunk_id"]
        == "a"
    )

    assert manifest_path.exists()
