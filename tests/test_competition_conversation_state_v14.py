from src.chat_followup_context import resolve_followup_question
from src.competition_response_service import ask_bansa
from src.competition_fast_router import parse_amount_and_maturity


def _turn(question, history):
    resolution = resolve_followup_question(question, history)
    answer = ask_bansa(resolution.resolved_question).text
    history.append(resolution.resolved_question)
    return resolution, answer


def test_tf_rate_to_monthly_calculation_replaces_old_intent_and_keeps_sigortali_variant():
    h = []
    _turn("Türkiye Finans'ta sigortalı taşıt finansmanı kar payı ne?", h)
    r2, a2 = _turn("36 ay", h)
    assert "sigortalı" in r2.resolved_question.casefold()
    assert "%3,48" in a2

    r3, a3 = _turn("100 bin TL için aylık taksit ne olur?", h)
    q = r3.resolved_question.casefold()
    assert "100000 tl" in q
    assert "36 ay" in q
    assert "sigortalı" in q
    assert "aylık taksit" in q
    assert "5.678,71 TL" in a3
    assert "204.433,56 TL" in a3
    assert a3.count("5.678,71 TL") == 1
    assert "fark yaklaşık **0,00 TL**" not in a3


def test_emlak_vehicle_value_band_beats_generic_48_month_product_ceiling():
    h = []
    _turn("Türkiye Emlak Katılım taşıt finansmanı nasıl?", h)
    r2, a2 = _turn("600 bin TL araç için kaç aya kadar vade var?", h)
    assert "Türkiye Emlak Katılım" in r2.resolved_question
    assert "araç değeri" in r2.resolved_question.casefold()
    assert "**%50**" in a2
    assert "**300.000,00 TL**" in a2
    assert "azami vade **36 ay**" in a2

    _, a3 = _turn("24 ay olur mu?", h)
    assert "**24 ay vade** olur." in a3
    assert "**36 aylık** üst sınır" in a3


def test_emlak_calculation_without_exact_rate_abstains_instead_of_misusing_vehicle_table():
    h = []
    _turn("Türkiye Emlak Katılım taşıt finansmanı nasıl?", h)
    _, answer = _turn("100 bin TL 36 ay için taksit hesapla", h)
    assert "birebir doğrulayabildiği güncel bir kâr payı/taksit satırı yok" in answer
    assert "aylık taksit veya toplam geri ödeme uydurmuyorum" in answer
    assert "araç değeri → azami finansman oranı/vade" in answer
    assert "100.000,00 TL / 24 ay" in answer


def test_dunya_same_bank_vehicle_value_followups_cover_all_official_bands():
    h = []
    _turn("Dünya Katılım araç finansmanı nasıl?", h)
    cases = [
        ("300 bin TL araç için en fazla kaç ay?", "%70", "48 ay"),
        ("600 bin TL araç için?", "%50", "36 ay"),
        ("900 bin TL araç için?", "%30", "24 ay"),
        ("1 milyon 500 bin TL araç için?", "%20", "12 ay"),
    ]
    for q, rate, maturity in cases:
        resolution, answer = _turn(q, h)
        assert "Dünya Katılım" in resolution.resolved_question
        assert "araç değeri" in resolution.resolved_question.casefold()
        assert rate in answer
        assert maturity in answer


def test_composite_turkish_amount_parser_handles_million_plus_thousand():
    amount, maturity = parse_amount_and_maturity("1 milyon 500 bin TL araç için?")
    assert amount == 1_500_000
    assert maturity is None


def test_campaign_detail_followups_keep_same_ziraat_teknosa_campaign():
    h = []
    _turn("Ziraat Katılım Teknosa kampanyasında kaç taksit var?", h)
    r2, a2 = _turn("Ne zamana kadar geçerli?", h)
    assert "Teknosa" in r2.resolved_question
    assert "2026-08-31" in a2
    assert "Türkiye Finans" not in a2

    r3, a3 = _turn("şartı ne", h)
    assert "Teknosa" in r3.resolved_question
    assert "Yararlanma koşulları" in a3
    assert "Bankkart" in a3
    assert "Türkiye Finans" not in a3


def test_rate_intent_switch_keeps_sigortali_qualifier():
    h = []
    _turn("Türkiye Finans sigortalı taşıt finansmanında tahsis ücreti ne?", h)
    r2, a2 = _turn("Peki kar payı?", h)
    assert "sigortalı" in r2.resolved_question.casefold()
    assert "Sigortasız" not in a2
    assert "**Sigortalı:**" in a2

    _, a3 = _turn("36 ay", h)
    assert "**Sigortalı · 36 ay:**" in a3
    assert "Sigortasız" not in a3


def test_explicit_product_switch_keeps_bank_but_drops_old_housing_family():
    h = []
    _turn("Vakıf Katılım konut finansmanı nasıl?", h)
    _turn("500 bin için?", h)
    r3, a3 = _turn("Peki motosiklet finansmanı 600 bin TL için nasıl?", h)
    assert "Vakıf Katılım" in r3.resolved_question
    assert "motosiklet finansmanı" in r3.resolved_question.casefold()
    assert "konut" not in r3.resolved_question.casefold()
    assert "**%50**" in a3
    assert "**36 ay**" in a3

    _, a4 = _turn("24 ay olur mu?", h)
    assert "**24 ay vade** olur." in a4


def test_explicit_bank_switch_keeps_motorcycle_subject_without_copying_vakif_product():
    h = []
    _turn("Vakıf Katılım motosiklet finansmanı nasıl?", h)
    _turn("600 bin için?", h)
    r3, a3 = _turn("Peki Ziraat Katılım'da?", h)
    assert "Ziraat Katılım" in r3.resolved_question
    assert "motosiklet finansmanı" in r3.resolved_question.casefold()
    assert "Vakıf Katılım" not in r3.resolved_question
    assert "ayrı bir **Motosiklet Finansmanı** ürünü bulamadım" in a3
    assert "Vakıf Katılım" not in a3


def test_repayment_winner_followup_reuses_last_comparison_scenario():
    h = []
    _turn("En uygun araç finansmanı hangisi?", h)
    _turn("100 bin TL 36 ay düşünüyorum", h)
    r3, a3 = _turn("En düşük geri ödeme hangisinde?", h)
    assert "100000 TL" in r3.resolved_question
    assert "36 ay" in r3.resolved_question
    assert "taşıt finansmanı" in r3.resolved_question.casefold()
    assert "**Vakıf Katılım**" in a3
    assert "**194.286,46 TL**" in a3
    assert "Vergi Ödemelerinize" not in a3


def test_missing_named_campaign_still_never_falls_back_to_unrelated_campaign():
    answer = ask_bansa("Ziraat Katılım MediaMarkt kampanyasında kaç taksit var?").text
    assert "yeterince güçlü eşleşen aktif kampanya bulamadım" in answer
    assert "PETLAS" not in answer
    assert "Teknosa'da 3 Taksit" not in answer
