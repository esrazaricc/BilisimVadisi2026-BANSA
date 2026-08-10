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


def source_by_name(name):
    bank = turkiye_finans_config()
    return next(
        source
        for source in bank["campaign_sources"]
        if source["source_group"] == name
    )


def test_card_sources_are_separated_without_losing_business_card():
    bank = turkiye_finans_config()

    groups = {
        source["source_group"]
        for source in bank["campaign_sources"]
    }

    assert "Türkiye Finans Happy Kart Kampanyaları" in groups
    assert "Türkiye Finans Âlâ Kart Kampanyaları" in groups
    assert "Türkiye Finans Ticari Kart Kampanyaları" in groups
    assert "Türkiye Finans Kredi Kartı Kampanyaları" not in groups
    assert len(bank["campaign_sources"]) == 11


def test_happy_card_detail_is_accepted():
    bank = turkiye_finans_config()
    source = source_by_name(
        "Türkiye Finans Happy Kart Kampanyaları"
    )
    source_config = {**bank, **source}

    assert is_detail_candidate(
        (
            "https://www.happycard.com.tr/"
            "kampanyalar/Sayfalar/2026yaz.aspx"
        ),
        "Detaylı Bilgi",
        source_config,
    )

    assert not is_detail_candidate(
        (
            "https://www.happycard.com.tr/"
            "kampanyalar/Sayfalar/default.aspx"
        ),
        "Kampanyalar",
        source_config,
    )


def test_ala_card_detail_is_accepted():
    bank = turkiye_finans_config()
    source = source_by_name(
        "Türkiye Finans Âlâ Kart Kampanyaları"
    )
    source_config = {**bank, **source}

    assert is_detail_candidate(
        (
            "https://www.turkiyefinans.com.tr/tr-tr/"
            "bireysel/ala-bankacilik/Sayfalar/"
            "kampanya/23.html"
        ),
        "Kampanya Koşulları",
        source_config,
    )

    assert not is_detail_candidate(
        (
            "https://www.turkiyefinans.com.tr/tr-tr/"
            "bireysel/ala-bankacilik/Sayfalar/"
            "index.html"
        ),
        "Âlâ Bankacılık",
        source_config,
    )


def test_happy_discovery_keeps_happy_group():
    bank = turkiye_finans_config()
    source = source_by_name(
        "Türkiye Finans Happy Kart Kampanyaları"
    )
    source_config = {
        **bank,
        **source,
        "source_page": source["url"],
    }

    html = """
    <a href="/kampanyalar/Sayfalar/2026yaz.aspx">
      Happy Bonus Yaz Kampanyası
    </a>
    <a href="/kampanyalar/Sayfalar/default.aspx">
      Tüm Kampanyalar
    </a>
    """

    pages = discover_from_html(
        bank=source_config,
        source_page=source["url"],
        html=html,
    )

    assert len(pages) == 1
    assert (
        pages[0].source_group
        == "Türkiye Finans Happy Kart Kampanyaları"
    )


def test_ala_discovery_keeps_ala_group():
    bank = turkiye_finans_config()
    source = source_by_name(
        "Türkiye Finans Âlâ Kart Kampanyaları"
    )
    source_config = {
        **bank,
        **source,
        "source_page": source["url"],
    }

    html = """
    <a href="/tr-tr/bireysel/ala-bankacilik/Sayfalar/kampanya/23.html">
      Âlâ Kart ile Kâr Paysız 6 Taksit
    </a>
    <a href="/tr-tr/bireysel/ala-bankacilik/Sayfalar/index.html">
      Âlâ Bankacılık
    </a>
    """

    pages = discover_from_html(
        bank=source_config,
        source_page=source["url"],
        html=html,
    )

    assert len(pages) == 1
    assert (
        pages[0].source_group
        == "Türkiye Finans Âlâ Kart Kampanyaları"
    )
