from src.processing.campaign_classifier import classify_campaign_record
from src.extraction.comparison_field_extractor import (
    clean_content_text,
    detect_finance_type,
    extract_finance_fields,
)
from src.scraping.campaign_page_fetcher import trim_tom_hadi_campaign_text


SOURCE = "T.O.M. Katılım / TOM Bank Hadi Kampanyaları"


def contaminated_page(main_title: str, main_body: str) -> str:
    return (
        "Hadi Hesap Hadi Krediler Veresiye Kredi Taksitli Kredi "
        "Mağazadan Alışveriş Kredisi Hemen İndir "
        f"{main_title} {main_body} "
        "İlginizi Çekebilir "
        "Hadi Black Kredi Kartı ile Restoderm’de %30 indirim! "
        "Kampanya Detayı "
        "A101’lerde süt ürünleri harcamalarında %50 Hediye Bakiye kazan! "
        "Kampanya Detayı "
        "Hadi Black Kredi Kartı ile MTV Ödemelerinde Vade Farksız 3 taksit "
        "fırsatını kaçırma! Kampanya Detayı "
        "Hadi bir T.O.M. Katılım Bankası Anonim Şirketi uygulamasıdır."
    )


def test_fetcher_strips_nav_and_related_cards():
    title = "A101’de her alışverişte %3'e varan nakit iade! | TOM Bank Hadi"
    body = contaminated_page(
        "A101’de her alışverişte %3'e varan nakit iade!",
        "Kampanya 31 Aralık 2026 tarihine kadar geçerlidir. "
        "Her alışverişte %3'e varan nakit iade kazan.",
    )
    cleaned = trim_tom_hadi_campaign_text(body, title=title)
    assert "%3'e varan nakit iade" in cleaned
    assert "MTV Ödemelerinde" not in cleaned
    assert "Mağazadan Alışveriş Kredisi Hemen İndir" not in cleaned


def test_a101_cashback_not_finance():
    title = "A101’de her alışverişte %3'e varan nakit iade! | TOM Bank Hadi"
    body = contaminated_page(
        "A101’de her alışverişte %3'e varan nakit iade!",
        "Kampanya 31 Aralık 2026 tarihine kadar geçerlidir. "
        "A101 alışverişlerinde %3'e varan nakit iade kazan.",
    )
    result = classify_campaign_record(
        title=title,
        clean_text=body,
        source_group=SOURCE,
    )
    assert result.campaign_category != "finance_campaign"


def test_health_credit_fields_and_no_related_mtv():
    title = (
        "Hadi Taksitli Sağlık Kredisi sağlık harcamalarında da yanında! "
        "| TOM Bank Hadi"
    )
    body = contaminated_page(
        "Hadi Taksitli Sağlık Kredisi sağlık harcamalarında da yanında!",
        "Kampanya eczane harcamalarında 4.99 Vade Farkıyla 3 Taksit, "
        "diğer sağlık sektörü harcamalarında 4.99 Vade Farkıyla "
        "3-6-9-12 Taksit ile sınırlıdır. "
        "Kampanya 31.12.2026 tarihinde sona erecektir.",
    )
    cleaned = clean_content_text(title, body)
    assert "MTV Ödemelerinde" not in cleaned
    assert detect_finance_type(title, cleaned) == "Sağlık Finansmanı"
    result = extract_finance_fields(title, body)
    assert result.finance_type == "Sağlık Finansmanı"
    assert result.profit_share_rate_min == 4.99
    assert result.profit_share_rate_max == 4.99
    assert result.installment_count == 12
    assert result.maturity_max_months == 12
    assert "MTV Ödemelerinde" not in (result.campaign_advantage or "")


def test_alfemo_fields():
    title = "TOM Bank Hadi'den Alfemo Kampanyası! | TOM Bank Hadi"
    body = contaminated_page(
        "TOM Bank Hadi'den Alfemo Kampanyası!",
        "31.12.2026'ya kadar Hadi Taksitli Alışveriş Kredisi ile "
        "anlaşmalı Alfemo mağazalarında vade farkı iade avantajı. "
        "1.000 TL – 150.000 TL arasındaki kredi kullandırımları için "
        "geçerlidir. 12 ay vadedeki kredilerde geçerlidir.",
    )
    result = extract_finance_fields(title, body)
    assert result.finance_type == "Alışveriş Finansmanı"
    assert result.financing_amount_min == 1000
    assert result.financing_amount_max == 150000
    assert result.maturity_max_months == 12
    assert "MTV Ödemelerinde" not in (result.campaign_advantage or "")
