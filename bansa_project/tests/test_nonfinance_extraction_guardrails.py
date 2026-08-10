from src.extraction.comparison_field_extractor import (
    extract_audiences,
    extract_benefits,
)


def benefit_types(title, text):
    return {
        item.benefit_type
        for item in extract_benefits(title, text)
    }


def audience_labels(
    title,
    text,
    source_group="",
    campaign_category="",
):
    return {
        item.audience_label
        for item in extract_audiences(
            title,
            text,
            source_group=source_group,
            campaign_category=campaign_category,
        )
    }


def test_privileged_transfer_price_is_not_special_rate():
    types = benefit_types(
        (
            "Âlâ Kart ile Havalimanı ve VIP Transfer "
            "Hizmetinden Yararlanın!"
        ),
        "Ayrıcalıklı fiyatlarla transfer hizmeti.",
    )

    assert "special_rate" not in types


def test_actual_advantageous_fx_rate_is_special_rate():
    types = benefit_types(
        "Döviz İşlemlerine Özel Kur",
        "Döviz alım satımında avantajlı kur sunulur.",
    )

    assert "special_rate" in types


def test_common_footer_does_not_create_new_or_business_audience():
    labels = audience_labels(
        "Sinema Kampanyası",
        (
            "Dijital Bankacılık Kampanyaları "
            "Ticari Kampanyalar Müşterimiz Olun "
            "Sayfa İçeriği Sinema biletlerinde indirim."
        ),
    )

    assert "Yeni Müşteriler" not in labels
    assert "Ticari Müşteriler" not in labels


def test_happy_source_adds_card_holder_audience():
    labels = audience_labels(
        "Petidi.com İndirim Fırsatı",
        "Petidi.com alışverişinde indirim.",
        source_group=(
            "Türkiye Finans Happy Kart Kampanyaları"
        ),
    )

    assert "Happy Kart Kullanıcıları" in labels


def test_employee_finance_audiences_are_extracted():
    bank_labels = audience_labels(
        "Banka Çalışanlarına Özel İhtiyaç Finansmanı",
        "Avantajlı ihtiyaç finansmanı.",
    )
    public_labels = audience_labels(
        "Kamu Çalışanlarına Özel İhtiyaç Finansmanı",
        "Avantajlı ihtiyaç finansmanı.",
    )

    assert "Banka Çalışanları" in bank_labels
    assert "Kamu Çalışanları" in public_labels


def test_lounge_and_qualitative_miles_are_benefits():
    lounge_types = benefit_types(
        "1.400+ Lounge Noktasında Ücretsiz Konfor",
        "Ücretsiz lounge hizmetinden yararlanın.",
    )
    miles_types = benefit_types(
        "Bonuslarınız Mil Puanına Dönüşüyor",
        "Bonuslarınız Mil Puanına dönüşüyor.",
    )

    assert "free_service" in lounge_types
    assert "miles" in miles_types
