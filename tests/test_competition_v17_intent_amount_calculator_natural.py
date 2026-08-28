from src.chat_followup_context import resolve_followup_question
from src.competition_response_service import ask_bansa


def _ask(q: str) -> str:
    return ask_bansa(q).text


def test_vakif_motorcycle_overview_leads_with_critical_facts_and_example():
    text = _ask("Vakıf Katılım motosiklet finansmanı nasıl?")
    assert "48 aya varan vade" in text
    assert "600.000,00 TL" in text
    assert "300.000,00 TL" in text
    assert "36 ay" in text
    assert "doğrulanmış bir fiyatlama olarak vermiyorum" not in text


def test_bare_600k_followup_is_clarified_not_assumed_asset_value():
    r = resolve_followup_question(
        "600 bin için?",
        ["Vakıf Katılım motosiklet finansmanı nasıl?"],
    )
    text = _ask(r.resolved_question)
    assert "fatura/kasko değerini mi" in text
    assert "finansman tutarını mı" in text
    assert "600.000,00 TL motosiklet değeri için azami finansman oranı" not in text


def test_amount_clarification_reply_keeps_previous_number_and_becomes_asset_value():
    h = [
        "Vakıf Katılım motosiklet finansmanı nasıl?",
        "Vakıf Katılım motosiklet finansmanı 600000 TL",
    ]
    r = resolve_followup_question("motosikletin değeri", h)
    assert "600000 TL motosiklet değeri" in r.resolved_question
    text = _ask(r.resolved_question)
    assert "**%50**" in text
    assert "**300.000,00 TL**" in text
    assert "**36 ay**" in text


def test_explicit_requested_financing_is_not_ltv_multiplied():
    text = _ask("Vakıf Katılım motosiklet finansmanı 600 bin TL finansman kullanmak istiyorum")
    assert "600.000,00 TL finansman talebini" in text
    assert "300.000,00 TL" not in text


def test_albaraka_education_advantages_use_benefit_section():
    text = _ask("Albaraka Türk eğitim finansmanının avantajları neler?")
    assert "12 aya kadar" in text
    assert "eşit taksit" in text
    assert "konaklama" in text
    assert "dil ve sertifika" in text
    assert "veliniz/vasiniz" in text
    assert "Konut Finansmanı" not in text


def test_albaraka_housing_overview_is_compact_and_no_historical_example_dump():
    text = _ask("Albaraka Türk konut finansmanı özellikleri nelerdir?")
    assert "**Azami vade:** 120 ay" in text
    assert "%0,50" in text
    assert "ekspertiz ve ipotek/rehin" in text
    assert "BANSA'daki doğrulanmış hesaplama örneği" not in text
    assert "100.000,00 TL / 36 ay" not in text


def test_vehicle_comparison_does_not_dump_asset_value_bands_for_missing_calculator_results():
    text = _ask("100 bin TL 36 ay araç finansmanlarını karşılaştır")
    assert "100.000,00 TL / 36 ay" in text
    assert "güncel sayısal sonucunu doğrulayabildiğim" in text
    assert "400.000,00 TL'ye kadar %70/48 ay" not in text
    assert "Eski hesap örneklerini veya araç-değeri tablolarını aylık taksitmiş gibi kullanmıyorum" in text


def test_vehicle_comparison_amount_is_requested_financing_scenario():
    text = _ask("100 bin TL 36 ay araç finansmanlarını karşılaştır")
    assert "100.000,00 TL araç değeri" not in text


def test_dunya_explicit_asset_value_uses_current_maturity_only_source():
    text = _ask("Dünya Katılım'da 600 bin TL araç için en fazla ne kadar finansman kullanabilirim ve kaç ay vade olur?")
    assert "**azami vade 36 ay**" in text
    assert "yüzdesel" in text
    assert "300.000,00 TL" not in text
    assert "%50" not in text


def test_explicit_new_product_after_housing_compare_clears_old_state():
    r = resolve_followup_question(
        "Albaraka Türk eğitim finansmanının avantajları neler?",
        [
            "Albaraka Türk ile Türkiye Finans konut finansmanlarını karşılaştır",
            "Albaraka Türk ve Türkiye Finans konut finansmanı 500000 TL 36 ay karşılaştır",
        ],
    )
    assert r.used_context is False
    assert "konut" not in r.resolved_question.casefold()
    assert "500000" not in r.resolved_question
    text = _ask(r.resolved_question)
    assert "Eğitim Finansmanı" in text
    assert "Konut Finansmanı" not in text


def test_dunya_generic_vehicle_rules_never_apply_to_motorcycle_amount_question():
    text = _ask("Dünya Katılım 600 bin TL motosiklet için ne kadar verir?")
    assert "ayrı bir **Motosiklet Finansmanı** ürünü/kapsamı bulamadım" in text
    assert "300.000,00 TL" not in text
    assert "%50" not in text


def test_albaraka_motorcycle_125cc_scope_is_respected():
    hi = _ask("Albaraka Türk 150 cc motosiklet için?")
    lo = _ask("Albaraka Türk 100 cc motosiklet için?")
    assert "125 cc ve üzeri" in hi
    assert "taşıt finansmanı" in hi.casefold()
    assert "125 cc altı" in lo
    assert "ihtiyaç finansmanı" in lo.casefold()
