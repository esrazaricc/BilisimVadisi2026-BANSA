from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


DEFAULT_DB_PATH = Path("data") / "campaigns.db"
DEFAULT_DISCOVERY_PATH = Path("data") / "discovered_campaign_pages.json"
DEFAULT_INDEX_PATH = Path("data") / "campaign_page_index.json"
DEFAULT_DISCOVERY_ERRORS = Path("data") / "campaign_discovery_errors.json"
DEFAULT_FETCH_ERRORS = Path("data") / "campaign_page_fetch_errors.json"
DEFAULT_REPORT_PATH = Path("data") / "live_db_sync_report.json"


@dataclass
class SyncResult:
    bank_name: str
    discovered: int = 0
    processed: int = 0
    created: int = 0
    content_changed: int = 0
    status_changed: int = 0
    reactivated: int = 0
    removed: int = 0
    unchanged: int = 0
    unavailable: int = 0
    errors: int = 0
    removal_skipped: bool = False
    removal_skip_reason: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    return re.sub(r"\s+", " ", text).strip()


def search_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", normalize_text(value))
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    return text.casefold()


def unwrap_url(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        for key in ("url", "href", "value"):
            if key in value:
                result = unwrap_url(value[key])
                if result:
                    return result

    return ""


def canonicalize_url(value: Any) -> str:
    url = unwrap_url(value)
    if not url:
        return ""

    parts = urlsplit(url)
    scheme = parts.scheme.casefold() or "https"
    host = parts.netloc.casefold()
    if host.startswith("www."):
        host = host[4:]

    path = re.sub(r"/+", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")

    return urlunsplit((scheme, host, path, "", ""))


def load_json(path: str | Path, default: Any) -> Any:
    json_path = Path(path)
    if not json_path.exists():
        return default

    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def ensure_schema(connection: sqlite3.Connection) -> None:
    """
    Mevcut campaigns.db dosyasını bozmadan canlı senkronizasyon
    tablolarını ekler.
    """
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS live_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_name TEXT NOT NULL,
            source_url TEXT NOT NULL UNIQUE,
            source_group TEXT,
            title TEXT,
            clean_text TEXT,
            content_hash TEXT,
            start_date TEXT,
            end_date TEXT,
            current_status TEXT NOT NULL DEFAULT 'unknown',
            listing_status TEXT NOT NULL DEFAULT 'unknown',
            fetch_status TEXT NOT NULL DEFAULT 'unknown',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            last_checked_at TEXT NOT NULL,
            is_current INTEGER NOT NULL DEFAULT 1,
            removed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_live_campaigns_bank
        ON live_campaigns(bank_name);

        CREATE INDEX IF NOT EXISTS idx_live_campaigns_status
        ON live_campaigns(current_status, is_current);

        CREATE TABLE IF NOT EXISTS live_campaign_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            bank_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            change_type TEXT NOT NULL,
            old_content_hash TEXT,
            new_content_hash TEXT,
            old_status TEXT,
            new_status TEXT,
            changed_at TEXT NOT NULL,
            details_json TEXT,
            FOREIGN KEY(campaign_id)
                REFERENCES live_campaigns(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_live_changes_campaign
        ON live_campaign_changes(campaign_id, changed_at);

        CREATE TABLE IF NOT EXISTS live_sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            discovered_count INTEGER NOT NULL DEFAULT 0,
            processed_count INTEGER NOT NULL DEFAULT 0,
            created_count INTEGER NOT NULL DEFAULT 0,
            content_changed_count INTEGER NOT NULL DEFAULT 0,
            status_changed_count INTEGER NOT NULL DEFAULT 0,
            reactivated_count INTEGER NOT NULL DEFAULT 0,
            removed_count INTEGER NOT NULL DEFAULT 0,
            unchanged_count INTEGER NOT NULL DEFAULT 0,
            unavailable_count INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            removal_skipped INTEGER NOT NULL DEFAULT 0,
            details_json TEXT
        );
        """
    )


def read_snapshot(index_item: dict[str, Any]) -> dict[str, Any]:
    merged = dict(index_item)
    snapshot_file = normalize_text(index_item.get("snapshot_file"))

    if snapshot_file:
        path = Path(snapshot_file)
        if path.exists():
            snapshot = load_json(path, {})
            if isinstance(snapshot, dict):
                merged.update(snapshot)

    return merged


def build_snapshot_lookup(
    index_items: list[dict[str, Any]],
    bank_name: str,
) -> dict[str, dict[str, Any]]:
    wanted = search_key(bank_name)
    lookup: dict[str, dict[str, Any]] = {}

    for item in index_items:
        if search_key(item.get("bank_name")) != wanted:
            continue

        snapshot = read_snapshot(item)

        final_url = canonicalize_url(snapshot.get("url"))
        requested_url = canonicalize_url(
            snapshot.get("requested_url")
        )

        if final_url:
            lookup[final_url] = snapshot
        if requested_url:
            lookup[requested_url] = snapshot

    return lookup


def log_change(
    connection: sqlite3.Connection,
    *,
    campaign_id: int,
    bank_name: str,
    source_url: str,
    change_type: str,
    old_hash: str = "",
    new_hash: str = "",
    old_status: str = "",
    new_status: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO live_campaign_changes (
            campaign_id,
            bank_name,
            source_url,
            change_type,
            old_content_hash,
            new_content_hash,
            old_status,
            new_status,
            changed_at,
            details_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            campaign_id,
            bank_name,
            source_url,
            change_type,
            old_hash or None,
            new_hash or None,
            old_status or None,
            new_status or None,
            now_iso(),
            json.dumps(details or {}, ensure_ascii=False),
        ),
    )


def upsert_campaign(
    connection: sqlite3.Connection,
    *,
    bank_name: str,
    discovery: dict[str, Any],
    snapshot: dict[str, Any] | None,
) -> tuple[set[str], bool]:
    url = canonicalize_url(discovery.get("url"))
    if not url:
        raise ValueError("Kampanya URL'si boş.")

    existing = connection.execute(
        "SELECT * FROM live_campaigns WHERE source_url = ?",
        (url,),
    ).fetchone()

    unavailable = snapshot is None
    source = snapshot or discovery

    title = normalize_text(source.get("title"))
    clean_text = normalize_text(
        source.get("clean_text")
        or source.get("listing_text")
    )
    new_hash = normalize_text(source.get("content_hash"))
    new_status = normalize_text(
        source.get("current_status")
        or discovery.get("listing_status")
        or "unknown"
    ).lower()
    listing_status = normalize_text(
        discovery.get("listing_status", "unknown")
    ).lower()
    fetch_status = normalize_text(
        source.get("fetch_status")
        or ("unavailable" if unavailable else "unknown")
    ).lower()

    if new_status not in {
        "active",
        "upcoming",
        "expired",
        "unknown",
        "removed",
    }:
        new_status = "unknown"

    timestamp = now_iso()
    changes: set[str] = set()

    if existing is None:
        connection.execute(
            """
            INSERT INTO live_campaigns (
                bank_name,
                source_url,
                source_group,
                title,
                clean_text,
                content_hash,
                start_date,
                end_date,
                current_status,
                listing_status,
                fetch_status,
                first_seen_at,
                last_seen_at,
                last_checked_at,
                is_current,
                removed_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?, ?)
            """,
            (
                bank_name,
                url,
                normalize_text(discovery.get("source_group")),
                title,
                clean_text,
                new_hash,
                normalize_text(source.get("campaign_start_date")),
                normalize_text(source.get("campaign_end_date")),
                new_status,
                listing_status,
                fetch_status,
                timestamp,
                timestamp,
                timestamp,
                timestamp,
                timestamp,
            ),
        )
        campaign_id = int(connection.execute(
            "SELECT id FROM live_campaigns WHERE source_url = ?",
            (url,),
        ).fetchone()["id"])

        log_change(
            connection,
            campaign_id=campaign_id,
            bank_name=bank_name,
            source_url=url,
            change_type="created",
            new_hash=new_hash,
            new_status=new_status,
        )
        changes.add("created")
        return changes, unavailable

    campaign_id = int(existing["id"])
    old_hash = normalize_text(existing["content_hash"])
    old_status = normalize_text(existing["current_status"]).lower()
    was_removed = int(existing["is_current"]) == 0

    # Detay çekimi geçici olarak başarısızsa eski içeriği koru.
    effective_title = title or normalize_text(existing["title"])
    effective_text = (
        clean_text
        if clean_text
        else normalize_text(existing["clean_text"])
    )
    effective_hash = new_hash or old_hash
    effective_status = (
        new_status
        if new_status != "unknown" or old_status == "unknown"
        else old_status
    )

    connection.execute(
        """
        UPDATE live_campaigns
        SET
            bank_name = ?,
            source_group = ?,
            title = ?,
            clean_text = ?,
            content_hash = ?,
            start_date = CASE
                WHEN ? <> '' THEN ?
                ELSE start_date
            END,
            end_date = CASE
                WHEN ? <> '' THEN ?
                ELSE end_date
            END,
            current_status = ?,
            listing_status = ?,
            fetch_status = ?,
            last_seen_at = ?,
            last_checked_at = ?,
            is_current = 1,
            removed_at = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (
            bank_name,
            normalize_text(discovery.get("source_group")),
            effective_title,
            effective_text,
            effective_hash,
            normalize_text(source.get("campaign_start_date")),
            normalize_text(source.get("campaign_start_date")),
            normalize_text(source.get("campaign_end_date")),
            normalize_text(source.get("campaign_end_date")),
            effective_status,
            listing_status,
            fetch_status,
            timestamp,
            timestamp,
            timestamp,
            campaign_id,
        ),
    )

    if was_removed:
        changes.add("reactivated")
        log_change(
            connection,
            campaign_id=campaign_id,
            bank_name=bank_name,
            source_url=url,
            change_type="reactivated",
            old_hash=old_hash,
            new_hash=effective_hash,
            old_status="removed",
            new_status=effective_status,
        )

    if old_hash and effective_hash and old_hash != effective_hash:
        changes.add("content_changed")
        log_change(
            connection,
            campaign_id=campaign_id,
            bank_name=bank_name,
            source_url=url,
            change_type="content_changed",
            old_hash=old_hash,
            new_hash=effective_hash,
            old_status=old_status,
            new_status=effective_status,
        )

    if old_status != effective_status:
        changes.add("status_changed")
        log_change(
            connection,
            campaign_id=campaign_id,
            bank_name=bank_name,
            source_url=url,
            change_type="status_changed",
            old_hash=old_hash,
            new_hash=effective_hash,
            old_status=old_status,
            new_status=effective_status,
        )

    if not changes:
        changes.add("unchanged")

    return changes, unavailable


def mark_removed_campaigns(
    connection: sqlite3.Connection,
    *,
    bank_name: str,
    current_urls: set[str],
) -> int:
    rows = connection.execute(
        """
        SELECT *
        FROM live_campaigns
        WHERE bank_name = ?
          AND is_current = 1
        """,
        (bank_name,),
    ).fetchall()

    removed = 0
    for row in rows:
        url = canonicalize_url(row["source_url"])
        if url in current_urls:
            continue

        timestamp = now_iso()
        old_status = normalize_text(row["current_status"])

        connection.execute(
            """
            UPDATE live_campaigns
            SET
                current_status = 'removed',
                is_current = 0,
                removed_at = ?,
                last_checked_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (timestamp, timestamp, timestamp, row["id"]),
        )

        log_change(
            connection,
            campaign_id=int(row["id"]),
            bank_name=bank_name,
            source_url=url,
            change_type="removed",
            old_hash=normalize_text(row["content_hash"]),
            old_status=old_status,
            new_status="removed",
            details={
                "reason": "latest_successful_discovery_missing_url"
            },
        )
        removed += 1

    return removed


def sync_bank(
    *,
    bank_name: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    discovery_path: str | Path = DEFAULT_DISCOVERY_PATH,
    index_path: str | Path = DEFAULT_INDEX_PATH,
    discovery_errors_path: str | Path = DEFAULT_DISCOVERY_ERRORS,
    fetch_errors_path: str | Path = DEFAULT_FETCH_ERRORS,
    report_path: str | Path = DEFAULT_REPORT_PATH,
    mark_removed: bool = True,
) -> SyncResult:
    started_at = now_iso()

    discovery_items = load_json(discovery_path, [])
    index_items = load_json(index_path, [])
    discovery_errors = load_json(discovery_errors_path, [])
    fetch_errors = load_json(fetch_errors_path, [])

    if not isinstance(discovery_items, list):
        raise ValueError("Keşif JSON dosyası liste olmalı.")
    if not isinstance(index_items, list):
        raise ValueError("Kampanya indeks JSON dosyası liste olmalı.")

    wanted = search_key(bank_name)
    discovery_items = [
        item
        for item in discovery_items
        if search_key(item.get("bank_name")) == wanted
    ]

    snapshot_lookup = build_snapshot_lookup(index_items, bank_name)

    bank_discovery_errors = [
        item
        for item in discovery_errors
        if search_key(item.get("bank_name")) == wanted
    ]
    bank_fetch_errors = [
        item
        for item in fetch_errors
        if search_key(item.get("bank_name")) == wanted
    ]

    result = SyncResult(
        bank_name=bank_name,
        discovered=len(discovery_items),
        errors=len(bank_discovery_errors) + len(bank_fetch_errors),
    )

    if not discovery_items:
        raise RuntimeError(
            f"{bank_name} için keşfedilmiş kampanya bulunamadı."
        )

    database = Path(db_path)
    database.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row

    try:
        ensure_schema(connection)
        current_urls: set[str] = set()

        with connection:
            for discovery in discovery_items:
                url = canonicalize_url(discovery.get("url"))
                if not url:
                    continue

                current_urls.add(url)
                snapshot = snapshot_lookup.get(url)

                changes, unavailable = upsert_campaign(
                    connection,
                    bank_name=bank_name,
                    discovery=discovery,
                    snapshot=snapshot,
                )

                result.processed += 1
                result.created += int("created" in changes)
                result.content_changed += int(
                    "content_changed" in changes
                )
                result.status_changed += int(
                    "status_changed" in changes
                )
                result.reactivated += int(
                    "reactivated" in changes
                )
                result.unchanged += int(
                    changes == {"unchanged"}
                )
                result.unavailable += int(unavailable)

            can_mark_removed = (
                mark_removed
                and not bank_discovery_errors
                and result.discovered > 0
            )

            if can_mark_removed:
                result.removed = mark_removed_campaigns(
                    connection,
                    bank_name=bank_name,
                    current_urls=current_urls,
                )
            else:
                result.removal_skipped = True
                if not mark_removed:
                    result.removal_skip_reason = (
                        "--no-mark-removed kullanıldı"
                    )
                elif bank_discovery_errors:
                    result.removal_skip_reason = (
                        "Keşif hatası varken güvenli silme yapılmadı"
                    )
                else:
                    result.removal_skip_reason = (
                        "Keşif sonucu boş"
                    )

            finished_at = now_iso()
            connection.execute(
                """
                INSERT INTO live_sync_runs (
                    bank_name,
                    started_at,
                    finished_at,
                    discovered_count,
                    processed_count,
                    created_count,
                    content_changed_count,
                    status_changed_count,
                    reactivated_count,
                    removed_count,
                    unchanged_count,
                    unavailable_count,
                    error_count,
                    removal_skipped,
                    details_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bank_name,
                    started_at,
                    finished_at,
                    result.discovered,
                    result.processed,
                    result.created,
                    result.content_changed,
                    result.status_changed,
                    result.reactivated,
                    result.removed,
                    result.unchanged,
                    result.unavailable,
                    result.errors,
                    int(result.removal_skipped),
                    json.dumps(
                        {
                            "removal_skip_reason": (
                                result.removal_skip_reason
                            )
                        },
                        ensure_ascii=False,
                    ),
                ),
            )

        report = {
            **asdict(result),
            "database": str(database),
            "started_at": started_at,
            "finished_at": now_iso(),
        }
        report_file = Path(report_path)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return result
    finally:
        connection.close()


def database_summary(
    db_path: str | Path = DEFAULT_DB_PATH,
    bank_name: str | None = None,
) -> dict[str, Any]:
    database = Path(db_path)
    if not database.exists():
        return {}

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row

    try:
        ensure_schema(connection)

        parameters: tuple[Any, ...] = ()
        where = ""
        if bank_name:
            where = "WHERE bank_name = ?"
            parameters = (bank_name,)

        rows = connection.execute(
            f"""
            SELECT
                current_status,
                is_current,
                COUNT(*) AS count
            FROM live_campaigns
            {where}
            GROUP BY current_status, is_current
            ORDER BY current_status, is_current
            """,
            parameters,
        ).fetchall()

        return {
            "database": str(database),
            "bank_name": bank_name,
            "status_counts": [
                {
                    "status": row["current_status"],
                    "is_current": bool(row["is_current"]),
                    "count": row["count"],
                }
                for row in rows
            ],
        }
    finally:
        connection.close()