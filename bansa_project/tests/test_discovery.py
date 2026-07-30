from src.scraping import campaign_discovery


def test_only_campaign_detail_links_are_returned(monkeypatch):
    html = """
    <html><body>
      <a href="/tr/kampanyalar/detay/egitim-kampanyasi-1">Eğitim Kampanyası</a>
      <a href="/tr/world-dunyasi/detay/market-kampanyasi">Market Kampanyası</a>
      <a href="/tr/bireysel/finansmanlar/tasit-finansmani">Taşıt Finansmanı</a>
      <a href="https://ornek.com/kampanya">Başka site</a>
    </body></html>
    """

    monkeypatch.setattr(campaign_discovery, "_download_html", lambda url: html)

    bank = {
        "base_url": "https://www.albaraka.com.tr",
        "campaign_pages": ["https://www.albaraka.com.tr/tr/kampanyalar"],
        "detail_paths": [
            "/tr/kampanyalar/detay/",
            "/tr/world-dunyasi/detay/",
        ],
    }

    links = campaign_discovery.discover_campaign_links(bank)

    assert len(links) == 2
    assert all("/detay/" in item["url"] for item in links)
