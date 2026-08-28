from src.rag_document_model import (
    SOURCE_KIND_CAMPAIGN,
    build_rag_document,
)

from src.rag_structure_chunker import (
    sectionize_document,
)

from src.rag_semantic_splitter import (
    cosine_distance,
    semantic_split_chunks,
    split_sentences,
)


def fake_embed_texts(texts):
    vectors = []

    for text in texts:

        lowered = text.casefold()

        if (
            "ucak" in lowered
            or "bilet" in lowered
            or "harcama" in lowered
            or "parafpara" in lowered
        ):
            vectors.append(
                [1.0, 0.0, 0.0]
            )

        elif (
            "kart" in lowered
            or "sanal" in lowered
            or "musteri" in lowered
        ):
            vectors.append(
                [0.0, 1.0, 0.0]
            )

        else:
            vectors.append(
                [0.0, 0.0, 1.0]
            )

    return vectors


def make_document(text):
    return build_rag_document(
        source_kind=SOURCE_KIND_CAMPAIGN,
        source_id=555,
        bank_name=(
            "Turkiye Emlak Katilim"
        ),
        title=(
            "Ucak Bileti Kampanyasi"
        ),
        text=text,
        source_url=(
            "https://example.com/campaign"
        ),
        checked_at=(
            "2026-08-21T12:00:00+03:00"
        ),
    )


def test_sentence_split():
    result = split_sentences(
        "Birinci cumle. "
        "Ikinci cumle! "
        "Ucuncu cumle?"
    )

    assert len(result) == 3


def test_cosine_distance_identical():
    assert (
        cosine_distance(
            [1.0, 0.0],
            [1.0, 0.0],
        )
        == 0.0
    )


def test_semantic_split_stays_inside_section():
    text = (
        "Kampanya Kosullari "
        "Ucak bileti harcamalari kampanyaya dahildir. "
        "Bilet harcamalarina ParafPara verilir. "
        "Ilk harcama tutari dikkate alinir. "
        "Kart sahipleri kampanyadan yararlanabilir. "
        "Sanal kartlar da kampanyaya dahildir. "
        "Musteri bazinda tek kullanim vardir. "
        "Iptal edilen islemler kampanyaya dahil degildir. "
        "Finans kuruluslari uzerinden yapilan islemler "
        "kampanyaya dahil degildir."
    )

    doc = make_document(
        text
    )

    structured = sectionize_document(
        doc,
        semantic_split_threshold=100,
    )

    assert len(structured) == 1
    assert (
        structured[0].section_type
        == "campaign_terms"
    )
    assert (
        structured[0]
        .requires_semantic_split
    )

    split = semantic_split_chunks(
        structured,
        embed_texts=fake_embed_texts,
        min_chars=40,
        max_chars=190,
        context_radius=0,
        breakpoint_percentile=60,
    )

    assert len(split) >= 2

    assert all(
        item.section_type
        == "campaign_terms"
        for item in split
    )

    assert all(
        not item.requires_semantic_split
        for item in split
    )

    assert all(
        item.metadata.get(
            "semantic_split"
        )
        is True
        for item in split
    )


def test_source_metadata_is_preserved():
    text = (
        "Kampanya Kosullari "
        + (
            "Ucak bileti harcamasi uygundur. "
            * 30
        )
    )

    doc = make_document(
        text
    )

    structured = sectionize_document(
        doc,
        semantic_split_threshold=100,
    )

    result = semantic_split_chunks(
        structured,
        embed_texts=fake_embed_texts,
        min_chars=50,
        max_chars=180,
        context_radius=0,
        breakpoint_percentile=70,
    )

    assert result

    for chunk in result:

        assert (
            chunk.source_url
            == "https://example.com/campaign"
        )

        assert (
            chunk.bank_name
            == "Turkiye Emlak Katilim"
        )

        assert (
            chunk.checked_at
            == "2026-08-21T12:00:00+03:00"
        )


def test_short_structural_chunk_is_unchanged():
    doc = make_document(
        "Kampanya Kosullari "
        "Kampanya ay sonuna kadar gecerlidir."
    )

    structured = sectionize_document(
        doc,
        semantic_split_threshold=1000,
    )

    result = semantic_split_chunks(
        structured,
        embed_texts=fake_embed_texts,
    )

    assert len(result) == 1

    assert (
        result[0].chunk_id
        == structured[0].chunk_id
    )


def test_embedding_count_guard():
    doc = make_document(
        "Kampanya Kosullari "
        + (
            "Bir kampanya cumlesidir. "
            * 30
        )
    )

    structured = sectionize_document(
        doc,
        semantic_split_threshold=100,
    )

    def broken_backend(texts):
        return [[1.0, 0.0]]

    try:
        semantic_split_chunks(
            structured,
            embed_texts=broken_backend,
        )
    except ValueError as exc:
        assert (
            "unexpected vector count"
            in str(exc)
        )
    else:
        raise AssertionError(
            "Embedding vector count guard "
            "calismadi."
        )



def test_numpy_embedding_vectors_are_supported():

    import numpy as np

    from src.rag_semantic_splitter import (
        cosine_similarity,
        cosine_distance,
    )

    left = np.array(
        [1.0, 0.0, 0.0],
        dtype=np.float32,
    )

    right = np.array(
        [1.0, 0.0, 0.0],
        dtype=np.float32,
    )

    similarity = cosine_similarity(
        left,
        right,
    )

    distance = cosine_distance(
        left,
        right,
    )

    assert abs(
        similarity - 1.0
    ) < 1e-6

    assert abs(
        distance
    ) < 1e-6



def test_semantic_child_offsets_are_precise():

    from src.rag_document_model import (
        SOURCE_KIND_CAMPAIGN,
        build_rag_document,
    )

    from src.rag_structure_chunker import (
        prepare_retrieval_text,
        sectionize_document,
    )

    from src.rag_semantic_splitter import (
        semantic_split_chunks,
    )

    text = (
        "   Kampanya Kosullari "
        "Ucak bileti harcamasi uygundur. "
        "Bilet islemlerine odul verilir. "
        "Kart sahipleri yararlanabilir. "
        "Sanal kartlar da dahildir. "
        "Iptal edilen islemler dahil degildir. "
        "Iade edilen islemler dahil degildir.   "
    )

    document = build_rag_document(
        source_kind=SOURCE_KIND_CAMPAIGN,
        source_id="offset-test",
        bank_name="Banka",
        title="Kampanya",
        text=text,
        source_url="https://example.com",
        checked_at="2026-08-21",
    )

    structured = sectionize_document(
        document,
        semantic_split_threshold=50,
    )

    result = semantic_split_chunks(
        structured,
        embed_texts=fake_embed_texts,
        min_chars=30,
        max_chars=100,
        context_radius=0,
        breakpoint_percentile=50,
    )

    prepared = prepare_retrieval_text(
        text
    ).text

    assert len(result) >= 2

    for child in result:

        sliced = prepared[
            child.retrieval_start:
            child.retrieval_end
        ]

        assert sliced == child.text
