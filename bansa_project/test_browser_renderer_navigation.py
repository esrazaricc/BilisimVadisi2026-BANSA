from src.scraping import browser_renderer as renderer


class SequenceDriver:
    def __init__(self):
        self.ready_calls = 0
        self._url_calls = 0
        self._source_calls = 0

    @property
    def current_url(self):
        self._url_calls += 1
        return "https://happycard.com.tr/kampanyalar/test.aspx"

    @property
    def page_source(self):
        self._source_calls += 1
        if self._source_calls == 1:
            raise RuntimeError(
                "loader has changed while resolving nodes"
            )
        return (
            "<html><body><main>"
            + ("Kampanya içeriği " * 20)
            + "</main></body></html>"
        )

    def execute_script(self, script, *args):
        self.ready_calls += 1
        if self.ready_calls == 1:
            raise RuntimeError(
                "loader has changed while resolving nodes"
            )
        return "complete"


class BrokenCountDriver:
    def execute_script(self, script, *args):
        raise RuntimeError(
            "aborted by navigation: loader has changed"
        )


def test_navigation_timeout_is_recoverable():
    assert renderer._is_recoverable_navigation_error(
        RuntimeError(
            "timeout from aborted by navigation: "
            "loader has changed"
        )
    )


def test_unrelated_webdriver_error_is_not_recoverable():
    assert not renderer._is_recoverable_navigation_error(
        RuntimeError("invalid session id")
    )


def test_safe_page_source_retries_after_loader_change(
    monkeypatch,
):
    monkeypatch.setattr(
        renderer.time,
        "sleep",
        lambda _: None,
    )
    driver = SequenceDriver()

    html = renderer._safe_page_source(
        driver,
        attempts=3,
    )

    assert "Kampanya içeriği" in html


def test_wait_for_stable_document_tolerates_redirect(
    monkeypatch,
):
    monkeypatch.setattr(
        renderer.time,
        "sleep",
        lambda _: None,
    )
    driver = SequenceDriver()

    assert renderer._wait_for_stable_document(
        driver,
        timeout=1.0,
        settle_seconds=0.0,
    )


def test_count_detail_links_returns_zero_during_navigation():
    assert (
        renderer._count_detail_links(
            BrokenCountDriver(),
            ["/kampanyalar/Sayfalar/"],
        )
        == 0
    )
