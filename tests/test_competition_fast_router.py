from src.competition_fast_router import (
    answer_fast,
    detect_banks,
    should_replace_failure_text,
)


def test_vakif_motosiklet_typo_returns_48_months():
    result = answer_fast("vakf katlm motosklet finansmani maksimum kac ay vade")
    assert result is not None
    assert "48 ay" in result.text
    assert "Vakıf Katılım" in result.text


def test_albaraka_needs_returns_36_months():
    result = answer_fast("Albaraka Türk İhtiyaç Finansmanı en fazla kaç ay vade sunuyor?")
    assert result is not None
    assert "36 ay" in result.text
    assert "İhtiyaç Finansmanı" in result.text


def test_typo_turkiye_finans_detected():
    assert "Türkiye Finans" in detect_banks("türkşye finans ihtiyac finansmani")


def test_housing_comparison_never_raw_unverified():
    result = answer_fast("Konut finansmanında Vakıf Katılım mı Türkiye Finans mı daha avantajlı?")
    assert result is not None
    assert "UNVERIFIED" not in result.text.upper()
    assert "Vakıf Katılım" in result.text
    assert "Türkiye Finans" in result.text
    assert "Konut Finansmanı" in result.text


def test_tf_75000_24_uses_verified_local_variants():
    result = answer_fast("75000 TL 24 ay Türkiye Finans ihtiyaç finansmanını hesapla")
    assert result is not None
    assert "%4,05" in result.text
    assert "5.576,28 TL" in result.text
    assert "%5,95" in result.text
    assert "6.966,60 TL" in result.text


def test_kuveyt_100000_36_housing_exact_snapshot():
    result = answer_fast("100000 TL 36 ay Kuveyt Türk konut finansmanı hesapla")
    assert result is not None
    assert "%3,56" in result.text
    assert "4.971,02 TL" in result.text
    assert "178.956,33 TL" in result.text


def test_campaign_typo_lists_current_campaigns():
    result = answer_fast("kuveytturk kampanyalrini ver")
    assert result is not None
    assert result.route == "campaign_search"
    assert "Kuveyt Türk" in result.text
    assert "Resmî kaynak" in result.text


def test_fee_missing_is_explicit_not_zero():
    result = answer_fast("Türkiye Finans ihtiyaç finansmanı ekspertiz ücreti nedir?")
    assert result is not None
    assert "Resmî kaynakta belirtilmemiş" in result.text
    assert "0 TL" not in result.text


def test_known_albaraka_appraisal_example_is_grounded():
    result = answer_fast("Albaraka konut ekspertiz ücreti nedir?")
    assert result is not None
    assert "23.642,27 TL" in result.text
    assert "doğrulanmış" in result.text.casefold()


def test_raw_failure_markers_are_detected():
    assert should_replace_failure_text("Doğrulanmış kaynaklardan güvenli bir yanıt oluşturulamadı.")
    assert should_replace_failure_text("UNVERIFIED")



def test_gree_without_campaign_word_routes_to_specific_campaign():
    result = answer_fast("gree klimada kac taksit imkani var")
    assert result is not None
    assert result.route == "campaign_detail"
    assert "Gree" in result.text
    assert "12 taksit" in result.text
    assert "Finansman Kataloğu" not in result.text


def test_shipentegra_detail_does_not_dump_all_kuveyt_campaigns():
    result = answer_fast("Kuveyt Türk E-İhracatçılara Özel ShipEntegra kampanyasının avantajları nedir")
    assert result is not None
    assert result.route == "campaign_detail"
    assert "ShipEntegra" in result.text
    assert "3 taksit" in result.text
    assert "Monster Notebook" not in result.text


def test_albaraka_needs_scenario_shows_canonical_product_only():
    result = answer_fast("Albaraka Türk'te 100.000 TL 24 ay ihtiyaç finansmanı için ne sunuluyor?")
    assert result is not None
    assert "**İhtiyaç Finansmanı**" in result.text
    assert "BES Teminatlı Finansman" not in result.text
    assert "Eğitim Finansmanı" not in result.text


def test_vakif_motorcycle_scenario_explains_maturity_and_amount_limits():
    result = answer_fast("Vakıf Katılım'dan 600.000 TL motosiklet finansmanı 24 ay kullanabilir miyim?")
    assert result is not None
    assert "Motosiklet Finansmanı" in result.text
    assert "24 ay" in result.text
    assert "48 aylık azami vade" in result.text
    assert "tutar uygunluğu kesinleştirilemiyor" in result.text
