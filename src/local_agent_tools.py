# BANSA_LOCAL_AGENT_TOOLS_V1

from __future__ import annotations

from dataclasses import (
    asdict,
    dataclass,
    is_dataclass,
)
from datetime import (
    date,
    datetime,
)
from decimal import Decimal

from src.local_agent_contract import (
    AgentDecision,
)


@dataclass(
    frozen=True
)
class AgentToolResult:

    status: str

    tool_name: str

    data: dict | None

    reasons: tuple[
        str,
        ...
    ]


def _json_safe(
    value,
):

    if is_dataclass(
        value
    ):
        return _json_safe(
            asdict(
                value
            )
        )

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key):
                _json_safe(
                    item
                )
            for key, item
            in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
            frozenset,
        ),
    ):
        return [
            _json_safe(
                item
            )
            for item in value
        ]

    if isinstance(
        value,
        Decimal,
    ):
        return str(
            value
        )

    if isinstance(
        value,
        (
            date,
            datetime,
        ),
    ):
        return value.isoformat()

    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    return str(
        value
    )


def _canonical_question(
    decision: AgentDecision,
    question,
) -> str:

    original = str(
        question
        or ""
    ).strip()

    if original:
        return original

    parts = []

    if decision.banks:
        parts.append(
            " ile ".join(
                decision.banks
            )
        )

    if decision.product:
        parts.append(
            decision.product
        )

    if decision.topic:
        parts.append(
            decision.topic
        )

    if decision.amount is not None:
        parts.append(
            str(
                decision.amount
            )
            + " TL"
        )

    if (
        decision.maturity_months
        is not None
    ):
        parts.append(
            str(
                decision.maturity_months
            )
            + " ay"
        )

    if (
        decision.customer_scope
        ==
        "business"
    ):
        parts.append(
            "ticari"
        )

    elif (
        decision.customer_scope
        ==
        "individual"
    ):
        parts.append(
            "bireysel"
        )

    if decision.intent == "campaign_compare":
        parts.append(
            "kampanyalarini karsilastir"
        )

    elif decision.intent == "campaign_search":
        parts.append(
            "kampanyalari"
        )

    elif decision.intent == "finance_compare":
        parts.append(
            "finansmanlarini karsilastir"
        )

    return " ".join(
        parts
    ).strip()


def _failure(
    tool_name,
    reason,
) -> AgentToolResult:

    return AgentToolResult(
        status="fallback",
        tool_name=str(
            tool_name
            or ""
        ),
        data=None,
        reasons=(
            str(
                reason
            ),
        ),
    )


def execute_agent_decision(
    decision,
    *,
    question=None,
    db_path=None,
    as_of=None,
    campaign_universe_fn=None,
    universe_resolver_fn=None,
    finance_fact_lookup_fn=None,
    finance_compare_fn=None,
    finance_products_fn=None,
    campaign_detail_fn=None,
    rag_execution_fn=None,
    grounded_context_fn=None,
) -> AgentToolResult:

    if not isinstance(
        decision,
        AgentDecision,
    ):
        return _failure(
            "",
            "invalid_agent_decision",
        )

    tool_name = (
        decision.tool_name
    )

    if not tool_name:
        return _failure(
            "",
            "decision_has_no_safe_tool",
        )

    effective_question = (
        _canonical_question(
            decision,
            question,
        )
    )

    try:

        # ====================================================
        # VERIFIED CAMPAIGN SEARCH
        # ====================================================

        if tool_name == "search_campaigns":

            if campaign_universe_fn is None:

                from src.campaign_comparison_universe import (
                    compare_campaign_universe,
                )

                campaign_universe_fn = (
                    compare_campaign_universe
                )

            result = (
                campaign_universe_fn(
                    "all_active",
                    bank_names=(
                        decision.banks
                        or None
                    ),
                    spend_amount=(
                        decision.amount
                    ),
                    question=(
                        effective_question
                    ),
                    as_of=as_of,
                    db_path=db_path,
                )
            )

            from src.chatbot_campaign_renderer import (
                render_campaign_answer,
            )

            rendered = (
                render_campaign_answer(
                    result
                )
            )

            verified_text = str(
                getattr(
                    rendered,
                    "text",
                    "",
                )
                or ""
            ).strip()

            if not verified_text:

                return _failure(
                    tool_name,
                    "campaign_search_rendering_blocked",
                )

            return AgentToolResult(
                status="ok",
                tool_name=tool_name,
                data={
                    "universe":
                        "all_active",

                    "verified_text":
                        verified_text,

                    "result":
                        _json_safe(
                            result
                        ),
                },
                reasons=(
                    "verified_campaign_search",
                ),
            )

        # ====================================================
        # VERIFIED CAMPAIGN COMPARISON
        # ====================================================

        if tool_name == "compare_campaigns":

            # ====================================================
            # CANONICAL MARKET CAMPAIGN TOOL
            # ====================================================
            #
            # The local LLM has already normalized the user's
            # semantic topic into AgentDecision.topic.
            #
            # Do not re-detect market intent from raw text here.
            # Use the existing strict TITLE+URL live market runtime.
            #
            # This is important because valid market campaigns may
            # live under card_campaign rather than the legacy
            # shopping_benefit category set.
            #
            if (
                str(
                    decision.topic
                    or ""
                ).strip().casefold()
                ==
                "market"
            ):

                from src.chatbot_market_campaign_runtime import (
                    answer_market_question,
                )

                result = (
                    answer_market_question(
                        effective_question,
                        db_path=db_path,
                        today=as_of,
                    )
                )

                if not isinstance(
                    result,
                    dict,
                ):
                    return _failure(
                        tool_name,
                        "invalid_market_runtime_result",
                    )

                verified_text = str(
                    result.get(
                        "text"
                    )
                    or ""
                ).strip()

                if not verified_text:

                    return _failure(
                        tool_name,
                        "canonical_market_missing_verified_text",
                    )

                return AgentToolResult(
                    status="ok",
                    tool_name=tool_name,
                    data={
                        "universe":
                            "canonical_market",

                        "verified_text":
                            verified_text,

                        "result":
                            _json_safe(
                                result
                            ),
                    },
                    reasons=(
                        "verified_canonical_market_runtime",
                    ),
                )

            if universe_resolver_fn is None:

                from src.chatbot_campaign_compare import (
                    resolve_campaign_universe_key,
                )

                universe_resolver_fn = (
                    resolve_campaign_universe_key
                )

            if campaign_universe_fn is None:

                from src.campaign_comparison_universe import (
                    compare_campaign_universe,
                )

                campaign_universe_fn = (
                    compare_campaign_universe
                )

            universe = (
                universe_resolver_fn(
                    effective_question
                )
                or
                "all_active"
            )

            result = (
                campaign_universe_fn(
                    universe,
                    bank_names=(
                        decision.banks
                        or None
                    ),
                    spend_amount=(
                        decision.amount
                    ),
                    question=(
                        effective_question
                    ),
                    as_of=as_of,
                    db_path=db_path,
                )
            )

            from src.chatbot_campaign_renderer import (
                render_campaign_answer,
            )

            rendered = (
                render_campaign_answer(
                    result
                )
            )

            verified_text = str(
                getattr(
                    rendered,
                    "text",
                    "",
                )
                or ""
            ).strip()

            if not verified_text:

                return _failure(
                    tool_name,
                    "campaign_comparison_rendering_blocked",
                )

            return AgentToolResult(
                status="ok",
                tool_name=tool_name,
                data={
                    "universe":
                        universe,

                    "verified_text":
                        verified_text,

                    "result":
                        _json_safe(
                            result
                        ),
                },
                reasons=(
                    "verified_campaign_comparison",
                ),
            )

        # ====================================================
        # VERIFIED FINANCE COMPARISON
        # ====================================================

        if tool_name == "compare_finance":

            # ------------------------------------------------
            # FAMILY CANONICALIZATION
            #
            # The LLM owns semantic intent.
            # The historical detector is reused only as a
            # deterministic vocabulary -> canonical family
            # mapper. It does NOT choose the route here.
            # ------------------------------------------------

            from src.chatbot_router import (
                _detect_family,
                _detect_purpose,
            )

            family = _detect_family(
                effective_question
            )

            if not family:

                return _failure(
                    tool_name,
                    "finance_family_unresolved",
                )

            purpose = _detect_purpose(
                effective_question,
                family,
            )

            # ------------------------------------------------
            # PRODUCT CATALOG / SCOPE RESOLUTION
            #
            # Never silently use the finance engine's
            # historical default scope="bireysel".
            #
            # If the user supplied a customer scope, map it to
            # the finance catalog vocabulary.
            #
            # Otherwise determine the only scope represented by
            # the requested banks + family. Ambiguity fails
            # closed.
            # ------------------------------------------------

            if finance_products_fn is None:

                from src.finance_live_compare import (
                    get_standard_products,
                )

                finance_products_fn = (
                    get_standard_products
                )

            products = (
                finance_products_fn()
                .copy()
            )

            def _norm(value):

                return (
                    str(
                        value
                        or ""
                    )
                    .strip()
                    .casefold()
                )

            requested_banks = tuple(
                decision.banks
                or ()
            )

            allowed_banks = {
                _norm(
                    value
                )
                for value
                in requested_banks
            }

            candidates = products[
                products[
                    "product_family_key"
                ]
                .fillna("")
                .astype(str)
                .str.casefold()
                .eq(
                    _norm(
                        family
                    )
                )
            ].copy()

            if allowed_banks:

                candidates = candidates[
                    candidates[
                        "bank_name"
                    ]
                    .fillna("")
                    .astype(str)
                    .apply(
                        _norm
                    )
                    .isin(
                        allowed_banks
                    )
                ].copy()

            scope_map = {
                "individual":
                    "bireysel",

                "business":
                    "ticari",
            }

            explicit_scope = (
                scope_map.get(
                    decision.customer_scope
                )
            )

            if (
                decision.customer_scope
                ==
                "all"
            ):

                return _failure(
                    tool_name,
                    "finance_scope_all_requires_explicit_multi_scope_support",
                )

            if explicit_scope is not None:

                scope = explicit_scope

                candidates = candidates[
                    candidates[
                        "scope"
                    ]
                    .fillna("")
                    .astype(str)
                    .str.casefold()
                    .eq(
                        _norm(
                            scope
                        )
                    )
                ].copy()

                if candidates.empty:

                    return _failure(
                        tool_name,
                        "finance_scope_has_no_matching_products",
                    )

            else:

                scopes = tuple(
                    sorted(
                        {
                            _norm(
                                value
                            )
                            for value
                            in candidates[
                                "scope"
                            ].dropna()
                            if _norm(
                                value
                            )
                        }
                    )
                )

                if len(scopes) == 0:

                    return _failure(
                        tool_name,
                        "finance_scope_unresolved",
                    )

                if len(scopes) > 1:

                    return _failure(
                        tool_name,
                        "finance_scope_ambiguous",
                    )

                scope = scopes[0]

            # Every explicitly requested bank must actually
            # remain represented after family/scope filtering.
            candidate_banks = {
                _norm(
                    value
                )
                for value
                in candidates[
                    "bank_name"
                ].dropna()
            }

            missing_banks = tuple(
                bank
                for bank
                in requested_banks
                if _norm(
                    bank
                )
                not in candidate_banks
            )

            if missing_banks:

                return _failure(
                    tool_name,
                    "finance_requested_bank_has_no_matching_product",
                )

            if finance_compare_fn is None:

                from src.finance_verified_resolver import (
                    compare_financing,
                )

                finance_compare_fn = (
                    compare_financing
                )

            live_results = tuple(
                finance_compare_fn(
                    family=family,
                    amount=decision.amount,
                    maturity=(
                        decision.maturity_months
                    ),
                    purpose=purpose,
                    scope=scope,
                    bank_names=(
                        requested_banks
                        or None
                    ),
                )
            )

            if not live_results:

                return _failure(
                    tool_name,
                    "no_finance_candidates",
                )

            # ------------------------------------------------
            # EXISTING GROUNDING BOUNDARY
            #
            # Do not expose LiveCalculationResult/raw_output
            # directly to the agent.
            # ------------------------------------------------

            from src.chatbot_answer_contract import (
                _finance_item,
                _finance_permissions,
            )

            grounded = tuple(
                _finance_item(
                    result
                )
                for result
                in live_results
            )

            (
                rankable,
                unresolved,
                may_use_financial_numbers,
                may_claim_finance_ranking,
            ) = _finance_permissions(
                grounded
            )

            from src.finance_comparison_evaluator import (
                evaluate_finance_results,
            )

            evaluation = (
                evaluate_finance_results(
                    grounded,
                    allow_ranking=(
                        may_claim_finance_ranking
                    ),
                )
            )

            reasons = [
                "verified_finance_comparison",
                "existing_finance_grounding_boundary_used",
            ]

            if (
                may_claim_finance_ranking
            ):

                reasons.append(
                    "finance_ranking_allowed"
                )

            else:

                reasons.append(
                    "finance_ranking_blocked"
                )

            if unresolved:

                reasons.append(
                    "unresolved_finance_candidates_present"
                )

            # ------------------------------------------------
            # DETERMINISTIC FINANCE PRESENTATION
            #
            # Use only the already-grounded finance results.
            # No LiveCalculationResult/raw_output crosses into
            # the answer layer.
            # ------------------------------------------------

            from src.chatbot_answer_contract import (
                GroundedAnswerContext,
            )

            from src.chatbot_finance_renderer import (
                render_finance_answer,
            )

            finance_context = GroundedAnswerContext(
                question=effective_question,
                route="finance_compare",
                execution_status="completed",
                answer_mode="finance",
                may_generate_answer=True,
                may_claim_finance_ranking=(
                    may_claim_finance_ranking
                ),
                may_use_financial_numbers=(
                    may_use_financial_numbers
                ),
                evidence=tuple(),
                finance_results=grounded,
                missing_fields=tuple(),
                reasons=tuple(
                    reasons
                ),
            )

            finance_rendered = (
                render_finance_answer(
                    finance_context
                )
            )

            verified_text = str(
                getattr(
                    finance_rendered,
                    "text",
                    "",
                )
                or ""
            ).strip()

            if not verified_text:

                return _failure(
                    tool_name,
                    "finance_comparison_rendering_blocked",
                )

            return AgentToolResult(
                status="ok",
                tool_name=tool_name,
                data={
                    "family":
                        family,

                    "purpose":
                        purpose,

                    "scope":
                        scope,

                    "may_use_financial_numbers":
                        may_use_financial_numbers,

                    "may_claim_finance_ranking":
                        may_claim_finance_ranking,

                    "rankable_count":
                        len(
                            rankable
                        ),

                    "verified_text":
                        verified_text,

                    "grounded_results":
                        _json_safe(
                            grounded
                        ),

                    "evaluation":
                        _json_safe(
                            evaluation
                        ),
                },
                reasons=tuple(
                    reasons
                ),
            )


        # ====================================================
        # VERIFIED SINGLE-BANK FINANCE CALCULATION
        # ====================================================

        if tool_name == "calculate_finance":

            from src.chatbot_router import (
                _detect_family,
                _detect_purpose,
            )

            family = _detect_family(
                effective_question
            )

            if not family:

                return _failure(
                    tool_name,
                    "finance_family_unresolved",
                )

            purpose = _detect_purpose(
                effective_question,
                family,
            )

            requested_banks = tuple(
                decision.banks
                or ()
            )

            if len(requested_banks) != 1:

                return _failure(
                    tool_name,
                    "single_finance_calculation_requires_one_bank",
                )

            # ------------------------------------------------
            # Resolve scope from explicit user evidence or
            # the actual matching product catalog.
            #
            # Never silently inherit compare_financing()'s
            # historical scope="bireysel" default.
            # ------------------------------------------------

            if finance_products_fn is None:

                from src.finance_live_compare import (
                    get_standard_products,
                )

                finance_products_fn = (
                    get_standard_products
                )

            products = (
                finance_products_fn()
                .copy()
            )

            def _norm(value):

                return (
                    str(
                        value
                        or ""
                    )
                    .strip()
                    .casefold()
                )

            allowed_banks = {
                _norm(
                    value
                )
                for value
                in requested_banks
            }

            candidates = products[
                products[
                    "product_family_key"
                ]
                .fillna("")
                .astype(str)
                .str.casefold()
                .eq(
                    _norm(
                        family
                    )
                )
            ].copy()

            candidates = candidates[
                candidates[
                    "bank_name"
                ]
                .fillna("")
                .astype(str)
                .apply(
                    _norm
                )
                .isin(
                    allowed_banks
                )
            ].copy()

            scope_map = {
                "individual":
                    "bireysel",

                "business":
                    "ticari",
            }

            explicit_scope = (
                scope_map.get(
                    decision.customer_scope
                )
            )

            if (
                decision.customer_scope
                ==
                "all"
            ):

                return _failure(
                    tool_name,
                    "finance_scope_all_not_valid_for_single_calculation",
                )

            if explicit_scope is not None:

                scope = explicit_scope

                candidates = candidates[
                    candidates[
                        "scope"
                    ]
                    .fillna("")
                    .astype(str)
                    .str.casefold()
                    .eq(
                        _norm(
                            scope
                        )
                    )
                ].copy()

                if candidates.empty:

                    return _failure(
                        tool_name,
                        "finance_scope_has_no_matching_products",
                    )

            else:

                scopes = tuple(
                    sorted(
                        {
                            _norm(
                                value
                            )
                            for value
                            in candidates[
                                "scope"
                            ].dropna()
                            if _norm(
                                value
                            )
                        }
                    )
                )

                if len(scopes) == 0:

                    return _failure(
                        tool_name,
                        "finance_scope_unresolved",
                    )

                if len(scopes) > 1:

                    return _failure(
                        tool_name,
                        "finance_scope_ambiguous",
                    )

                scope = scopes[0]

            candidate_banks = {
                _norm(
                    value
                )
                for value
                in candidates[
                    "bank_name"
                ].dropna()
            }

            if (
                _norm(
                    requested_banks[0]
                )
                not in candidate_banks
            ):

                return _failure(
                    tool_name,
                    "finance_requested_bank_has_no_matching_product",
                )

            if finance_compare_fn is None:

                from src.finance_verified_resolver import (
                    compare_financing,
                )

                finance_compare_fn = (
                    compare_financing
                )

            live_results = tuple(
                finance_compare_fn(
                    family=family,
                    amount=decision.amount,
                    maturity=(
                        decision.maturity_months
                    ),
                    purpose=purpose,
                    scope=scope,
                    bank_names=(
                        requested_banks
                    ),
                )
            )

            if not live_results:

                return _failure(
                    tool_name,
                    "no_finance_candidates",
                )

            # ------------------------------------------------
            # Existing finance grounding boundary.
            # raw_output never crosses this layer.
            # ------------------------------------------------

            from src.chatbot_answer_contract import (
                _finance_item,
                _finance_permissions,
            )

            grounded = tuple(
                _finance_item(
                    result
                )
                for result
                in live_results
            )

            (
                rankable,
                unresolved,
                may_use_financial_numbers,
                _may_claim_finance_ranking,
            ) = _finance_permissions(
                grounded
            )

            # Single-bank calculation must resolve to one
            # unique VERIFIED + exact + rankable candidate.
            #
            # INELIGIBLE candidates are already deterministically
            # resolved and do not count as unresolved.
            if (
                len(rankable) != 1
                or
                bool(unresolved)
            ):

                return _failure(
                    tool_name,
                    "single_finance_result_not_unique_verified",
                )

            selected = rankable[0]

            # ------------------------------------------------
            # DETERMINISTIC SINGLE-BANK PRESENTATION
            #
            # Reuse the existing finance renderer with the
            # already-grounded single verified candidate.
            # Ranking remains explicitly disabled.
            # ------------------------------------------------

            from src.chatbot_answer_contract import (
                GroundedAnswerContext,
            )

            from src.chatbot_finance_renderer import (
                render_finance_answer,
            )

            finance_context = GroundedAnswerContext(
                question=effective_question,
                route="finance_compare",
                execution_status="completed",
                answer_mode="finance",
                may_generate_answer=True,
                may_claim_finance_ranking=False,
                may_use_financial_numbers=(
                    may_use_financial_numbers
                ),
                evidence=tuple(),
                finance_results=grounded,
                missing_fields=tuple(),
                reasons=(
                    "single_bank_calculation_presentation",
                ),
            )

            finance_rendered = (
                render_finance_answer(
                    finance_context
                )
            )

            verified_text = str(
                getattr(
                    finance_rendered,
                    "text",
                    "",
                )
                or ""
            ).strip()

            if not verified_text:

                return _failure(
                    tool_name,
                    "finance_calculation_rendering_blocked",
                )

            return AgentToolResult(
                status="ok",
                tool_name=tool_name,
                data={
                    "family":
                        family,

                    "purpose":
                        purpose,

                    "scope":
                        scope,

                    "may_use_financial_numbers":
                        may_use_financial_numbers,

                    "may_claim_finance_ranking":
                        False,

                    "rankable_count":
                        1,

                    "verified_text":
                        verified_text,

                    "result":
                        _json_safe(
                            selected
                        ),

                    "grounded_results":
                        _json_safe(
                            grounded
                        ),
                },
                reasons=(
                    "verified_single_bank_finance_calculation",
                    "existing_finance_grounding_boundary_used",
                    "finance_ranking_not_applicable_single_bank",
                ),
            )


        # ====================================================
        # VERIFIED FINANCE FACT
        # ====================================================

        if tool_name == "get_finance_fact":

            # ------------------------------------------------
            # STRUCTURED ATTRIBUTE RESOLUTION
            #
            # The LLM already chose finance_fact intent.
            # Reuse the existing deterministic attribute
            # detector only to map the user's wording to the
            # canonical finance fact field.
            # ------------------------------------------------

            from src.chatbot_router import (
                _detect_finance_fact_attribute,
            )

            attribute = (
                _detect_finance_fact_attribute(
                    effective_question
                )
            )

            if not attribute:

                return _failure(
                    tool_name,
                    "finance_fact_attribute_unresolved",
                )

            if finance_fact_lookup_fn is None:

                from src.chatbot_finance_fact_lookup import (
                    lookup_finance_fact,
                )

                finance_fact_lookup_fn = (
                    lookup_finance_fact
                )

            result = (
                finance_fact_lookup_fn(
                    question=(
                        effective_question
                    ),
                    attribute=attribute,
                )
            )

            if isinstance(
                result,
                dict,
            ):

                result_status = str(
                    result.get(
                        "status"
                    )
                    or ""
                ).strip().casefold()

                verified_text = str(
                    result.get(
                        "text"
                    )
                    or ""
                ).strip()

            else:

                result_status = str(
                    getattr(
                        result,
                        "status",
                        "",
                    )
                    or ""
                ).strip().casefold()

                verified_text = str(
                    getattr(
                        result,
                        "text",
                        "",
                    )
                    or ""
                ).strip()

            if (
                result_status
                ==
                "unsupported_attribute"
            ):

                return _failure(
                    tool_name,
                    "finance_fact_attribute_unsupported",
                )

            if not verified_text:

                return _failure(
                    tool_name,
                    "finance_fact_missing_verified_text",
                )

            return AgentToolResult(
                status="ok",
                tool_name=tool_name,
                data={
                    "verified_text":
                        verified_text,

                    "result":
                        _json_safe(
                            result
                        ),
                },
                reasons=(
                    "verified_finance_fact",
                ),
            )

        # ====================================================
        # VERIFIED MARKET CAMPAIGN DETAIL
        # ====================================================

        if tool_name == "get_campaign_detail":

            topic = (
                str(
                    decision.topic
                    or ""
                )
                .strip()
                .casefold()
            )

            # Normalize only the semantic topic already produced
            # by the validated local planner.
            #
            # Do NOT re-detect campaign intent from raw user text.
            # "market ve gıda", "market/gıda" etc. all belong
            # to the same canonical live market runtime.
            topic_tokens = {
                token
                for token in (
                    topic
                    .replace("/", " ")
                    .replace("-", " ")
                    .replace("&", " ")
                    .split()
                )
                if token
            }

            if (
                "market" in topic_tokens
                or "gıda" in topic_tokens
                or "gida" in topic_tokens
            ):
                topic = "market"

            # The canonical live runtime currently owns only
            # market/gida campaign truth.
            #
            # Do not pretend generic campaign-detail support
            # exists for other topics.
            if topic not in {
                "market",
                "g\u0131da",
                "gida",
            }:

                return _failure(
                    tool_name,
                    "campaign_detail_topic_not_wired",
                )

            requested_banks = tuple(
                decision.banks
                or ()
            )

            if len(requested_banks) != 1:

                return _failure(
                    tool_name,
                    "campaign_detail_requires_one_bank",
                )

            if campaign_detail_fn is None:

                from src.chatbot_market_campaign_runtime import (
                    answer_market_question,
                )

                campaign_detail_fn = (
                    answer_market_question
                )

            result = campaign_detail_fn(
                effective_question,
                db_path=db_path,
                today=as_of,
            )

            if not isinstance(
                result,
                dict,
            ):

                return _failure(
                    tool_name,
                    "invalid_market_campaign_detail_result",
                )

            route = str(
                result.get(
                    "route"
                )
                or ""
            )

            # A one-bank detail request must stay on the
            # campaign_rag/detail path. Never silently accept
            # a comparison result.
            if route != "campaign_rag":

                return _failure(
                    tool_name,
                    "unexpected_market_campaign_detail_route",
                )

            result_banks = tuple(
                result.get(
                    "banks"
                )
                or ()
            )

            if len(result_banks) != 1:

                return _failure(
                    tool_name,
                    "market_campaign_detail_bank_lock_failed",
                )

            def _norm(value):

                return (
                    str(
                        value
                        or ""
                    )
                    .strip()
                    .casefold()
                )

            if (
                _norm(
                    result_banks[0]
                )
                !=
                _norm(
                    requested_banks[0]
                )
            ):

                return _failure(
                    tool_name,
                    "market_campaign_detail_bank_lock_failed",
                )

            status = str(
                result.get(
                    "status"
                )
                or ""
            )

            if status not in {
                "FOUND",
                "NO_MATCH",
            }:

                return _failure(
                    tool_name,
                    "invalid_market_campaign_detail_status",
                )

            verified_text = str(
                result.get(
                    "text"
                )
                or ""
            ).strip()

            if not verified_text:

                return _failure(
                    tool_name,
                    "campaign_detail_missing_verified_text",
                )

            return AgentToolResult(
                status="ok",
                tool_name=tool_name,
                data={
                    "universe":
                        "canonical_market",

                    "verified_text":
                        verified_text,

                    "result":
                        _json_safe(
                            result
                        ),
                },
                reasons=(
                    "verified_canonical_market_campaign_detail",
                    "strict_title_url_topic_lock",
                    "bank_lock",
                    "active_date_lock",
                ),
            )


        # ====================================================
        # VERIFIED PRODUCT RAG SEARCH
        # ====================================================

        if tool_name == "rag_search":

            # Campaign intents have dedicated safe tools:
            #
            #   search_campaigns
            #   compare_campaigns
            #   get_campaign_detail
            #
            # Therefore generic rag_search is intentionally
            # mapped only to the standard-product RAG lane.
            #
            # The local LLM chooses the semantic intent.
            # We do NOT call route_question() here.

            from src.chatbot_router import (
                ChatbotRouteDecision,
                ROUTE_PRODUCT_RAG,
                _detect_family,
                _detect_purpose,
            )

            family = _detect_family(
                effective_question
            )

            purpose = _detect_purpose(
                effective_question,
                family,
            )

            route_decision = (
                ChatbotRouteDecision(
                    route=(
                        ROUTE_PRODUCT_RAG
                    ),
                    normalized_question=(
                        effective_question
                    ),
                    family=family,
                    purpose=purpose,
                    amount=decision.amount,
                    maturity=(
                        decision.maturity_months
                    ),
                    finance_attribute=None,
                    missing_fields=tuple(),
                    reasons=(
                        "local_agent_product_rag_route",
                    ),
                    bank_names=tuple(
                        decision.banks
                        or ()
                    ),
                )
            )

            # ------------------------------------------------
            # Existing RAG execution:
            #
            # retrieval
            # -> verifier
            # -> PASS / ABSTAIN
            #
            # route_decision is explicitly supplied, therefore
            # the historical router does not choose intent.
            # ------------------------------------------------

            if rag_execution_fn is None:

                from src.chatbot_orchestrator import (
                    run_chatbot,
                )

                rag_execution_fn = (
                    run_chatbot
                )

            execution = rag_execution_fn(
                effective_question,
                route_decision=(
                    route_decision
                ),
            )

            execution_route = str(
                getattr(
                    execution,
                    "route",
                    "",
                )
                or ""
            )

            if (
                execution_route
                !=
                ROUTE_PRODUCT_RAG
            ):

                return _failure(
                    tool_name,
                    "rag_execution_route_changed",
                )

            # ------------------------------------------------
            # Existing answer grounding boundary:
            #
            # EvidencePack / raw retrieval results never cross
            # into the local agent.
            #
            # Only selected GroundedEvidence objects with
            # traceable source URLs are exposed.
            # ------------------------------------------------

            if grounded_context_fn is None:

                from src.chatbot_answer_contract import (
                    build_grounded_answer_context,
                )

                grounded_context_fn = (
                    build_grounded_answer_context
                )

            context = grounded_context_fn(
                execution
            )

            if (
                str(
                    getattr(
                        context,
                        "route",
                        "",
                    )
                )
                !=
                ROUTE_PRODUCT_RAG
            ):

                return _failure(
                    tool_name,
                    "rag_grounding_route_changed",
                )

            evidence = tuple(
                getattr(
                    context,
                    "evidence",
                    (),
                )
                or ()
            )

            may_generate = bool(
                getattr(
                    context,
                    "may_generate_answer",
                    False,
                )
            )

            if (
                not may_generate
                or
                not evidence
            ):

                return _failure(
                    tool_name,
                    "rag_grounding_blocked",
                )

            # Defense in depth. _rag_evidence() already applies
            # expected source-kind filtering and requires both
            # evidence text and source URL.
            for item in evidence:

                source_kind = (
                    str(
                        getattr(
                            item,
                            "source_kind",
                            "",
                        )
                        or ""
                    )
                    .strip()
                    .casefold()
                )

                source_url = str(
                    getattr(
                        item,
                        "source_url",
                        "",
                    )
                    or ""
                ).strip()

                evidence_text = str(
                    getattr(
                        item,
                        "text",
                        "",
                    )
                    or ""
                ).strip()

                if (
                    source_kind
                    !=
                    "standard_product"
                ):

                    return _failure(
                        tool_name,
                        "rag_grounding_source_kind_mismatch",
                    )

                if (
                    not source_url
                    or
                    not evidence_text
                ):

                    return _failure(
                        tool_name,
                        "rag_grounding_untraceable_evidence",
                    )

            # ------------------------------------------------
            # EXISTING DETERMINISTIC RAG RENDERER
            #
            # The renderer receives the already-grounded
            # context. Raw retrieval results never cross into
            # the answer model.
            # ------------------------------------------------

            from src.chatbot_rag_extractive_renderer import (
                render_extractive_rag_answer,
            )

            rendered = (
                render_extractive_rag_answer(
                    context,
                    question=(
                        effective_question
                    ),
                )
            )

            verified_text = str(
                getattr(
                    rendered,
                    "text",
                    "",
                )
                or ""
            ).strip()

            rendered_evidence_ids = tuple(
                getattr(
                    rendered,
                    "evidence_ids",
                    (),
                )
                or ()
            )

            if (
                not verified_text
                or
                not rendered_evidence_ids
            ):

                return _failure(
                    tool_name,
                    "rag_extractive_rendering_blocked",
                )

            return AgentToolResult(
                status="ok",
                tool_name=tool_name,
                data={
                    "route":
                        ROUTE_PRODUCT_RAG,

                    "source_kind":
                        "standard_product",

                    "family":
                        family,

                    "verified_text":
                        verified_text,

                    "evidence_count":
                        len(
                            evidence
                        ),

                    "evidence":
                        _json_safe(
                            evidence
                        ),

                    "grounding_reasons":
                        _json_safe(
                            tuple(
                                getattr(
                                    context,
                                    "reasons",
                                    (),
                                )
                                or ()
                            )
                        ),
                },
                reasons=(
                    "verified_product_rag",
                    "existing_rag_verifier_used",
                    "existing_answer_evidence_selector_used",
                    "existing_rag_grounding_boundary_used",
                ),
            )


        # ====================================================
        # NOT YET WIRED
        # ====================================================

        return _failure(
            tool_name,
            (
                "safe_tool_not_wired:"
                + tool_name
            ),
        )

    except Exception as exc:

        return _failure(
            tool_name,
            (
                "tool_execution_error:"
                + type(
                    exc
                ).__name__
            ),
        )
