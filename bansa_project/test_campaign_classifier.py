from src.processing.campaign_classifier import (
    classify_campaign_record,
)


def test_togg_finance_overrides_atm_footer():
    result = classify_campaign_record(
        title="Togg Finansmanı",
        clean_text=(
            "Togg alımlarına özel finansman imkânı sunulur. "
            "Footer: Ortak ATM iş birlikleri ve ATM kullanım bilgileri."
        ),
        source_group="Genel Kampanyalar",
    )

    assert result.record_kind == "campaign"
    assert result.campaign_category == "finance_campaign"


def test_umre_finance_campaign_is_kept():
    result = classify_campaign_record(
        title="Şubesiz Umre Finansmanı",
        clean_text="Şubesiz başvuru ve avantajlı vade seçenekleri.",
        source_group="Genel Kampanyalar",
    )

    assert result.record_kind == "campaign"
    assert result.campaign_category == "finance_campaign"


def test_atm_title_is_service_information():
    result = classify_campaign_record(
        title="Ortak ATM İş Birlikleri",
        clean_text="ATM işlem limitleri ve kullanım bilgileri.",
        source_group="Genel Kampanyalar",
    )

    assert result.record_kind == "service_information"


def test_footer_customer_link_does_not_create_new_customer_campaign():
    result = classify_campaign_record(
        title="Akaryakıt Kampanyası",
        clean_text=(
            "1.000 TL harcamaya 100 TL Worldpuan. "
            "Footer bağlantısı: Müşteri Ol."
        ),
        source_group="World Kampanyaları",
    )

    assert result.campaign_category == "points_campaign"


def test_explicit_new_customer_campaign():
    result = classify_campaign_record(
        title="Yeni Müşterilere Özel Kampanya",
        clean_text="Yeni müşterilerimize özel 500 TL ödül.",
        source_group="Genel Kampanyalar",
    )

    assert result.campaign_category == "new_customer_campaign"


def test_plain_generic_finance_product():
    result = classify_campaign_record(
        title="Taşıt Finansmanı",
        clean_text="Ürün özellikleri ve başvuru koşulları.",
        source_group="Finansmanlar",
    )

    assert result.record_kind == "standard_product"