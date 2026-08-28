from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.live_campaign_sync import ensure_schema
from scripts import safe_campaign_removals as removal


def _insert_campaign(db: Path, *, url: str, end_date: str = "") -> None:
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    now = "2026-08-10T00:00:00+00:00"
    with connection:
        connection.execute(
            """
            INSERT INTO live_campaigns (
                bank_name, source_url, source_group, title, clean_text,
                content_hash, start_date, end_date, current_status,
                listing_status, fetch_status, first_seen_at, last_seen_at,
                last_checked_at, is_current, removed_at, created_at, updated_at
            ) VALUES (?, ?, '', ?, 'text', 'hash', '', ?, 'active',
                      'active', 'ok', ?, ?, ?, 1, NULL, ?, ?)
            """,
            (
                "Test Bank",
                url,
                "Test Campaign",
                end_date,
                now,
                now,
                now,
                now,
                now,
            ),
        )
    connection.close()


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_reachable_missing_campaign_is_not_removed_on_first_run(tmp_path, monkeypatch):
    db = tmp_path / "campaigns.db"
    discovery = tmp_path / "discovery.json"
    errors = tmp_path / "errors.json"
    state = tmp_path / "state.json"
    report = tmp_path / "report.json"
    url = "https://example.com/campaign"

    _insert_campaign(db, url=url)
    _write_json(discovery, [{"bank_name": "Test Bank", "url": "https://example.com/other"}])
    _write_json(errors, [])
    monkeypatch.setattr(
        removal,
        "_probe_url",
        lambda url, timeout: removal.ProbeResult(True, 200, url),
    )

    result = removal.process_bank(
        bank_name="Test Bank",
        db_path=db,
        discovery_path=discovery,
        discovery_errors_path=errors,
        state_path=state,
        report_path=report,
        confirm_after=2,
        timeout=1,
    )

    assert result["pending_count"] == 1
    connection = sqlite3.connect(db)
    assert connection.execute(
        "SELECT is_current FROM live_campaigns WHERE source_url=?", (url,)
    ).fetchone()[0] == 1
    connection.close()


def test_second_missing_and_404_removes_campaign(tmp_path, monkeypatch):
    db = tmp_path / "campaigns.db"
    discovery = tmp_path / "discovery.json"
    errors = tmp_path / "errors.json"
    state = tmp_path / "state.json"
    report = tmp_path / "report.json"
    url = "https://example.com/campaign"

    _insert_campaign(db, url=url)
    _write_json(discovery, [{"bank_name": "Test Bank", "url": "https://example.com/other"}])
    _write_json(errors, [])

    monkeypatch.setattr(
        removal,
        "_probe_url",
        lambda url, timeout: removal.ProbeResult(True, 200, url),
    )
    removal.process_bank(
        bank_name="Test Bank",
        db_path=db,
        discovery_path=discovery,
        discovery_errors_path=errors,
        state_path=state,
        report_path=report,
        confirm_after=2,
        timeout=1,
    )

    monkeypatch.setattr(
        removal,
        "_probe_url",
        lambda url, timeout: removal.ProbeResult(False, 404, url),
    )
    result = removal.process_bank(
        bank_name="Test Bank",
        db_path=db,
        discovery_path=discovery,
        discovery_errors_path=errors,
        state_path=state,
        report_path=report,
        confirm_after=2,
        timeout=1,
    )

    assert result["removed_count"] == 1
    connection = sqlite3.connect(db)
    row = connection.execute(
        "SELECT is_current, current_status FROM live_campaigns WHERE source_url=?",
        (url,),
    ).fetchone()
    assert row == (0, "removed")
    connection.close()


def test_missing_campaign_with_past_end_date_expires_immediately(tmp_path, monkeypatch):
    db = tmp_path / "campaigns.db"
    discovery = tmp_path / "discovery.json"
    errors = tmp_path / "errors.json"
    state = tmp_path / "state.json"
    report = tmp_path / "report.json"
    url = "https://example.com/expired"
    past = (date.today() - timedelta(days=1)).isoformat()

    _insert_campaign(db, url=url, end_date=past)
    _write_json(discovery, [{"bank_name": "Test Bank", "url": "https://example.com/other"}])
    _write_json(errors, [])
    monkeypatch.setattr(
        removal,
        "_probe_url",
        lambda url, timeout: removal.ProbeResult(True, 200, url),
    )

    result = removal.process_bank(
        bank_name="Test Bank",
        db_path=db,
        discovery_path=discovery,
        discovery_errors_path=errors,
        state_path=state,
        report_path=report,
        confirm_after=2,
        timeout=1,
    )

    assert result["expired_count"] == 1
    connection = sqlite3.connect(db)
    row = connection.execute(
        "SELECT is_current, current_status FROM live_campaigns WHERE source_url=?",
        (url,),
    ).fetchone()
    assert row == (0, "expired")
    connection.close()
