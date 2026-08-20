from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.live_campaign_sync import (
    canonicalize_url,
    ensure_schema,
    log_change,
    now_iso,
)

DEFAULT_DB = PROJECT_ROOT / "data" / "campaigns.db"
DEFAULT_DISCOVERY = PROJECT_ROOT / "data" / "discovered_campaign_pages.json"
DEFAULT_DISCOVERY_ERRORS = PROJECT_ROOT / "data" / "campaign_discovery_errors.json"
DEFAULT_STATE = PROJECT_ROOT / "data" / "campaign_missing_state.json"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "safe_campaign_removal_report.json"


@dataclass
class ProbeResult:
    reachable: bool | None
    status_code: int | None
    final_url: str
    error: str = ""


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _date_from_iso(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _probe_url(url: str, timeout: int) -> ProbeResult:
    try:
        response = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/150 Safari/537.36"
                )
            },
            stream=True,
        )
        status = int(response.status_code)
        final_url = canonicalize_url(response.url)
        response.close()

        if status in {404, 410}:
            return ProbeResult(False, status, final_url)
        if 200 <= status < 400:
            return ProbeResult(True, status, final_url)

        return ProbeResult(None, status, final_url)
    except requests.RequestException as error:
        return ProbeResult(None, None, "", f"{type(error).__name__}: {error}")


def _bank_discovery_urls(path: Path, bank_name: str) -> set[str]:
    rows = _load_json(path, [])
    if not isinstance(rows, list):
        raise RuntimeError("Keşif dosyası liste değil.")

    return {
        canonicalize_url(row.get("url"))
        for row in rows
        if isinstance(row, dict)
        and str(row.get("bank_name") or "") == bank_name
        and canonicalize_url(row.get("url"))
    }


def _has_discovery_error(path: Path, bank_name: str) -> bool:
    rows = _load_json(path, [])
    if not isinstance(rows, list):
        return True
    return any(
        isinstance(row, dict)
        and str(row.get("bank_name") or "") == bank_name
        for row in rows
    )


def _state_key(bank_name: str, url: str) -> str:
    return f"{bank_name}\n{canonicalize_url(url)}"


def _deactivate(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    new_status: str,
    reason: str,
    details: dict[str, Any],
) -> None:
    timestamp = now_iso()
    old_status = str(row["current_status"] or "unknown")

    connection.execute(
        """
        UPDATE live_campaigns
        SET
            current_status = ?,
            is_current = 0,
            removed_at = ?,
            last_checked_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            new_status,
            timestamp,
            timestamp,
            timestamp,
            row["id"],
        ),
    )

    log_change(
        connection,
        campaign_id=int(row["id"]),
        bank_name=str(row["bank_name"]),
        source_url=str(row["source_url"]),
        change_type=(
            "expired_missing_listing"
            if new_status == "expired"
            else "removed"
        ),
        old_hash=str(row["content_hash"] or ""),
        old_status=old_status,
        new_status=new_status,
        details={"reason": reason, **details},
    )


def process_bank(
    *,
    bank_name: str,
    db_path: Path,
    discovery_path: Path,
    discovery_errors_path: Path,
    state_path: Path,
    report_path: Path,
    confirm_after: int,
    timeout: int,
) -> dict[str, Any]:
    if _has_discovery_error(discovery_errors_path, bank_name):
        raise RuntimeError(
            f"{bank_name}: keşif hatası bulunduğu için kaldırma kontrolü yapılmadı."
        )

    discovered = _bank_discovery_urls(discovery_path, bank_name)
    if not discovered:
        raise RuntimeError(
            f"{bank_name}: keşif sonucu boş; kaldırma kontrolü güvenlik nedeniyle durdu."
        )

    state = _load_json(state_path, {})
    if not isinstance(state, dict):
        state = {}

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)

    rows = connection.execute(
        """
        SELECT *
        FROM live_campaigns
        WHERE bank_name = ?
          AND is_current = 1
        ORDER BY id
        """,
        (bank_name,),
    ).fetchall()

    current_by_url = {
        canonicalize_url(row["source_url"]): row
        for row in rows
        if canonicalize_url(row["source_url"])
    }

    # Yeniden keşfedilen URL'lerin bekleme durumunu temizle.
    for url in discovered:
        state.pop(_state_key(bank_name, url), None)

    missing = sorted(set(current_by_url) - discovered)
    today = date.today()
    actions: list[dict[str, Any]] = []
    removed = 0
    expired = 0
    pending = 0

    try:
        with connection:
            for url in missing:
                row = current_by_url[url]
                key = _state_key(bank_name, url)
                previous = state.get(key, {})
                if not isinstance(previous, dict):
                    previous = {}

                listing_miss_count = int(previous.get("listing_miss_count") or 0) + 1
                end_date = _date_from_iso(row["end_date"])
                status = str(row["current_status"] or "unknown").casefold()

                probe = _probe_url(url, timeout)
                entry = {
                    "bank_name": bank_name,
                    "url": url,
                    "title": str(row["title"] or ""),
                    "listing_miss_count": listing_miss_count,
                    "last_missing_at": now_iso(),
                    "http_status": probe.status_code,
                    "reachable": probe.reachable,
                    "final_url": probe.final_url,
                    "probe_error": probe.error,
                    "end_date": str(row["end_date"] or ""),
                }

                expired_by_date = end_date is not None and end_date < today
                already_expired = status == "expired"

                if expired_by_date or already_expired:
                    _deactivate(
                        connection,
                        row,
                        new_status="expired",
                        reason="missing_from_listing_and_expired",
                        details=entry,
                    )
                    state.pop(key, None)
                    entry["action"] = "expired"
                    expired += 1
                    actions.append(entry)
                    continue

                if (
                    probe.reachable is False
                    and listing_miss_count >= max(confirm_after, 1)
                ):
                    _deactivate(
                        connection,
                        row,
                        new_status="removed",
                        reason=(
                            "missing_from_successful_discovery_and_url_unavailable"
                        ),
                        details=entry,
                    )
                    state.pop(key, None)
                    entry["action"] = "removed"
                    removed += 1
                    actions.append(entry)
                    continue

                # URL hâlâ erişilebiliyorsa veya ağ sonucu belirsizse aktif kaydı
                # hemen silme. Bir sonraki başarılı taramada tekrar değerlendir.
                entry["action"] = "pending"
                state[key] = entry
                pending += 1
                actions.append(entry)
    finally:
        connection.close()

    _save_json(state_path, state)

    report = {
        "bank_name": bank_name,
        "generated_at": now_iso(),
        "discovered_count": len(discovered),
        "current_before_count": len(current_by_url),
        "missing_count": len(missing),
        "expired_count": expired,
        "removed_count": removed,
        "pending_count": pending,
        "confirm_after": confirm_after,
        "actions": actions,
    }
    _save_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Başarılı keşif sonrasında listede görünmeyen kampanyaları güvenli "
            "biçimde değerlendirir. Tek eksik taramada aktif kampanyayı silmez."
        )
    )
    parser.add_argument("--bank", required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--discovery", type=Path, default=DEFAULT_DISCOVERY)
    parser.add_argument(
        "--discovery-errors",
        type=Path,
        default=DEFAULT_DISCOVERY_ERRORS,
    )
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--confirm-after", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    report = process_bank(
        bank_name=args.bank,
        db_path=args.db,
        discovery_path=args.discovery,
        discovery_errors_path=args.discovery_errors,
        state_path=args.state,
        report_path=args.report,
        confirm_after=max(args.confirm_after, 1),
        timeout=max(args.timeout, 1),
    )

    print("\nGüvenli kaldırma kontrolü tamamlandı.")
    print("Banka:", report["bank_name"])
    print("Keşfedilen:", report["discovered_count"])
    print("Listede olmayan:", report["missing_count"])
    print("Süresi dolduğu için kapatılan:", report["expired_count"])
    print("İki aşamalı doğrulamayla kaldırılan:", report["removed_count"])
    print("Beklemede tutulan:", report["pending_count"])
    print("Rapor:", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
