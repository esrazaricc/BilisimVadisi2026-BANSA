from datetime import date

from src.campaign_compare import (
    _topic_terms,
)

from src.campaign_comparison_universe import (
    compare_campaign_universe,
)

from src.chat_followup_context import (
    resolve_followup_question,
)

from src.chatbot_campaign_compare import (
    run_campaign_compare,
)

from src.chatbot_router import (
    route_question,
)


BANKS = (
    "Albaraka T\u00fcrk",
    "Kuveyt T\u00fcrk",
)


DIRECT = (
    "Albaraka Turk ve Kuveyt Turk "
    "egitim kampanyalarini karsilastir"
)


RESOLVED = (
    "Egitim kampanyalarini karsilastir "
    "- Peki sadece Albaraka ile Kuveyt Turk?"
)


def test_followup_discourse_words_are_not_topic_terms():

    direct_terms = _topic_terms(
        DIRECT,
        bank_names=BANKS,
    )

    resolved_terms = _topic_terms(
        RESOLVED,
        bank_names=BANKS,
    )

    assert (
        direct_terms
        == (
            "egitim",
        )
    )

    assert (
        resolved_terms
        == (
            "egitim",
        )
    )


def test_direct_and_equivalent_followup_have_same_candidates():

    direct = compare_campaign_universe(
        "card_installment",
        bank_names=BANKS,
        question=DIRECT,
        as_of=date(
            2026,
            8,
            24,
        ),
    )

    resolved = compare_campaign_universe(
        "card_installment",
        bank_names=BANKS,
        question=RESOLVED,
        as_of=date(
            2026,
            8,
            24,
        ),
    )

    direct_ids = tuple(
        item.campaign_id
        for item
        in direct.candidates
    )

    resolved_ids = tuple(
        item.campaign_id
        for item
        in resolved.candidates
    )

    assert (
        direct_ids
        == (
            18,
            26,
            142,
            143,
        )
    )

    assert (
        resolved_ids
        == direct_ids
    )


def test_non_education_installment_campaigns_do_not_leak():

    result = compare_campaign_universe(
        "card_installment",
        bank_names=BANKS,
        question=RESOLVED,
        as_of=date(
            2026,
            8,
            24,
        ),
    )

    ids = {
        item.campaign_id
        for item
        in result.candidates
    }

    assert not (
        ids
        & {
            92,
            146,
            156,
            160,
            161,
        }
    )


def test_followup_safe_installment_winner_returns_to_albaraka():

    result = compare_campaign_universe(
        "card_installment",
        bank_names=BANKS,
        question=RESOLVED,
        as_of=date(
            2026,
            8,
            24,
        ),
    )

    installment = next(
        item
        for item
        in result.criterion_winners
        if item.criterion
        == "installment_count"
    )

    assert (
        int(
            installment.value
        )
        == 6
    )

    assert (
        installment.campaign_ids
        == (
            18,
        )
    )


def test_real_bank_narrowing_followup_preserves_education_topic():

    resolution = (
        resolve_followup_question(
            (
                "Peki sadece Albaraka ile "
                "Kuveyt Turk?"
            ),
            [
                (
                    "Egitim kampanyalarini "
                    "karsilastir"
                ),
            ],
        )
    )

    assert (
        resolution.used_context
        is True
    )

    decision = route_question(
        resolution.resolved_question
    )

    assert (
        decision.route
        == "campaign_compare"
    )

    result = run_campaign_compare(
        resolution.resolved_question,
        route_decision=decision,
    )

    assert (
        result.comparison
        is not None
    )

    assert tuple(
        item.campaign_id
        for item
        in result.comparison.candidates
    ) == (
        18,
        26,
        142,
        143,
    )


def test_business_followup_still_preserves_education_topic():

    resolution = (
        resolve_followup_question(
            "Peki ticari olanlar?",
            [
                (
                    "Egitim kampanyalarini "
                    "karsilastir"
                ),
            ],
        )
    )

    assert (
        resolution.used_context
        is True
    )

    decision = route_question(
        resolution.resolved_question
    )

    assert (
        decision.route
        == "campaign_compare"
    )

    result = run_campaign_compare(
        resolution.resolved_question,
        route_decision=decision,
    )

    assert (
        result.comparison
        is not None
    )

    assert tuple(
        item.campaign_id
        for item
        in result.comparison.candidates
    ) == (
        115,
    )


def test_market_bank_followup_is_preserved():

    resolution = (
        resolve_followup_question(
            "Peki sadece Emlak Katilim?",
            [
                (
                    "5.000 TL market "
                    "kampanyalarini karsilastir"
                ),
            ],
        )
    )

    assert (
        resolution.used_context
        is True
    )

    decision = route_question(
        resolution.resolved_question
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

    result = run_campaign_compare(
        resolution.resolved_question,
        route_decision=decision,
    )

    assert (
        result.comparison
        is not None
    )

    ids = tuple(
        item.campaign_id
        for item
        in result.comparison.candidates
    )

    assert (
        ids
        == (
            502,
            503,
        )
    )


def test_finance_compare_route_is_untouched():

    decision = route_question(
        (
            "100.000 TL 36 ay konut "
            "finansmaninda hangi banka "
            "daha avantajli?"
        )
    )

    assert (
        decision.route
        == "finance_compare"
    )
