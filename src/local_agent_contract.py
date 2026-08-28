# BANSA_LOCAL_AGENT_CONTRACT_V1

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import unicodedata


ALLOWED_INTENTS = frozenset(
    {
        "campaign_search",
        "campaign_compare",
        "campaign_detail",
        "finance_fact",
        "finance_compare",
        "finance_calculate",
        "rag_search",
        "unknown",
    }
)


ALLOWED_CUSTOMER_SCOPES = frozenset(
    {
        "individual",
        "business",
        "all",
    }
)


ALLOWED_TIME_SCOPES = frozenset(
    {
        "current",
        "all",
    }
)


CANONICAL_BANKS = (
    "Adil Kat\u0131l\u0131m",
    "Albaraka T\u00fcrk",
    "D\u00fcnya Kat\u0131l\u0131m",
    "Hayat Finans",
    "Kuveyt T\u00fcrk",
    "T.O.M. Kat\u0131l\u0131m",
    "T\u00fcrkiye Emlak Kat\u0131l\u0131m",
    "T\u00fcrkiye Finans",
    "Vak\u0131f Kat\u0131l\u0131m",
    "Ziraat Kat\u0131l\u0131m",
)


INTENT_TOOL_MAP = {
    "campaign_search":
        "search_campaigns",

    "campaign_compare":
        "compare_campaigns",

    "campaign_detail":
        "get_campaign_detail",

    "finance_fact":
        "get_finance_fact",

    "finance_compare":
        "compare_finance",

    "finance_calculate":
        "calculate_finance",

    "rag_search":
        "rag_search",

    "unknown":
        None,
}


PLANNER_TOOL_NAME = (
    "plan_bansa_request"
)


class AgentDecisionError(
    ValueError
):
    pass


def _norm(
    value,
) -> str:

    text = unicodedata.normalize(
        "NFKD",
        str(
            value
            or ""
        ),
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(
            char
        )
    )

    return " ".join(
        text.casefold().split()
    )


_BANK_ALIASES = {
    _norm(bank):
        bank
    for bank in CANONICAL_BANKS
}


_BANK_ALIASES.update(
    {
        "albaraka":
            "Albaraka T\u00fcrk",

        "kuveyt":
            "Kuveyt T\u00fcrk",

        "kuveyt turk":
            "Kuveyt T\u00fcrk",

        "dunya":
            "D\u00fcnya Kat\u0131l\u0131m",

        "dunya katilim":
            "D\u00fcnya Kat\u0131l\u0131m",

        "turkiye finans":
            "T\u00fcrkiye Finans",

        "emlak katilim":
            "T\u00fcrkiye Emlak Kat\u0131l\u0131m",

        "turkiye emlak katilim":
            "T\u00fcrkiye Emlak Kat\u0131l\u0131m",

        "vakif katilim":
            "Vak\u0131f Kat\u0131l\u0131m",

        "ziraat katilim":
            "Ziraat Kat\u0131l\u0131m",

        "hayat finans":
            "Hayat Finans",

        "adil katilim":
            "Adil Kat\u0131l\u0131m",

        "tom":
            "T.O.M. Kat\u0131l\u0131m",

        "tom katilim":
            "T.O.M. Kat\u0131l\u0131m",

        "t.o.m. katilim":
            "T.O.M. Kat\u0131l\u0131m",
    }
)


def canonicalize_bank(
    value,
) -> str:

    normalized = _norm(
        value
    )

    result = _BANK_ALIASES.get(
        normalized
    )

    if result is None:
        raise AgentDecisionError(
            "unknown_bank:"
            + str(
                value
            )
        )

    return result


def _short_text(
    value,
    *,
    field_name,
    max_length=160,
):

    if value is None:
        return None

    text = " ".join(
        str(
            value
        ).split()
    ).strip()

    if not text:
        return None

    if len(text) > max_length:
        raise AgentDecisionError(
            field_name
            + "_too_long"
        )

    if any(
        control in text
        for control in (
            "\x00",
            "\r",
            "\n",
        )
    ):
        raise AgentDecisionError(
            field_name
            + "_invalid_control"
        )

    return text


def _decimal_or_none(
    value,
):

    if value in (
        None,
        "",
    ):
        return None

    try:
        result = Decimal(
            str(
                value
            ).replace(
                ",",
                ".",
            )
        )
    except (
        InvalidOperation,
        ValueError,
    ) as exc:
        raise AgentDecisionError(
            "invalid_amount"
        ) from exc

    if result <= 0:
        raise AgentDecisionError(
            "amount_must_be_positive"
        )

    if result > Decimal(
        "1000000000000"
    ):
        raise AgentDecisionError(
            "amount_too_large"
        )

    return result


def _maturity_or_none(
    value,
):

    if value in (
        None,
        "",
    ):
        return None

    try:
        result = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise AgentDecisionError(
            "invalid_maturity"
        ) from exc

    if (
        result < 1
        or
        result > 360
    ):
        raise AgentDecisionError(
            "maturity_out_of_range"
        )

    return result


@dataclass(
    frozen=True
)
class AgentDecision:

    intent: str

    banks: tuple[
        str,
        ...
    ]

    topic: str | None

    product: str | None

    amount: Decimal | None

    maturity_months: int | None

    customer_scope: str | None

    time_scope: str

    @property
    def tool_name(
        self,
    ) -> str | None:

        return INTENT_TOOL_MAP[
            self.intent
        ]


def validate_agent_decision(
    payload,
) -> AgentDecision:

    if not isinstance(
        payload,
        dict,
    ):
        raise AgentDecisionError(
            "decision_must_be_object"
        )

    intent = str(
        payload.get(
            "intent"
        )
        or "unknown"
    ).strip()

    if intent not in ALLOWED_INTENTS:
        raise AgentDecisionError(
            "unknown_intent:"
            + intent
        )

    raw_banks = (
        payload.get(
            "banks"
        )
        or []
    )

    if not isinstance(
        raw_banks,
        list,
    ):
        raise AgentDecisionError(
            "banks_must_be_list"
        )

    canonical_banks = []

    for bank in raw_banks:

        canonical = canonicalize_bank(
            bank
        )

        if canonical not in canonical_banks:
            canonical_banks.append(
                canonical
            )

    banks = tuple(
        canonical_banks
    )

    if intent in {
        "campaign_compare",
        "finance_compare",
    } and len(banks) < 2:
        raise AgentDecisionError(
            "compare_requires_two_banks"
        )

    if intent in {
        "campaign_detail",
        "finance_fact",
        "finance_calculate",
    } and not banks:
        raise AgentDecisionError(
            "intent_requires_bank"
        )

    topic = _short_text(
        payload.get(
            "topic"
        ),
        field_name="topic",
    )

    product = _short_text(
        payload.get(
            "product"
        ),
        field_name="product",
    )

    amount = _decimal_or_none(
        payload.get(
            "amount"
        )
    )

    maturity = _maturity_or_none(
        payload.get(
            "maturity_months"
        )
    )

    raw_customer_scope = (
        payload.get(
            "customer_scope"
        )
    )

    customer_scope = None

    if raw_customer_scope not in (
        None,
        "",
    ):

        customer_scope = str(
            raw_customer_scope
        ).strip()

        if (
            customer_scope
            not in ALLOWED_CUSTOMER_SCOPES
        ):
            raise AgentDecisionError(
                "invalid_customer_scope"
            )

    time_scope = str(
        payload.get(
            "time_scope"
        )
        or "current"
    ).strip()

    if (
        time_scope
        not in ALLOWED_TIME_SCOPES
    ):
        raise AgentDecisionError(
            "invalid_time_scope"
        )

    return AgentDecision(
        intent=intent,
        banks=banks,
        topic=topic,
        product=product,
        amount=amount,
        maturity_months=maturity,
        customer_scope=customer_scope,
        time_scope=time_scope,
    )


PLANNER_TOOL_SCHEMA = {
    "type":
        "function",

    "function": {
        "name":
            PLANNER_TOOL_NAME,

        "description":
            (
                "Kullanicinin bankacilik sorusunu "
                "BANSA'nin guvenli yapilandirilmis "
                "karar semasina donusturur. "
                "Cevap uretmez ve SQL yazmaz."
            ),

        "parameters": {
            "type":
                "object",

            "additionalProperties":
                False,

            "properties": {
                "intent": {
                    "type":
                        "string",

                    "enum":
                        sorted(
                            ALLOWED_INTENTS
                        ),
                },

                "banks": {
                    "type":
                        "array",

                    "items": {
                        "type":
                            "string",
                    },

                    "maxItems":
                        10,
                },

                "topic": {
                    "type": [
                        "string",
                        "null",
                    ],
                },

                "product": {
                    "type": [
                        "string",
                        "null",
                    ],
                },

                "amount": {
                    "type": [
                        "number",
                        "null",
                    ],
                },

                "maturity_months": {
                    "type": [
                        "integer",
                        "null",
                    ],
                },

                "customer_scope": {
                    "type": [
                        "string",
                        "null",
                    ],

                    "enum": [
                        "individual",
                        "business",
                        "all",
                        None,
                    ],
                },

                "time_scope": {
                    "type":
                        "string",

                    "enum":
                        sorted(
                            ALLOWED_TIME_SCOPES
                        ),
                },
            },

            "required": [
                "intent",
                "banks",
                "topic",
                "product",
                "amount",
                "maturity_months",
                "customer_scope",
                "time_scope",
            ],
        },
    },
}
