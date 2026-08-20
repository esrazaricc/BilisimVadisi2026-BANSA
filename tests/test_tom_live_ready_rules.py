from datetime import date

from src.processing.campaign_classifier import classify_campaign_record
from src.scraping.campaign_page_fetcher import trim_tom_hadi_campaign_text
from src.scraping.campaign_status import evaluate_campaign_status


SOURCE = "T.O.M. Katılım / TOM Bank Hadi Kampanyaları"


def test_cashback_with_negative_veresiye_mention_is_not_finance():
    title = "A101’de her alışverişte %3'e varan nakit iade! | TOM Bank Hadi"
    body = (
        "Kampanya 31 Aralık 2026 tarihine kadar geçerlidir. "
        "A101 alışverişlerinde %3'e varan nakit iade kazanabilirsin. "
        "Hadi Kredi Kartları ile yapılan alışverişlerde %1 harcama iadesi. "
        "Hadi Veresiye kullandığın alışverişlerinde nakit iade kazanımı yoktur."
    )
    result = classify_campaign_record(
        title=title,
        clean_text=body,
        source_group=SOURCE,
    )
    assert result.campaign_category != "finance_campaign"


def test_generic_brand_credit_offer_is_finance():
    title = "TOM Bank Hadi'den Alfemo Kampanyası! | TOM Bank Hadi"
    body = (
        "31.12.2026'ya kadar Hadi Taksitli Alışveriş Kredisi ile "
        "anlaşmalı Alfemo mağazalarında vade farkı iade avantajı. "
        "1.000 TL – 150.000 TL arasındaki kredi kullandırımları için "
        "geçerlidir. 12 ay vadedeki kredilerde geçerlidir."
    )
    result = classify_campaign_record(
        title=title,
        clean_text=body,
        source_group=SOURCE,
    )
    assert result.campaign_category == "finance_campaign"


def test_hesapli_credit_vade_offer_is_finance():
    title = 'TOM Bank Hadi\'nin "Hesaplı" Kampanyası | TOM Bank Hadi'
    body = (
        "Seçili markaların bayilerinden kredi kullanan müşterilerin "
        "oluşan vade farkının iade edildiği ve uzun vadeli kredi "
        "kullanmasını sağlayan bir kampanyadır. "
        "Kredilerin güncel aylık kâr oranı %4.99’dur."
    )
    result = classify_campaign_record(
        title=title,
        clean_text=body,
        source_group=SOURCE,
    )
    assert result.campaign_category == "finance_campaign"


def test_trim_preserves_pre_title_campaign_dates():
    title = (
        "Hadi Mağazadan Alışveriş Kredisi ile Konfor Mağazalarına "
        "Özel 15 Taksit! | TOM Bank Hadi"
    )
    page = (
        "Hadi Krediler Taksitli Kredi Hemen İndir "
        "Kampanya Tarihleri 03 Ekim - 31 Aralık 2026 Image "
        "Hadi Mağazadan Alışveriş Kredisi ile Konfor Mağazalarına "
        "Özel 15 Taksit! "
        "31.12.2026'ya kadar anlaşmalı mağazalarda 15 taksit fırsatı. "
        "İlginizi Çekebilir Hadi Black Kredi Kartı ile MTV Ödemelerinde "
        "Vade Farksız 3 taksit!"
    )
    cleaned = trim_tom_hadi_campaign_text(page, title=title)
    assert "Kampanya Tarihleri 03 Ekim - 31 Aralık 2026" in cleaned
    assert "MTV Ödemelerinde" not in cleaned

    result = evaluate_campaign_status(
        text=cleaned,
        reference_date=date(2026, 8, 10),
    )
    assert result.start_date == "2026-10-03"
    assert result.end_date == "2026-12-31"
    assert result.status == "upcoming"
