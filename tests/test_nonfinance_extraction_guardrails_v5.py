from src.extraction.comparison_field_extractor import (
    extract_audiences,
    extract_benefits,
)


def benefit_items(title, text):
    return extract_benefits(title, text)


def audience_items(
    title,
    text,
    source_group="",
    campaign_category="",
):
    return extract_audiences(
        title,
        text,
        source_group=source_group,
        campaign_category=campaign_category,
    )


def test_passport_fee_extracts_three_installments():
    items = benefit_items(
        "Pasaport Harcı Ödemelerinize Kâr Paysız Taksit!",
        (
            "Happy Bonus Kredi Kartı ile Pasaport Harcı "
            "Ödemelerinize Kâr Paysız 3 ay "
            "taksitlendirilebilecektir."
        ),
    )

    installments = [
        item
        for item in items
        if item.benefit_type == "installment"
    ]

    assert len(installments) == 1
    assert installments[0].description == "3 taksit"


def test_assistance_services_targets_ala_card_holders():
    items = audience_items(
        "Asistanlık Hizmetleri",
        (
            "Âlâ Kart yaşamınızın her anında size destek "
            "olacak Asistanlık hizmetleri sunuyor."
        ),
        source_group="Türkiye Finans Âlâ Kart Kampanyaları",
    )

    labels = {
        item.audience_label
        for item in items
    }

    assert "Âlâ Kart Sahipleri" in labels


def test_yolcu360_targets_individual_ala_card_holders():
    items = audience_items(
        "Yolcu360’da Araç Kiralamak Daha Avantajlı!",
        (
            "Kampanyaya Bireysel Âlâ ve ek kartlar "
            "dahildir."
        ),
        source_group="Türkiye Finans Âlâ Kart Kampanyaları",
    )

    labels = {
        item.audience_label
        for item in items
    }

    assert "Bireysel Âlâ Kart Sahipleri" in labels


def test_ala_bes_targets_ala_banking_customers():
    items = audience_items(
        (
            "Âlâ Müşterilere Özel Âlâ BES ile "
            "Geleceğe Yatırım Yapın!"
        ),
        (
            "Türkiye Finans Katılım Bankası'nın özel "
            "müşterileri için tasarlanmıştır."
        ),
        source_group="Türkiye Finans Âlâ Kart Kampanyaları",
        campaign_category="insurance_campaign",
    )

    result = {
        item.audience_type: item.audience_label
        for item in items
    }

    assert result["premium_customer"] == (
        "Âlâ Bankacılık Müşterileri"
    )


def test_ala_hgs_targets_ala_card_holders():
    items = audience_items(
        (
            "Âlâ ile HGS alarak vereceğiniz HGS "
            "talimatına 700 TL Bonus!"
        ),
        (
            "Âlâ Kart ile HGS etiketi alıp HGS talimatı "
            "vererek 700 TL Bonus kazanın."
        ),
        source_group="Türkiye Finans Âlâ Kart Kampanyaları",
    )

    labels = {
        item.audience_label
        for item in items
    }

    assert "Âlâ Kart Sahipleri" in labels
