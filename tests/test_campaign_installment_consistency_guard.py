from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.campaign_compare import (
    CampaignCandidate,
)

from src.campaign_comparison_universe import (
    _sanitize_installment_candidate_v1_1,
    compare_campaign_universe,
)

from src.chatbot_campaign_renderer import (
    render_campaign_answer,
)


def _candidate(
    campaign_id,
    title,
    *,
    url="https://example.com/campaign",
    card=None,
    campaign=None,
):

    return CampaignCandidate(
        campaign_id=campaign_id,
        bank_name="Bank A",
        campaign_name=title,
        campaign_category="card_campaign",
        start_date="2026-08-01",
        end_date="2026-12-31",
        source_url=url,
        reward_amount=None,
        discount_rate=None,
        cashback_value=None,
        shopping_points=None,
        campaign_installment_count=(
            Decimal(
                str(campaign)
            )
            if campaign is not None
            else None
        ),
        minimum_spending=None,
        maximum_benefit=None,
        minimum_transaction_amount=None,
        maximum_transaction_amount=None,
        card_installment_count=(
            Decimal(
                str(card)
            )
            if card is not None
            else None
        ),
        installment_cost_rate=None,
        installment_cost_text=None,
        search_text="",
    )


def test_matching_title_preserves_installment():

    candidate = _candidate(
        1,
        "Egitimde 6 Taksit",
        card=6,
        campaign=6,
    )

    safe, blocked = (
        _sanitize_installment_candidate_v1_1(
            candidate
        )
    )

    assert blocked is False

    assert (
        safe.card_installment_count
        == Decimal(
            "6"
        )
    )


def test_title_conflict_blocks_installment():

    candidate = _candidate(
        2,
        "Trendyol 3 Taksit",
        card=6,
        campaign=6,
    )

    safe, blocked = (
        _sanitize_installment_candidate_v1_1(
            candidate
        )
    )

    assert blocked is True

    assert (
        safe.card_installment_count
        is None
    )

    assert (
        safe.campaign_installment_count
        is None
    )


def test_url_conflict_blocks_installment():

    candidate = _candidate(
        3,
        "Okul Odemelerinde Taksit",
        url=(
            "https://example.com/"
            "okul-odemelerinize-7-aya-kadar-"
            "kar-paysiz-taksit"
        ),
        card=2,
    )

    safe, blocked = (
        _sanitize_installment_candidate_v1_1(
            candidate
        )
    )

    assert blocked is True

    assert (
        safe.card_installment_count
        is None
    )


def test_no_title_url_number_preserves_structured_value():

    candidate = _candidate(
        4,
        "Kampanyaya Katilim Adimlari",
        card=4,
    )

    safe, blocked = (
        _sanitize_installment_candidate_v1_1(
            candidate
        )
    )

    assert blocked is False

    assert (
        safe.card_installment_count
        == Decimal(
            "4"
        )
    )


def test_conflicting_structured_fields_are_blocked():

    candidate = _candidate(
        5,
        "Okul Odemelerinde 7 Taksit",
        card=2,
        campaign=7,
    )

    safe, blocked = (
        _sanitize_installment_candidate_v1_1(
            candidate
        )
    )

    assert blocked is True

    assert (
        safe.card_installment_count
        is None
    )

    assert (
        safe.campaign_installment_count
        is None
    )


def test_ambiguous_title_and_url_are_blocked():

    candidate = _candidate(
        6,
        "Alisveriste 3 Taksit",
        url=(
            "https://example.com/"
            "alisveriste-6-taksit"
        ),
        card=3,
    )

    safe, blocked = (
        _sanitize_installment_candidate_v1_1(
            candidate
        )
    )

    assert blocked is True

    assert (
        safe.card_installment_count
        is None
    )


def test_renderer_adds_consistency_note():

    candidate = _candidate(
        7,
        "Okul Odemelerinde Taksit",
        card=None,
    )

    comparison = SimpleNamespace(
        candidates=(
            candidate,
        ),
        criterion_winners=(),
        may_claim_overall_winner=False,
        overall_metric=None,
        overall_winner_bank_names=(),
        bank_representatives=(),
        spend_amount=None,
        reasons=(
            "overall_ranking_blocked_for_campaign_universe",
            "installment_consistency_conflicts_present",
            "installment_consistency_blocked:7",
        ),
    )

    rendered = (
        render_campaign_answer(
            comparison
        )
    )

    assert (
        "Veri do\u011frulama notu"
        in rendered.text
    )

    assert (
        "taksit s\u0131ralamas\u0131nda kullan\u0131lmad\u0131"
        in rendered.text
    )


def test_real_education_id_199_is_blocked():

    result = compare_campaign_universe(
        "card_installment",
        question=(
            "egitim kampanyalarini "
            "karsilastir"
        ),
        as_of=date(
            2026,
            8,
            23,
        ),
    )

    by_id = {
        item.campaign_id:
            item
        for item
        in result.candidates
    }

    assert 199 in by_id

    assert (
        by_id[
            199
        ].card_installment_count
        is None
    )

    assert (
        by_id[
            199
        ].campaign_installment_count
        is None
    )

    assert (
        "installment_consistency_blocked:199"
        in result.reasons
    )

    installment_winners = [
        item
        for item
        in result.criterion_winners
        if item.criterion
        == "installment_count"
    ]

    assert (
        installment_winners
        == []
    )


def test_explicit_albaraka_kuveyt_safe_winner():

    result = compare_campaign_universe(
        "card_installment",
        bank_names=(
            "Albaraka T\u00fcrk",
            "Kuveyt T\u00fcrk",
        ),
        question=(
            "Albaraka Turk ve Kuveyt Turk "
            "egitim kampanyalarini "
            "karsilastir"
        ),
        as_of=date(
            2026,
            8,
            23,
        ),
    )

    assert {
        item.bank_name
        for item in result.candidates
    } == {
        "Albaraka T\u00fcrk",
        "Kuveyt T\u00fcrk",
    }

    installment = next(
        item
        for item
        in result.criterion_winners
        if item.criterion
        == "installment_count"
    )

    assert (
        installment.value
        == Decimal(
            "6"
        )
    )

    assert (
        installment.campaign_ids
        == (
            18,
        )
    )
