from src.scraping.campaign_discovery import (
    canonicalize_url,
    discover_from_html,
    is_detail_candidate,
)


ALBARAKA = {
    "name": "Albaraka Türk",
    "base_url": "https://www.albaraka.com.tr",
    "detail_paths": ["/tr/kampanyalar/detay/"],
    "exclude_paths": [
        "/tr/bireysel/finansmanlar/",
        "/tr/hesaplama-araclari/",
    ],
    "discovery_mode": "detail_links",
}


def test_campaign_detail_link_is_discovered():
    html = """
    <html><body>
      <a href="/tr/kampanyalar/detay/market-odulu?utm_source=test">
        Market kampanyası
      </a>
    </body></html>
    """

    pages = discover_from_html(
        bank=ALBARAKA,
        source_page="https://www.albaraka.com.tr/tr/kampanyalar",
        html=html,
    )

    assert len(pages) == 1
    assert pages[0].page_type == "campaign_detail"
    assert pages[0].url == (
        "https://albaraka.com.tr/tr/kampanyalar/detay/market-odulu"
    )


def test_standard_financing_product_is_not_discovered():
    html = """
    <a href="/tr/bireysel/finansmanlar/tasit-finansmani/">
      Taşıt Finansmanı
    </a>
    """

    pages = discover_from_html(
        bank=ALBARAKA,
        source_page="https://www.albaraka.com.tr/tr/kampanyalar",
        html=html,
    )

    assert pages == []


def test_external_domain_is_rejected():
    result = is_detail_candidate(
        "https://example.com/tr/kampanyalar/detay/sahte",
        "Kampanya",
        ALBARAKA,
    )

    assert result is False


def test_canonical_url_removes_tracking_and_fragment():
    url = (
        "https://www.Albaraka.com.tr/tr/kampanyalar/detay/test/"
        "?utm_campaign=x&ref=ana#kosullar"
    )

    assert canonicalize_url(url) == (
        "https://albaraka.com.tr/tr/kampanyalar/detay/test?ref=ana"
    )


def test_single_listing_page_is_kept_when_no_detail_link_exists():
    bank = {
        "name": "T.O.M. Katılım",
        "base_url": "https://tombank.com.tr",
        "detail_paths": [],
        "exclude_paths": ["/urunlerimiz.html"],
        "discovery_mode": "single_listing_page",
    }

    pages = discover_from_html(
        bank=bank,
        source_page="https://tombank.com.tr/kampanyalar.html",
        html="<html><body><h1>Kampanyalar</h1></body></html>",
    )

    assert len(pages) == 1
    assert pages[0].page_type == "campaign_listing_content"
