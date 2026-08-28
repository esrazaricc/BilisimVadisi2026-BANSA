from decimal import Decimal

from src.competition_natural_chat import answer_natural
from src.finance_live_contract import (
    LiveCalculationResult,
    LiveCalculationStatus,
)


class AlbarakaKonutLiveAdapter:
    bank_name = "Albaraka Türk"

    def can_handle(self, request):
        return (
            int(request.product_id) == 97
            and request.bank_name == "Albaraka Türk"
            and request.family_key == "konut_finansmani"
            and (request.variant or "") in {"", "ilk_ev", "mevcut_konut"}
        )

    def calculate(self, request):
        if not request.variant:
            return LiveCalculationResult(
                request=request,
                status=LiveCalculationStatus.UNVERIFIED,
                reason="condition-specific housing pricing",
            )

        if request.variant == "ilk_ev":
            rate = Decimal("3.10")
            monthly = Decimal("23200.00")
            total = Decimal("835200.00")
        else:
            rate = Decimal("3.20")
            monthly = Decimal("23550.00")
            total = Decimal("847800.00")

        return LiveCalculationResult(
            request=request,
            status=LiveCalculationStatus.VERIFIED,
            calculated_amount=Decimal("500000"),
            calculated_maturity_months=36,
            profit_share_rate=rate,
            monthly_installment=monthly,
            total_repayment=total,
            allocation_fee=Decimal("2500.00"),
            source_kind="official_live_calculator_endpoint",
            source_url=(
                "https://www.albaraka.com.tr/tr/hesaplama-araclari/"
                "finansman-hesaplama/konut-finansmani-hesaplama"
            ),
        )


def test_named_housing_compare_keeps_albaraka_live_and_tf_projection(monkeypatch):
    import src.finance_live_compare as flc

    monkeypatch.setattr(
        flc,
        "default_live_adapters",
        lambda: [AlbarakaKonutLiveAdapter()],
    )

    result = answer_natural(
        "Albaraka Türk ve Türkiye Finans konut finansmanlarını "
        "500.000 TL 36 ay karşılaştır hangisi daha avantajlı?"
    )

    assert result is not None
    assert result.route == "finance_compare"
    assert "Albaraka Türk" in result.text
    assert "Türkiye Finans" in result.text
    assert "Konut Finansmanı" in result.text
    assert "Mevcut Konut" in result.text or "Mevcut konut" in result.text
    assert "BANSA resmî kaynak modeli" in result.text
    assert "resmî fiyatlama tablosu" in result.text
    assert "Albaraka Türk" not in result.text.split("güncel sayısal sonucu doğrulayamadığım bankalar")[-1] if "güncel sayısal sonucu doğrulayamadığım bankalar" in result.text else True


def test_old_albaraka_dynamic_snapshot_is_not_projected_as_current():
    import pandas as pd
    from src.competition_natural_chat import (
        _filter_products,
        _direct_family_product,
        _enrich_row,
    )
    from src.finance_scenario_projection import project_row

    q = "Albaraka Türk konut finansmanı 500.000 TL 36 ay"
    work = _filter_products(q, ("Albaraka Türk",), "konut_finansmani")
    assert not work.empty
    row, _ = _direct_family_product(work, "konut_finansmani", q)
    row = _enrich_row(row)

    # V40 user-approved source catalog deliberately enables Albaraka konut
    # inside BANSA.  It must still be labelled as BANSA's managed calculator
    # model, not as a live bank offer.
    projections = project_row(row, 500000, 36)
    assert projections
    assert all(p.mode == "bansa_managed_calculator_model" for p in projections)
