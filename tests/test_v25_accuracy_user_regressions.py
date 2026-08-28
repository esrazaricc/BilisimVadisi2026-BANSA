from src.competition_fast_router import detect_banks
from src.v25_accuracy_layer import answer_accuracy_first
from src.chat_followup_context import resolve_followup_question


def _text(q: str) -> str:
    out = answer_accuracy_first(q)
    assert out is not None, q
    return out.text


def test_generic_all_banks_does_not_fuzzy_match_tom_or_dunya():
    assert detect_banks("Konut finansmanı sunan bütün katılım bankalarını ve ürünlerini göster") == ()


def test_tf_vehicle_variant_compare_uses_published_rate_table():
    t = _text("Türkiye Finans sigortalı ve sigortasız taşıt finansmanını karşılaştır.")
    assert "%3,48" in t
    assert "%4,08" in t
    assert "%0,50" in t


def test_all_housing_catalog_lists_products_without_amount_clarification():
    t = _text("Konut finansmanı sunan bütün katılım bankalarını ve ürünlerini göster")
    assert "Albaraka Türk" in t and "Dünya Katılım" in t and "Ziraat Katılım" in t
    assert "19 ürün" in t
    assert "Önce finansman tutarı" not in t


def test_general_two_bank_housing_compare_does_not_require_scenario():
    t = _text("Albaraka Türk ile Dünya Katılım konut finansmanını karşılaştır.")
    assert "genel koşul karşılaştırması" in t
    assert "Albaraka Türk" in t and "Dünya Katılım" in t
    assert "Önce finansman tutarı" not in t


def test_first_home_max_ltv_answers_the_actual_superlative():
    t = _text("İlk konut alacağım. Konut değerine göre en yüksek finansman oranı hangi bankada?")
    assert "%90" in t
    assert "5 milyon" in t
    assert "Tek bir banka" in t


def test_housing_fee_question_returns_fees_not_rate_table():
    t = _text("Konut finansmanında tahsis ücreti, ekspertiz ve ipotek masraflarını karşılaştır.")
    assert "tahsis / ekspertiz / ipotek" in t
    assert "Türkiye Finans" in t
    assert "16.500 TL" in t
    assert "Ziraat Katılım" in t
    assert "Azami vade | Fiyatlama" not in t


def test_dunya_600k_vehicle_value_returns_50pct_300k_36m():
    t = _text("Dünya Katılım araç finansmanında 600.000 TL değerindeki ikinci el araç için en fazla ne kadar finansman kullanılabilir ve vade kaç ay olur?")
    assert "%50" in t
    assert "300.000,00 TL" in t
    assert "36 ay" in t


def test_hayat_tom_maturity_compare_does_not_request_amount():
    t = _text("Hayat Finans Bana Bunu Al ile TOM Mağazadan Alışveriş finansmanını vade açısından karşılaştır")
    assert "18 ay" in t
    assert "36 aya kadar" in t
    assert "bilgisayar" in t.lower() and "12 taksit" in t
    assert "Önce finansman tutarı" not in t


def test_shopping_catalog_is_curated_9_banks_without_false_electronic_products():
    t = _text("Alışveriş finansmanı için hangi bankaların hangi ürünleri kullanılabilir?")
    for bank in ["Albaraka Türk", "Dünya Katılım", "Hayat Finans", "Kuveyt Türk", "T.O.M. Katılım", "Türkiye Emlak Katılım", "Türkiye Finans", "Vakıf Katılım", "Ziraat Katılım"]:
        assert bank in t
    assert "Kapsam:** 9 banka" in t
    assert "Elektronik Teminat Mektubu" not in t
    assert "ELÜS" not in t
    assert "Leasing" not in t


def test_laptop_50k_returns_multiple_relevant_banks_only():
    t = _text("50.000 TL laptop almak istiyorum. Katılım bankalarında hangi finansman seçeneklerim var?")
    for bank in ["Albaraka Türk", "Dünya Katılım", "Hayat Finans", "Kuveyt Türk", "T.O.M. Katılım", "Türkiye Emlak Katılım", "Türkiye Finans", "Vakıf Katılım", "Ziraat Katılım"]:
        assert bank in t
    assert "Bilgisayar Finansmanı" in t
    assert "Dayanıklı Tüketim Finansmanı" in t
    assert "Elektronik Teminat Mektubu" not in t
    assert "ELÜS" not in t
    assert "Leasing" not in t


def test_need_100k_36_eligibility_has_current_explicit_rules():
    t = _text("100.000 TL 36 ay ihtiyaç finansmanında hangi katılım bankaları seçenek sunuyor?")
    assert "Dünya Katılım" in t
    assert "Türkiye Finans" in t
    assert "Vakıf Katılım" in t
    assert "125.000 TL ve altında azami 36 ay" in t
    assert "Amaca özel" in t


def test_technology_campaign_question_lists_multiple_offers():
    t = _text("Şu anda aktif kampanyalarda teknoloji veya elektronik alışverişine yönelik fırsatlar var mı?")
    assert "İlk 10" in t
    assert "Dünya Katılım" in t
    assert "Türkiye Emlak Katılım" in t
    assert t.count("[Kaynak]") >= 5


def test_enerya_minimum_maturity_followup_inherits_latest_subject():
    r = resolve_followup_question(
        "Peki minimum vadesi ne?",
        [
            "Hayat Finans Bana Bunu Al ile TOM Mağazadan Alışveriş finansmanını vade açısından karşılaştır",
            "Dünya Katılım Enerya Karz-ı Hasen ürününün özellikleri ve vadesi nedir?",
        ],
    )
    assert r.used_context
    assert "Enerya" in r.resolved_question
    assert "minimum vadesi" in r.resolved_question


def test_self_contained_laptop_query_does_not_inherit_previous_bank_pair():
    r = resolve_followup_question(
        "50.000 TL laptop almak istiyorum. Katılım bankalarında hangi finansman seçeneklerim var?",
        [
            "Hayat Finans Bana Bunu Al ile TOM Mağazadan Alışveriş finansmanını vade açısından karşılaştır",
            "Alışveriş finansmanı için hangi bankaların hangi ürünleri kullanılabilir?",
        ],
    )
    assert not r.used_context
    assert "Hayat Finans ile T.O.M." not in r.resolved_question
    t = _text(r.resolved_question)
    assert "Albaraka Türk" in t and "Dünya Katılım" in t and "Vakıf Katılım" in t
    assert "Bilgisayar Finansmanı" in t


def test_broad_need_bank_query_does_not_inherit_previous_single_bank():
    r = resolve_followup_question(
        "100.000 TL 36 ay ihtiyaç finansmanında hangi katılım bankaları seçenek sunuyor?",
        ["Türkiye Finans sigortalı ve sigortasız taşıt finansmanını karşılaştır."],
    )
    assert not r.used_context
    assert r.resolved_question.startswith("100.000 TL")
    assert not r.resolved_question.startswith("Türkiye Finans -")


def test_all_housing_catalog_query_does_not_inherit_previous_single_bank():
    r = resolve_followup_question(
        "Konut finansmanı sunan bütün katılım bankalarını ve ürünlerini göster",
        ["Türkiye Finans sigortalı ve sigortasız taşıt finansmanını karşılaştır."],
    )
    assert not r.used_context
    assert r.resolved_question.startswith("Konut finansmanı")
