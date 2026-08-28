from src.finance_runtime_repository import get_standard_products
from src.finance_scenario_projection import project_row
from src.bansa_v40_finance_catalog import apply_source_overrides, canonical_scenario_products, is_personal_offer


def _canonical(family: str):
    frame = apply_source_overrides(get_standard_products().copy())
    frame = frame[frame["product_family_key"].eq(family)].copy()
    return canonical_scenario_products(frame, family)


def _banks_with_projection(family: str, amount: int, maturity: int):
    out = set()
    for _, row in _canonical(family).iterrows():
        if project_row(row, amount, maturity):
            out.add(str(row.get("bank_name")))
    return out


def test_v40_housing_calculates_five_core_banks_and_keeps_emlak_ziraat_personal():
    expected = {"Albaraka Türk", "Dünya Katılım", "Kuveyt Türk", "Türkiye Finans", "Vakıf Katılım"}
    assert _banks_with_projection("konut_finansmani", 120_000, 36) == expected
    personal = {
        str(row.get("bank_name"))
        for _, row in _canonical("konut_finansmani").iterrows()
        if is_personal_offer(row)
    }
    assert {"Türkiye Emlak Katılım", "Ziraat Katılım"}.issubset(personal)


def test_v40_vehicle_calculates_five_core_banks_and_keeps_emlak_ziraat_personal():
    expected = {"Albaraka Türk", "Dünya Katılım", "Kuveyt Türk", "Türkiye Finans", "Vakıf Katılım"}
    assert _banks_with_projection("arac_finansmani", 120_000, 36) == expected
    personal = {
        str(row.get("bank_name"))
        for _, row in _canonical("arac_finansmani").iterrows()
        if is_personal_offer(row)
    }
    assert {"Türkiye Emlak Katılım", "Ziraat Katılım"}.issubset(personal)


def test_v40_need_calculates_core_banks_with_kuveyt_alt_products():
    expected = {"Albaraka Türk", "Dünya Katılım", "Kuveyt Türk", "Türkiye Finans", "Vakıf Katılım"}
    assert _banks_with_projection("ihtiyac_finansmani", 100_000, 36) == expected


def test_v40_projector_blocks_unsourced_personal_offer_rows():
    frame = get_standard_products()
    for product_id in (242, 377, 230, 347, 273, 341):
        row = frame[frame["id"].eq(product_id)].iloc[0]
        assert project_row(row, 120_000, 36) == tuple()
