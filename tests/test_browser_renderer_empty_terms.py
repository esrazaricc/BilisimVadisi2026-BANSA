from selenium import webdriver

from src.scraping import browser_renderer as renderer


class FakeDriver:
    def __init__(self):
        self.scroll_calls = 0
        self.quit_called = False

    def set_page_load_timeout(self, timeout):
        self.timeout = timeout

    def get(self, url):
        self._url = url

    @property
    def current_url(self):
        return self._url

    @property
    def page_source(self):
        return (
            "<html><body><main>"
            + ("Kampanya içeriği " * 20)
            + "</main></body></html>"
        )

    def execute_script(self, script, *args):
        if "document.readyState" in script:
            return "complete"
        if "window.scrollTo" in script:
            self.scroll_calls += 1
            return None
        if "document.querySelectorAll" in script:
            return 0
        if "window.stop" in script:
            return None
        return None

    def quit(self):
        self.quit_called = True


def test_empty_load_more_terms_skip_click_loop(monkeypatch):
    driver = FakeDriver()
    monkeypatch.setattr(
        webdriver,
        "Chrome",
        lambda options=None: driver,
    )
    monkeypatch.setattr(
        renderer.time,
        "sleep",
        lambda _: None,
    )

    result = renderer.render_dynamic_page(
        "https://www.happycard.com.tr/kampanyalar/test.aspx",
        detail_paths=[],
        load_more_terms=[],
        cookie_accept_terms=[],
        headless=False,
        timeout=2,
        maximum_load_more_clicks=1,
        settle_seconds=0,
    )

    # load_more_terms boşsa yönlendirme anındaki DOM'a dokunmamak için
    # hiçbir scroll/load-more etkileşimi yapılmamalıdır.
    assert driver.scroll_calls == 0
    assert result.load_more_clicks == 0
    assert "Kampanya içeriği" in result.html
    assert driver.quit_called
