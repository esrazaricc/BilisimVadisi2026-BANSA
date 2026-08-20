from src.scraping import campaign_discovery
from src.scraping.browser_renderer import RenderResult


class ClientThatMustNotBeUsed:
    def get(self, url: str):
        raise AssertionError("Selenium bankasında requests kullanılmamalı")


def test_selenium_rendered_html_is_used(monkeypatch):
    bank = {
        "name": "Albaraka Türk",
        "base_url": "https://www.albaraka.com.tr",
        "campaign_pages": [
            "https://www.albaraka.com.tr/tr/kampanyalar"
        ],
        "detail_paths": ["/tr/kampanyalar/detay/"],
        "exclude_paths": [],
        "discovery_mode": "detail_links",
        "render_mode": "selenium",
        "load_more_terms": ["Daha Fazla Kampanya Göster"],
        "reference_visible_count": 3,
    }

    html = """
      <a href='/tr/kampanyalar/detay/bir'>Bir</a>
      <a href='/tr/kampanyalar/detay/iki'>İki</a>
      <a href='/tr/kampanyalar/detay/uc'>Üç</a>
    """

    monkeypatch.setattr(
        campaign_discovery,
        "render_dynamic_page",
        lambda *args, **kwargs: RenderResult(
            url="https://www.albaraka.com.tr/tr/kampanyalar",
            html=html,
            load_more_clicks=4,
            detail_link_count=3,
            reached_click_limit=False,
        ),
    )

    pages, errors, diagnostics = (
        campaign_discovery.discover_bank_pages(
            bank,
            ClientThatMustNotBeUsed(),
        )
    )

    assert len(pages) == 3
    assert errors == []
    assert diagnostics[0].load_more_clicks == 4
    assert diagnostics[0].completeness_status == "COMPLETE_OR_HIGHER"


def test_below_reference_count_is_reported(monkeypatch):
    bank = {
        "name": "Albaraka Türk",
        "base_url": "https://www.albaraka.com.tr",
        "campaign_pages": [
            "https://www.albaraka.com.tr/tr/kampanyalar"
        ],
        "detail_paths": ["/tr/kampanyalar/detay/"],
        "exclude_paths": [],
        "discovery_mode": "detail_links",
        "render_mode": "selenium",
        "load_more_terms": ["Daha Fazla Kampanya Göster"],
        "reference_visible_count": 52,
    }

    monkeypatch.setattr(
        campaign_discovery,
        "render_dynamic_page",
        lambda *args, **kwargs: RenderResult(
            url="https://www.albaraka.com.tr/tr/kampanyalar",
            html="<a href='/tr/kampanyalar/detay/bir'>Bir</a>",
            load_more_clicks=1,
            detail_link_count=1,
            reached_click_limit=False,
        ),
    )

    _, _, diagnostics = campaign_discovery.discover_bank_pages(
        bank,
        ClientThatMustNotBeUsed(),
    )

    assert diagnostics[0].completeness_status == "BELOW_REFERENCE_COUNT"

