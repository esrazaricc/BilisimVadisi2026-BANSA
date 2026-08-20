from dataclasses import dataclass

from src.scraping.campaign_page_fetcher import (
    build_request_url,
    fetch_page,
    is_unexpected_home_redirect,
)


def test_kuveyt_request_uses_configured_www_host():
    result = build_request_url(
        (
            "https://kuveytturk.com.tr/kampanyalar/"
            "kendim-icin/kart-kampanyalari/test-kampanya"
        ),
        {
            "base_url": "https://www.kuveytturk.com.tr",
        },
    )

    assert result == (
        "https://www.kuveytturk.com.tr/kampanyalar/"
        "kendim-icin/kart-kampanyalari/test-kampanya"
    )


def test_request_url_preserves_query():
    result = build_request_url(
        (
            "https://kuveytturk.com.tr/kampanyalar/test"
            "?source=mobile"
        ),
        {
            "base_url": "https://www.kuveytturk.com.tr",
        },
    )

    assert result.endswith(
        "/kampanyalar/test?source=mobile"
    )


def test_albaraka_uses_its_configured_host():
    result = build_request_url(
        "https://albaraka.com.tr/tr/kampanyalar/test",
        {
            "base_url": "https://www.albaraka.com.tr",
        },
    )

    assert result == (
        "https://www.albaraka.com.tr/tr/kampanyalar/test"
    )


def test_unexpected_home_redirect_detection():
    assert is_unexpected_home_redirect(
        (
            "https://www.kuveytturk.com.tr/"
            "kampanyalar/kendim-icin/test"
        ),
        "https://www.kuveytturk.com.tr/",
    )
    assert not is_unexpected_home_redirect(
        (
            "https://www.kuveytturk.com.tr/"
            "kampanyalar/kendim-icin/test"
        ),
        (
            "https://www.kuveytturk.com.tr/"
            "kampanyalar/kendim-icin/test"
        ),
    )


@dataclass
class FakeResult:
    url: str
    status_code: int = 200
    text: str = """
        <html>
          <main>
            <h1>Test Kampanyası</h1>
            <p>
              Bu kampanya metni yeterli uzunluğa sahip olmak
              için tekrar edilen açıklamalar içerir. Avantaj,
              kampanya süresi ve başvuru koşulları açıklanır.
              Bu kampanya metni yeterli uzunluğa sahiptir.
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


def test_fetch_page_calls_www_request_url():
    client = FakeClient()
    page = {
        "bank_name": "Kuveyt Türk",
        "url": (
            "https://kuveytturk.com.tr/kampanyalar/"
            "kendim-icin/kart-kampanyalari/test-kampanya"
        ),
        "source_page": "",
        "page_type": "campaign_detail",
        "discovery_mode": "detail_links",
        "source_group": "Test",
        "listing_status": "unknown",
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

    assert client.called_url.startswith(
        "https://www.kuveytturk.com.tr/"
    )
    assert snapshot.title == "Test Kampanyası"
