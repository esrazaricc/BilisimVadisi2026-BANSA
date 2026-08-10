from __future__ import annotations

import json
import os
import time
from pathlib import Path

import scripts.run_turkiye_finans_full_refresh_pipeline as pipeline
from scripts.run_turkiye_finans_full_refresh_pipeline import (
    Step,
    command_for,
    count_error_entries,
    count_unique_urls,
    supports_flag,
    validate_url_artifact,
)


def test_supports_flag_matches_exact_option():
    help_text = "usage: x.py [--bank BANK] [--no-mark-removed]"
    assert supports_flag(help_text, "--bank")
    assert supports_flag(help_text, "--no-mark-removed")
    assert not supports_flag(help_text, "--headed")


def test_count_unique_urls_is_recursive_and_unique():
    payload = {
        "items": [
            {"url": "https://example.com/a"},
            {"url": "https://example.com/b"},
            {"text": "Tekrar https://example.com/a"},
        ]
    }
    assert count_unique_urls(payload) == 2


def test_count_error_entries_common_shapes():
    assert count_error_entries([]) == 0
    assert count_error_entries({"errors": []}) == 0
    assert count_error_entries({"errors": ["x", "y"]}) == 2
    assert count_error_entries({"failed": 3}) == 3
    assert count_error_entries({"error": "boom"}) == 1


def test_command_for_uses_scripts_folder():
    step = Step(
        "Test",
        "sample.py",
        ("--bank", "Türkiye Finans"),
    )
    command = command_for(step)
    assert command[1].endswith(
        str(Path("scripts") / "sample.py")
    )
    assert command[-2:] == ["--bank", "Türkiye Finans"]


def test_validation_prefers_primary_campaign_artifact(
    tmp_path,
    monkeypatch,
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    discovered = data_dir / "discovered_campaign_pages.json"
    report = data_dir / "campaign_discovery_report.json"

    discovered.write_text(
        json.dumps(
            {
                "pages": [
                    f"https://example.com/campaign/{index}"
                    for index in range(49)
                ]
            }
        ),
        encoding="utf-8",
    )
    report.write_text(
        json.dumps(
            {
                "sources": [
                    f"https://example.com/source/{index}"
                    for index in range(22)
                ]
            }
        ),
        encoding="utf-8",
    )

    now = time.time()
    os.utime(discovered, (now, now))
    os.utime(report, (now + 1, now + 1))

    monkeypatch.setattr(pipeline, "DATA", data_dir)
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)

    path, count = validate_url_artifact(
        (
            "discovered_campaign_pages.json",
            "campaign_discovery_report.json",
        ),
        started_at=now - 1,
        minimum_urls=49,
        label="Keşif",
    )

    assert path.resolve() == discovered.resolve()
    assert count == 49


def test_validation_can_fall_back_to_secondary_artifact(
    tmp_path,
    monkeypatch,
):
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    primary = data_dir / "campaign_page_index.json"
    secondary = data_dir / "campaign_page_fetch_report.json"

    primary.write_text(
        json.dumps({"pages": ["https://example.com/only-one"]}),
        encoding="utf-8",
    )
    secondary.write_text(
        json.dumps(
            {
                "pages": [
                    f"https://example.com/page/{index}"
                    for index in range(49)
                ]
            }
        ),
        encoding="utf-8",
    )

    now = time.time()
    os.utime(primary, (now, now))
    os.utime(secondary, (now, now))

    monkeypatch.setattr(pipeline, "DATA", data_dir)
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)

    path, count = validate_url_artifact(
        (
            "campaign_page_index.json",
            "campaign_page_fetch_report.json",
        ),
        started_at=now - 1,
        minimum_urls=49,
        label="Fetch",
    )

    assert path.resolve() == secondary.resolve()
    assert count == 49
