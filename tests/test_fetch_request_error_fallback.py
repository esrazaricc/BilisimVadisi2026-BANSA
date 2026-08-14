from types import SimpleNamespace

import pytest

from src.scraping import campaign_page_fetcher as fetcher


PAGE = {
    "bank_name": "Türkiye Finans",
    "url": (
        "https://happycard.com.tr/kampanyalar/"
        "Sayfalar/ornek-kampanya.aspx"
    ),
    "source_page": (
        "https://happycard.com.tr/kampanyalar/"
        "Sayfalar/default.aspx"
    ),
    "page_type": "campaign_detail",
    "discovery_mode": "same_folder_with_exclusions",
    "source_group": "Türkiye Finans Happy Kart Kampanyaları",
    "listing_status": "unknown",
    "status_evidence": "",
}


class FailingClient:
    def get(self, url):
        raise RuntimeError("certificate verify failed")


def valid_html():
    return """
    <html>
      <body>
        <main>
          <h1>Happy Bonus Kart Kampanyası</h1>
          <p>
            Kampanya kapsamında Happy Bonus Kart ile yapacağınız
            harcamalarda 31 Aralık 2026 tarihine kadar indirim,
            bonus ve taksit avantajlarından yararlanabilirsiniz.
          </p>
          <p>
            Kampanyaya katılım ve kullanım koşulları kampanya
            sayfasında açıklanmıştır.
          </p>
        </main>
      </body>
    </html>
    """


def fake_status(*args, **kwargs):
    return SimpleNamespace(
        start_date="",
        end_date="",
        status="unknown",
        reason="",
        evidence="",
        checked_at="2026-08-03T00:00:00+00:00",
    )


def test_request_error_uses_selenium_fallback(monkeypatch):
    monkeypatch.setattr(
        fetcher,
        "_render_fallback",
        lambda url, headless: (url, valid_html()),
    )
    monkeypatch.setattr(
        fetcher,
        "evaluate_campaign_status",
        fake_status,
    )

    snapshot = fetcher.fetch_page(
        PAGE,
        FailingClient(),
        bank_config={},
        browser_fallback=True,
        headless=True,
    )

    assert snapshot.fetch_method == (
        "selenium_after_request_error"
    )
    assert snapshot.http_status == 0
    assert snapshot.content_type == "text/html"
    assert snapshot.fetch_status == "ok"
    assert snapshot.title == "Happy Bonus Kart Kampanyası"


def test_request_error_is_raised_when_fallback_disabled():
    with pytest.raises(
        RuntimeError,
        match="certificate verify failed",
    ):
        fetcher.fetch_page(
            PAGE,
            FailingClient(),
            bank_config={},
            browser_fallback=False,
            headless=True,
        )


def test_browser_failure_reports_both_errors(monkeypatch):
    def fail_browser(url, headless):
        raise RuntimeError("Chrome açılamadı")

    monkeypatch.setattr(
        fetcher,
        "_render_fallback",
        fail_browser,
    )

    with pytest.raises(
        RuntimeError,
        match="HTTP isteği başarısız oldu",
    ):
        fetcher.fetch_page(
            PAGE,
            FailingClient(),
            bank_config={},
            browser_fallback=True,
            headless=True,
        )
