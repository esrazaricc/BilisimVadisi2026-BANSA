from __future__ import annotations

from src.chat_followup_context import resolve_followup_question
from src.competition_response_service import ask_bansa
from src.ui_finance_dashboard import (
    bank_options_for_family,
    build_finance_catalog_table,
    finance_catalog_insights,
    finance_family_options,
    public_catalog_columns,
)


def _text(q: str) -> str:
    return str(ask_bansa(q).text)


def test_two_bank_finance_compare_without_scenario_asks_amount_and_maturity():
    text = _text("Albaraka Türk ile Türkiye Finans konut finansmanlarını karşılaştır")
    assert "finansman tutarı ve vade" in text
    assert "500.000 TL / 36 ay" in text
    assert "Genel ürün koşullarını karşılaştırıyorum" not in text


def test_followup_amount_maturity_restores_two_bank_comparison_context():
    resolved = resolve_followup_question(
        "500 bin TL 36 ay",
        ["Albaraka Türk ile Türkiye Finans konut finansmanlarını karşılaştır"],
    )
    assert resolved.used_context is True
    assert "Albaraka Türk" in resolved.resolved_question
    assert "Türkiye Finans" in resolved.resolved_question
    assert "konut finansmanı" in resolved.resolved_question
    assert "500000 TL" in resolved.resolved_question
    assert "36 ay" in resolved.resolved_question
    assert "karşılaştır" in resolved.resolved_question



def test_two_step_amount_then_maturity_keeps_both_slots():
    history = ["Albaraka Türk ile Türkiye Finans konut finansmanlarını karşılaştır"]
    first = resolve_followup_question("500 bin TL", history)
    assert "500000 TL" in first.resolved_question
    history.append("500 bin TL")
    second = resolve_followup_question("36 ay", history)
    assert "500000 TL" in second.resolved_question
    assert "36 ay" in second.resolved_question
    assert "Albaraka Türk" in second.resolved_question and "Türkiye Finans" in second.resolved_question

def test_finance_dashboard_family_selection_returns_all_products_not_one_per_bank():
    frame = build_finance_catalog_table("konut_finansmani")
    assert len(frame) >= 15
    assert frame["Banka"].nunique() >= 7
    assert (frame["Banka"] == "Türkiye Emlak Katılım").sum() >= 5
    assert "Ürün Kaynağı" in public_catalog_columns(frame, "konut_finansmani")


def test_finance_dashboard_bank_filter_keeps_all_products_for_that_bank():
    frame = build_finance_catalog_table("konut_finansmani", ["Türkiye Emlak Katılım"])
    assert not frame.empty
    assert set(frame["Banka"]) == {"Türkiye Emlak Katılım"}
    assert len(frame) >= 5


def test_dunya_vehicle_dashboard_never_reintroduces_stale_percentage_ratio():
    frame = build_finance_catalog_table("arac_finansmani", ["Dünya Katılım"])
    assert not frame.empty
    ratio_text = " ".join(frame["Finansman Oranı / Kuralı"].astype(str).tolist())
    assert "%50" not in ratio_text
    assert "%70" not in ratio_text
    assert ratio_text.strip() == ""


def test_finance_dashboard_has_all_major_families_and_insights():
    options = dict(finance_family_options())
    for key in (
        "konut_finansmani", "arac_finansmani", "ihtiyac_finansmani",
        "ticari_finansman", "gayri_nakdi_finansman", "tarim_finansmani", "leasing",
    ):
        assert key in options
    frame = build_finance_catalog_table("konut_finansmani")
    labels = [x[0] for x in finance_catalog_insights(frame)]
    assert "En fazla ürün seçeneği" in labels
    assert "En uzun yayımlanmış vade" in labels


def test_enerya_and_dunya_v21_source_guards_remain_active():
    enerya = _text("Enerya Karz-ı Hasen finansmanında minimum kaç ay vade?")
    assert "Minimum vade 2 ay" in enerya
    dunya = _text("Dünya Katılım'da 600 bin TL değerinde ikinci el araç için en fazla ne kadar finansman kullanabilirim?")
    assert "36 ay" in dunya
    assert "calculator giriş sınırıdır" in dunya
    assert "300.000,00 TL finansmana kadar" not in dunya
