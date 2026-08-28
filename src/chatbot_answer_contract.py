# CHATBOT_ANSWER_CONTRACT_V1

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.chatbot_answer_evidence_selector import (
    select_answer_evidence,
)



ANSWER_MODE_RAG = "rag"
ANSWER_MODE_FINANCE = "finance"
ANSWER_MODE_HYBRID = "hybrid"
ANSWER_MODE_ABSTAIN = "abstain"
ANSWER_MODE_NEEDS_INPUT = "needs_input"
ANSWER_MODE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class GroundedEvidence:

    evidence_id: str

    source_kind: str

    bank_name: str
    document_title: str

    section_type: str

    text: str

    source_url: str
    checked_at: str | None

    # Curated canonical product facts coming
    # from the already-selected evidence.
    #
    # This allows the answer layer to use
    # deterministic structured facts even when
    # the exact sentence was not returned by
    # semantic retrieval.
    structured_fields: dict[str, Any] | None = None


@dataclass(frozen=True)
class GroundedFinanceResult:

    product_id: int

    bank_name: str
    product_name: str

    status: str

    requested_amount: Decimal
    requested_maturity_months: int

    verified: bool
    exact_match: bool
    rankable: bool

    profit_share_rate: Decimal | None
    monthly_installment: Decimal | None
    total_repayment: Decimal | None

    allocation_fee: Decimal | None
    mortgage_fee: Decimal | None
    appraisal_fee: Decimal | None
    total_fees: Decimal | None

    source_kind: str | None
    source_url: str | None
    checked_at: str | None

    reason: str | None

    # ========================================================
    # FINANCE_CONDITIONAL_VERIFIED_VARIANTS_V1
    #
    # Sanitized, presentation-safe child results.
    # raw_output never crosses this boundary.
    # ========================================================

    conditional_verified_variants: tuple[
        dict[str, object],
        ...,
    ] = ()

    # GROUNDING_PRESENTATION_VARIANTS_V4
    # Presentation-only metadata. No raw calculator payload crosses
    # the grounding boundary.
    presentation_variants: tuple[str, ...] = ()

    # VERIFIED_FEE_PRESENTATION_BRIDGE_V1
    # Presentation-only, explicitly selected metadata.
    # raw_output itself never crosses the grounding boundary.
    minimum_appraisal_fee: Decimal | None = None
    minimum_mortgage_establishment_fee: Decimal | None = None
    minimum_verified_fees_total: Decimal | None = None


@dataclass(frozen=True)
class GroundedAnswerContext:

    question: str

    route: str
    execution_status: str

    answer_mode: str

    may_generate_answer: bool

    may_claim_finance_ranking: bool
    may_use_financial_numbers: bool

    evidence: tuple[
        GroundedEvidence,
        ...
    ]

    finance_results: tuple[
        GroundedFinanceResult,
        ...
    ]

    missing_fields: tuple[
        str,
        ...
    ]

    reasons: tuple[
        str,
        ...
    ]


def _enum_value(
    value,
) -> str:

    if hasattr(
        value,
        "value",
    ):
        return str(
            value.value
        )

    return str(
        value
    )


def _checked_at(
    value,
) -> str | None:

    if value is None:
        return None

    if hasattr(
        value,
        "isoformat",
    ):

        try:
            return value.isoformat()
        except Exception:
            pass

    text = str(
        value
    ).strip()

    return text or None


def _rag_evidence(
    execution,
) -> tuple[
    GroundedEvidence,
    ...
]:

    rag_result = getattr(
        execution,
        "rag_result",
        None,
    )

    if rag_result is None:
        return tuple()

    pack = getattr(
        rag_result,
        "evidence_pack",
        None,
    )

    if pack is None:
        return tuple()

    selection = select_answer_evidence(
        pack,
        question=str(
            getattr(
                execution,
                "question",
                "",
            )
        ),
        expected_source_kind=getattr(
            rag_result,
            "expected_source_kind",
            None,
        ),
        family=getattr(
            getattr(
                execution,
                "route_decision",
                None,
            ),
            "family",
            None,
        ),
    )

    result = []

    for item in (
        selection.items
    ):

        text = str(
            item.evidence_text
            or ""
        ).strip()

        url = str(
            item.source_url
            or ""
        ).strip()

        # Answer-generation evidence must
        # remain source traceable.
        if not text or not url:
            continue

        metadata = getattr(
            item,
            "metadata",
            None,
        )

        structured_fields = (
            metadata.get(
                "structured_fields"
            )
            if isinstance(
                metadata,
                dict,
            )
            else None
        )

        if not isinstance(
            structured_fields,
            dict,
        ):
            structured_fields = {}

        # Defensive copy:
        # the answer layer receives only the
        # selected evidence's canonical facts.
        structured_fields = dict(
            structured_fields
        )

        result.append(
            GroundedEvidence(
                evidence_id=str(
                    item.evidence_id
                ),
                source_kind=str(
                    item.source_kind
                ),
                bank_name=str(
                    item.bank_name
                    or ""
                ),
                document_title=str(
                    item.document_title
                    or ""
                ),
                section_type=str(
                    item.section_type
                    or ""
                ),
                text=text,
                source_url=url,
                checked_at=_checked_at(
                    item.checked_at
                ),
                structured_fields=(
                    structured_fields
                ),
            )
        )

    return tuple(
        result
    )


def _finance_item(
    result,
) -> GroundedFinanceResult:

    request = result.request

    status = _enum_value(
        result.status
    )

    verified = (
        status.casefold()
        == "verified"
    )

    exact_match = bool(
        getattr(
            result,
            "is_exact_match",
            False,
        )
    )

    rankable = bool(
        getattr(
            result,
            "is_rankable",
            False,
        )
    )

    # Critical safety boundary:
    #
    # Numbers from UNVERIFIED or
    # non-exact results must not enter
    # the answer-generation context.
    if verified and exact_match:

        profit_share_rate = (
            result.profit_share_rate
        )

        monthly_installment = (
            result.monthly_installment
        )

        total_repayment = (
            result.total_repayment
        )

        allocation_fee = (
            result.allocation_fee
        )

        mortgage_fee = (
            result.mortgage_fee
        )

        appraisal_fee = (
            result.appraisal_fee
        )

        total_fees = (
            result.total_fees
        )

    else:

        profit_share_rate = None
        monthly_installment = None
        total_repayment = None

        allocation_fee = None
        mortgage_fee = None
        appraisal_fee = None
        total_fees = None

    # ========================================================
    # FINANCE_CONDITIONAL_VERIFIED_VARIANTS_V1
    #
    # The parent may be UNVERIFIED because no variant was
    # selected. Only independently VERIFIED + exact + rankable
    # children may cross the grounding boundary.
    # ========================================================

    conditional_verified_variants = []

    seen_conditional_variants = set()

    for child in tuple(
        getattr(
            result,
            "conditional_verified_variants",
            (),
        )
        or ()
    ):

        child_status = _enum_value(
            getattr(
                child,
                "status",
                "",
            )
        )

        if (
            child_status.casefold()
            !=
            "verified"
        ):
            continue

        if not bool(
            getattr(
                child,
                "is_exact_match",
                False,
            )
        ):
            continue

        if not bool(
            getattr(
                child,
                "is_rankable",
                False,
            )
        ):
            continue

        child_request = getattr(
            child,
            "request",
            None,
        )

        if child_request is None:
            continue

        try:
            child_product_id = int(
                child_request.product_id
            )
        except Exception:
            continue

        if (
            child_product_id
            !=
            int(
                request.product_id
            )
        ):
            continue

        variant_key = str(
            getattr(
                child_request,
                "variant",
                "",
            )
            or ""
        ).strip()

        if not variant_key:
            continue

        variant_normalized = (
            variant_key.casefold()
        )

        if (
            variant_normalized
            in seen_conditional_variants
        ):
            continue

        seen_conditional_variants.add(
            variant_normalized
        )

        conditional_verified_variants.append(
            {
                "variant":
                    variant_key,

                "profit_share_rate":
                    child.profit_share_rate,

                "monthly_installment":
                    child.monthly_installment,

                "total_repayment":
                    child.total_repayment,

                "allocation_fee":
                    child.allocation_fee,

                "mortgage_fee":
                    child.mortgage_fee,

                "appraisal_fee":
                    child.appraisal_fee,

                "total_fees":
                    child.total_fees,

                "source_kind":
                    child.source_kind,

                "source_url":
                    child.source_url,

                "checked_at":
                    _checked_at(
                        child.checked_at
                    ),
            }
        )


    conditional_verified_variants = tuple(
        conditional_verified_variants
    )


    # GROUNDING_PRESENTATION_VARIANTS_V4
    #
    # Only an already VERIFIED + exact result may carry
    # collapsed variant names into presentation.
    #
    # We intentionally do NOT expose raw_output itself.
    presentation_variants = tuple()

    minimum_appraisal_fee = None
    minimum_mortgage_establishment_fee = None
    minimum_verified_fees_total = None

    if verified and exact_match:

        raw_output = getattr(
            result,
            "raw_output",
            {},
        ) or {}

        if isinstance(
            raw_output,
            dict,
        ):

            raw_variants = raw_output.get(
                "collapsed_housing_variants",
                (),
            ) or ()

            if isinstance(
                raw_variants,
                (
                    list,
                    tuple,
                ),
            ):

                presentation_variants = tuple(
                    str(value).strip()
                    for value in raw_variants
                    if str(value).strip()
                )


    # VERIFIED_FEE_PRESENTATION_BRIDGE_V1
    #
    # Do not expose raw_output. Only copy the three
    # explicitly approved presentation values and only
    # from VERIFIED + exact finance results.
    if verified and exact_match:

        presentation_raw = (
            getattr(
                result,
                "raw_output",
                {},
            )
            or {}
        )

        if isinstance(
            presentation_raw,
            dict,
        ):

            def presentation_decimal(
                key,
            ):

                value = (
                    presentation_raw.get(
                        key
                    )
                )

                if value is None:
                    return None

                try:
                    parsed = Decimal(
                        str(
                            value
                        )
                    )
                except Exception:
                    return None

                if parsed < 0:
                    return None

                return parsed


            minimum_appraisal_fee = (
                presentation_decimal(
                    "minimum_appraisal_fee"
                )
            )

            minimum_mortgage_establishment_fee = (
                presentation_decimal(
                    "minimum_mortgage_establishment_fee"
                )
            )

            minimum_verified_fees_total = (
                presentation_decimal(
                    "minimum_verified_fees_total"
                )
            )


    return GroundedFinanceResult(
        product_id=int(
            request.product_id
        ),
        bank_name=str(
            request.bank_name
        ),
        product_name=str(
            request.product_name
        ),
        status=status,
        requested_amount=(
            request.amount
        ),
        requested_maturity_months=int(
            request.maturity_months
        ),
        verified=verified,
        exact_match=exact_match,
        rankable=rankable,
        profit_share_rate=(
            profit_share_rate
        ),
        monthly_installment=(
            monthly_installment
        ),
        total_repayment=(
            total_repayment
        ),
        allocation_fee=(
            allocation_fee
        ),
        mortgage_fee=(
            mortgage_fee
        ),
        appraisal_fee=(
            appraisal_fee
        ),
        total_fees=(
            total_fees
        ),
        source_kind=(
            result.source_kind
        ),
        source_url=(
            result.source_url
        ),
        checked_at=_checked_at(
            result.checked_at
        ),
        reason=(
            result.reason
        ),

        conditional_verified_variants=(
            conditional_verified_variants
        ),

        presentation_variants=(
            presentation_variants
        ),

        minimum_appraisal_fee=(
            minimum_appraisal_fee
        ),

        minimum_mortgage_establishment_fee=(
            minimum_mortgage_establishment_fee
        ),

        minimum_verified_fees_total=(
            minimum_verified_fees_total
        ),
    )


def _finance_results(
    execution,
) -> tuple[
    GroundedFinanceResult,
    ...
]:

    values = getattr(
        execution,
        "finance_results",
        (),
    )

    return tuple(
        _finance_item(
            result
        )
        for result in values
    )


def _finance_permissions(
    finance,
):
    """
    Fail-closed finance permissions.

    Financial values:
    - At least one VERIFIED + exact +
      rankable result allows exposure
      of that result's verified values.

    Comparative ranking:
    - At least two rankable results.
    - No unresolved comparison candidate.

    INELIGIBLE is resolved by the
    deterministic rule engine.

    UNVERIFIED or any other non-rankable
    unresolved candidate blocks global
    ranking claims.
    """

    rankable = tuple(
        item
        for item in finance
        if item.rankable
    )

    unresolved = tuple(
        item
        for item in finance
        if (
            not item.rankable
            and
            item.status
            .strip()
            .casefold()
            != "ineligible"
        )
    )

    may_use_financial_numbers = bool(
        rankable
    )

    may_claim_finance_ranking = (
        len(rankable) >= 2
        and
        not unresolved
    )

    return (
        rankable,
        unresolved,
        may_use_financial_numbers,
        may_claim_finance_ranking,
    )



# ============================================================
# SCOPED_PARTIAL_VERIFIED_FINANCE_RECOMMENDATION_V1_1
# ============================================================

_PARTIAL_VERIFIED_GENERIC_FAMILIES = {
    "konut_finansmani",
    "arac_finansmani",
    "arsa_finansmani",
    "isyeri_finansmani",
}


def _allow_partial_verified_finance_ranking(
    *,
    execution,
    rankable,
    unresolved,
) -> bool:
    """
    Permit ranking only inside the VERIFIED subset.

    This does NOT mean best among all banks.
    """

    if str(
        getattr(
            execution,
            "route",
            "",
        )
    ) != "finance_compare":

        return False


    if not unresolved:

        return False


    if len(
        rankable
    ) < 2:

        return False


    if tuple(
        getattr(
            execution,
            "missing_fields",
            (),
        )
        or ()
    ):

        return False


    decision = getattr(
        execution,
        "route_decision",
        None,
    )


    if decision is None:

        return False


    # Explicit bank selections remain strictly fail-closed.
    explicit_banks = tuple(
        getattr(
            decision,
            "bank_names",
            (),
        )
        or ()
    )


    if explicit_banks:

        return False


    family = (
        str(
            getattr(
                decision,
                "family",
                "",
            )
            or ""
        )
        .strip()
        .casefold()
    )


    purpose = (
        str(
            getattr(
                decision,
                "purpose",
                "",
            )
            or ""
        )
        .strip()
        .casefold()
    )


    semantic_scope_verified = (
        family
        in _PARTIAL_VERIFIED_GENERIC_FAMILIES
        or
        (
            family
            == "ihtiyac_finansmani"
            and
            bool(
                purpose
            )
        )
    )


    if not semantic_scope_verified:

        return False


    # Every ranked item must already satisfy the
    # deterministic finance grounding contract.
    if not all(
        bool(
            getattr(
                item,
                "rankable",
                False,
            )
        )
        and
        bool(
            getattr(
                item,
                "verified",
                False,
            )
        )
        and
        bool(
            getattr(
                item,
                "exact_match",
                False,
            )
        )

        for item
        in rankable
    ):

        return False


    verified_banks = {
        str(
            getattr(
                item,
                "bank_name",
                "",
            )
            or ""
        ).strip()

        for item
        in rankable

        if str(
            getattr(
                item,
                "bank_name",
                "",
            )
            or ""
        ).strip()
    }


    if len(
        verified_banks
    ) < 2:

        return False


    # All candidates must represent the same requested
    # amount and maturity.
    candidates = (
        tuple(
            rankable
        )
        +
        tuple(
            unresolved
        )
    )


    amounts = set()

    maturities = set()


    for item in candidates:

        amount = getattr(
            item,
            "requested_amount",
            None,
        )

        maturity = getattr(
            item,
            "requested_maturity_months",
            None,
        )


        if (
            amount is None
            or
            maturity is None
        ):

            return False


        amounts.add(
            str(
                amount
            )
        )

        maturities.add(
            str(
                maturity
            )
        )


    if (
        len(
            amounts
        ) != 1
        or
        len(
            maturities
        ) != 1
    ):

        return False


    return True


def build_grounded_answer_context(
    execution,
) -> GroundedAnswerContext:

    route = str(
        execution.route
    )

    execution_status = str(
        execution.status
    )

    evidence = _rag_evidence(
        execution
    )

    finance = _finance_results(
        execution
    )

    (
        rankable,
        unresolved_finance,
        may_use_financial_numbers,
        may_claim_finance_ranking,
    ) = _finance_permissions(
        finance
    )


    partial_verified_ranking = (
        _allow_partial_verified_finance_ranking(
            execution=execution,
            rankable=rankable,
            unresolved=(
                unresolved_finance
            ),
        )
    )


    if partial_verified_ranking:

        may_claim_finance_ranking = True

    missing_fields = tuple(
        str(value)
        for value in getattr(
            execution,
            "missing_fields",
            (),
        )
    )

    reasons = [
        str(value)
        for value in getattr(
            execution,
            "reasons",
            (),
        )
    ]


    # ========================================================
    # NEEDS INPUT
    # ========================================================

    if execution_status == "needs_input":

        return GroundedAnswerContext(
            question=str(
                execution.question
            ),
            route=route,
            execution_status=(
                execution_status
            ),
            answer_mode=(
                ANSWER_MODE_NEEDS_INPUT
            ),
            may_generate_answer=False,
            may_claim_finance_ranking=False,
            may_use_financial_numbers=False,
            evidence=evidence,
            finance_results=finance,
            missing_fields=missing_fields,
            reasons=tuple(
                reasons
            ),
        )


    # ========================================================
    # RAG ABSTENTION
    # ========================================================

    if execution_status == "abstain":

        reasons.append(
            "answer_generation_blocked"
        )

        return GroundedAnswerContext(
            question=str(
                execution.question
            ),
            route=route,
            execution_status=(
                execution_status
            ),
            answer_mode=(
                ANSWER_MODE_ABSTAIN
            ),
            may_generate_answer=False,
            may_claim_finance_ranking=False,
            may_use_financial_numbers=False,
            evidence=evidence,
            finance_results=finance,
            missing_fields=missing_fields,
            reasons=tuple(
                reasons
            ),
        )


    # ========================================================
    # FINANCE
    # ========================================================

    if route == "finance_compare":

        if partial_verified_ranking:

            reasons.extend(
                (
                    "partial_verified_finance_ranking_allowed",
                    "ranking_scope_verified_candidates_only",
                )
            )


        may_rank = (
            may_claim_finance_ranking
        )

        if not may_rank:

            reasons.append(
                "finance_ranking_claim_blocked"
            )

        if unresolved_finance:

            reasons.append(
                "unresolved_finance_candidates_present"
            )

        return GroundedAnswerContext(
            question=str(
                execution.question
            ),
            route=route,
            execution_status=(
                execution_status
            ),
            answer_mode=(
                ANSWER_MODE_FINANCE
            ),
            may_generate_answer=True,
            may_claim_finance_ranking=(
                may_rank
            ),
            may_use_financial_numbers=(
                may_use_financial_numbers
            ),
            evidence=evidence,
            finance_results=finance,
            missing_fields=missing_fields,
            reasons=tuple(
                reasons
            ),
        )


    # ========================================================
    # RAG ONLY
    # ========================================================

    if route in {
        "campaign_rag",
        "product_rag",
    }:

        may_generate = bool(
            evidence
        )

        if not may_generate:

            reasons.append(
                "answer_generation_blocked"
            )

        return GroundedAnswerContext(
            question=str(
                execution.question
            ),
            route=route,
            execution_status=(
                execution_status
            ),
            answer_mode=(
                ANSWER_MODE_RAG
            ),
            may_generate_answer=(
                may_generate
            ),
            may_claim_finance_ranking=False,
            may_use_financial_numbers=False,
            evidence=evidence,
            finance_results=finance,
            missing_fields=missing_fields,
            reasons=tuple(
                reasons
            ),
        )


    # ========================================================
    # HYBRID
    # ========================================================

    if route == "hybrid":

        may_generate = bool(
            evidence
            or finance
        )

        may_rank = (
            may_claim_finance_ranking
        )

        return GroundedAnswerContext(
            question=str(
                execution.question
            ),
            route=route,
            execution_status=(
                execution_status
            ),
            answer_mode=(
                ANSWER_MODE_HYBRID
            ),
            may_generate_answer=(
                may_generate
            ),
            may_claim_finance_ranking=(
                may_rank
            ),
            may_use_financial_numbers=(
                may_use_financial_numbers
            ),
            evidence=evidence,
            finance_results=finance,
            missing_fields=missing_fields,
            reasons=tuple(
                reasons
            ),
        )


    return GroundedAnswerContext(
        question=str(
            execution.question
        ),
        route=route,
        execution_status=(
            execution_status
        ),
        answer_mode=(
            ANSWER_MODE_UNKNOWN
        ),
        may_generate_answer=False,
        may_claim_finance_ranking=False,
        may_use_financial_numbers=False,
        evidence=evidence,
        finance_results=finance,
        missing_fields=missing_fields,
        reasons=tuple(
            reasons
            + [
                "unsupported_answer_mode",
            ]
        ),
    )


def build_llm_grounding_payload(
    context: GroundedAnswerContext,
) -> dict[str, Any]:

    """
    Strict machine-readable payload for
    the future local answer model.

    This function does NOT call an LLM.
    """

    evidence_payload = [
        {
            "evidence_id":
                item.evidence_id,

            "source_kind":
                item.source_kind,

            "bank_name":
                item.bank_name,

            "document_title":
                item.document_title,

            "section_type":
                item.section_type,

            "text":
                item.text,

            "source_url":
                item.source_url,

            "checked_at":
                item.checked_at,

            "structured_fields":
                dict(
                    item.structured_fields
                    or {}
                ),
        }
        for item in context.evidence
    ]

    finance_payload = [
        {
            "product_id":
                item.product_id,

            "bank_name":
                item.bank_name,

            "product_name":
                item.product_name,

            "status":
                item.status,

            "requested_amount":
                str(
                    item.requested_amount
                ),

            "requested_maturity_months":
                item.requested_maturity_months,

            "verified":
                item.verified,

            "exact_match":
                item.exact_match,

            "rankable":
                item.rankable,

            "profit_share_rate":
                (
                    None
                    if item.profit_share_rate
                    is None
                    else str(
                        item.profit_share_rate
                    )
                ),

            "monthly_installment":
                (
                    None
                    if item.monthly_installment
                    is None
                    else str(
                        item.monthly_installment
                    )
                ),

            "total_repayment":
                (
                    None
                    if item.total_repayment
                    is None
                    else str(
                        item.total_repayment
                    )
                ),

            "allocation_fee":
                (
                    None
                    if item.allocation_fee
                    is None
                    else str(
                        item.allocation_fee
                    )
                ),

            "mortgage_fee":
                (
                    None
                    if item.mortgage_fee
                    is None
                    else str(
                        item.mortgage_fee
                    )
                ),

            "appraisal_fee":
                (
                    None
                    if item.appraisal_fee
                    is None
                    else str(
                        item.appraisal_fee
                    )
                ),

            "total_fees":
                (
                    None
                    if item.total_fees
                    is None
                    else str(
                        item.total_fees
                    )
                ),

            "source_kind":
                item.source_kind,

            "source_url":
                item.source_url,

            "checked_at":
                item.checked_at,

            "reason":
                item.reason,
        }
        for item in context.finance_results
    ]

    return {
        "question":
            context.question,

        "route":
            context.route,

        "answer_mode":
            context.answer_mode,

        "permissions": {
            "may_generate_answer":
                context.may_generate_answer,

            "may_claim_finance_ranking":
                context.may_claim_finance_ranking,

            "may_use_financial_numbers":
                context.may_use_financial_numbers,
        },

        "rules": [
            (
                "Use only facts contained "
                "in this payload."
            ),
            (
                "Do not calculate financial "
                "values yourself."
            ),
            (
                "Do not infer missing rates, "
                "fees, installments or totals."
            ),
            (
                "Only finance items with "
                "verified=true and "
                "exact_match=true may contain "
                "answerable financial values."
            ),
            (
                "Do not claim that a bank is "
                "best, cheapest or most "
                "advantageous unless "
                "may_claim_finance_ranking=true."
            ),
            (
                "For RAG factual claims, cite "
                "the supporting evidence_id."
            ),
            (
                "If may_generate_answer=false, "
                "do not answer the factual "
                "question."
            ),
        ],

        "evidence":
            evidence_payload,

        "finance_results":
            finance_payload,

        "missing_fields":
            list(
                context.missing_fields
            ),

        "reasons":
            list(
                context.reasons
            ),
    }

# ============================================================
# CAMPAIGN_COMPARE_ANSWER_CONTRACT_V1_3
# ============================================================

from dataclasses import dataclass as _campaign_context_dataclass_v1_3


ANSWER_MODE_CAMPAIGN_COMPARE = "campaign_compare"


@_campaign_context_dataclass_v1_3(
    frozen=True
)
class CampaignGroundedAnswerContextV1_3:
    question: str
    route: str
    execution_status: str
    answer_mode: str
    may_generate_answer: bool
    may_claim_finance_ranking: bool
    may_use_financial_numbers: bool
    evidence: tuple
    finance_results: tuple
    missing_fields: tuple[str, ...]
    reasons: tuple[str, ...]
    campaign_result: object | None = None
    campaign_universe_key: str | None = None


_build_grounded_answer_context_before_campaign_compare_v1_3 = (
    build_grounded_answer_context
)


def build_grounded_answer_context(
    execution,
):

    route = str(
        getattr(
            execution,
            "route",
            "",
        )
    )

    if route == "campaign_compare":

        return CampaignGroundedAnswerContextV1_3(
            question=str(
                getattr(
                    execution,
                    "question",
                    "",
                )
            ),
            route=route,
            execution_status=str(
                getattr(
                    execution,
                    "status",
                    "completed",
                )
            ),
            answer_mode=(
                ANSWER_MODE_CAMPAIGN_COMPARE
            ),
            may_generate_answer=True,
            may_claim_finance_ranking=False,
            may_use_financial_numbers=False,
            evidence=tuple(),
            finance_results=tuple(),
            missing_fields=tuple(
                getattr(
                    execution,
                    "missing_fields",
                    (),
                )
            ),
            reasons=tuple(
                str(value)
                for value
                in getattr(
                    execution,
                    "reasons",
                    (),
                )
            ),
            campaign_result=getattr(
                execution,
                "campaign_result",
                None,
            ),
            campaign_universe_key=getattr(
                execution,
                "campaign_universe_key",
                None,
            ),
        )

    return (
        _build_grounded_answer_context_before_campaign_compare_v1_3(
            execution
        )
    )
