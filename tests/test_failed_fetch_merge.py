from src.scraping.failed_fetch_retry import (
    merge_index_rows,
    remove_resolved_errors,
)


def row(bank, requested_url, title):
    return {
        "bank_name": bank,
        "requested_url": requested_url,
        "url": requested_url,
        "title": title,
    }


def test_partial_retry_preserves_other_kuveyt_rows():
    existing = [
        row("Kuveyt Türk", "https://example.com/a", "A"),
        row("Kuveyt Türk", "https://example.com/b", "B"),
        row("Albaraka Türk", "https://example.com/c", "C"),
    ]
    replacement = [
        row(
            "Kuveyt Türk",
            "https://example.com/b",
            "B Güncel",
        )
    ]

    merged = merge_index_rows(existing, replacement)

    assert len(merged) == 3
    titles = {
        item["requested_url"]: item["title"]
        for item in merged
    }
    assert titles["https://example.com/a"] == "A"
    assert titles["https://example.com/b"] == "B Güncel"
    assert titles["https://example.com/c"] == "C"


def test_successful_retry_removes_only_resolved_error():
    errors = [
        {
            "bank_name": "Kuveyt Türk",
            "url": "https://example.com/a",
        },
        {
            "bank_name": "Kuveyt Türk",
            "url": "https://example.com/b",
        },
        {
            "bank_name": "Albaraka Türk",
            "url": "https://example.com/c",
        },
    ]

    remaining = remove_resolved_errors(
        errors,
        bank_name="Kuveyt Türk",
        resolved_urls={"https://example.com/a"},
    )

    assert len(remaining) == 2
    assert {
        item["url"]
        for item in remaining
    } == {
        "https://example.com/b",
        "https://example.com/c",
    }


def test_new_url_is_added_without_bank_replacement():
    existing = [
        row("Kuveyt Türk", "https://example.com/a", "A"),
        row("Kuveyt Türk", "https://example.com/b", "B"),
    ]
    replacement = [
        row("Kuveyt Türk", "https://example.com/c", "C"),
    ]

    merged = merge_index_rows(existing, replacement)

    assert len(merged) == 3
