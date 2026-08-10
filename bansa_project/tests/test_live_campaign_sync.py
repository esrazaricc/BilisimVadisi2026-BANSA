import json
import sqlite3
from pathlib import Path

from src.database.live_campaign_sync import sync_bank


def write_json(path: Path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def prepare_files(tmp_path: Path, status="active", text="İlk metin"):
    discovery = tmp_path / "discovered.json"
    index = tmp_path / "index.json"
    discovery_errors = tmp_path / "discovery_errors.json"
    fetch_errors = tmp_path / "fetch_errors.json"
    report = tmp_path / "report.json"

    write_json(
        discovery,
        [
            {
                "bank_name": "Albaraka Türk",
                "url": "https://www.albaraka.com.tr/tr/kampanyalar/detay/ornek",
                "source_group": "Genel Kampanyalar",
                "listing_status": status,
            }
        ],
    )
    write_json(
        index,
        [
            {
                "bank_name": "Albaraka Türk",
                "url": "https://albaraka.com.tr/tr/kampanyalar/detay/ornek",
                "title": "Örnek Kampanya",
                "clean_text": text,
                "content_hash": f"hash-{text}",
                "current_status": status,
                "campaign_start_date": "2026-07-01",
                "campaign_end_date": "2026-08-31",
                "fetch_status": "ok",
            }
        ],
    )
    write_json(discovery_errors, [])
    write_json(fetch_errors, [])

    return {
        "discovery_path": discovery,
        "index_path": index,
        "discovery_errors_path": discovery_errors,
        "fetch_errors_path": fetch_errors,
        "report_path": report,
    }


def test_first_sync_creates_and_second_sync_is_unchanged(tmp_path):
    db = tmp_path / "campaigns.db"
    files = prepare_files(tmp_path)

    first = sync_bank(
        bank_name="Albaraka Türk",
        db_path=db,
        **files,
    )
    second = sync_bank(
        bank_name="Albaraka Türk",
        db_path=db,
        **files,
    )

    assert first.created == 1
    assert first.unchanged == 0
    assert second.created == 0
    assert second.unchanged == 1

    connection = sqlite3.connect(db)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM live_campaigns"
        ).fetchone()[0]
        assert count == 1
    finally:
        connection.close()


def test_content_and_status_changes_are_recorded(tmp_path):
    db = tmp_path / "campaigns.db"
    files = prepare_files(tmp_path, status="active", text="İlk metin")

    sync_bank(
        bank_name="Albaraka Türk",
        db_path=db,
        **files,
    )

    write_json(
        files["index_path"],
        [
            {
                "bank_name": "Albaraka Türk",
                "url": "https://albaraka.com.tr/tr/kampanyalar/detay/ornek",
                "title": "Örnek Kampanya",
                "clean_text": "Yeni metin",
                "content_hash": "hash-yeni",
                "current_status": "expired",
                "fetch_status": "ok",
            }
        ],
    )

    result = sync_bank(
        bank_name="Albaraka Türk",
        db_path=db,
        **files,
    )

    assert result.content_changed == 1
    assert result.status_changed == 1

    connection = sqlite3.connect(db)
    try:
        types = {
            row[0]
            for row in connection.execute(
                "SELECT change_type FROM live_campaign_changes"
            )
        }
        assert "created" in types
        assert "content_changed" in types
        assert "status_changed" in types
    finally:
        connection.close()


def test_missing_url_is_marked_removed_only_after_successful_discovery(tmp_path):
    db = tmp_path / "campaigns.db"
    files = prepare_files(tmp_path)

    sync_bank(
        bank_name="Albaraka Türk",
        db_path=db,
        **files,
    )

    write_json(
        files["discovery_path"],
        [
            {
                "bank_name": "Albaraka Türk",
                "url": "https://albaraka.com.tr/tr/kampanyalar/detay/yeni",
                "source_group": "Genel Kampanyalar",
                "listing_status": "active",
            }
        ],
    )
    write_json(
        files["index_path"],
        [
            {
                "bank_name": "Albaraka Türk",
                "url": "https://albaraka.com.tr/tr/kampanyalar/detay/yeni",
                "title": "Yeni Kampanya",
                "clean_text": "Yeni kampanya metni",
                "content_hash": "hash-yeni",
                "current_status": "active",
                "fetch_status": "ok",
            }
        ],
    )

    result = sync_bank(
        bank_name="Albaraka Türk",
        db_path=db,
        **files,
    )

    assert result.created == 1
    assert result.removed == 1

    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    try:
        old = connection.execute(
            """
            SELECT current_status, is_current
            FROM live_campaigns
            WHERE source_url LIKE '%/ornek'
            """
        ).fetchone()
        assert old["current_status"] == "removed"
        assert old["is_current"] == 0
    finally:
        connection.close()


def test_discovery_error_prevents_removed_marking(tmp_path):
    db = tmp_path / "campaigns.db"
    files = prepare_files(tmp_path)

    sync_bank(
        bank_name="Albaraka Türk",
        db_path=db,
        **files,
    )

    write_json(
        files["discovery_path"],
        [
            {
                "bank_name": "Albaraka Türk",
                "url": "https://albaraka.com.tr/tr/kampanyalar/detay/yeni",
                "source_group": "Genel Kampanyalar",
                "listing_status": "active",
            }
        ],
    )
    write_json(
        files["index_path"],
        [
            {
                "bank_name": "Albaraka Türk",
                "url": "https://albaraka.com.tr/tr/kampanyalar/detay/yeni",
                "title": "Yeni Kampanya",
                "clean_text": "Yeni kampanya metni",
                "content_hash": "hash-yeni",
                "current_status": "active",
                "fetch_status": "ok",
            }
        ],
    )
    write_json(
        files["discovery_errors_path"],
        [
            {
                "bank_name": "Albaraka Türk",
                "message": "Geçici keşif hatası",
            }
        ],
    )

    result = sync_bank(
        bank_name="Albaraka Türk",
        db_path=db,
        **files,
    )

    assert result.removal_skipped is True
    assert result.removed == 0

    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    try:
        old = connection.execute(
            """
            SELECT current_status, is_current
            FROM live_campaigns
            WHERE source_url LIKE '%/ornek'
            """
        ).fetchone()
        assert old["is_current"] == 1
    finally:
        connection.close()
