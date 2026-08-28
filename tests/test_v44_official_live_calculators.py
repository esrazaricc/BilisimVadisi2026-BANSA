from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd

from src.finance_live_contract import (
    LiveCalculationRequest,
    LiveCalculationResult,
    LiveCalculationStatus,
)
from src.finance_live_adapters.vakif_katilim import VakifKatilimLiveAdapter
from src.finance_official_calculator_service import (
    live_records_for_row,
    live_records_for_rows,
)


def _request(product_id, family, *, bank="Vakıf Katılım", variant=None):
    return LiveCalculationRequest(
        product_id=product_id,
        bank_name=bank,
        product_name="Test Ürün",
        family_key=family,
        amount=Decimal("100000"),
        maturity_months=36,
        variant=variant,
    )


def _verified(request, *, rate="2.50", monthly="4000.00", total="144000.00"):
    return LiveCalculationResult(
        request=request,
        status=LiveCalculationStatus.VERIFIED,
        calculated_amount=request.amount,
        calculated_maturity_months=request.maturity_months,
        profit_share_rate=Decimal(rate),
        monthly_installment=Decimal(monthly),
        total_repayment=Decimal(total),
        allocation_fee=Decimal("500.00"),
        source_kind="official_live_calculator_endpoint",
        source_url="https://bank.example/calculator",
        checked_at=datetime.now(timezone.utc),
    )


def test_vakif_adapter_maps_all_three_user_scenario_families():
    adapter = VakifKatilimLiveAdapter()
    assert adapter.can_handle(_request(296, "konut_finansmani"))
    assert adapter.can_handle(_request(286, "arac_finansmani"))
    assert adapter.can_handle(_request(318, "ihtiyac_finansmani"))
    assert not adapter.can_handle(_request(296, "arac_finansmani"))


def test_vakif_calculator_type_code_is_discovered_from_official_form(monkeypatch):
    import src.finance_live_adapters.vakif_katilim as module

    html = """
    <form id="financing-calculator">
      <input name="__RequestVerificationToken" value="token-123" />
      <select id="financing-type-select">
        <option value="KONUT-CODE" data-installments="120">Konut Finansmanı</option>
        <option value="TASIT-CODE" data-installments="48">Taşıt Finansmanı</option>
        <option value="IHTIYAC-CODE" data-installments="36">İhtiyaç Finansmanı</option>
      </select>
      <input type="radio" name="finansman-type" value="1" checked />
    </form>
    <script>var langId: 'tr-TR'; var language: 'tr';</script>
    """

    class Response:
        text = html
        def raise_for_status(self):
            return None

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(module.requests, "Session", lambda: Session())
    adapter = VakifKatilimLiveAdapter()

    expected = [
        (296, "konut_finansmani", "KONUT-CODE"),
        (286, "arac_finansmani", "TASIT-CODE"),
        (318, "ihtiyac_finansmani", "IHTIYAC-CODE"),
    ]
    for product_id, family, code in expected:
        prepared = adapter._prepare_session(_request(product_id, family))
        assert isinstance(prepared, dict)
        assert prepared["financing_type"] == code


class ExactLiveAdapter:
    def can_handle(self, request):
        return request.product_id == 999

    def calculate(self, request):
        return _verified(request)


def test_shared_service_accepts_only_exact_verified_live_output():
    row = pd.Series({
        "id": 999,
        "bank_name": "Test Bank",
        "product_name": "Konut Finansmanı",
        "product_family_key": "konut_finansmani",
        "source_url": "https://bank.example/product",
    })
    records = live_records_for_row(row, 100000, 36, adapters=[ExactLiveAdapter()])
    assert len(records) == 1
    assert records[0]["rate"] == Decimal("2.50")
    assert records[0]["monthly"] == Decimal("4000.00")
    assert records[0]["freshness_mode"] == "live_calculator"


class WrongScenarioAdapter(ExactLiveAdapter):
    def calculate(self, request):
        result = _verified(request)
        result.calculated_amount = Decimal("90000")
        return result


def test_shared_service_rejects_non_exact_live_output():
    row = pd.Series({
        "id": 999,
        "bank_name": "Test Bank",
        "product_name": "Konut Finansmanı",
        "product_family_key": "konut_finansmani",
    })
    assert live_records_for_row(row, 100000, 36, adapters=[WrongScenarioAdapter()]) == []


class AlbarakaKonutLiveAdapter:
    def can_handle(self, request):
        return request.product_id == 97

    def calculate(self, request):
        if not request.variant:
            return LiveCalculationResult(
                request=request,
                status=LiveCalculationStatus.UNVERIFIED,
                reason="variant required",
            )
        if request.variant == "ilk_ev":
            return _verified(request, rate="3.10", monthly="4500", total="162000")
        if request.variant == "mevcut_konut":
            return _verified(request, rate="3.20", monthly="4600", total="165600")
        return LiveCalculationResult(request=request, status=LiveCalculationStatus.UNVERIFIED)


def test_shared_service_expands_verified_condition_variants():
    row = pd.Series({
        "id": 97,
        "bank_name": "Albaraka Türk",
        "product_name": "Konut Finansmanı",
        "product_family_key": "konut_finansmani",
    })
    records = live_records_for_row(row, 100000, 36, adapters=[AlbarakaKonutLiveAdapter()])
    assert {r["variant"] for r in records} == {"ilk_ev", "mevcut_konut"}


def test_bulk_live_resolution_keeps_bank_failures_isolated():
    class SometimesFails(ExactLiveAdapter):
        def can_handle(self, request):
            return request.product_id in {998, 999}
        def calculate(self, request):
            if request.product_id == 998:
                raise RuntimeError("bank temporarily unavailable")
            return _verified(request)

    products = pd.DataFrame([
        {"id": 998, "bank_name": "A", "product_name": "Konut", "product_family_key": "konut_finansmani"},
        {"id": 999, "bank_name": "B", "product_name": "Konut", "product_family_key": "konut_finansmani"},
    ])
    out = live_records_for_rows(products, 100000, 36, adapters=[SometimesFails()], max_workers=2)
    assert out[998] == []
    assert len(out[999]) == 1


def test_chatbot_uses_official_live_result_before_v43_projection(monkeypatch):
    import src.finance_live_compare as flc
    from src.competition_natural_chat import answer_natural

    class EmlakFakeAdapter:
        def can_handle(self, request):
            return (
                request.bank_name == "Türkiye Emlak Katılım"
                and request.family_key == "konut_finansmani"
                and request.product_id == 242
            )
        def calculate(self, request):
            return _verified(request, rate="2.41", monthly="4210.55", total="151579.80")

    monkeypatch.setattr(flc, "default_live_adapters", lambda: [EmlakFakeAdapter()])
    result = answer_natural(
        "Türkiye Emlak Katılım konut finansmanı 100000 TL 36 ay aylık taksit ve toplam geri ödeme nedir?"
    )
    assert result is not None
    assert "4.210,55 TL" in result.text
    assert "151.579,80 TL" in result.text
    assert "2,41" in result.text


def test_current_canonical_live_mapping_coverage_is_explicit_and_stable():
    from src.finance_runtime_repository import get_standard_products
    from src.bansa_v40_finance_catalog import canonical_scenario_products
    from src.finance_official_calculator_service import is_live_capable_row

    products = get_standard_products().copy()
    expected = {
        "konut_finansmani": {"Dünya Katılım", "Albaraka Türk", "Türkiye Emlak Katılım", "Vakıf Katılım"},
        "arac_finansmani": {"Türkiye Emlak Katılım", "Vakıf Katılım"},
        "ihtiyac_finansmani": {"Türkiye Emlak Katılım", "Vakıf Katılım"},
    }
    for family, banks in expected.items():
        frame = products[products["product_family_key"].astype(str).eq(family)].copy()
        frame = canonical_scenario_products(frame, family)
        actual = {
            str(row.get("bank_name"))
            for _, row in frame.iterrows()
            if is_live_capable_row(row)
        }
        assert actual == banks


def test_finance_dashboard_metrics_distinguish_mapping_live_and_model_counts():
    from pathlib import Path
    source = Path("pages/2_Finansman_Karsilastirmasi.py").read_text(encoding="utf-8")
    # V47 keeps the same live-vs-model distinction but uses cleaner,
    # user-facing metric labels instead of internal implementation wording.
    assert '"Canlı hesaplama destekleyen banka"' in source
    assert '"Bu senaryoda sonuç veren banka"' in source
    assert '"Banka aracından doğrulanan"' in source
    assert '"Resmî fiyatlamayla hesaplanan"' in source
    assert "live_records_for_rows(products, amount, maturity)" in source
