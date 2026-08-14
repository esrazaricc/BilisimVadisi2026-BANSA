from src.processing.campaign_classifier import (
    classify_campaign_record,
)


def test_source_group_does_not_force_campaign():
    result = classify_campaign_record(
        title="Ortak ATM İş Birlikleri",
        clean_text=(
            "Müşteriler ortak ATM ağı üzerinden işlem yapabilir. "
            "İşlem limitleri ve kullanım bilgileri açıklanmıştır."
        ),
        source_group="Genel Kampanyalar",
    )

    assert result.record_kind == "service_information"
    assert result.comparison_eligible is False


def test_finance_campaign_is_still_kept():
    result = classify_campaign_record(
        title="Şubesiz Umre Finansmanı",
        clean_text=(
            "Şubesiz başvuruya özel finansman fırsatı ve "
            "avantajlı vade seçenekleri sunulmaktadır."
        ),
        source_group="Genel Kampanyalar",
    )

    assert result.record_kind == "campaign"
    assert result.campaign_category == "finance_campaign"


def test_plain_finance_product_is_not_forced_to_campaign():
    result = classify_campaign_record(
        title="Taşıt Finansmanı",
        clean_text=(
            "Taşıt finansmanı başvurusu ve ürün özellikleri."
        ),
        source_group="Genel Kampanyalar",
    )

    assert result.record_kind == "standard_product"
    assert result.comparison_eligible is False
