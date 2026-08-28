# BANSA_LOCAL_AGENT_ORCHESTRATOR_V2

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
import json
import os
import re

from src.local_agent_contract import (
    AgentDecision,
    AgentDecisionError,
    CANONICAL_BANKS,
    PLANNER_TOOL_NAME,
    PLANNER_TOOL_SCHEMA,
    validate_agent_decision,
)

from src.local_llm_client import (
    LocalLLMClient,
)


@dataclass(
    frozen=True
)
class AgentPlan:

    status: str

    decision: AgentDecision | None

    tool_name: str | None

    reasons: tuple[
        str,
        ...
    ]


def _env_enabled() -> bool:

    value = str(
        os.getenv(
            "BANSA_LOCAL_AGENT_ENABLED",
            "0",
        )
        or ""
    ).strip().casefold()

    return value in {
        "1",
        "true",
        "yes",
        "on",
    }


def _intent_contract_text() -> str:

    return (
        "INTENT KURALLARI:\n"
        "- campaign_search: Kullanici aktif kampanyalarin "
        "listesini veya hangi kampanyalarin oldugunu sorar.\n"
        "- campaign_compare: Iki veya daha fazla bankanin "
        "kampanyalarini karsilastirir.\n"
        "- campaign_detail: Bir kampanyaya nasil katilindigi, "
        "hangi kartlarin gecerli oldugu, kosullar, kapsam veya "
        "kampanya detaylari sorulur.\n"
        "- finance_fact: Tek bir finansman urununun kar payi, "
        "azami vade, tahsis ucreti, ekspertiz, limit veya benzeri "
        "tekil dogrulanabilir bilgisi sorulur.\n"
        "- finance_compare: Iki veya daha fazla bankanin "
        "finansman urunleri karsilastirilir.\n"
        "- finance_calculate: Belirli tutar ve/veya vade ile "
        "finansman hesaplamasi istenir.\n"
        "- rag_search: Yapilandirilmis kampanya/finans intentlerine "
        "girmeyen acik uclu urun aciklamalari icindir.\n"
        "- unknown: Yalnizca soru BANSA kapsami disindaysa veya "
        "gercekten anlasilamiyorsa kullan."
    )


def _bank_contract_text() -> str:

    return (
        "BANKA KURALLARI:\n"
        "banks alanina yalnizca su kanonik banka adlarindan "
        "birini veya birkacini yaz:\n- "
        + "\n- ".join(
            CANONICAL_BANKS
        )
        + "\n"
        "Urun veya kampanya kelimelerini banka adina EKLEME. "
        "Ornegin banka adi ile urun adi yan yana gecse bile "
        "banks alaninda sadece kanonik banka adi bulunmalidir."
    )


def _normalization_contract_text() -> str:

    return (
        "NORMALIZASYON KURALLARI:\n"
        "- 200 bin TL -> amount=200000\n"
        "- 1,5 milyon TL -> amount=1500000\n"
        "- 5000 TL -> amount=5000\n"
        "- 36 ay -> maturity_months=36\n"
        "- Kullanici bireysel/ticari kapsam belirtmediyse "
        "customer_scope=null.\n"
        "- 'bugun', 'su anda', 'guncel' gibi ifadelerde "
        "time_scope=current.\n"
        "- Kullanici iki banka soyluyorsa ikisini de banks "
        "alanina koy; birini topic veya product alanina tasima."
    )


def _system_prompt() -> str:

    return (
        "Sen BANSA'nin tamamen yerel calisan karar "
        "planlayicisisin. Kullaniciya cevap VERME. "
        "Yalnizca plan_bansa_request aracini cagir.\n\n"
        + _intent_contract_text()
        + "\n\n"
        + _bank_contract_text()
        + "\n\n"
        + _normalization_contract_text()
        + "\n\n"
        "topic kullanicinin sordugu konu/kategori icindir. "
        "product urun veya urun ailesi icindir. "
        "Bilmedigin bilgiyi uydurma. "
        "SQL, URL veya serbest tool adi uretme. "
        "Kullanicinin TUM cumlesini birlikte yorumla."
    )


def _repair_system_prompt() -> str:

    return (
        "Sen BANSA'nin yerel plan duzeltme katmanisin. "
        "Onceki plan validation veya semantik kontrolden "
        "gecemedi. Kullaniciya cevap VERME. "
        "Yalnizca plan_bansa_request aracini tekrar cagir "
        "ve hatayi duzelt.\n\n"
        + _intent_contract_text()
        + "\n\n"
        + _bank_contract_text()
        + "\n\n"
        + _normalization_contract_text()
        + "\n\n"
        "Onceki plani korumak zorunda degilsin. "
        "Kullanici sorusunu bastan ve butun olarak yorumla."
    )


def _safe_history(
    history,
):

    if not history:
        return []

    safe = []

    for item in list(
        history
    )[-6:]:

        if not isinstance(
            item,
            dict,
        ):
            continue

        role = str(
            item.get(
                "role"
            )
            or ""
        ).strip()

        content = str(
            item.get(
                "content"
            )
            or ""
        ).strip()

        if (
            role
            not in {
                "user",
                "assistant",
            }
            or
            not content
        ):
            continue

        safe.append(
            {
                "role":
                    role,

                "content":
                    content[:4000],
            }
        )

    return safe


def _extract_planner_payload(
    message,
):

    if not isinstance(
        message,
        dict,
    ):
        raise AgentDecisionError(
            "invalid_model_message"
        )

    tool_calls = (
        message.get(
            "tool_calls"
        )
        or []
    )

    if len(tool_calls) != 1:
        raise AgentDecisionError(
            "planner_requires_one_tool_call"
        )

    function = (
        tool_calls[0].get(
            "function"
        )
        or {}
    )

    name = str(
        function.get(
            "name"
        )
        or ""
    ).strip()

    if name != PLANNER_TOOL_NAME:
        raise AgentDecisionError(
            "unexpected_tool_name"
        )

    arguments = function.get(
        "arguments"
    )

    if isinstance(
        arguments,
        dict,
    ):
        return arguments

    if not isinstance(
        arguments,
        str,
    ):
        raise AgentDecisionError(
            "invalid_tool_arguments"
        )

    try:
        payload = json.loads(
            arguments
        )
    except json.JSONDecodeError as exc:
        raise AgentDecisionError(
            "invalid_tool_json"
        ) from exc

    return payload


def _call_planner(
    client,
    messages,
):

    return client.chat(
        messages,
        tools=[
            PLANNER_TOOL_SCHEMA
        ],
        tool_choice={
            "type":
                "function",

            "function": {
                "name":
                    PLANNER_TOOL_NAME,
            },
        },
        max_tokens=400,
        temperature=0.0,
    )


def _scaled_amounts_from_question(
    question,
) -> tuple[
    Decimal,
    ...
]:

    text = str(
        question
        or ""
    ).casefold()

    values = []

    # ASCII-SAFE scaled amount detector.
    #
    # Currency suffix is intentionally not part of this regex.
    # We only need the numeric scale relation:
    #
    #   200 bin     -> 200000
    #   1,5 milyon  -> 1500000
    #
    # This also avoids Windows/PowerShell encoding damage
    # from currency/Turkish characters inside regex source.
    pattern = re.compile(
        (
            r"(?<!\d)"
            r"(\d+(?:[.,]\d+)?)"
            r"\s*"
            r"(bin|milyon)"
            r"\b"
        ),
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(
        text
    ):

        raw = str(
            match.group(
                1
            )
        ).strip()

        # Turkish natural-number convention:
        #
        #   1,5  -> 1.5
        #   200  -> 200
        #
        # A single dot followed by exactly three digits is
        # treated as a thousands separator.
        if (
            "," in raw
        ):

            normalized = (
                raw
                .replace(
                    ".",
                    "",
                )
                .replace(
                    ",",
                    ".",
                )
            )

        elif (
            raw.count(
                "."
            )
            == 1
            and
            len(
                raw.split(
                    "."
                )[1]
            )
            == 3
        ):

            normalized = (
                raw.replace(
                    ".",
                    "",
                )
            )

        else:

            normalized = raw

        try:

            base = Decimal(
                normalized
            )

        except InvalidOperation:

            continue

        unit = str(
            match.group(
                2
            )
        ).casefold()

        multiplier = (
            Decimal(
                "1000000"
            )
            if unit
            ==
            "milyon"
            else
            Decimal(
                "1000"
            )
        )

        values.append(
            base
            *
            multiplier
        )

    return tuple(
        values
    )


def _explicit_customer_scope_from_question(
    question,
):

    low = str(
        question
        or ""
    ).casefold()

    individual_terms = (
        "bireysel",
        "kisisel",
        "ki\u015fisel",
        "kendim icin",
        "kendim i\u00e7in",
        "ferdi",
        "sahsi",
        "\u015fahsi",
    )

    business_terms = (
        "ticari",
        "isletme",
        "i\u015fletme",
        "sirket",
        "\u015firket",
        "kurumsal",
        "esnaf",
        "business",
    )

    all_terms = (
        "tum musteriler",
        "t\u00fcm m\u00fc\u015fteriler",
        "tum segmentler",
        "t\u00fcm segmentler",
        "tum musteri segmentleri",
        "t\u00fcm m\u00fc\u015fteri segmentleri",
        "herkes icin",
        "herkes i\u00e7in",
    )

    has_individual = any(
        term in low
        for term in individual_terms
    )

    has_business = any(
        term in low
        for term in business_terms
    )

    has_all = any(
        term in low
        for term in all_terms
    )

    if (
        has_all
        or
        (
            has_individual
            and
            has_business
        )
    ):
        return "all"

    if has_individual:
        return "individual"

    if has_business:
        return "business"

    return None


def _normalize_customer_scope(
    question,
    decision,
):

    explicit_scope = (
        _explicit_customer_scope_from_question(
            question
        )
    )

    # No customer segment was expressed by the user.
    # Never allow the LLM to invent one.
    if explicit_scope is None:

        if (
            decision.customer_scope
            is None
        ):
            return (
                decision,
                (),
            )

        return (
            replace(
                decision,
                customer_scope=None,
            ),
            (
                "customer_scope_removed_without_user_evidence",
            ),
        )

    # User wording has authority over model inference.
    if (
        decision.customer_scope
        ==
        explicit_scope
    ):
        return (
            decision,
            (),
        )

    return (
        replace(
            decision,
            customer_scope=explicit_scope,
        ),
        (
            "customer_scope_aligned_to_user_evidence",
        ),
    )


def _normalize_open_product_intent(
    question,
    decision,
):
    """
    finance_fact is only for structured, individually
    verifiable finance attributes.

    Open-ended product explanation requests belong to the
    verified product RAG lane.

    This does NOT use the historical router to choose intent.
    The existing finance attribute detector is reused only as
    a deterministic structured-attribute guard.
    """

    if (
        decision.intent
        !=
        "finance_fact"
    ):
        return (
            decision,
            (),
        )

    from src.chatbot_router import (
        _detect_finance_fact_attribute,
    )

    # Existing structured fact vocabulary always wins:
    # maturity, rate, fees, limit, financing ratio, etc.
    if (
        _detect_finance_fact_attribute(
            question
        )
        is not None
    ):
        return (
            decision,
            (),
        )

    low = str(
        question
        or ""
    ).casefold()

    open_terms = (
        "avantaj",
        "fayda",
        "\u00f6zellik",
        "ozellik",
        "ko\u015ful",
        "kosul",
        "\u00f6ne \u00e7\u0131kan",
        "one cikan",
        "neler sunuyor",
        "ne sunuyor",
        "genel olarak",
        "genel bilgi",
        "anlat",
        "detaylar\u0131",
        "detaylari",
    )

    if not any(
        term in low
        for term in open_terms
    ):
        return (
            decision,
            (),
        )

    return (
        replace(
            decision,
            intent="rag_search",
        ),
        (
            "open_ended_product_question_routed_to_rag",
        ),
    )


def _semantic_plan_reasons(
    question,
    decision,
) -> tuple[
    str,
    ...
]:

    reasons = []

    low = str(
        question
        or ""
    ).casefold()

    scaled_amounts = (
        _scaled_amounts_from_question(
            question
        )
    )

    if (
        scaled_amounts
        and
        decision.amount is not None
        and
        decision.amount
        not in scaled_amounts
    ):

        reasons.append(
            "amount_scale_mismatch"
        )

    # Campaign questions must not silently fall into generic RAG.
    if (
        decision.intent
        ==
        "rag_search"
        and
        "kampanya"
        in low
    ):

        reasons.append(
            "campaign_routed_to_generic_rag"
        )

    # A domain question should get one repair chance before
    # accepting unknown.
    if (
        decision.intent
        ==
        "unknown"
        and
        (
            "kampanya"
            in low
            or
            "finansman"
            in low
            or
            bool(
                decision.banks
            )
        )
    ):

        reasons.append(
            "domain_question_marked_unknown"
        )

    return tuple(
        reasons
    )


def _repair_messages(
    *,
    question,
    history,
    first_payload,
    problem,
):

    messages = [
        {
            "role":
                "system",

            "content":
                _repair_system_prompt(),
        }
    ]

    messages.extend(
        _safe_history(
            history
        )
    )

    try:
        previous = json.dumps(
            first_payload,
            ensure_ascii=False,
        )
    except Exception:
        previous = str(
            first_payload
        )

    messages.append(
        {
            "role":
                "user",

            "content":
                (
                    "ORIGINAL QUESTION:\n"
                    + str(
                        question
                        or ""
                    )
                    + "\n\n"
                    + "PREVIOUS PLAN:\n"
                    + previous
                    + "\n\n"
                    + "PROBLEM:\n"
                    + str(
                        problem
                        or ""
                    )
                    + "\n\n"
                    + "Soruyu bastan yorumla ve "
                    + "yalnizca duzeltilmis "
                    + "plan_bansa_request tool call uret."
                ),
        }
    )

    return messages


class LocalAgentOrchestrator:

    def __init__(
        self,
        *,
        client=None,
        enabled=None,
    ):

        self.enabled = (
            _env_enabled()
            if enabled is None
            else bool(
                enabled
            )
        )

        self._client = client

    def plan(
        self,
        question,
        *,
        history=None,
    ) -> AgentPlan:

        if not self.enabled:

            return AgentPlan(
                status="disabled",
                decision=None,
                tool_name=None,
                reasons=(
                    "local_agent_disabled",
                ),
            )

        question = str(
            question
            or ""
        ).strip()

        if not question:

            return AgentPlan(
                status="fallback",
                decision=None,
                tool_name=None,
                reasons=(
                    "empty_question",
                ),
            )

        client = (
            self._client
            or LocalLLMClient()
        )

        messages = [
            {
                "role":
                    "system",

                "content":
                    _system_prompt(),
            }
        ]

        messages.extend(
            _safe_history(
                history
            )
        )

        messages.append(
            {
                "role":
                    "user",

                "content":
                    question,
            }
        )

        first_payload = None
        first_problem = None
        decision = None
        first_normalization_reasons = ()

        try:

            message = _call_planner(
                client,
                messages,
            )

            first_payload = (
                _extract_planner_payload(
                    message
                )
            )

            decision = (
                validate_agent_decision(
                    first_payload
                )
            )

            (
                decision,
                first_normalization_reasons,
            ) = _normalize_customer_scope(
                question,
                decision,
            )

            (
                decision,
                intent_normalization_reasons,
            ) = _normalize_open_product_intent(
                question,
                decision,
            )

            first_normalization_reasons = (
                first_normalization_reasons
                + intent_normalization_reasons
            )

            semantic_reasons = (
                _semantic_plan_reasons(
                    question,
                    decision,
                )
            )

            if semantic_reasons:

                first_problem = (
                    "semantic:"
                    + ",".join(
                        semantic_reasons
                    )
                )

            elif (
                decision.tool_name
                is None
            ):

                first_problem = (
                    "no_safe_tool_for_intent"
                )

        except Exception as exc:

            first_problem = (
                "validation:"
                + type(
                    exc
                ).__name__
                + ":"
                + str(
                    exc
                )
            )

        # ----------------------------------------------------
        # FAST PATH
        # ----------------------------------------------------

        if (
            decision is not None
            and
            not first_problem
        ):

            return AgentPlan(
                status="planned",
                decision=decision,
                tool_name=(
                    decision.tool_name
                ),
                reasons=(
                    "validated_local_agent_plan",
                )
                + first_normalization_reasons,
            )

        # ----------------------------------------------------
        # ONE STRICT LOCAL REPAIR
        #
        # This is a generic schema/semantic repair pass.
        # No bank-specific routing or answer generation occurs.
        # ----------------------------------------------------

        try:

            retry_message = _call_planner(
                client,
                _repair_messages(
                    question=question,
                    history=history,
                    first_payload=(
                        first_payload
                    ),
                    problem=(
                        first_problem
                    ),
                ),
            )

            retry_payload = (
                _extract_planner_payload(
                    retry_message
                )
            )

            retry_decision = (
                validate_agent_decision(
                    retry_payload
                )
            )

            (
                retry_decision,
                retry_normalization_reasons,
            ) = _normalize_customer_scope(
                question,
                retry_decision,
            )

            (
                retry_decision,
                retry_intent_normalization_reasons,
            ) = _normalize_open_product_intent(
                question,
                retry_decision,
            )

            retry_normalization_reasons = (
                retry_normalization_reasons
                + retry_intent_normalization_reasons
            )

            retry_semantic = (
                _semantic_plan_reasons(
                    question,
                    retry_decision,
                )
            )

            if retry_semantic:

                return AgentPlan(
                    status="fallback",
                    decision=None,
                    tool_name=None,
                    reasons=(
                        "planner_repair_semantic_failure:"
                        + ",".join(
                            retry_semantic
                        ),
                    ),
                )

            if (
                retry_decision.tool_name
                is None
            ):

                return AgentPlan(
                    status="fallback",
                    decision=retry_decision,
                    tool_name=None,
                    reasons=(
                        "no_safe_tool_for_intent",
                    ),
                )

            return AgentPlan(
                status="planned",
                decision=retry_decision,
                tool_name=(
                    retry_decision.tool_name
                ),
                reasons=(
                    "validated_local_agent_plan",
                    "planner_repair_used",
                    (
                        "first_problem:"
                        + str(
                            first_problem
                            or "unknown"
                        )
                    ),
                )
                + retry_normalization_reasons,
            )

        except Exception as exc:

            return AgentPlan(
                status="fallback",
                decision=None,
                tool_name=None,
                reasons=(
                    (
                        "planner_repair_error:"
                        + type(
                            exc
                        ).__name__
                    ),
                    (
                        "first_problem:"
                        + str(
                            first_problem
                            or "unknown"
                        )
                    ),
                ),
            )
