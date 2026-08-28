from src.chat_followup_context import resolve_followup_question
from src.competition_response_service import ask_bansa


def _ask(q: str) -> str:
    return ask_bansa(q).text


def test_raw_history_asset_value_reply_recovers_bank_product_and_amount():
    history = [
        "Vakıf Katılım motosiklet finansmanı nasıl?",
        "600 bin için?",
    ]
    r = resolve_followup_question("Motosikletin değeri 600 bin TL", history)
    assert r.used_context is True
    assert "Vakıf Katılım" in r.resolved_question
    assert "motosiklet finansmanı" in r.resolved_question.casefold()
    assert "600000 TL motosiklet değeri" in r.resolved_question
    text = _ask(r.resolved_question)
    assert "**%50**" in text
    assert "**300.000,00 TL**" in text
    assert "**36 ay**" in text


def test_same_bank_generic_requested_amount_inherits_recent_product_not_random_soik():
    history = [
        "Vakıf Katılım motosiklet finansmanı nasıl?",
        "600 bin için?",
        "Motosikletin değeri 600 bin TL",
    ]
    r = resolve_followup_question(
        "Vakıf Katılım'da 600 bin TL finansman kullanmak istiyorum, olur mu?",
        history,
    )
    assert r.used_context is True
    assert "motosiklet finansmanı" in r.resolved_question.casefold()
    assert "600000 TL finansman tutarı" in r.resolved_question
    text = _ask(r.resolved_question)
    assert "Motosiklet Finansmanı" in text
    assert "SÖİK" not in text
    assert "600.000,00 TL finansman talebini" in text
    assert "300.000,00 TL" not in text


def test_standalone_generic_bank_requested_amount_asks_product_instead_of_guessing():
    text = _ask("Vakıf Katılım'da 600 bin TL finansman kullanmak istiyorum, olur mu?")
    assert "Finansman seçimi" in text
    assert "hangi finansman ürününü" in text
    assert "SÖİK" not in text


def test_dunya_second_hand_calculator_hard_limit_rejects_450k():
    text = _ask("Dünya Katılım 2. el araç finansmanı 450 bin TL 36 ay kullanmak istiyorum")
    assert "Araç Binek 2.El" in text
    assert "450.000,00 TL finansman tutarı" in text
    assert "400.000,00 TL" in text
    assert "aşıyor" in text


def test_dunya_second_hand_asset_value_separates_maturity_from_calculator_input_limit():
    text = _ask("Dünya Katılım 2. el 600 bin TL araç değeri için ne kadar finansman 36 ay")
    assert "azami vade 36 ay" in text
    assert "400.000,00 TL" in text
    assert "calculator giriş sınırıdır" in text
    assert "300.000,00 TL" not in text
    assert "%50" not in text


def test_vakif_second_hand_observed_18m_calculator_limit_is_term_scoped():
    text = _ask("Vakıf Katılım 2. el taşıt finansmanı 600 bin TL 18 ay kullanmak istiyorum")
    assert "Taşıt Finansmanı 2.El" in text
    assert "400.000,00 TL" in text
    assert "aşıyor" in text
    assert "yalnız doğrulandığı seçili vade" in text


def test_vakif_observed_18m_limit_is_not_generalized_to_24m():
    text = _ask("Vakıf Katılım 2. el taşıt finansmanı 600 bin TL 24 ay kullanmak istiyorum")
    assert "400.000,00 TL üst hesaplama tutarını aşıyor" not in text


def test_product_overview_labels_bansa_derived_example():
    text = _ask("Vakıf Katılım motosiklet finansmanı nasıl?")
    assert "Örnek senaryo (BANSA hesaplaması)" in text
    assert "600.000,00 TL" in text
    assert "300.000,00 TL" in text


def test_albaraka_education_benefits_remain_intent_aware():
    text = _ask("Albaraka Türk eğitim finansmanının avantajları neler?")
    assert "12 aya kadar" in text
    assert "konaklama" in text
    assert "veliniz/vasiniz" in text


def test_vehicle_comparison_stays_compact_and_calculator_first():
    text = _ask("100 bin TL 36 ay araç finansmanlarını karşılaştır")
    assert "güncel sayısal sonucunu doğrulayabildiğim" in text
    assert "400.000,00 TL'ye kadar %70/48 ay" not in text
    assert "Eski hesap örneklerini veya araç-değeri tablolarını aylık taksitmiş gibi kullanmıyorum" in text
