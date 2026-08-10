from pathlib import Path

from src.scraping.campaign_discovery import load_bank_config


CONFIG_PATH = Path("config") / "banks.json"


def turkiye_finans():
    banks = load_bank_config(CONFIG_PATH)
    return next(
        bank
        for bank in banks
        if bank["name"] == "Türkiye Finans"
    )


def source(group_name):
    bank = turkiye_finans()
    return next(
        item
        for item in bank["campaign_sources"]
        if item["source_group"] == group_name
    )


def test_happy_uses_selenium_for_local_ssl_chain_problem():
    item = source("Türkiye Finans Happy Kart Kampanyaları")

    assert item["render_mode"] == "selenium"
    assert item["url"] == (
        "https://www.happycard.com.tr/"
        "kampanyalar/Sayfalar/default.aspx"
    )
    assert item["base_url"] == "https://www.happycard.com.tr"


def test_ala_uses_direct_official_campaign_domain():
    item = source("Türkiye Finans Âlâ Kart Kampanyaları")

    assert item["render_mode"] == "selenium"
    assert item["url"] == (
        "https://www.turkiyefinansala.com/tr-tr/"
        "kampanyalar/Sayfalar/default.aspx"
    )
    assert item["base_url"] == (
        "https://www.turkiyefinansala.com"
    )
    assert item["detail_paths"] == [
        "/tr-tr/kampanyalar/Sayfalar/"
    ]


def test_savings_listing_uses_case_sensitive_official_url():
    item = source(
        "Türkiye Finans Birikim / Fon Kampanyaları"
    )

    assert item["url"] == (
        "https://www.turkiyefinans.com.tr/tr-tr/"
        "kampanyalar/Sayfalar/mevduat-kampanyalari.aspx"
    )


def test_all_three_sources_exist_in_campaign_pages():
    bank = turkiye_finans()
    pages = set(bank["campaign_pages"])

    assert (
        "https://www.happycard.com.tr/"
        "kampanyalar/Sayfalar/default.aspx"
    ) in pages
    assert (
        "https://www.turkiyefinansala.com/tr-tr/"
        "kampanyalar/Sayfalar/default.aspx"
    ) in pages
    assert (
        "https://www.turkiyefinans.com.tr/tr-tr/"
        "kampanyalar/Sayfalar/mevduat-kampanyalari.aspx"
    ) in pages


def test_turkiye_finans_still_has_eleven_sources():
    bank = turkiye_finans()

    assert len(bank["campaign_sources"]) == 11
