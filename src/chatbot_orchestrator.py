# CHATBOT_ORCHESTRATOR_V1

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


from src.chatbot_router import (
    route_question,
)

from src.chatbot_rag_orchestrator import (
    VERIFIER_ABSTAIN,
    VERIFIER_PASS,
    RAG_STATUS_NOT_APPLICABLE,
    run_chatbot_rag,
)

from src.finance_verified_resolver import (
    compare_financing,
)

from src.chatbot_finance_fact_lookup import (
    lookup_finance_fact,
)


ROUTE_CAMPAIGN_RAG = "campaign_rag"
ROUTE_PRODUCT_RAG = "product_rag"
ROUTE_FINANCE_COMPARE = "finance_compare"
ROUTE_FINANCE_FACT = "finance_fact"
ROUTE_HYBRID = "hybrid"
ROUTE_UNKNOWN = "unknown"


STATUS_COMPLETED = "completed"
STATUS_NEEDS_INPUT = "needs_input"
STATUS_ABSTAIN = "abstain"
STATUS_PARTIAL = "partial"
STATUS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ChatbotExecutionResult:

    question: str

    route: str
    status: str

    route_decision: object

    rag_result: object | None

    finance_results: tuple

    finance_executed: bool

    rankable_finance_count: int

    missing_fields: tuple[
        str,
        ...
    ]

    reasons: tuple[
        str,
        ...
    ]

    finance_fact_result: object | None = None


def _route_missing_fields(
    decision,
) -> tuple[str, ...]:

    values = getattr(
        decision,
        "missing_fields",
        (),
    )

    if not values:
        return tuple()

    return tuple(
        str(value)
        for value in values
    )


def _finance_ready(
    decision,
) -> bool:

    ready = getattr(
        decision,
        "ready_for_finance_compare",
        None,
    )

    if ready is not None:
        return bool(
            ready
        )

    return not bool(
        _route_missing_fields(
            decision
        )
    )


def _execute_finance(
    decision,
    *,
    finance_compare_fn: Callable,
    finance_adapters=None,
):

    if not _finance_ready(
        decision
    ):

        return tuple()

    kwargs = {
        "family":
            decision.family,

        "amount":
            decision.amount,

        "maturity":
            decision.maturity,

        "purpose":
            decision.purpose,

        "scope":
            "bireysel",
    }

    requested_banks = tuple(
        getattr(
            decision,
            "bank_names",
            (),
        )
        or ()
    )

    if requested_banks:

        kwargs[
            "bank_names"
        ] = requested_banks

    if finance_adapters is not None:

        kwargs[
            "adapters"
        ] = finance_adapters

    results = finance_compare_fn(
        **kwargs
    )

    return tuple(
        results
    )


def _rankable_count(
    results,
) -> int:

    return sum(
        1
        for result in results
        if bool(
            getattr(
                result,
                "is_rankable",
                False,
            )
        )
    )


def run_chatbot(
    question: str,
    *,
    runtime=None,
    route_decision=None,
    rag_runner=run_chatbot_rag,
    finance_compare_fn=compare_financing,
    finance_fact_lookup_fn=(
        lookup_finance_fact
    ),
    finance_adapters=None,
) -> ChatbotExecutionResult:

    question = str(
        question or ""
    ).strip()

    if route_decision is None:

        route_decision = (
            route_question(
                question
            )
        )

    route = str(
        route_decision.route
    )

    missing = _route_missing_fields(
        route_decision
    )



    # ========================================================
    # STRUCTURED FINANCE FACT
    # ========================================================

    if route == ROUTE_FINANCE_FACT:

        fact_result = (
            finance_fact_lookup_fn(
                question=question,
                attribute=getattr(
                    route_decision,
                    "finance_attribute",
                    None,
                ),
            )
        )

        return ChatbotExecutionResult(
            question=question,
            route=route,
            status=STATUS_COMPLETED,
            route_decision=(
                route_decision
            ),
            rag_result=None,
            finance_results=tuple(),
            finance_executed=False,
            rankable_finance_count=0,
            missing_fields=tuple(),
            reasons=(
                "deterministic_finance_fact_lookup_executed",
                (
                    "finance_fact_status:"
                    + str(
                        getattr(
                            fact_result,
                            "status",
                            "unknown",
                        )
                    )
                ),
            ),
            finance_fact_result=(
                fact_result
            ),
        )


    # ========================================================
    # FINANCE ONLY
    # ========================================================

    if route == ROUTE_FINANCE_COMPARE:

        if not _finance_ready(
            route_decision
        ):

            return ChatbotExecutionResult(
                question=question,
                route=route,
                status=STATUS_NEEDS_INPUT,
                route_decision=(
                    route_decision
                ),
                rag_result=None,
                finance_results=tuple(),
                finance_executed=False,
                rankable_finance_count=0,
                missing_fields=missing,
                reasons=(
                    "finance_fields_missing",
                ),
            )

        finance_results = (
            _execute_finance(
                route_decision,
                finance_compare_fn=(
                    finance_compare_fn
                ),
                finance_adapters=(
                    finance_adapters
                ),
            )
        )

        reasons = [
            "deterministic_finance_engine_executed",
        ]

        if not finance_results:

            reasons.append(
                "no_finance_candidates"
            )

        rankable = _rankable_count(
            finance_results
        )

        if rankable == 0:

            reasons.append(
                "no_rankable_verified_finance_result"
            )

        return ChatbotExecutionResult(
            question=question,
            route=route,
            status=STATUS_COMPLETED,
            route_decision=(
                route_decision
            ),
            rag_result=None,
            finance_results=(
                finance_results
            ),
            finance_executed=True,
            rankable_finance_count=(
                rankable
            ),
            missing_fields=tuple(),
            reasons=tuple(
                reasons
            ),
        )


    # ========================================================
    # CAMPAIGN / PRODUCT RAG
    # ========================================================

    if route in {
        ROUTE_CAMPAIGN_RAG,
        ROUTE_PRODUCT_RAG,
    }:

        rag_result = rag_runner(
            question,
            runtime=runtime,
            route_decision=(
                route_decision
            ),
        )

        if rag_result.status == (
            VERIFIER_PASS
        ):

            status = STATUS_COMPLETED

        elif rag_result.status == (
            VERIFIER_ABSTAIN
        ):

            status = STATUS_ABSTAIN

        else:

            # run_chatbot_rag already performs
            # its retry loop internally.
            status = STATUS_ABSTAIN

        return ChatbotExecutionResult(
            question=question,
            route=route,
            status=status,
            route_decision=(
                route_decision
            ),
            rag_result=rag_result,
            finance_results=tuple(),
            finance_executed=False,
            rankable_finance_count=0,
            missing_fields=missing,
            reasons=tuple(
                rag_result.reasons
            ),
        )


    # ========================================================
    # HYBRID
    # ========================================================

    if route == ROUTE_HYBRID:

        # RAG owns only campaign evidence
        # in the current hybrid contract.
        rag_result = rag_runner(
            question,
            runtime=runtime,
            route_decision=(
                route_decision
            ),
        )

        finance_results = tuple()
        finance_executed = False

        if _finance_ready(
            route_decision
        ):

            finance_results = (
                _execute_finance(
                    route_decision,
                    finance_compare_fn=(
                        finance_compare_fn
                    ),
                    finance_adapters=(
                        finance_adapters
                    ),
                )
            )

            finance_executed = True

        rankable = _rankable_count(
            finance_results
        )

        rag_ok = (
            rag_result.status
            == VERIFIER_PASS
        )

        finance_ready = _finance_ready(
            route_decision
        )

        if (
            rag_ok
            and finance_ready
            and finance_executed
        ):

            status = STATUS_COMPLETED

        elif (
            rag_ok
            or finance_executed
        ):

            status = STATUS_PARTIAL

        else:

            status = STATUS_ABSTAIN

        reasons = []

        reasons.extend(
            str(reason)
            for reason in (
                rag_result.reasons
            )
        )

        if missing:

            reasons.append(
                "finance_fields_missing"
            )

        if finance_executed:

            reasons.append(
                "deterministic_finance_engine_executed"
            )

        if (
            finance_executed
            and rankable == 0
        ):

            reasons.append(
                "no_rankable_verified_finance_result"
            )

        return ChatbotExecutionResult(
            question=question,
            route=route,
            status=status,
            route_decision=(
                route_decision
            ),
            rag_result=rag_result,
            finance_results=(
                finance_results
            ),
            finance_executed=(
                finance_executed
            ),
            rankable_finance_count=(
                rankable
            ),
            missing_fields=missing,
            reasons=tuple(
                reasons
            ),
        )


    # ========================================================
    # UNKNOWN
    # ========================================================

    return ChatbotExecutionResult(
        question=question,
        route=route,
        status=STATUS_UNKNOWN,
        route_decision=(
            route_decision
        ),
        rag_result=None,
        finance_results=tuple(),
        finance_executed=False,
        rankable_finance_count=0,
        missing_fields=missing,
        reasons=(
            "unsupported_question_route",
        ),
    )

# ============================================================
# CAMPAIGN_COMPARE_ORCHESTRATOR_V1_3
# ============================================================

from dataclasses import dataclass as _campaign_compare_dataclass_v1_3

from src.chatbot_campaign_compare import (
    run_campaign_compare as _run_campaign_compare_v1_3,
)


@_campaign_compare_dataclass_v1_3(
    frozen=True
)
class CampaignChatbotExecutionResultV1_3:
    question: str
    route: str
    status: str
    route_decision: object
    rag_result: object | None
    finance_results: tuple
    finance_executed: bool
    rankable_finance_count: int
    missing_fields: tuple[str, ...]
    reasons: tuple[str, ...]
    finance_fact_result: object | None = None
    campaign_result: object | None = None
    campaign_universe_key: str | None = None


_run_chatbot_before_campaign_compare_v1_3 = (
    run_chatbot
)


def run_chatbot(
    question: str,
    *args,
    campaign_compare_fn=_run_campaign_compare_v1_3,
    **kwargs,
):

    question = str(
        question
        or ""
    ).strip()

    route_decision = kwargs.get(
        "route_decision"
    )

    if route_decision is None:

        route_decision = (
            route_question(
                question
            )
        )

        kwargs[
            "route_decision"
        ] = route_decision

    route = str(
        getattr(
            route_decision,
            "route",
            "",
        )
    )

    if route == "campaign_compare":

        campaign_run = (
            campaign_compare_fn(
                question,
                route_decision=(
                    route_decision
                ),
            )
        )

        missing = tuple(
            getattr(
                campaign_run,
                "missing_fields",
                (),
            )
        )

        return CampaignChatbotExecutionResultV1_3(
            question=question,
            route=route,
            status=(
                STATUS_NEEDS_INPUT
                if missing
                else STATUS_COMPLETED
            ),
            route_decision=route_decision,
            rag_result=None,
            finance_results=tuple(),
            finance_executed=False,
            rankable_finance_count=0,
            missing_fields=missing,
            reasons=tuple(
                getattr(
                    campaign_run,
                    "reasons",
                    (),
                )
            ),
            finance_fact_result=None,
            campaign_result=getattr(
                campaign_run,
                "comparison",
                None,
            ),
            campaign_universe_key=getattr(
                campaign_run,
                "universe_key",
                None,
            ),
        )

    return (
        _run_chatbot_before_campaign_compare_v1_3(
            question,
            *args,
            **kwargs,
        )
    )
