from src.extraction.comparison_field_extractor import (
    extract_audiences,
    extract_benefits,
)


def audience_map(
    title,
    text,
    source_group="",
    campaign_category="",
):
    return {
        item.audience_type: item.audience_label
        for item in extract_audiences(
            title,
            text,
            source_group=source_group,
            campaign_category=campaign_category,
        )
    }


def benefit_types(title, text):
    return {
        item.benefit_type
        for item in extract_benefits(title, text)
    }


def test_unrelated_card_page_is_not_business_customer():
    result = audience_map(
        "Okul Ödemelerinize Kâr Paysız Taksit!",
        (
            "KOBİ ve ticari bankacılık bağlantıları footer "
            "alanında yer alır."
        ),
        source_group=(
            "Türkiye Finans Happy Kart Kampanyaları"
        ),
    )

    assert "business_customer" not in result
    assert "card_holder" in result


def test_existing_and_new_employee_finance_is_not_new_only():
    bank_result = audience_map(
        "Banka Çalışanlarına Özel İhtiyaç Finansmanı",
        (
            "Mevcut ve yeni müşterilerimiz kampanyadan "
            "yararlanabilir."
        ),
    )
    public_result = audience_map(
        "Kamu Çalışanlarına Özel İhtiyaç Finansmanı",
        (
            "Mevcut ve yeni müşterilerimiz kampanyadan "
            "yararlanabilir."
        ),
    )

    assert "new_customer" not in bank_result
    assert "new_customer" not in public_result
    assert "bank_employee" in bank_result
    assert "public_employee" in public_result


def test_new_customer_category_is_preserved():
    result = audience_map(
        "TÜSHAD Üyeleri Âlâ Bankacılık Dünyası",
        "TUSHAD koduyla müşteri olanlara özel.",
        campaign_category="new_customer_campaign",
    )

    assert "new_customer" in result
    assert result["association_member"] == "TÜSHAD Üyeleri"


def test_health_package_is_profession_group_not_new_only():
    result = audience_map(
        "Sağlık Meslek Paketi Avantajları",
        (
            "Hem mevcut hem yeni doktor, diş hekimi, "
            "hemşire ve eczacılar yararlanabilir."
        ),
        campaign_category="other_campaign",
    )

    assert "new_customer" not in result
    assert result["profession_group"] == (
        "Sağlık Meslek Mensupları"
    )


def test_daily_account_has_new_and_individual_audience():
    result = audience_map(
        "Günlük Hesap’la İhtiyaç Anında Vadeni Bozma!",
        "İlk kez Günlük Hesap açan yeni müşteriler.",
        campaign_category="other_campaign",
    )

    assert "new_customer" in result
    assert "individual_customer" in result


def test_ala_source_alone_does_not_force_card_holder():
    result = audience_map(
        "Genel Âlâ Bankacılık Ayrıcalıkları",
        "Âlâ müşterilerine özel genel bankacılık hizmetleri.",
        source_group="Türkiye Finans Âlâ Kart Kampanyaları",
    )

    assert "card_holder" not in result


def test_qualitative_benefits_are_title_led():
    installment_types = benefit_types(
        "Okul Ödemelerinize Kâr Paysız Taksit!",
        (
            "İlgili kampanyalar arasında lounge, "
            "GastroClub ve Fast Track bulunmaktadır."
        ),
    )
    lounge_types = benefit_types(
        "1.400+ Lounge Noktasında Ücretsiz Konfor",
        "Ücretsiz lounge hizmeti.",
    )

    assert "privilege" not in installment_types
    assert "membership" not in installment_types
    assert "free_service" not in installment_types
    assert "free_service" in lounge_types
