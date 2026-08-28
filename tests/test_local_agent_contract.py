from decimal import Decimal

from src.local_agent_contract import (
    AgentDecisionError,
    canonicalize_bank,
    validate_agent_decision,
)

from src.local_agent_orchestrator import (
    LocalAgentOrchestrator,
)


class FakePlannerClient:

    def __init__(
        self,
        arguments,
        *,
        tool_name="plan_bansa_request",
    ):
        self.arguments = arguments
        self.tool_name = tool_name
        self.called = False

    def chat(
        self,
        messages,
        **kwargs,
    ):

        self.called = True

        return {
            "role":
                "assistant",

            "content":
                None,

            "tool_calls": [
                {
                    "id":
                        "call_1",

                    "type":
                        "function",

                    "function": {
                        "name":
                            self.tool_name,

                        "arguments":
                            self.arguments,
                    },
                }
            ],
        }


def _valid_market_compare_json():

    return (
        "{"
        '"intent":"campaign_compare",'
        '"banks":["Kuveyt Turk","Turkiye Finans"],'
        '"topic":"market",'
        '"product":null,'
        '"amount":5000,'
        '"maturity_months":null,'
        '"customer_scope":null,'
        '"time_scope":"current"'
        "}"
    )


def test_bank_aliases_are_canonicalized():

    assert (
        canonicalize_bank(
            "Kuveyt Turk"
        )
        ==
        "Kuveyt T\u00fcrk"
    )

    assert (
        canonicalize_bank(
            "Albaraka"
        )
        ==
        "Albaraka T\u00fcrk"
    )


def test_valid_decision_is_typed():

    decision = (
        validate_agent_decision(
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
                    "all",

                "time_scope":
                    "current",
            }
        )
    )

    assert (
        decision.banks
        ==
        (
            "Kuveyt T\u00fcrk",
            "T\u00fcrkiye Finans",
        )
    )

    assert (
        decision.amount
        ==
        Decimal(
            "5000"
        )
    )

    assert (
        decision.tool_name
        ==
        "compare_campaigns"
    )


def test_compare_requires_two_banks():

    try:
        validate_agent_decision(
            {
                "intent":
                    "campaign_compare",

                "banks": [
                    "Kuveyt Turk"
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
    except AgentDecisionError as exc:
        assert (
            "compare_requires_two_banks"
            in str(
                exc
            )
        )
    else:
        raise AssertionError(
            "single-bank comparison accepted"
        )


def test_negative_amount_fails_closed():

    try:
        validate_agent_decision(
            {
                "intent":
                    "finance_fact",

                "banks": [
                    "Albaraka"
                ],

                "topic":
                    "konut",

                "product":
                    "Konut Finansmani",

                "amount":
                    -1,

                "maturity_months":
                    36,

                "customer_scope":
                    "individual",

                "time_scope":
                    "current",
            }
        )
    except AgentDecisionError as exc:
        assert (
            "amount_must_be_positive"
            in str(
                exc
            )
        )
    else:
        raise AssertionError(
            "negative amount accepted"
        )


def test_disabled_agent_never_calls_model():

    fake = FakePlannerClient(
        _valid_market_compare_json()
    )

    agent = LocalAgentOrchestrator(
        client=fake,
        enabled=False,
    )

    result = agent.plan(
        "test"
    )

    assert (
        result.status
        ==
        "disabled"
    )

    assert (
        fake.called
        is False
    )


def test_valid_local_plan_maps_to_safe_tool():

    fake = FakePlannerClient(
        _valid_market_compare_json()
    )

    agent = LocalAgentOrchestrator(
        client=fake,
        enabled=True,
    )

    result = agent.plan(
        (
            "Kuveyt Turk ile Turkiye Finans "
            "market kampanyalarini karsilastir."
        )
    )

    assert (
        result.status
        ==
        "planned"
    )

    assert (
        result.tool_name
        ==
        "compare_campaigns"
    )

    assert (
        result.decision.topic
        ==
        "market"
    )


def test_arbitrary_tool_name_fails_closed():

    fake = FakePlannerClient(
        _valid_market_compare_json(),
        tool_name="drop_database",
    )

    agent = LocalAgentOrchestrator(
        client=fake,
        enabled=True,
    )

    result = agent.plan(
        "test"
    )

    assert (
        result.status
        ==
        "fallback"
    )

    assert (
        result.tool_name
        is None
    )
