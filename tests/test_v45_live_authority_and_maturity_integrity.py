from datetime import datetime, timezone
from decimal import Decimal
import json

import pandas as pd

from src.finance_live_contract import LiveCalculationResult, LiveCalculationStatus
from src.finance_user_scenario_resolver import resolve_user_scenario


def _row():
    return pd.Series({
        "id": 97,
        "bank_name": "Albaraka Türk",
        "product_name": "Konut Finansmanı",
        "product_family_key": "konut_finansmani",
        "maximum_maturity_months": 120,
        "source_url": "https://www.albaraka.com.tr/tr/bireysel/finansmanlar/konut-finansmani/konut-finansmani",
    })


def test_live_mapped_bank_never_falls_back_to_stale_model(monkeypatch):
    import src.finance_user_scenario_resolver as resolver

    class StaleProjection:
        pass

    monkeypatch.setattr(resolver, "is_live_capable_row", lambda row, adapters=None: True)
    monkeypatch.setattr(resolver, "live_records_for_row", lambda *a, **k: [])
    monkeypatch.setattr(resolver, "project_row", lambda *a, **k: (StaleProjection(),))

    result = resolve_user_scenario(_row(), 500000, 120)
    assert result.mode == "live_unavailable"
    assert result.live_capable is True
    assert result.projections == ()
    assert result.live_records == ()


class CurrentAlbarakaAdapter:
    bank_name = "Albaraka Türk"

    def can_handle(self, request):
        return (
            int(request.product_id) == 97
            and request.bank_name == "Albaraka Türk"
            and request.family_key == "konut_finansmani"
            and (request.variant or "") in {"", "ilk_ev", "mevcut_konut"}
        )

    def calculate(self, request):
        # V45 regression fixture mirrors the user-observed official calculator
        # rate for 500,000 TL / 120 months.  Production code does NOT hard-code
        # this rate; it must pass through the live adapter response unchanged.
        monthly = Decimal("15200.00")
        return LiveCalculationResult(
            request=request,
            status=LiveCalculationStatus.VERIFIED,
            calculated_amount=request.amount,
            calculated_maturity_months=request.maturity_months,
            profit_share_rate=Decimal("2.90"),
            monthly_installment=monthly,
            total_repayment=monthly * Decimal(request.maturity_months),
            allocation_fee=Decimal("2500.00"),
            source_kind="official_live_calculator_endpoint",
            source_url=(
                "https://www.albaraka.com.tr/tr/hesaplama-araclari/"
                "finansman-hesaplama/konut-finansmani-hesaplama"
            ),
            checked_at=datetime.now(timezone.utc),
        )


def test_chatbot_uses_current_albaraka_live_rate_for_exact_500k_120(monkeypatch):
    import src.finance_live_compare as flc
    from src.competition_natural_chat import answer_natural

    monkeypatch.setattr(flc, "default_live_adapters", lambda: [CurrentAlbarakaAdapter()])

    result = answer_natural(
        "Albaraka Türk konut finansmanı 500.000 TL 120 ay aylık taksit ve toplam geri ödeme nedir?"
    )
    assert result is not None
    assert "%2,90" in result.text
    assert "15.200,00 TL" in result.text
    assert "1.824.000,00 TL" in result.text
    assert "%3,04" not in result.text


def test_no_maturity_uses_one_common_120_month_scenario_not_hidden_36(monkeypatch):
    import src.finance_live_compare as flc
    from src.competition_natural_chat import answer_natural

    monkeypatch.setattr(flc, "default_live_adapters", lambda: [CurrentAlbarakaAdapter()])

    result = answer_natural(
        "500 bin TL konut finansmanı için hangi seçenekler var?"
    )
    assert result is not None
    assert "120 ay" in result.text
    assert "aynı senaryoda" in result.text
    # The Albaraka live record must be calculated at the displayed term.
    assert "Albaraka Türk" in result.text
    assert "%2,90" in result.text
    assert "1.824.000,00 TL" in result.text


def test_albaraka_housing_selector_discovers_dynamic_campaign_codes(monkeypatch):
    import src.finance_live_adapters.albaraka_konut as module

    first = {
        "ProductCode": "KONTKRD",
        "ProductParCode": "1",
        "ProjectCode": "NEW2026-FIRST",
        "CampaingCode": "CAMPAIGN-AUG-001",
        "CampaignName": "İLK EVİM KONUT FİNANSMANI",
        "MaturityMinValue": "3",
        "MaturityMaxValue": "120",
        "AmountMinValue": "10000",
        "AmountMaxValue": "10000000",
    }
    second = {
        "ProductCode": "KONTKRD",
        "ProductParCode": "1",
        "ProjectCode": "NEW2026-EXISTING",
        "CampaingCode": "CAMPAIGN-AUG-002",
        "CampaignName": "2. VE SONRAKİ KONUT FİNANSMANI",
        "MaturityMinValue": "3",
        "MaturityMaxValue": "120",
        "AmountMinValue": "10000",
        "AmountMaxValue": "10000000",
    }
    html = f"""
    <script>var langId: 'tr-TR'; var language: 'tr'; var Slug: 'konut-finansmani-hesaplama';</script>
    <select id="slcfinansmanTuru">
      <option projectparcode="901" value='{json.dumps(first, ensure_ascii=False)}'>İlk Evim Konut Finansmanı</option>
      <option projectparcode="902" value='{json.dumps(second, ensure_ascii=False)}'>2. ve Sonraki Konut Finansmanı</option>
    </select>
    """

    class Response:
        text = html
        def raise_for_status(self):
            return None

    class Session:
        headers = {}
        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(module.requests, "Session", lambda: Session())
    prepared = module.AlbarakaKonutLiveAdapter()._prepare_housing()

    assert set(prepared["mappings"]) == {"ilk_ev", "mevcut_konut"}
    assert prepared["mappings"]["ilk_ev"]["data"]["CampaingCode"] == "CAMPAIGN-AUG-001"
    assert prepared["mappings"]["mevcut_konut"]["data"]["CampaingCode"] == "CAMPAIGN-AUG-002"
