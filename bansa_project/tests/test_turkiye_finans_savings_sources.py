from pathlib import Path

from src.scraping.campaign_discovery import (
    discover_from_html,
    load_bank_config,
)


CONFIG_PATH = Path("config") / "banks.json"


def turkiye_finans():
    banks = load_bank_config(CONFIG_PATH)
    return next(
        bank
        for bank in banks
        if bank["name"] == "Türkiye Finans"
    )


def savings_sources():
    bank = turkiye_finans()
    return [
        source
        for source in bank["campaign_sources"]
        if source["source_group"]
        == "Türkiye Finans Birikim / Fon Kampanyaları"
    ]


def test_broken_savings_listing_is_removed():
    bank = turkiye_finans()
    urls = {
        source["url"].casefold()
        for source in bank["campaign_sources"]
    }

    assert not any(
        "mevduat-kampanyalari.aspx" in url
        for url in urls
    )


def test_two_direct_savings_campaign_sources_exist():
    sources = savings_sources()

    assert len(sources) == 2
    assert {
        source["url"]
        for source in sources
    } == {
        (
            "https://www.turkiyefinans.com.tr/tr-tr/"
            "kampanyalar/Sayfalar/"
            "gunluk-hesap-vade-kampanyasi.aspx"
        ),
        (
            "https://www.turkiyefinans.com.tr/tr-tr/"
            "kampanyalar/Sayfalar/"
            "katilim-hesabi-kampanyasi.aspx"
        ),
    }


def test_direct_sources_use_single_listing_page_mode():
    for source in savings_sources():
        assert (
            source["discovery_mode"]
            == "single_listing_page"
        )
        assert source["render_mode"] == "requests"


def test_direct_daily_campaign_is_returned_as_source_itself():
    bank = turkiye_finans()
    source = next(
        item
        for item in savings_sources()
        if "gunluk-hesap" in item["url"]
    )
    source_config = {
        **bank,
        **source,
        "source_page": source["url"],
    }

    pages = discover_from_html(
        bank=source_config,
        source_page=source["url"],
        html="<html><body>Günlük Hesap Kampanyası</body></html>",
    )

    assert len(pages) == 1
    assert pages[0].url.endswith(
        "/gunluk-hesap-vade-kampanyasi.aspx"
    )
    assert (
        pages[0].source_group
        == "Türkiye Finans Birikim / Fon Kampanyaları"
    )


def test_turkiye_finans_now_has_twelve_sources():
    bank = turkiye_finans()

    assert len(bank["campaign_sources"]) == 12
