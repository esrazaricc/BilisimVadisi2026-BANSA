from src.scraping.campaign_discovery import discover_from_html


BANK = {
    "name": "Albaraka Türk",
    "base_url": "https://www.albaraka.com.tr",
    "detail_paths": ["/tr/world-dunyasi/detay/"],
    "exclude_paths": [],
    "discovery_mode": "detail_links",
    "source_group": "Albaraka World Kampanyaları",
}


def test_listing_cards_are_classified():
    html = """
    <div class="campaign-card">
      <span>Bu kampanya sona ermiştir.</span>
      <a href="/tr/world-dunyasi/detay/eski">Eski Kampanya</a>
    </div>
    <div class="campaign-card">
      <span>Son 12 Gün</span>
      <a href="/tr/world-dunyasi/detay/aktif">Aktif Kampanya</a>
    </div>
    """

    pages = discover_from_html(
        bank=BANK,
        source_page=(
            "https://www.albaraka.com.tr/"
            "tr/world-dunyasi/kampanyalar"
        ),
        html=html,
    )
    by_url = {page.url: page for page in pages}

    assert by_url[
        "https://albaraka.com.tr/tr/world-dunyasi/detay/eski"
    ].listing_status == "expired"
    assert by_url[
        "https://albaraka.com.tr/tr/world-dunyasi/detay/aktif"
    ].listing_status == "active"
    assert all(
        page.source_group == "Albaraka World Kampanyaları"
        for page in pages
    )
