import json
from dataclasses import dataclass
from pathlib import Path

from src.scraping.campaign_page_fetcher import (
    build_request_url,
    fetch_page,
    resolve_campaign_url_alias,
)


OLD_URL = (
    "https://kuveytturk.com.tr/kampanyalar/"
    "kendim-icin/kart-kampanyalari/"
    "konforda-5000-tl-indirim-ve-vade-farksiz-"
    "9-aya-varan-taksit-firsati"
)
TARGET_URL = (
    "https://milesandsmiles.kuveytturk.com.tr/kampanyalar/"
    "konforda-pesin-fiyatina-9-aya-varan-taksit-imkani-1876"
)


def write_alias_file(path: Path):
    path.write_text(
        json.dumps(
            [
                {
                    "source_url": OLD_URL,
                    "target_url": TARGET_URL,
                }
            ]
        ),
        encoding="utf-8",
    )


def test_alias_resolves_stale_konfor_url(tmp_path, monkeypatch):
    alias_path = tmp_path / "aliases.json"
    write_alias_file(alias_path)

    result = resolve_campaign_url_alias(
        OLD_URL,
        alias_path=alias_path,
    )

    assert result == TARGET_URL


def test_official_card_subdomain_is_preserved(
    tmp_path,
    monkeypatch,
):
    alias_path = tmp_path / "aliases.json"
    write_alias_file(alias_path)

    from src.scraping import campaign_page_fetcher as module

    monkeypatch.setattr(
        module,
        "DEFAULT_URL_ALIAS_PATH",
        alias_path,
    )

    # build_request_url uses the resolver's default at runtime through
    # the module constant only in production; direct subdomain should
    # always remain unchanged.
    result = build_request_url(
        TARGET_URL,
        {
            "base_url": "https://www.kuveytturk.com.tr",
        },
    )

    assert result == TARGET_URL


def test_normal_main_site_url_still_uses_www():
    source = (
        "https://kuveytturk.com.tr/kampanyalar/"
        "kendim-icin/kart-kampanyalari/test"
    )

    result = build_request_url(
        source,
        {
            "base_url": "https://www.kuveytturk.com.tr",
        },
    )

    assert result == (
        "https://www.kuveytturk.com.tr/kampanyalar/"
        "kendim-icin/kart-kampanyalari/test"
    )


@dataclass
class FakeResult:
    url: str
    status_code: int = 200
    text: str = """
    <html>
      <main>
        <h1>Konfor’da Vade Farksız 9 Aya Varan Taksit Fırsatı!</h1>
        <p>
          Kuveyt Türk Bireysel Kredi Kartları ile 31 Aralık 2026
          tarihine kadar Konfor Grubu mağazalarında peşin fiyatına
          9 aya varan taksit imkanı sunulmaktadır. Kampanyaya tüm
          bireysel kredi kartları dahildir ve koşullar geçerlidir.
        </p>
      </main>
    </html>
    """
    content_type: str = "text/html"


class FakeClient:
    def __init__(self):
        self.called_url = None

    def get(self, url):
        self.called_url = url
        return FakeResult(url=url)


def test_fetch_keeps_discovered_identity_and_uses_alias(
    tmp_path,
    monkeypatch,
):
    alias_path = tmp_path / "aliases.json"
    write_alias_file(alias_path)

    from src.scraping import campaign_page_fetcher as module

    original_loader = module.load_campaign_url_aliases

    def load_test_aliases(path=alias_path):
        return original_loader(alias_path)

    monkeypatch.setattr(
        module,
        "load_campaign_url_aliases",
        load_test_aliases,
    )

    client = FakeClient()
    page = {
        "bank_name": "Kuveyt Türk",
        "url": OLD_URL,
        "source_page": "",
        "page_type": "campaign_detail",
        "discovery_mode": "detail_links",
        "source_group": "Kart Kampanyaları",
        "listing_status": "active",
        "status_evidence": "",
    }

    snapshot = fetch_page(
        page,
        client,
        bank_config={
            "base_url": "https://www.kuveytturk.com.tr",
        },
        browser_fallback=False,
    )

    assert client.called_url == TARGET_URL
    assert snapshot.requested_url == OLD_URL
    assert snapshot.url == TARGET_URL
    assert snapshot.fetch_status == "ok"
    assert snapshot.title.startswith("Konfor")
