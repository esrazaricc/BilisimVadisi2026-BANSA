from src.scraping import browser_renderer as renderer


SHELL_HTML = "<html><head><title>Happy</title></head><body></body></html>"
FULL_HTML = (
    "<html><head><title>Happy Kampanya</title></head><body>"
    + ("Kampanya içeriği ve koşulları. " * 20)
    + "</body></html>"
)


class SequenceDriver:
    def __init__(self, snapshots):
        self.snapshots = list(snapshots)
        self.index = 0

    @property
    def current_url(self):
        return self.snapshots[
            min(self.index, len(self.snapshots) - 1)
        ]["current_url"]

    @property
    def page_source(self):
        return self.snapshots[
            min(self.index, len(self.snapshots) - 1)
        ]["html"]

    def execute_script(self, script, *args):
        snapshot = self.snapshots[
            min(self.index, len(self.snapshots) - 1)
        ]

        if "return {" in script:
            result = {
                "ready_state": snapshot["ready_state"],
                "title": snapshot["title"],
                "body_text": snapshot["body_text"],
                "html": snapshot["html"],
            }
            if self.index < len(self.snapshots) - 1:
                self.index += 1
            return result

        if "document.querySelectorAll" in script:
            return 0

        return None


def test_empty_shell_is_not_usable():
    snapshot = {
        "current_url": (
            "https://www.happycard.com.tr/kampanyalar/test.aspx"
        ),
        "ready_state": "interactive",
        "title": "Happy",
        "body_text": "",
        "html": SHELL_HTML,
    }

    assert not renderer._snapshot_is_usable(snapshot)


def test_real_happy_page_is_usable():
    snapshot = {
        "current_url": (
            "https://www.happycard.com.tr/kampanyalar/test.aspx"
        ),
        "ready_state": "interactive",
        "title": "Happy Kampanya",
        "body_text": "Kampanya metni " * 20,
        "html": FULL_HTML,
    }

    assert renderer._snapshot_is_usable(snapshot)


def test_about_blank_is_not_usable_even_when_complete():
    snapshot = {
        "current_url": "about:blank",
        "ready_state": "complete",
        "title": "",
        "body_text": "",
        "html": "<html><head></head><body></body></html>",
    }

    assert not renderer._snapshot_is_usable(snapshot)


def test_wait_ignores_shell_then_accepts_stable_content(
    monkeypatch,
):
    monkeypatch.setattr(
        renderer.time,
        "sleep",
        lambda _: None,
    )

    driver = SequenceDriver(
        [
            {
                "current_url": (
                    "https://www.happycard.com.tr/"
                    "kampanyalar/test.aspx"
                ),
                "ready_state": "loading",
                "title": "Happy Kampanya",
                "body_text": "",
                "html": SHELL_HTML,
            },
            {
                "current_url": (
                    "https://www.happycard.com.tr/"
                    "kampanyalar/test.aspx"
                ),
                "ready_state": "interactive",
                "title": "Happy Kampanya",
                "body_text": "Kampanya metni " * 20,
                "html": FULL_HTML,
            },
            {
                "current_url": (
                    "https://www.happycard.com.tr/"
                    "kampanyalar/test.aspx"
                ),
                "ready_state": "complete",
                "title": "Happy Kampanya",
                "body_text": "Kampanya metni " * 20,
                "html": FULL_HTML,
            },
        ]
    )

    assert renderer._wait_for_stable_document(
        driver,
        timeout=1.0,
        settle_seconds=0.0,
        detail_paths=[],
    )
