from src.local_agent_orchestrator import (
    LocalAgentOrchestrator,
)


class SequenceClient:

    def __init__(
        self,
        payloads,
    ):
        self.payloads = list(
            payloads
        )
        self.calls = 0

    def chat(
        self,
        *args,
        **kwargs,
    ):

        payload = (
            self.payloads[
                self.calls
            ]
        )

        self.calls += 1

        return {
            "role":
                "assistant",

            "content":
                "",

            "tool_calls": [
                {
                    "id":
                        "call_"
                        + str(
                            self.calls
                        ),

                    "type":
                        "function",

                    "function": {
                        "name":
                            "plan_bansa_request",

                        "arguments":
                            payload,
                    },
                }
            ],
        }


def test_invalid_bank_plan_is_repaired():

    client = SequenceClient(
        [
            (
                "{"
                '"intent":"finance_fact",'
                '"banks":["Albaraka Turk Bayide"],'
                '"topic":"finansman",'
                '"product":"finansman",'
                '"amount":null,'
                '"maturity_months":null,'
                '"customer_scope":null,'
                '"time_scope":"current"'
                "}"
            ),
            (
                "{"
                '"intent":"finance_fact",'
                '"banks":["Albaraka Turk"],'
                '"topic":"vade",'
                '"product":"Bayide Finansman",'
                '"amount":null,'
                '"maturity_months":null,'
                '"customer_scope":null,'
                '"time_scope":"current"'
                "}"
            ),
        ]
    )

    agent = LocalAgentOrchestrator(
        client=client,
        enabled=True,
    )

    result = agent.plan(
        (
            "Albaraka Turk Bayide Finansman "
            "en fazla kac ay vadeli?"
        )
    )

    assert result.status == "planned"

    assert (
        result.decision.banks
        ==
        (
            "Albaraka T\u00fcrk",
        )
    )

    assert (
        result.tool_name
        ==
        "get_finance_fact"
    )

    assert (
        "planner_repair_used"
        in result.reasons
    )

    assert client.calls == 2


def test_missing_second_bank_is_repaired():

    client = SequenceClient(
        [
            (
                "{"
                '"intent":"campaign_compare",'
                '"banks":["Albaraka Turk"],'
                '"topic":"Dunya Katilim konut finansmani",'
                '"product":"konut finansmani",'
                '"amount":200000,'
                '"maturity_months":36,'
                '"customer_scope":null,'
                '"time_scope":"current"'
                "}"
            ),
            (
                "{"
                '"intent":"finance_compare",'
                '"banks":["Albaraka Turk","Dunya Katilim"],'
                '"topic":"konut",'
                '"product":"konut finansmani",'
                '"amount":200000,'
                '"maturity_months":36,'
                '"customer_scope":null,'
                '"time_scope":"current"'
                "}"
            ),
        ]
    )

    result = LocalAgentOrchestrator(
        client=client,
        enabled=True,
    ).plan(
        (
            "Albaraka Turk ile Dunya Katilim "
            "konut finansmanini 200 bin TL ve "
            "36 ay icin karsilastir."
        )
    )

    assert result.status == "planned"

    assert (
        result.decision.intent
        ==
        "finance_compare"
    )

    assert len(
        result.decision.banks
    ) == 2

    assert client.calls == 2


def test_scaled_amount_mismatch_triggers_repair():

    client = SequenceClient(
        [
            (
                "{"
                '"intent":"finance_calculate",'
                '"banks":["Albaraka Turk"],'
                '"topic":"konut",'
                '"product":"finansman",'
                '"amount":200,'
                '"maturity_months":36,'
                '"customer_scope":null,'
                '"time_scope":"current"'
                "}"
            ),
            (
                "{"
                '"intent":"finance_calculate",'
                '"banks":["Albaraka Turk"],'
                '"topic":"konut",'
                '"product":"finansman",'
                '"amount":200000,'
                '"maturity_months":36,'
                '"customer_scope":null,'
                '"time_scope":"current"'
                "}"
            ),
        ]
    )

    result = LocalAgentOrchestrator(
        client=client,
        enabled=True,
    ).plan(
        (
            "Albaraka Turk Konut Finansmaninda "
            "200 bin TL'yi 36 ay icin hesapla."
        )
    )

    assert result.status == "planned"

    assert (
        str(
            result.decision.amount
        )
        ==
        "200000"
    )

    assert client.calls == 2


def test_campaign_rag_misroute_is_repaired():

    client = SequenceClient(
        [
            (
                "{"
                '"intent":"rag_search",'
                '"banks":["Kuveyt Turk"],'
                '"topic":"saglik kampanyalari",'
                '"product":null,'
                '"amount":null,'
                '"maturity_months":null,'
                '"customer_scope":null,'
                '"time_scope":"current"'
                "}"
            ),
            (
                "{"
                '"intent":"campaign_search",'
                '"banks":["Kuveyt Turk"],'
                '"topic":"saglik",'
                '"product":null,'
                '"amount":null,'
                '"maturity_months":null,'
                '"customer_scope":null,'
                '"time_scope":"current"'
                "}"
            ),
        ]
    )

    result = LocalAgentOrchestrator(
        client=client,
        enabled=True,
    ).plan(
        (
            "Kuveyt Turk'te su anda "
            "saglik kampanyalari neler?"
        )
    )

    assert result.status == "planned"

    assert (
        result.decision.intent
        ==
        "campaign_search"
    )

    assert client.calls == 2


def test_domain_unknown_gets_one_repair():

    client = SequenceClient(
        [
            (
                "{"
                '"intent":"unknown",'
                '"banks":["Kuveyt Turk"],'
                '"topic":"market campaign",'
                '"product":null,'
                '"amount":null,'
                '"maturity_months":null,'
                '"customer_scope":null,'
                '"time_scope":"current"'
                "}"
            ),
            (
                "{"
                '"intent":"campaign_detail",'
                '"banks":["Kuveyt Turk"],'
                '"topic":"market",'
                '"product":null,'
                '"amount":null,'
                '"maturity_months":null,'
                '"customer_scope":null,'
                '"time_scope":"current"'
                "}"
            ),
        ]
    )

    result = LocalAgentOrchestrator(
        client=client,
        enabled=True,
    ).plan(
        (
            "Kuveyt Turk'un market kampanyasina "
            "nasil katiliyorum ve hangi kartlar gecerli?"
        )
    )

    assert result.status == "planned"

    assert (
        result.decision.intent
        ==
        "campaign_detail"
    )

    assert (
        result.tool_name
        ==
        "get_campaign_detail"
    )

    assert client.calls == 2


def test_open_product_unicode_terms_route_to_rag():

    from src.local_agent_contract import (
        validate_agent_decision,
    )

    from src.local_agent_orchestrator import (
        _normalize_open_product_intent,
    )

    def make_decision():

        return validate_agent_decision(
            {
                "intent":
                    "finance_fact",

                "banks": [
                    "Albaraka T\u00fcrk",
                ],

                "topic":
                    "Konut Finansman\u0131",

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

    questions = (
        (
            "Albaraka T\u00fcrk Konut "
            "Finansman\u0131n\u0131n avantajlar\u0131 neler?"
        ),
        (
            "Konut Finansman\u0131n\u0131n "
            "\u00f6zellikleri neler?"
        ),
        (
            "Konut Finansman\u0131n\u0131n "
            "ko\u015fullar\u0131 neler?"
        ),
        (
            "Konut Finansman\u0131n\u0131n "
            "\u00f6ne \u00e7\u0131kan y\u00f6nleri neler?"
        ),
        (
            "Konut Finansman\u0131n\u0131n "
            "detaylar\u0131 nelerdir?"
        ),
    )

    for question in questions:

        decision, reasons = (
            _normalize_open_product_intent(
                question,
                make_decision(),
            )
        )

        assert (
            decision.intent
            ==
            "rag_search"
        ), question

        assert (
            reasons
            ==
            (
                "open_ended_product_question_routed_to_rag",
            )
        ), question


def test_open_product_normalizer_keeps_structured_finance_facts():

    from src.local_agent_contract import (
        validate_agent_decision,
    )

    from src.local_agent_orchestrator import (
        _normalize_open_product_intent,
    )

    def make_decision():

        return validate_agent_decision(
            {
                "intent":
                    "finance_fact",

                "banks": [
                    "Albaraka T\u00fcrk",
                ],

                "topic":
                    "Konut Finansman\u0131",

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

    questions = (
        (
            "Albaraka T\u00fcrk Konut Finansman\u0131nda "
            "k\u00e2r pay\u0131 ne?"
        ),
        (
            "Albaraka T\u00fcrk Konut Finansman\u0131 "
            "ka\u00e7 aya kadar?"
        ),
        "Tahsis \u00fccreti ne kadar?",
        "Ekspertiz \u00fccreti nedir?",
        "Finansman limiti ne kadar?",
        "Finansman oran\u0131 nedir?",
    )

    for question in questions:

        decision, reasons = (
            _normalize_open_product_intent(
                question,
                make_decision(),
            )
        )

        assert (
            decision.intent
            ==
            "finance_fact"
        ), question

        assert reasons == (), question

