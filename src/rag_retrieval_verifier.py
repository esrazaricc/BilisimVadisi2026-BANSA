# RAG_RETRIEVAL_VERIFIER_V1

from __future__ import annotations

from dataclasses import dataclass


from src.rag_bm25_index import (
    tokenize,
)

from src.rag_evidence_pack import (
    EvidencePack,
    build_evidence_pack,
)


VERIFIER_PASS = "pass"

VERIFIER_RETRIEVE_MORE = (
    "retrieve_more"
)

VERIFIER_ABSTAIN = "abstain"


_GENERIC_QUERY_TERMS = {
    "banka",
    "bankasi",
    "bankanin",
    "finansman",
    "finansmani",
    "kampanya",
    "kampanyasi",
    "urun",
    "urunu",
    "bilgi",
    "nedir",
    "var",
    "mi",
    "mu",
    "midir",
    "icin",
    "hangi",
    "ne",
    "bir",
    "ve",
    "ile",
    "da",
    "de",
    "bu",
    "ben",
    "istiyorum",
    "ariyorum",
}


@dataclass(frozen=True)
class RetrievalVerification:

    status: str

    reasons: tuple[
        str,
        ...
    ]

    evidence_pack: EvidencePack

    meaningful_query_tokens: tuple[
        str,
        ...
    ]

    covered_query_tokens: tuple[
        str,
        ...
    ]

    lexical_coverage: float

    cross_lane_item_count: int

    eligible_item_count: int

    expected_source_kind: str | None

    attempt: int
    max_attempts: int


def meaningful_tokens(
    text: str,
) -> tuple[str, ...]:

    tokens = tokenize(
        text
    )

    result = []

    seen = set()

    for token in tokens:

        if token in (
            _GENERIC_QUERY_TERMS
        ):
            continue

        if len(token) <= 1:
            continue

        if token in seen:
            continue

        seen.add(
            token
        )

        result.append(
            token
        )

    return tuple(
        result
    )


def _covered_tokens(
    query_tokens,
    evidence_items,
) -> tuple[str, ...]:

    if not query_tokens:
        return tuple()

    evidence_tokens = set()

    for item in evidence_items:

        searchable = " ".join(
            [
                item.bank_name,
                item.document_title,
                item.section_heading,
                item.evidence_text,
            ]
        )

        evidence_tokens.update(
            tokenize(
                searchable
            )
        )

    return tuple(
        token
        for token in query_tokens
        if token in evidence_tokens
    )


def _weak_status(
    *,
    attempt: int,
    max_attempts: int,
) -> str:

    if int(attempt) < int(
        max_attempts
    ):
        return (
            VERIFIER_RETRIEVE_MORE
        )

    return VERIFIER_ABSTAIN


def verify_retrieval(
    query: str,
    reranked_hits,
    *,
    expected_source_kind: str | None = None,
    attempt: int = 1,
    max_attempts: int = 2,
    max_evidence_items: int = 6,
    max_per_document: int = 2,
    minimum_lexical_coverage: float = 0.40,
) -> RetrievalVerification:

    attempt = max(
        1,
        int(attempt),
    )

    max_attempts = max(
        attempt,
        int(max_attempts),
    )

    raw_pack = build_evidence_pack(
        query,
        reranked_hits,
        max_items=max_evidence_items,
        max_per_document=(
            max_per_document
        ),
    )

    reasons = []

    if not raw_pack.items:

        return RetrievalVerification(
            status=VERIFIER_ABSTAIN,
            reasons=(
                "no_evidence",
            ),
            evidence_pack=raw_pack,
            meaningful_query_tokens=tuple(),
            covered_query_tokens=tuple(),
            lexical_coverage=0.0,
            cross_lane_item_count=0,
            eligible_item_count=0,
            expected_source_kind=(
                expected_source_kind
            ),
            attempt=attempt,
            max_attempts=max_attempts,
        )

    eligible = []

    for item in raw_pack.items:

        if item.grounding_policy in {
            "live_only",
            "exclude",
        }:
            continue

        if item.grounding_limited:
            continue

        if (
            expected_source_kind
            is not None
            and item.source_kind
            != expected_source_kind
        ):
            continue

        eligible.append(
            item
        )

    if not eligible:

        reasons.append(
            "no_groundable_evidence"
        )

        if expected_source_kind:
            reasons.append(
                "expected_source_kind_missing"
            )

        status = _weak_status(
            attempt=attempt,
            max_attempts=max_attempts,
        )

        return RetrievalVerification(
            status=status,
            reasons=tuple(
                reasons
            ),
            evidence_pack=raw_pack,
            meaningful_query_tokens=tuple(),
            covered_query_tokens=tuple(),
            lexical_coverage=0.0,
            cross_lane_item_count=0,
            eligible_item_count=0,
            expected_source_kind=(
                expected_source_kind
            ),
            attempt=attempt,
            max_attempts=max_attempts,
        )

    eligible_ids = {
        item.chunk_id
        for item in eligible
    }

    filtered_pack = EvidencePack(
        query=raw_pack.query,
        items=tuple(
            item
            for item in raw_pack.items
            if item.chunk_id
            in eligible_ids
        ),
        source_count=len(
            {
                item.source_url
                for item in eligible
                if item.source_url
            }
        ),
        document_count=len(
            {
                item.doc_id
                for item in eligible
            }
        ),
    )

    query_tokens = meaningful_tokens(
        query
    )

    covered = _covered_tokens(
        query_tokens,
        eligible,
    )

    if query_tokens:

        lexical_coverage = (
            len(covered)
            / len(query_tokens)
        )

    else:

        lexical_coverage = 1.0

    cross_lane_count = sum(
        1
        for item in eligible
        if (
            item.dense_rank
            is not None
            and item.bm25_rank
            is not None
        )
    )

    if lexical_coverage >= float(
        minimum_lexical_coverage
    ):

        reasons.append(
            "lexical_coverage"
        )

    if cross_lane_count > 0:

        reasons.append(
            "dense_bm25_agreement"
        )

    if filtered_pack.source_count > 0:

        reasons.append(
            "official_source_present"
        )

    strong_support = (
        filtered_pack.source_count > 0
        and (
            lexical_coverage
            >= float(
                minimum_lexical_coverage
            )
            or cross_lane_count > 0
        )
    )

    if strong_support:

        status = VERIFIER_PASS

    else:

        reasons.append(
            "insufficient_retrieval_support"
        )

        status = _weak_status(
            attempt=attempt,
            max_attempts=max_attempts,
        )

    return RetrievalVerification(
        status=status,
        reasons=tuple(
            reasons
        ),
        evidence_pack=filtered_pack,
        meaningful_query_tokens=(
            query_tokens
        ),
        covered_query_tokens=(
            covered
        ),
        lexical_coverage=float(
            lexical_coverage
        ),
        cross_lane_item_count=int(
            cross_lane_count
        ),
        eligible_item_count=len(
            eligible
        ),
        expected_source_kind=(
            expected_source_kind
        ),
        attempt=attempt,
        max_attempts=max_attempts,
    )
