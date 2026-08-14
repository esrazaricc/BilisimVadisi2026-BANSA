from pathlib import Path

from src.scraping.campaign_discovery import (
    discover_from_html,
    is_detail_candidate,
    load_bank_config,
)


CONFIG_PATH = Path("config") / "banks.json"


def turkiye_finans_config():
    banks = load_bank_config(CONFIG_PATH)
    return next(
        bank
        for bank in banks
        if bank["name"] == "Türkiye Finans"
    )


def test_turkiye_finans_has_nine_independent_sources():
    bank = turkiye_finans_config()

    assert bank["scanner_ready"] is True
    assert len(bank["campaign_sources"]) == 9
    assert len(bank["campaign_pages"]) == 9

    source_groups = {
        item["source_group"]
        for item in bank["campaign_sources"]
    }

    assert (
        "Türkiye Finans Finansman Kampanyaları"
        in source_groups
    )
    assert (
        "Türkiye Finans Ticari Kampanyalar"
        in source_groups
    )


def test_official_savings_source_is_used():
    bank = turkiye_finans_config()

    urls = {
        item["url"].casefold()
        for item in bank["campaign_sources"]
    }

    assert (
        "https://www.turkiyefinans.com.tr/tr-tr/"
        "kampanyalar/sayfalar/mevduat-kampanyalari.aspx"
    ) in urls

    assert not any(
        "birikim-fon-kampanyalari.aspx" in url
        for url in urls
    )


def test_listing_and_ended_pages_are_rejected():
    bank = turkiye_finans_config()

    rejected_urls = (
        (
            "https://www.turkiyefinans.com.tr/tr-tr/"
            "kampanyalar/sayfalar/default.aspx"
        ),
        (
            "https://www.turkiyefinans.com.tr/tr-tr/"
            "kampanyalar/sayfalar/kart-kampanyalari.aspx"
        ),
        (
            "https://www.turkiyefinans.com.tr/tr-tr/"
            "kampanyalar/sayfalar/mevduat-kampanyalari.aspx"
        ),
        (
            "https://www.turkiyefinans.com.tr/tr-tr/"
            "kampanyalar/sayfalar/biten-kampanyalar.aspx"
        ),
    )

    for url in rejected_urls:
        assert not is_detail_candidate(
            url,
            "Detaylı Bilgi",
            bank,
        )


def test_real_campaign_detail_is_accepted():
    bank = turkiye_finans_config()

    assert is_detail_candidate(
        (
            "https://www.turkiyefinans.com.tr/tr-tr/"
            "kampanyalar/Sayfalar/"
            "gunluk-hesap-vade-kampanyasi.aspx"
        ),
        "Detaylı Bilgi",
        bank,
    )


def test_standard_product_page_is_rejected():
    bank = turkiye_finans_config()

    assert not is_detail_candidate(
        (
            "https://www.turkiyefinans.com.tr/tr-tr/"
            "bireysel/ihtiyac-finansmani/sayfalar/"
            "ihtiyac-finansmani.aspx"
        ),
        "İhtiyaç Finansmanı",
        bank,
    )


def test_html_discovery_keeps_source_group():
    bank = turkiye_finans_config()
    source = next(
        item
        for item in bank["campaign_sources"]
        if "Birikim / Fon" in item["source_group"]
    )

    source_config = {
        **bank,
        **source,
        "source_page": source["url"],
    }

    html = """
    <html><body>
      <a href="/tr-tr/kampanyalar/Sayfalar/gunluk-hesap-vade-kampanyasi.aspx">
        Detaylı Bilgi
      </a>
      <a href="/tr-tr/kampanyalar/sayfalar/mevduat-kampanyalari.aspx">
        Kategori
      </a>
      <a href="/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/ihtiyac-finansmani.aspx">
        Standart Ürün
      </a>
    </body></html>
    """

    pages = discover_from_html(
        bank=source_config,
        source_page=source["url"],
        html=html,
    )

    assert len(pages) == 1
    assert (
        pages[0].source_group
        == "Türkiye Finans Birikim / Fon Kampanyaları"
    )
