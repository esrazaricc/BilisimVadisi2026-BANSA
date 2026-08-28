from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.local_agent_contract import (
    validate_agent_decision,
)

from src.local_agent_tools import (
    execute_agent_decision,
)


@dataclass(
    frozen=True
)
class FakeCampaignResult:

    candidate_count: int

    amount: Decimal | None


@dataclass(
    frozen=True
)
class FakeFinanceResult:

    status: str

    value: Decimal

    text: str = "verified finance fact"


def _campaign_compare_decision():

    return validate_agent_decision(
        {
            "intent":
                "campaign_compare",

            "banks": [
                "Kuveyt Turk",
                "Turkiye Finans",
            ],

            "topic":
                "saglik",

            "product":
                None,

            "amount":
                5000,

            "maturity_months":
                None,

            "customer_scope":
                "all",

            "time_scope":
                "current",
        }
    )


def test_campaign_compare_uses_verified_engine():

    calls = {}

    def fake_resolver(
        question,
    ):

        calls[
            "resolver_question"
        ] = question

        return "shopping_benefit"

    def fake_compare(
        universe,
        *,
        bank_names,
        spend_amount,
        question,
        as_of,
        db_path,
    ):

        calls[
            "universe"
        ] = universe

        calls[
            "banks"
        ] = bank_names

        calls[
            "amount"
        ] = spend_amount

        calls[
            "question"
        ] = question

        return FakeCampaignResult(
            candidate_count=2,
            amount=spend_amount,
        )

    result = execute_agent_decision(
        _campaign_compare_decision(),
        question=(
            "Kuveyt Turk ile Turkiye Finans "
            "market kampanyalarini karsilastir."
        ),
        campaign_universe_fn=fake_compare,
        universe_resolver_fn=fake_resolver,
    )

    assert result.status == "ok"

    assert (
        result.tool_name
        ==
        "compare_campaigns"
    )

    assert (
        calls["universe"]
        ==
        "shopping_benefit"
    )

    assert (
        calls["banks"]
        ==
        (
            "Kuveyt T\u00fcrk",
            "T\u00fcrkiye Finans",
        )
    )

    assert (
        calls["amount"]
        ==
        Decimal(
            "5000"
        )
    )

    assert (
        result.data[
            "result"
        ][
            "amount"
        ]
        ==
        "5000"
    )


def test_campaign_search_forces_all_active():

    calls = {}

    decision = validate_agent_decision(
        {
            "intent":
                "campaign_search",

            "banks": [
                "Kuveyt Turk",
            ],

            "topic":
                "saglik",

            "product":
                None,

            "amount":
                None,

            "maturity_months":
                None,

            "customer_scope":
                None,

            "time_scope":
                "current",
        }
    )

    def fake_compare(
        universe,
        *,
        bank_names,
        spend_amount,
        question,
        as_of,
        db_path,
    ):

        calls[
            "universe"
        ] = universe

        calls[
            "banks"
        ] = bank_names

        calls[
            "question"
        ] = question

        return FakeCampaignResult(
            candidate_count=3,
            amount=None,
        )

    result = execute_agent_decision(
        decision,
        question=(
            "Kuveyt Turk saglik kampanyalari"
        ),
        campaign_universe_fn=fake_compare,
    )

    assert result.status == "ok"

    assert (
        calls["universe"]
        ==
        "all_active"
    )

    assert (
        calls["banks"]
        ==
        (
            "Kuveyt T\u00fcrk",
        )
    )


def test_finance_fact_uses_existing_lookup():

    calls = {}

    decision = validate_agent_decision(
        {
            "intent":
                "finance_fact",

            "banks": [
                "Albaraka"
            ],

            "topic":
                "tahsis ucreti",

            "product":
                "Konut Finansmani",

            "amount":
                None,

            "maturity_months":
                None,

            "customer_scope":
                "individual",

            "time_scope":
                "current",
        }
    )

    def fake_lookup(
        *,
        question,
        attribute,
    ):

        calls[
            "question"
        ] = question

        calls[
            "attribute"
        ] = attribute

        return FakeFinanceResult(
            status="FOUND",
            value=Decimal(
                "0.50"
            ),
        )

    result = execute_agent_decision(
        decision,
        question=(
            "Albaraka Turk Konut Finansmani "
            "tahsis ucreti nedir?"
        ),
        finance_fact_lookup_fn=fake_lookup,
    )

    assert result.status == "ok"

    assert (
        calls["attribute"]
        ==
        "allocation_fee"
    )


    assert (
        result.data[
            "result"
        ][
            "value"
        ]
        ==
        "0.50"
    )


def test_unknown_intent_has_no_safe_tool():

    decision = validate_agent_decision(
        {
            "intent":
                "unknown",

            "banks":
                [],

            "topic":
                None,

            "product":
                None,

            "amount":
                None,

            "maturity_months":
                None,

            "customer_scope":
                None,

            "time_scope":
                "current",
        }
    )

    result = execute_agent_decision(
        decision,
        question="test",
    )

    assert (
        result.status
        ==
        "fallback"
    )

    assert (
        result.reasons
        ==
        (
            "decision_has_no_safe_tool",
        )
    )

def test_invalid_decision_fails_closed():

    result = execute_agent_decision(
        object(),
        question="test",
    )

    assert (
        result.status
        ==
        "fallback"
    )

    assert (
        result.reasons
        ==
        (
            "invalid_agent_decision",
        )
    )


def test_canonical_question_is_built_when_missing():

    calls = {}

    def fake_resolver(
        question,
    ):

        calls[
            "question"
        ] = question

        return "shopping_benefit"

    def fake_compare(
        universe,
        *,
        bank_names,
        spend_amount,
        question,
        as_of,
        db_path,
    ):

        return FakeCampaignResult(
            candidate_count=1,
            amount=spend_amount,
        )

    result = execute_agent_decision(
        _campaign_compare_decision(),
        question=None,
        campaign_universe_fn=fake_compare,
        universe_resolver_fn=fake_resolver,
    )

    assert result.status == "ok"

    assert (
        "Kuveyt T\u00fcrk"
        in calls[
            "question"
        ]
    )

    assert (
        "T\u00fcrkiye Finans"
        in calls[
            "question"
        ]
    )

    assert (
        "saglik"
        in calls[
            "question"
        ]
    )

    assert (
        "5000 TL"
        in calls[
            "question"
        ]
    )

    assert (
        "karsilastir"
        in calls[
            "question"
        ]
    )


def test_date_is_json_safe():

    @dataclass(
        frozen=True
    )
    class DateResult:

        checked_at: date

    decision = validate_agent_decision(
        {
            "intent":
                "campaign_search",

            "banks":
                [],

            "topic":
                "market",

            "product":
                None,

            "amount":
                None,

            "maturity_months":
                None,

            "customer_scope":
                None,

            "time_scope":
                "current",
        }
    )

    def fake_compare(
        universe,
        *,
        bank_names,
        spend_amount,
        question,
        as_of,
        db_path,
    ):

        return DateResult(
            checked_at=date(
                2026,
                8,
                24,
            )
        )

    result = execute_agent_decision(
        decision,
        question=(
            "market kampanyalari"
        ),
        campaign_universe_fn=fake_compare,
    )

    assert (
        result.data[
            "result"
        ][
            "checked_at"
        ]
        ==
        "2026-08-24"
    )



def test_market_compare_uses_canonical_market_runtime(
    monkeypatch,
):

    decision = validate_agent_decision(
        {
            "intent":
                "campaign_compare",

            "banks": [
                "Kuveyt Turk",
                "Turkiye Finans",
            ],

            "topic":
                "market",

            "product":
                None,

            "amount":
                5000,

            "maturity_months":
                None,

            "customer_scope":
                None,

            "time_scope":
                "current",
        }
    )

    calls = {}

    def fake_market_answer(
        question,
        db_path=None,
        today=None,
    ):

        calls["question"] = question
        calls["db_path"] = db_path
        calls["today"] = today

        return {
            "status":
                "FOUND",

            "route":
                "campaign_compare",

            "banks": (
                "Kuveyt T\u00fcrk",
                "T\u00fcrkiye Finans",
            ),

            "campaigns": {
                "Kuveyt T\u00fcrk": (
                    {
                        "id":
                            91,

                        "campaign_category":
                            "card_campaign",

                        "title":
                            "Market kampanyasi",
                    },
                ),

                "T\u00fcrkiye Finans":
                    (),
            },

            "text":
                "verified market result",
        }

    monkeypatch.setattr(
        (
            "src.chatbot_market_campaign_runtime."
            "answer_market_question"
        ),
        fake_market_answer,
    )

    def forbidden_generic_compare(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "generic campaign universe "
            "must not run for canonical market topic"
        )

    result = execute_agent_decision(
        decision,
        question=(
            "Kuveyt Turk ile Turkiye Finans "
            "market kampanyalarini karsilastir"
        ),
        campaign_universe_fn=(
            forbidden_generic_compare
        ),
    )

    assert result.status == "ok"

    assert (
        result.tool_name
        ==
        "compare_campaigns"
    )

    assert (
        result.data[
            "universe"
        ]
        ==
        "canonical_market"
    )

    assert (
        result.data[
            "result"
        ][
            "campaigns"
        ][
            "Kuveyt T\u00fcrk"
        ][0][
            "campaign_category"
        ]
        ==
        "card_campaign"
    )

    assert (
        result.reasons
        ==
        (
            "verified_canonical_market_runtime",
        )
    )


def test_market_campaign_detail_uses_canonical_runtime():

    decision = validate_agent_decision(
        {
            "intent":
                "campaign_detail",

            "banks": [
                "Kuveyt T\u00fcrk",
            ],

            "topic":
                "market",

            "product":
                None,

            "amount":
                None,

            "maturity_months":
                None,

            "customer_scope":
                None,

            "time_scope":
                "current",
        }
    )

    seen = {}

    def fake_detail(
        question,
        *,
        db_path=None,
        today=None,
    ):

        seen["question"] = question
        seen["db_path"] = db_path
        seen["today"] = today

        return {
            "route":
                "campaign_rag",

            "status":
                "FOUND",

            "banks":
                [
                    "Kuveyt T\u00fcrk",
                ],

            "campaigns":
                {
                    "Kuveyt T\u00fcrk":
                        [
                            {
                                "campaign_id":
                                    91,

                                "title":
                                    "Market kampanyas\u0131",
                            }
                        ]
                },

            "text":
                "Aktif market kampanyas\u0131 bulundu.",
        }

    question = (
        "Kuveyt T\u00fcrk'\u00fcn market "
        "kampanyas\u0131n\u0131n detaylar\u0131 neler?"
    )

    result = execute_agent_decision(
        decision,
        question=question,
        campaign_detail_fn=(
            fake_detail
        ),
    )

    assert result.status == "ok"

    assert (
        result.tool_name
        ==
        "get_campaign_detail"
    )

    assert seen["question"] == question

    assert (
        result.data[
            "universe"
        ]
        ==
        "canonical_market"
    )

    assert (
        result.data[
            "result"
        ][
            "status"
        ]
        ==
        "FOUND"
    )

    assert (
        result.data[
            "result"
        ][
            "banks"
        ]
        ==
        [
            "Kuveyt T\u00fcrk",
        ]
    )


def test_non_market_campaign_detail_fails_closed():

    decision = validate_agent_decision(
        {
            "intent":
                "campaign_detail",

            "banks": [
                "Kuveyt T\u00fcrk",
            ],

            "topic":
                "sa\u011fl\u0131k",

            "product":
                None,

            "amount":
                None,

            "maturity_months":
                None,

            "customer_scope":
                None,

            "time_scope":
                "current",
        }
    )

    result = execute_agent_decision(
        decision,
        question=(
            "Kuveyt T\u00fcrk sa\u011fl\u0131k "
            "kampanyas\u0131n\u0131n detaylar\u0131 neler?"
        ),
    )

    assert result.status == "fallback"

    assert (
        result.reasons
        ==
        (
            "campaign_detail_topic_not_wired",
        )
    )


def test_rag_search_uses_existing_product_rag_grounding():

    from types import SimpleNamespace

    from src.chatbot_answer_contract import (
        GroundedEvidence,
    )

    decision = validate_agent_decision(
        {
            "intent":
                "rag_search",

            "banks": [
                "Albaraka T\u00fcrk",
            ],

            "topic":
                "avantajlar",

            "product":
                "Konut Finansman\u0131",

            "amount":
                None,

            "maturity_months":
                None,

            "customer_scope":
                None,

            "time_scope":
                "current",
        }
    )

    seen = {}

    def fake_execution(
        question,
        *,
        route_decision=None,
    ):

        seen[
            "question"
        ] = question

        seen[
            "route_decision"
        ] = route_decision

        return SimpleNamespace(
            question=question,
            route="product_rag",
            status="completed",
            route_decision=(
                route_decision
            ),
        )

    evidence = GroundedEvidence(
        evidence_id="E1",
        source_kind="standard_product",
        bank_name="Albaraka T\u00fcrk",
        document_title="Konut Finansman\u0131",
        section_type="advantages",
        text="Konut finansman\u0131 avantaj bilgisi.",
        source_url=(
            "https://example.invalid/"
            "konut-finansmani"
        ),
        checked_at="2026-08-24T00:00:00+00:00",
        structured_fields={},
    )

    def fake_grounding(
        execution,
    ):

        return SimpleNamespace(
            route="product_rag",
            answer_mode="rag",
            may_generate_answer=True,
            evidence=(
                evidence,
            ),
            reasons=(
                "verified_test_evidence",
            ),
        )

    question = (
        "Albaraka T\u00fcrk Konut "
        "Finansman\u0131n\u0131n avantajlar\u0131 neler?"
    )

    result = execute_agent_decision(
        decision,
        question=question,
        rag_execution_fn=(
            fake_execution
        ),
        grounded_context_fn=(
            fake_grounding
        ),
    )

    assert result.status == "ok"

    assert (
        result.tool_name
        ==
        "rag_search"
    )

    route_decision = (
        seen[
            "route_decision"
        ]
    )

    assert (
        route_decision.route
        ==
        "product_rag"
    )

    assert (
        route_decision.family
        ==
        "konut_finansmani"
    )

    assert (
        route_decision.bank_names
        ==
        (
            "Albaraka T\u00fcrk",
        )
    )

    assert (
        result.data[
            "source_kind"
        ]
        ==
        "standard_product"
    )

    assert (
        result.data[
            "evidence_count"
        ]
        ==
        1
    )

    assert (
        result.data[
            "evidence"
        ][0][
            "bank_name"
        ]
        ==
        "Albaraka T\u00fcrk"
    )

    assert (
        result.data[
            "evidence"
        ][0][
            "source_url"
        ]
    )


def test_rag_search_abstention_fails_closed():

    from types import SimpleNamespace

    decision = validate_agent_decision(
        {
            "intent":
                "rag_search",

            "banks": [
                "Albaraka T\u00fcrk",
            ],

            "topic":
                "bilinmeyen bilgi",

            "product":
                "Konut Finansman\u0131",

            "amount":
                None,

            "maturity_months":
                None,

            "customer_scope":
                None,

            "time_scope":
                "current",
        }
    )

    def fake_execution(
        question,
        *,
        route_decision=None,
    ):

        return SimpleNamespace(
            question=question,
            route="product_rag",
            status="abstain",
            route_decision=(
                route_decision
            ),
        )

    def fake_grounding(
        execution,
    ):

        return SimpleNamespace(
            route="product_rag",
            answer_mode="abstain",
            may_generate_answer=False,
            evidence=tuple(),
            reasons=(
                "answer_generation_blocked",
            ),
        )

    result = execute_agent_decision(
        decision,
        question=(
            "Albaraka T\u00fcrk Konut "
            "Finansman\u0131 hakk\u0131nda "
            "kaynakta olmayan bir \u015fey s\u00f6yle."
        ),
        rag_execution_fn=(
            fake_execution
        ),
        grounded_context_fn=(
            fake_grounding
        ),
    )

    assert result.status == "fallback"

    assert (
        result.reasons
        ==
        (
            "rag_grounding_blocked",
        )
    )

