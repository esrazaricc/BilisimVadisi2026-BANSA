import json

from src.scraping.campaign_page_fetcher import (
    _fetch_item_bank,
    write_fetch_results,
)


def test_turkish_bank_name_uses_same_search_key():
    assert _fetch_item_bank(
        {"bank_name": "Türkiye Finans"}
    ) == "turkiye finans"


def test_old_turkiye_finans_errors_are_replaced(tmp_path):
    index_path = tmp_path / "campaign_page_index.json"
    error_path = tmp_path / "campaign_page_fetch_errors.json"
    report_path = tmp_path / "campaign_page_fetch_report.json"
    snapshot_root = tmp_path / "campaign_pages"

    old_errors = [
        {
            "bank_name": "Türkiye Finans",
            "url": "https://happycard.com.tr/old-1",
            "error_type": "RuntimeError",
            "message": "old",
        },
        {
            "bank_name": "Türkiye Finans",
            "url": "https://happycard.com.tr/old-2",
            "error_type": "RuntimeError",
            "message": "old",
        },
        {
            "bank_name": "Kuveyt Türk",
            "url": "https://example.com/keep",
            "error_type": "RuntimeError",
            "message": "keep",
        },
    ]
    error_path.write_text(
        json.dumps(old_errors, ensure_ascii=False),
        encoding="utf-8",
    )

    new_errors = [
        {
            "bank_name": "Türkiye Finans",
            "url": "https://happycard.com.tr/new",
            "request_url": "https://www.happycard.com.tr/new",
            "error_type": "RuntimeError",
            "message": "new",
        }
    ]

    write_fetch_results(
        [],
        new_errors,
        snapshot_root=snapshot_root,
        index_path=index_path,
        error_path=error_path,
        report_path=report_path,
    )

    result = json.loads(
        error_path.read_text(encoding="utf-8")
    )

    tf_errors = [
        item
        for item in result
        if item["bank_name"] == "Türkiye Finans"
    ]
    kuveyt_errors = [
        item
        for item in result
        if item["bank_name"] == "Kuveyt Türk"
    ]

    assert len(tf_errors) == 1
    assert tf_errors[0]["url"].endswith("/new")
    assert len(kuveyt_errors) == 1
