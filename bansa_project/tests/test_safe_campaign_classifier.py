from src.processing.campaign_classifier import (
    classify_campaign_record,
)


def classify(title: str, text: str):
    return classify_campaign_record(
        title=title,
        clean_text=text,
        source_group="",
    )


def test_card_installment_is_not_finance():
    result = classify(
        "Adore Mobilya’da Vade Farksız 9 Taksit",
        (
            "Kredi kartları ile 9 aya varan taksit. "
            "Menü: Alışveriş Finansmanı."
        ),
    )
    assert result.campaign_category == "card_campaign"


def test_discount_with_installment_stays_discount():
    result = classify(
        "Bella Maison'da %25 İndirim",
        (
            "%25 indirim ve vade farksız "
            "3 taksit imkanı."
        ),
    )
    assert result.campaign_category == "discount_campaign"


def test_real_finance_title_is_finance():
    result = classify(
        "Diyanet Umre Finansmanı ile 3 Taksit",
        "Vade farksız 3 taksit.",
    )
    assert result.campaign_category == "finance_campaign"


def test_ihtiyac_card_title_is_finance():
    result = classify(
        "Yeni Müşterilere Özel İhtiyaç Kart",
        (
            "100.000 TL'ye kadar %1,99 oranla "
            "12 taksit."
        ),
    )
    assert result.campaign_category == "finance_campaign"


def test_shopping_finance_title_is_finance():
    result = classify(
        "Taksitlio Alışveriş Finansmanı Fırsatı",
        "100.000 TL'ye kadar 6 taksit.",
    )
    assert result.campaign_category == "finance_campaign"


def test_hepsiburada_waits_for_verified_override():
    result = classify(
        (
            "Hepsiburada’da Yeni Müşteriye Özel "
            "Vade Farksız 50.000 TL Fırsatı"
        ),
        (
            "Kuveyt Türk Alışveriş Finansmanı ile "
            "vade farksız 9 taksit."
        ),
    )
    assert result.campaign_category == "new_customer_campaign"
