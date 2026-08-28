from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

from src.chatbot_router import (
    route_question,
)

from src.chatbot_campaign_compare import (
    resolve_campaign_universe_key,
    run_campaign_compare,
)

from src.chatbot_campaign_renderer import (
    render_campaign_answer,
)

from src.chatbot_orchestrator import (
    run_chatbot,
)

from src.chatbot_answer_contract import (
    build_grounded_answer_context,
)

from src.chatbot_response_service import (
    BansaResponseService,
)

from src.campaign_compare import (
    CampaignCandidate,
    CampaignCriterionWinner,
)

from src.campaign_comparison_universe import (
    CampaignBankRepresentative,
    CampaignUniverseComparisonResult,
)


def _number(
    value,
):

    if value is None:

        return None

    return Decimal(
        str(value)
    )


def _candidate(
    campaign_id,
    bank,
    title,
    *,
    category="card_campaign",
    reward=None,
    points=None,
    installments=None,
):

    return CampaignCandidate(
        campaign_id=campaign_id,
        bank_name=bank,
        campaign_name=title,
        campaign_category=category,
        start_date="2026-08-01",
        end_date="2026-08-31",
        source_url=(
            "https://example.com/"
            + str(
                campaign_id
            )
        ),
        reward_amount=_number(
            reward
        ),
        discount_rate=None,
        cashback_value=None,
        shopping_points=_number(
            points
        ),
        campaign_installment_count=_number(
            installments
        ),
        minimum_spending=None,
        maximum_benefit=None,
        minimum_transaction_amount=None,
        maximum_transaction_amount=None,
        card_installment_count=_number(
            installments
        ),
        installment_cost_rate=None,
        installment_cost_text=None,
        search_text="",
    )


def test_router_is_already_campaign_compare():

    assert (
        route_question(
            "Market alisverisinde "
            "hangi banka daha avantajli?"
        ).route
        == "campaign_compare"
    )


def test_normal_campaign_question_still_rag():

    assert (
        route_question(
            "Emlak Katilim market "
            "kampanyasi var mi?"
        ).route
        == "campaign_rag"
    )


def test_finance_route_still_preserved():

    assert (
        route_question(
            "100000 TL 36 ay konut "
            "finansmaninda hangi banka "
            "daha avantajli?"
        ).route
        == "finance_compare"
    )


def test_universe_resolution():

    assert (
        resolve_campaign_universe_key(
            "market kampanyalarini "
            "karsilastir"
        )
        == "shopping_benefit"
    )

    assert (
        resolve_campaign_universe_key(
            "egitim kampanyalarini "
            "karsilastir"
        )
        == "card_installment"
    )

    assert (
        resolve_campaign_universe_key(
            "yeni musteri kampanyalarini "
            "karsilastir"
        )
        == "new_customer"
    )


def test_spend_amount_parser():

    result = run_campaign_compare(
        "5.000 TL market kampanyalarinda "
        "hangi banka daha avantajli?"
    )

    assert (
        result.comparison
        is not None
    )

    assert (
        result.comparison.spend_amount
        == Decimal(
            "5000"
        )
    )


@dataclass(frozen=True)
class FakeCampaignRun:
    universe_key: str
    comparison: object
    missing_fields: tuple = ()
    reasons: tuple = (
        "deterministic_campaign_engine_executed",
    )


def test_orchestrator_campaign_skips_rag_finance():

    comparison = SimpleNamespace(
        candidates=(),
    )

    calls = {
        "campaign": 0,
        "rag": 0,
        "finance": 0,
    }

    def campaign_fn(
        question,
        *,
        route_decision=None,
    ):

        calls[
            "campaign"
        ] += 1

        return FakeCampaignRun(
            universe_key=(
                "shopping_benefit"
            ),
            comparison=comparison,
        )

    def rag_fn(
        *args,
        **kwargs,
    ):

        calls[
            "rag"
        ] += 1

        raise AssertionError(
            "RAG must not run."
        )

    def finance_fn(
        *args,
        **kwargs,
    ):

        calls[
            "finance"
        ] += 1

        raise AssertionError(
            "Finance must not run."
        )

    result = run_chatbot(
        "Market kampanyalarini karsilastir",
        route_decision=route_question(
            "Market kampanyalarini karsilastir"
        ),
        campaign_compare_fn=campaign_fn,
        rag_runner=rag_fn,
        finance_compare_fn=finance_fn,
    )

    assert (
        result.route
        == "campaign_compare"
    )

    assert (
        result.campaign_result
        is comparison
    )

    assert calls == {
        "campaign": 1,
        "rag": 0,
        "finance": 0,
    }


def test_answer_contract_campaign_mode():

    comparison = SimpleNamespace(
        candidates=(),
    )

    execution = SimpleNamespace(
        question="market",
        route="campaign_compare",
        status="completed",
        missing_fields=(),
        reasons=(),
        campaign_result=comparison,
        campaign_universe_key=(
            "shopping_benefit"
        ),
    )

    context = (
        build_grounded_answer_context(
            execution
        )
    )

    assert (
        context.answer_mode
        == "campaign_compare"
    )

    assert (
        context.campaign_result
        is comparison
    )

    assert context.evidence == ()
    assert context.finance_results == ()


def test_renderer_card_criterion_without_global_winner():

    first = _candidate(
        1,
        "Bank A",
        "Egitim 6 Taksit",
        installments=6,
    )

    second = _candidate(
        2,
        "Bank B",
        "Okul 10 Taksit",
        installments=10,
    )

    comparison = (
        CampaignUniverseComparisonResult(
            universe_key=(
                "card_installment"
            ),
            categories=(
                "card_campaign",
            ),
            requested_banks=(),
            spend_amount=None,
            candidates=(
                first,
                second,
            ),
            criterion_winners=(
                CampaignCriterionWinner(
                    criterion=(
                        "installment_count"
                    ),
                    direction="max",
                    campaign_ids=(
                        2,
                    ),
                    value=Decimal(
                        "10"
                    ),
                ),
            ),
            bank_representatives=(),
            overall_winner_bank_names=(),
            overall_winner_campaign_ids=(),
            overall_metric=None,
            reasons=(
                "overall_ranking_blocked_for_campaign_universe",
            ),
        )
    )

    rendered = (
        render_campaign_answer(
            comparison
        )
    )

    assert (
        rendered.ranking_claimed
        is False
    )

    assert (
        "10 taksit"
        in rendered.text
    )


def test_renderer_single_bank_guard():

    first = _candidate(
        1,
        "Bank A",
        "Market 500",
        category="points_campaign",
        reward=500,
        points=500,
    )

    second = _candidate(
        2,
        "Bank A",
        "Market 800",
        category="points_campaign",
        reward=800,
        points=800,
    )

    comparison = (
        CampaignUniverseComparisonResult(
            universe_key=(
                "shopping_benefit"
            ),
            categories=(
                "points_campaign",
            ),
            requested_banks=(),
            spend_amount=Decimal(
                "5000"
            ),
            candidates=(
                first,
                second,
            ),
            criterion_winners=(),
            bank_representatives=(
                CampaignBankRepresentative(
                    bank_name="Bank A",
                    campaign_ids=(
                        2,
                    ),
                    effective_monetary_benefit=(
                        Decimal(
                            "800"
                        )
                    ),
                ),
            ),
            overall_winner_bank_names=(),
            overall_winner_campaign_ids=(),
            overall_metric=None,
            reasons=(
                "overall_ranking_requires_multiple_banks",
            ),
        )
    )

    rendered = (
        render_campaign_answer(
            comparison
        )
    )

    assert (
        rendered.ranking_claimed
        is False
    )

    assert (
        "genel kazanan belirtmiyorum"
        in rendered.text
    )


def test_response_service_campaign_backend():

    candidate = _candidate(
        1,
        "Bank A",
        "Market Reward",
        category="points_campaign",
        reward=500,
        points=500,
    )

    comparison = (
        CampaignUniverseComparisonResult(
            universe_key=(
                "shopping_benefit"
            ),
            categories=(
                "points_campaign",
            ),
            requested_banks=(),
            spend_amount=Decimal(
                "5000"
            ),
            candidates=(
                candidate,
            ),
            criterion_winners=(),
            bank_representatives=(
                CampaignBankRepresentative(
                    bank_name="Bank A",
                    campaign_ids=(
                        1,
                    ),
                    effective_monetary_benefit=(
                        Decimal(
                            "500"
                        )
                    ),
                ),
            ),
            overall_winner_bank_names=(),
            overall_winner_campaign_ids=(),
            overall_metric=None,
            reasons=(
                "overall_ranking_requires_multiple_banks",
            ),
        )
    )

    execution = SimpleNamespace(
        question="market",
        route="campaign_compare",
        status="completed",
        missing_fields=(),
        reasons=(),
        campaign_result=comparison,
        campaign_universe_key=(
            "shopping_benefit"
        ),
    )

    def runner(
        question,
        *,
        finance_adapters=None,
    ):

        return execution

    response = (
        BansaResponseService(
            runner=runner,
        ).ask(
            "market"
        )
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
        response.finance_renderer_used
        is False
    )

    assert (
        "Bank A"
        in response.text
    )
