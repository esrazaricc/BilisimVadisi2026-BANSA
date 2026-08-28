from src.classification.campaign_detector import classify_page


def test_campaign_page():
    result = classify_page(
        "Yeni Müşteri Kampanyası",
        "Yeni müşterilere özel %10 iade kampanyası 31 Aralık 2026 tarihine kadar geçerlidir.",
    )

    assert result["is_campaign"] is True
    assert result["page_type"] == "campaign"


def test_standard_product_page():
    result = classify_page(
        "Taşıt Finansmanı",
        "Araç değerinin belirli oranına kadar finansman sağlanır. Gerekli belgeler ve finansman hesaplama aracı bulunmaktadır.",
    )

    assert result["is_campaign"] is False
    assert result["page_type"] == "standard_product"
