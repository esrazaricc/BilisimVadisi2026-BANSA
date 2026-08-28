from src.campaign_compare import (
    _normalize,
)

from src.chat_followup_context import (
    resolve_followup_question,
)

from src.chatbot_router import (
    route_question,
)

from src.chatbot_response_service import (
    ask_bansa,
)


def _resolve(
    current,
    previous,
):

    return resolve_followup_question(
        current,
        list(
            previous
        ),
    )


def test_campaign_bank_narrowing_preserves_context():

    result = _resolve(
        (
            "Peki sadece Albaraka ile "
            "Kuveyt Turk?"
        ),
        (
            "Egitim kampanyalarini karsilastir",
        ),
    )

    assert (
        result.used_context
        is True
    )

    normalized = _normalize(
        result.resolved_question
    )

    assert (
        "egitim kampanyalarini karsilastir"
        in normalized
    )

    assert (
        "albaraka"
        in normalized
    )

    assert (
        "kuveyt turk"
        in normalized
    )

    decision = route_question(
        result.resolved_question
    )

    assert (
        decision.route
        == "campaign_compare"
    )

    assert {
        _normalize(
            value
        )
        for value
        in decision.bank_names
    } == {
        "albaraka turk",
        "kuveyt turk",
    }


def test_campaign_business_scope_preserves_topic():

    result = _resolve(
        "Peki ticari olanlar?",
        (
            "Egitim kampanyalarini karsilastir",
        ),
    )

    assert (
        result.used_context
        is True
    )

    normalized = _normalize(
        result.resolved_question
    )

    assert (
        "egitim"
        in normalized
    )

    assert (
        "ticari"
        in normalized
    )

    decision = route_question(
        result.resolved_question
    )

    assert (
        decision.route
        == "campaign_compare"
    )


def test_market_bank_followup_preserves_amount_and_topic():

    result = _resolve(
        "Peki sadece Emlak Katilim?",
        (
            (
                "5.000 TL market "
                "kampanyalarini karsilastir"
            ),
        ),
    )

    assert (
        result.used_context
        is True
    )

    normalized = _normalize(
        result.resolved_question
    )

    assert (
        "market"
        in normalized
    )

    decision = route_question(
        result.resolved_question
    )

    assert (
        decision.route
        == "campaign_compare"
    )

    assert (
        str(
            decision.amount
        )
        == "5000"
    )

    assert {
        _normalize(
            value
        )
        for value
        in decision.bank_names
    } == {
        "turkiye emlak katilim",
    }


def test_campaign_followup_does_not_inherit_as_finance_product():

    result = _resolve(
        (
            "Peki sadece Albaraka ile "
            "Kuveyt Turk?"
        ),
        (
            "Egitim kampanyalarini karsilastir",
        ),
    )

    assert (
        result.inherited_product
        is None
    )

    assert (
        "egitim finansmani"
        not in _normalize(
            result.resolved_question
        )
    )


def test_finance_numeric_completion_is_preserved():

    result = _resolve(
        "150.000 TL, 36 ay",
        (
            "Konut finansmanlarini karsilastir",
        ),
    )

    assert (
        result.used_context
        is True
    )

    decision = route_question(
        result.resolved_question
    )

    assert (
        decision.route
        == "finance_compare"
    )

    assert (
        str(
            decision.amount
        )
        == "150000"
    )

    assert (
        decision.maturity
        == 36
    )


def test_finance_to_campaign_boundary_is_preserved():

    result = _resolve(
        (
            "Emlak Katilim kampanyalari "
            "neler?"
        ),
        (
            (
                "100.000 TL 36 ay konut "
                "finansmanlarini karsilastir"
            ),
        ),
    )

    assert (
        result.used_context
        is False
    )

    decision = route_question(
        result.resolved_question
    )

    assert (
        decision.route
        == "campaign_rag"
    )


def test_explicit_new_campaign_topic_does_not_inherit_old_topic():

    result = _resolve(
        (
            "Peki akaryakit "
            "kampanyalarini karsilastir?"
        ),
        (
            "Egitim kampanyalarini karsilastir",
        ),
    )

    assert (
        result.used_context
        is False
    )

    normalized = _normalize(
        result.resolved_question
    )

    assert (
        "egitim"
        not in normalized
    )

    assert (
        "akaryakit"
        in normalized
    )


def test_real_campaign_bank_followup_e2e():

    resolution = _resolve(
        (
            "Peki sadece Albaraka ile "
            "Kuveyt Turk?"
        ),
        (
            "Egitim kampanyalarini karsilastir",
        ),
    )

    response = ask_bansa(
        resolution.resolved_question
    )

    normalized = _normalize(
        response.text
    )

    assert (
        response.route
        == "campaign_compare"
    )

    assert (
        response.backend
        == "deterministic_campaign_compare"
    )

    assert (
        response.qwen_used
        is False
    )

    assert (
        "6 taksit"
        in normalized
        or
        "taksit 6"
        in normalized
    )

    assert (
        "tom katilim"
        not in normalized
    )

    assert (
        "turkiye finans"
        not in normalized
    )

    assert (
        "ziraat katilim"
        not in normalized
    )


def test_real_campaign_business_followup_e2e():

    resolution = _resolve(
        "Peki ticari olanlar?",
        (
            "Egitim kampanyalarini karsilastir",
        ),
    )

    response = ask_bansa(
        resolution.resolved_question
    )

    normalized = _normalize(
        response.text
    )

    assert (
        response.route
        == "campaign_compare"
    )

    assert (
        response.backend
        == "deterministic_campaign_compare"
    )

    assert (
        response.qwen_used
        is False
    )

    assert (
        "taksitli pos kampanyasi"
        in normalized
    )

    assert (
        "taksit 12"
        in normalized
    )


def test_real_market_bank_followup_e2e():

    resolution = _resolve(
        "Peki sadece Emlak Katilim?",
        (
            (
                "5.000 TL market "
                "kampanyalarini karsilastir"
            ),
        ),
    )

    response = ask_bansa(
        resolution.resolved_question
    )

    normalized = _normalize(
        response.text
    )

    assert (
        response.route
        == "campaign_compare"
    )

    assert (
        response.backend
        == "deterministic_campaign_compare"
    )

    assert (
        response.qwen_used
        is False
    )

    assert (
        "turkiye emlak katilim"
        in normalized
    )

    assert (
        "market"
        in normalized
    )
