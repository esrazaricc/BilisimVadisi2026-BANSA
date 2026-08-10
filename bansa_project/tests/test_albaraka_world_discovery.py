from src.scraping import campaign_discovery
from src.scraping.browser_renderer import RenderResult


class ClientThatMustNotBeUsed:
    def get(self, url: str):
        raise AssertionError("Selenium kaynağında requests kullanılmamalı")


def albaraka_config():
    return {
        "name": "Albaraka Türk",
        "base_url": "https://www.albaraka.com.tr",
        "exclude_paths": [
            "/tr/bireysel/finansmanlar/",
            "/tr/hesaplama-araclari/",
        ],
        "discovery_mode": "detail_links",
        "campaign_sources": [
            {
                "source_group": "Genel Kampanyalar",
                "url": "https://www.albaraka.com.tr/tr/kampanyalar",
                "detail_paths": ["/tr/kampanyalar/detay/"],
                "render_mode": "selenium",
                "load_more_terms": ["Daha Fazla Kampanya Göster"],
                "reference_visible_count": 2,
            },
            {
                "source_group": "Albaraka World Kampanyaları",
                "url": (
                    "https://www.albaraka.com.tr/"
                    "tr/world-dunyasi/kampanyalar"
                ),
                "detail_paths": ["/tr/world-dunyasi/detay/"],
                "render_mode": "selenium",
                "load_more_terms": ["Daha Fazla Kampanya Göster"],
                "reference_visible_count": 2,
            },
        ],
    }


def test_campaign_sources_are_configured_independently():
    sources = campaign_discovery.campaign_sources(albaraka_config())

    assert len(sources) == 2
    assert sources[0]["detail_paths"] == ["/tr/kampanyalar/detay/"]
    assert sources[1]["detail_paths"] == ["/tr/world-dunyasi/detay/"]
    assert sources[0]["reference_visible_count"] == 2
    assert sources[1]["reference_visible_count"] == 2


def test_general_and_world_links_are_combined(monkeypatch):
    general_html = """
      <a href='/tr/kampanyalar/detay/genel-bir'>Genel Bir</a>
      <a href='/tr/kampanyalar/detay/genel-iki'>Genel İki</a>
      <a href='/tr/world-dunyasi/detay/yanlis-kaynak'>
        Bu bağlantı genel kaynakta alınmamalı
      </a>
    """
    world_html = """
      <a href='/tr/world-dunyasi/detay/world-bir'>World Bir</a>
      <a href='/tr/world-dunyasi/detay/world-iki'>World İki</a>
      <a href='/tr/kampanyalar/detay/yanlis-kaynak'>
        Bu bağlantı World kaynağında alınmamalı
      </a>
    """

    def fake_render(url, **kwargs):
        if "/world-dunyasi/" in url:
            return RenderResult(
                url=url,
                html=world_html,
                load_more_clicks=1,
                detail_link_count=2,
                reached_click_limit=False,
            )

        return RenderResult(
            url=url,
            html=general_html,
            load_more_clicks=1,
            detail_link_count=2,
            reached_click_limit=False,
        )

    monkeypatch.setattr(
        campaign_discovery,
        "render_dynamic_page",
        fake_render,
    )

    pages, errors, diagnostics = (
        campaign_discovery.discover_bank_pages(
            albaraka_config(),
            ClientThatMustNotBeUsed(),
        )
    )

    urls = {page.url for page in pages}

    assert errors == []
    assert len(pages) == 4
    assert (
        "https://albaraka.com.tr/tr/kampanyalar/detay/genel-bir"
        in urls
    )
    assert (
        "https://albaraka.com.tr/tr/world-dunyasi/detay/world-bir"
        in urls
    )
    assert all(
        diagnostic.completeness_status == "COMPLETE_OR_HIGHER"
        for diagnostic in diagnostics
    )


def test_world_detail_link_is_accepted():
    source = campaign_discovery.campaign_sources(
        albaraka_config()
    )[1]

    assert campaign_discovery.is_detail_candidate(
        (
            "https://www.albaraka.com.tr/tr/world-dunyasi/"
            "detay/amazon-world-kampanyasi"
        ),
        "Amazon World Kampanyası",
        source,
    )


def test_standard_product_page_is_still_rejected():
    source = campaign_discovery.campaign_sources(
        albaraka_config()
    )[0]

    assert not campaign_discovery.is_detail_candidate(
        (
            "https://www.albaraka.com.tr/tr/bireysel/"
            "finansmanlar/tasit-finansmani"
        ),
        "Taşıt Finansmanı",
        source,
    )

