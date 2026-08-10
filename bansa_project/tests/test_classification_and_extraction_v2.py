from src.extraction.comparison_field_extractor import (
    detect_finance_type,
    extract_allocation_fee,
    extract_finance_fields,
)
from src.processing.campaign_classifier import (
    classify_campaign_record,
)


def classify(title, body):
    return classify_campaign_record(
        title=title,
        clean_text=body,
        source_group="Genel Kampanyalar",
    )


def test_card_title_is_not_finance_due_to_footer():
    result = classify(
        "Dyson Harcamalarınızda World'e Özel 9 Taksit Fırsatı!",
        (
            "World kart ile 9 taksit. Footer: konut finansmanı, "
            "taşıt finansmanı ve işyeri finansmanı."
        ),
    )
    assert result.campaign_category == "card_campaign"


def test_education_installment_is_card_campaign():
    result = classify(
        "Eğitim Harcamalarınıza Vade Farksız 6 Taksit Kampanyası",
        "World kart ile eğitim harcamalarınıza 6 taksit.",
    )
    assert result.campaign_category == "card_campaign"


def test_togg_is_finance_campaign():
    result = classify(
        "Togg Finansmanı",
        "Togg için 48 aya kadar vade.",
    )
    assert result.campaign_category == "finance_campaign"


def test_mixed_zero_profit_campaign_is_finance():
    result = classify(
        "Vade Farksız 140.000 TL’ye Varan Destek!",
        (
            "Yeni müşteriler %0 kâr payı ile 40.000 TL’ye "
            "kadar Pratik Finansman Kart kullanabilir."
        ),
    )
    assert result.campaign_category == "finance_campaign"


def test_finance_type_uses_title_not_footer():
    result = detect_finance_type(
        "Dijital Müşterilere Özel Pratik Finansman Kart",
        (
            "Footer: konut finansmanı ve taşıt finansmanı. "
            "Pratik Finansman Kart avantajı."
        ),
    )
    assert result == "İhtiyaç Finansmanı"


def test_mixed_home_vehicle_type():
    result = detect_finance_type(
        "Dijitale Özel Konut ve Taşıt Finansmanı Kampanyası",
        "Konut ve taşıt ihtiyaçları için.",
    )
    assert result == "Konut ve Taşıt Finansmanı"


def test_zero_profit_and_amount_extraction():
    result = extract_finance_fields(
        "Vade Farksız 140.000 TL’ye Varan Destek!",
        (
            "Şimdi Albaraka Mobil’den müşteri olanlar, %0 kâr "
            "payı ile 40.000 TL’ye kadar Pratik Finansman Kart "
            "kullanabiliyor."
        ),
    )
    assert result.profit_share_rate_min == 0
    assert result.financing_amount_max == 40000
    assert result.finance_type == "İhtiyaç Finansmanı"


def test_allocation_fee_does_not_capture_unrelated_rate():
    amount, rate, status = extract_allocation_fee(
        (
            "Tahsis ücreti hakkında bilgi için sözleşmeye bakınız. "
            "Kâr payı oranı %1,99'dur."
        )
    )
    assert amount is None
    assert rate is None
    assert status is None


def test_advantage_removes_boilerplate():
    result = extract_finance_fields(
        "Taksitlio.com Alışveriş Finansmanı",
        (
            "Albaraka Mobil Mobil Bankacılık Aç "
            "Taksitlio.com Alışveriş Finansmanı "
            "Kampanya Başlangıç ve Bitiş "
            "01.01.2026 - 31.12.2026 "
            "Müşteri Ol Müşteri Ol "
            "Albaraka Türk ve Taksitlio.com iş birliği ile "
            "avantajlı alışveriş finansmanı fırsatı."
        ),
    )
    assert result.campaign_advantage is not None
    assert "Müşteri Ol Müşteri Ol" not in result.campaign_advantage
    assert "Mobil Bankacılık Aç" not in result.campaign_advantage
