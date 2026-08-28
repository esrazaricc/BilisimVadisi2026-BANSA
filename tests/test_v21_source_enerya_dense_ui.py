from __future__ import annotations

from src.chat_followup_context import resolve_followup_question
from src.competition_response_service import ask_bansa
from src.finance_runtime_repository import clear_finance_snapshot_cache, get_standard_products
from src.ui_finance_comparison import build_finance_comparison_table


def _text(question: str) -> str:
    return str(ask_bansa(question).text)


def test_dunya_vehicle_current_source_is_maturity_only_not_ratio():
    text = _text(
        "Dünya Katılım'da 600 bin TL değerinde ikinci el araç için en fazla ne kadar finansman kullanabilirim?"
    )
    assert "36 ay" in text
    assert "400.000,00 TL" in text
    assert "calculator giriş sınırıdır" in text
    assert "300.000,00 TL finansmana kadar" not in text
    assert "azami finansman oranı **%50**" not in text


def test_dunya_financing_ratio_fact_does_not_reuse_stale_percentage_table():
    text = _text("Dünya Katılım araç finansmanında azami finansman oranı nedir?")
    assert "yüzdesel azami finansman oranı" in text
    assert "doğrulanmış değil" in text
    assert "%70" not in text
    assert "%50" not in text


def test_runtime_snapshot_dunya_ratio_is_null_and_integrity_is_valid():
    clear_finance_snapshot_cache()
    frame = get_standard_products()
    row = frame[(frame["bank_name"] == "Dünya Katılım") & (frame["product_name"] == "Araç Finansmanı")].iloc[0]
    assert row["maximum_financing_ratio"] != row["maximum_financing_ratio"]  # NaN
    assert "yüzdesel finansman oranı yayımlanmamış" in str(row["financing_ratio_rules_text"])
    assert "36 ay" in str(row["maturity_rules_text"])


def test_enerya_karz_hasen_minimum_maturity_is_two_months():
    text = _text("Enerya Karz-ı Hasen finansmanında minimum kaç ay vade?")
    assert "Minimum vade 2 ay" in text
    assert "enerya-finansmani" in text
    assert "Araç Finansmanı" not in text


def test_enerya_karz_hasen_features_are_finance_campaign_specific():
    text = _text("Enerya Karz-ı Hasen finansmanı özellikleri nelerdir?")
    assert "6.500,00 TL–16.500,00 TL" in text
    assert "2–6 ay" in text
    assert "Antalya" in text and "Konya" in text
    assert "Enerya İhtiyaç Finansmanı" in text


def test_enerya_branded_product_never_inherits_unrelated_bank():
    history = [
        "Vakıf Katılım taşıt finansmanı nasıl?",
        "600 bin TL finansman kullanmak istiyorum",
    ]
    resolved = resolve_followup_question(
        "Enerya Karz-ı Hasen finansmanında minimum kaç ay vade?",
        history,
    )
    assert resolved.resolved_question.startswith("Dünya Katılım -")
    assert "Vakıf Katılım" not in resolved.resolved_question


def test_dense_vehicle_table_keeps_verified_numbers_and_maximizes_safe_metadata():
    answer = _text("100000 TL 36 ay taşıt finansmanı seçeneklerini karşılaştır")
    table = build_finance_comparison_table(
        answer,
        product_label="Taşıt Finansmanı",
        amount=100000,
    )
    assert len(table) >= 7
    for required in (
        "Banka",
        "Kâr Payı",
        "Aylık Taksit",
        "Toplam Geri Ödeme",
        "Vade / Vade Bantları",
        "Finansman Oranı / Kuralı",
        "Hesaplama Aracı Sınırı",
        "Tahsis Ücreti",
        "Resmî Kaynak",
    ):
        assert required in table.columns

    tf = table[table["Banka"] == "Türkiye Finans"]
    assert not tf.empty
    assert "5.678,71 TL" in set(tf["Aylık Taksit"])

    dunya = table[table["Banka"] == "Dünya Katılım"].iloc[0]
    assert dunya["Finansman Oranı / Kuralı"] == ""
    assert "36 ay" in dunya["Vade / Vade Bantları"]
    assert "giriş ≤ 400.000 TL" in dunya["Hesaplama Aracı Sınırı"]
    assert dunya["Aylık Taksit"] == ""
    assert dunya["Durum"] == "Güncel sayısal sonuç yok"
