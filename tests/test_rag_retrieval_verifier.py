from dataclasses import dataclass


from src.rag_evidence_pack import (
    build_evidence_pack,
)

from src.rag_retrieval_verifier import (
    VERIFIER_ABSTAIN,
    VERIFIER_PASS,
    VERIFIER_RETRIEVE_MORE,
    verify_retrieval,
)


@dataclass
class FakeRecord:

    chunk_id: str
    doc_id: str

    source_kind: str

    bank_name: str
    document_title: str

    section_type: str
    section_heading: str

    evidence_text: str

    source_url: str
    checked_at: str

    grounding_policy: str

    metadata: dict


@dataclass
class FakeHit:

    rank: int
    rerank_score: float

    record: FakeRecord

    rrf_rank: int
    rrf_score: float

    dense_rank: int | None
    dense_score: float | None

    bm25_rank: int | None
    bm25_score: float | None


def make_hit(
    *,
    chunk_id="c1",
    doc_id="d1",
    source_kind="campaign",
    title=(
        "Ucak Bileti "
        "ParafPara Kampanyasi"
    ),
    text=(
        "Ucak bileti "
        "harcamalarina "
        "ParafPara verilir."
    ),
    dense_rank=1,
    bm25_rank=1,
    limited=False,
    policy="allow",
):

    return FakeHit(
        rank=1,
        rerank_score=7.0,
        record=FakeRecord(
            chunk_id=chunk_id,
            doc_id=doc_id,
            source_kind=source_kind,
            bank_name="Banka",
            document_title=title,
            section_type=(
                "campaign_terms"
            ),
            section_heading=(
                "Kampanya Kosullari"
            ),
            evidence_text=text,
            source_url=(
                "https://example.com"
            ),
            checked_at=(
                "2026-08-21"
            ),
            grounding_policy=policy,
            metadata={
                "grounding_limited":
                    limited,
            },
        ),
        rrf_rank=1,
        rrf_score=0.03,
        dense_rank=dense_rank,
        dense_score=(
            0.7
            if dense_rank is not None
            else None
        ),
        bm25_rank=bm25_rank,
        bm25_score=(
            10.0
            if bm25_rank is not None
            else None
        ),
    )


def test_evidence_pack_deduplicates_chunk():

    hit = make_hit()

    pack = build_evidence_pack(
        "ucak bileti",
        [hit, hit],
    )

    assert len(
        pack.items
    ) == 1


def test_evidence_pack_limits_per_document():

    hits = [
        make_hit(
            chunk_id="a",
            doc_id="same",
        ),
        make_hit(
            chunk_id="b",
            doc_id="same",
        ),
        make_hit(
            chunk_id="c",
            doc_id="same",
        ),
    ]

    pack = build_evidence_pack(
        "ucak bileti",
        hits,
        max_per_document=2,
    )

    assert len(
        pack.items
    ) == 2


def test_cross_lane_supported_evidence_passes():

    result = verify_retrieval(
        (
            "ucak bileti "
            "ParafPara"
        ),
        [
            make_hit()
        ],
        expected_source_kind=(
            "campaign"
        ),
    )

    assert (
        result.status
        == VERIFIER_PASS
    )

    assert (
        result.cross_lane_item_count
        == 1
    )


def test_wrong_source_kind_requests_retry():

    result = verify_retrieval(
        "ucak bileti",
        [
            make_hit(
                source_kind=(
                    "standard_product"
                )
            )
        ],
        expected_source_kind=(
            "campaign"
        ),
        attempt=1,
        max_attempts=2,
    )

    assert (
        result.status
        == VERIFIER_RETRIEVE_MORE
    )


def test_wrong_source_kind_abstains_after_retry():

    result = verify_retrieval(
        "ucak bileti",
        [
            make_hit(
                source_kind=(
                    "standard_product"
                )
            )
        ],
        expected_source_kind=(
            "campaign"
        ),
        attempt=2,
        max_attempts=2,
    )

    assert (
        result.status
        == VERIFIER_ABSTAIN
    )


def test_grounding_limited_cannot_pass():

    result = verify_retrieval(
        "ucak bileti",
        [
            make_hit(
                limited=True
            )
        ],
        expected_source_kind=(
            "campaign"
        ),
        attempt=2,
        max_attempts=2,
    )

    assert (
        result.status
        == VERIFIER_ABSTAIN
    )


def test_dense_only_weak_result_retrieves_more():

    result = verify_retrieval(
        (
            "zxqvplm "
            "nrtkshw"
        ),
        [
            make_hit(
                dense_rank=1,
                bm25_rank=None,
            )
        ],
        expected_source_kind=(
            "campaign"
        ),
        attempt=1,
        max_attempts=2,
    )

    assert (
        result.status
        == VERIFIER_RETRIEVE_MORE
    )


def test_dense_only_weak_result_abstains_second_attempt():

    result = verify_retrieval(
        (
            "zxqvplm "
            "nrtkshw"
        ),
        [
            make_hit(
                dense_rank=1,
                bm25_rank=None,
            )
        ],
        expected_source_kind=(
            "campaign"
        ),
        attempt=2,
        max_attempts=2,
    )

    assert (
        result.status
        == VERIFIER_ABSTAIN
    )


def test_no_results_abstains():

    result = verify_retrieval(
        "herhangi bir soru",
        [],
        expected_source_kind=(
            "campaign"
        ),
    )

    assert (
        result.status
        == VERIFIER_ABSTAIN
    )


def test_score_is_not_used_as_probability_threshold():

    hit = make_hit()

    hit.rerank_score = -5.0

    result = verify_retrieval(
        (
            "ucak bileti "
            "ParafPara"
        ),
        [hit],
        expected_source_kind=(
            "campaign"
        ),
    )

    # Cross-lane + lexical/source evidence
    # can pass even though the raw
    # reranker score is negative.
    # Raw scores are not calibrated
    # probabilities.
    assert (
        result.status
        == VERIFIER_PASS
    )
