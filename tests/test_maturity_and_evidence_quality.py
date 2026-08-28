from src.extraction.comparison_field_extractor import (
    extract_finance_fields,
    extract_grace_period_months,
    extract_maturities,
)


def test_practical_card_maturity_excludes_deferral():
    text = (
        "250 TL-40.000 TL (3 ay ertelemeli) 1-6 ay vade %0 "
        "40.001-150.000 TL (3 ay ertelemeli) 7-12 ay vade "
        "250-150.000 TL 13-36 ay vade."
    )

    minimum, maximum, display = extract_maturities(text)

    assert minimum == 1
    assert maximum == 36
    assert display == "1-36 ay"


def test_practical_card_grace_period():
    text = (
        "3 ay ertelemeli finansman ve 36 aya varan vade "
        "imkânı."
    )

    assert extract_grace_period_months(text) == 3


def test_support_campaign_has_six_month_maturity():
    text = (
        "%0 kâr paylı 40.000 TL'ye kadar, 3 aya varan "
        "ödemesiz dönem ve 4 taksit. Vade: 6 aya kadar."
    )

    result = extract_finance_fields(
        "Vade Farksız 140.000 TL’ye Varan Destek!",
        text,
    )

    assert result.maturity_min_months == 6
    assert result.maturity_max_months == 6
    assert result.maturity_text == "6 aya kadar"
    assert result.grace_period_months == 3


def test_payini_sen_sec_advantage_prefers_specific_benefit():
    result = extract_finance_fields(
        "Payını Sen Seç Finansmanı",
        (
            "Yeni model ile ödeme planınızı kendiniz belirleyin. "
            "Ne kadar peşinat ödemek isterseniz, kâr oranınız "
            "o kadar düşer ve finansman süreciniz daha "
            "avantajlı hale gelir. "
            "Konut ve taşıt finansmanları için hazır kampanya "
            "fırsatlarımız bulunuyor."
        ),
    )

    assert result.campaign_advantage is not None
    assert "peşinat" in result.campaign_advantage.casefold()
    assert "kâr oranınız" in result.campaign_advantage.casefold()


def test_practical_card_advantage_avoids_campaign_conditions():
    result = extract_finance_fields(
        "Dijital Müşterilere Özel Pratik Finansman Kart",
        (
            "Pratik Finansman Kart Finansman Kampanyası Koşulları "
            "kampanyaya başvurabilecektir. "
            "Vade farksız, azami 40.000 TL limitli, 3 aya "
            "varan ödemesiz dönem ve toplam 6 aya varan "
            "vade imkânı sunulur."
        ),
    )

    assert result.campaign_advantage is not None
    assert "vade farksız" in result.campaign_advantage.casefold()
    assert "kampanya koşulları" not in (
        result.campaign_advantage.casefold()
    )
