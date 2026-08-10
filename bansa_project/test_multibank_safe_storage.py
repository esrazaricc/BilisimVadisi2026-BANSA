import json
from dataclasses import asdict
from pathlib import Path

from src.scraping.campaign_discovery import (
    DiscoveredPage,
    DiscoveryDiagnostic,
    discover_from_html,
    write_discovery_results,
)
from src.scraping.campaign_page_fetcher import (
    CampaignPageSnapshot,
    write_fetch_results,
)


def discovery_page(bank, url):
    return DiscoveredPage(
        bank_name=bank,
        url=url,
        source_page="https://example.com/kampanyalar",
        page_type="campaign_detail",
        discovery_mode="detail_links",
        source_group="Test",
    )


def diagnostic(bank, count):
    return DiscoveryDiagnostic(
        bank_name=bank,
        source_page="https://example.com/kampanyalar",
        render_mode="requests",
        load_more_clicks=0,
        rendered_detail_link_count=count,
        discovered_count=count,
        reference_visible_count=None,
        completeness_status="NOT_CHECKED",
        reached_click_limit=False,
    )


def snapshot(bank, url):
    return CampaignPageSnapshot(
        bank_name=bank,
        title="Kampanya",
        url=url,
        requested_url=url,
        source_page="https://example.com/kampanyalar",
        page_type="campaign_detail",
        discovery_mode="detail_links",
        source_group="Test",
        listing_status="active",
        listing_status_evidence="",
        fetch_method="requests",
        http_status=200,
        content_type="text/html",
        raw_text="Kampanya metni " * 20,
        clean_text="Kampanya metni " * 20,
        content_hash="abc",
        text_length=300,
        campaign_start_date="",
        campaign_end_date="",
        current_status="active",
        status_reason="",
        status_evidence="",
        status_checked_at="2026-07-31T00:00:00+00:00",
        first_seen_at="2026-07-31T00:00:00+00:00",
        last_checked_at="2026-07-31T00:00:00+00:00",
        fetch_status="ok",
    )


def test_discovery_merge_preserves_other_bank(tmp_path: Path):
    output = tmp_path / "discovery.json"
    errors = tmp_path / "errors.json"
    report = tmp_path / "report.json"

    output.write_text(
        json.dumps(
            [
                asdict(
                    discovery_page(
                        "Albaraka Türk",
                        "https://albaraka.com.tr/tr/kampanya/a",
                    )
                )
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    write_discovery_results(
        [
            discovery_page(
                "Kuveyt Türk",
                (
                    "https://kuveytturk.com.tr/kampanyalar/"
                    "kendim-icin/kart-kampanyalari/test"
                ),
            )
        ],
        [],
        [diagnostic("Kuveyt Türk", 1)],
        output_path=output,
        error_path=errors,
        report_path=report,
    )

    rows = json.loads(output.read_text(encoding="utf-8"))
    assert {row["bank_name"] for row in rows} == {
        "Albaraka Türk",
        "Kuveyt Türk",
    }


def test_failed_discovery_does_not_delete_old_bank(tmp_path: Path):
    output = tmp_path / "discovery.json"
    errors = tmp_path / "errors.json"
    report = tmp_path / "report.json"

    old = asdict(
        discovery_page(
            "Kuveyt Türk",
            (
                "https://kuveytturk.com.tr/kampanyalar/"
                "kendim-icin/kart-kampanyalari/eski"
            ),
        )
    )
    output.write_text(
        json.dumps([old], ensure_ascii=False),
        encoding="utf-8",
    )

    write_discovery_results(
        [],
        [
            {
                "bank_name": "Kuveyt Türk",
                "source_page": "https://example.com",
                "error_type": "TimeoutError",
                "message": "timeout",
            }
        ],
        [],
        output_path=output,
        error_path=errors,
        report_path=report,
    )

    rows = json.loads(output.read_text(encoding="utf-8"))
    assert rows == [old]


def test_exact_listing_path_excluded_detail_kept():
    bank = {
        "name": "Kuveyt Türk",
        "base_url": "https://www.kuveytturk.com.tr",
        "detail_paths": [
            "/kampanyalar/kendim-icin/kart-kampanyalari/"
        ],
        "exclude_paths": [],
        "exclude_exact_paths": [
            "/kampanyalar/kendim-icin/kart-kampanyalari"
        ],
        "discovery_mode": "detail_links",
        "source_group": "Kart Kampanyaları",
    }

    html = """
    <a href="/kampanyalar/kendim-icin/kart-kampanyalari">
      Kart Kampanyaları
    </a>
    <article>
      <a href="/kampanyalar/kendim-icin/kart-kampanyalari/test">
        Test Kampanyası
      </a>
    </article>
    """

    rows = discover_from_html(
        bank=bank,
        source_page=(
            "https://www.kuveytturk.com.tr/"
            "kampanyalar/kendim-icin"
        ),
        html=html,
    )

    assert len(rows) == 1
    assert rows[0].url.endswith(
        "/kampanyalar/kendim-icin/kart-kampanyalari/test"
    )


def test_fetch_index_preserves_other_bank(tmp_path: Path):
    index_path = tmp_path / "index.json"
    error_path = tmp_path / "errors.json"
    report_path = tmp_path / "report.json"
    snapshot_root = tmp_path / "pages"

    albaraka = asdict(
        snapshot(
            "Albaraka Türk",
            "https://albaraka.com.tr/tr/kampanya/a",
        )
    )
    albaraka.pop("raw_text")
    albaraka.pop("clean_text")
    albaraka["snapshot_file"] = "old.json"

    index_path.write_text(
        json.dumps([albaraka], ensure_ascii=False),
        encoding="utf-8",
    )

    write_fetch_results(
        [
            snapshot(
                "Kuveyt Türk",
                (
                    "https://kuveytturk.com.tr/kampanyalar/"
                    "kendim-icin/kart-kampanyalari/test"
                ),
            )
        ],
        [],
        snapshot_root=snapshot_root,
        index_path=index_path,
        error_path=error_path,
        report_path=report_path,
    )

    rows = json.loads(index_path.read_text(encoding="utf-8"))
    assert {row["bank_name"] for row in rows} == {
        "Albaraka Türk",
        "Kuveyt Türk",
    }
