from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.live_campaign_sync import (
    ensure_schema,
    upsert_campaign,
)
from src.extraction.comparison_field_extractor import (
    extract_finance_fields,
)
from src.scraping.campaign_discovery import (
    canonicalize_url,
    load_bank_config,
)
from src.scraping.campaign_page_fetcher import fetch_page
from src.scraping.http_client import HttpClient


BANK_NAME = "Albaraka Türk"
TARGET_URL = (
    "https://albaraka.com.tr/tr/kampanyalar/detay/"
    "taksitliocom-alisveris-finansmani"
)
TARGET_TITLE_KEY = "taksitlio.com alışveriş finansmanı"

DB_PATH = PROJECT_ROOT / "data" / "campaigns.db"
DISCOVERY_PATH = PROJECT_ROOT / "data" / "discovered_campaign_pages.json"
INDEX_PATH = PROJECT_ROOT / "data" / "campaign_page_index.json"


def now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


def load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"JSON kökü liste olmalı: {path}")
    return value


def find_discovery_row() -> dict:
    wanted = canonicalize_url(TARGET_URL)
    rows = load_json_list(DISCOVERY_PATH)

    for row in rows:
        if row.get("bank_name") != BANK_NAME:
            continue
        if canonicalize_url(str(row.get("url") or "")) == wanted:
            return dict(row)

    # Discovery dosyasındaki eski veri eksik olsa bile hedef sayfa
    # banka sitesinin doğrulanmış kampanya detay URL'sidir.
    return {
        "bank_name": BANK_NAME,
        "url": wanted,
        "source_page": "https://albaraka.com.tr/tr/kampanyalar",
        "page_type": "campaign_detail",
        "discovery_mode": "targeted_live_refresh",
        "source_group": "Genel Kampanyalar",
        "listing_status": "unknown",
        "status_evidence": "",
        "listing_text": "Taksitlio.com Alışveriş Finansmanı",
    }


def bank_config() -> dict:
    for row in load_bank_config(
        PROJECT_ROOT / "config" / "banks.json"
    ):
        if row.get("name") == BANK_NAME:
            return row
    raise RuntimeError("Albaraka Türk config kaydı bulunamadı.")


def find_existing_index_row(rows: list[dict]) -> tuple[int | None, dict | None]:
    wanted = canonicalize_url(TARGET_URL)

    for index, row in enumerate(rows):
        if row.get("bank_name") != BANK_NAME:
            continue
        candidates = (
            row.get("requested_url"),
            row.get("url"),
        )
        if any(
            canonicalize_url(str(value or "")) == wanted
            for value in candidates
        ):
            return index, row

    return None, None


def snapshot_path_for(existing_row: dict | None) -> Path:
    if existing_row:
        value = str(existing_row.get("snapshot_file") or "").strip()
        if value:
            path = Path(value)
            return path if path.is_absolute() else PROJECT_ROOT / path

    return (
        PROJECT_ROOT
        / "data"
        / "campaign_pages"
        / "albaraka_turk"
        / "taksitlio_com_alisveris_finansmani_live.json"
    )


def backup_files(snapshot_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = (
        PROJECT_ROOT
        / "data"
        / "backups"
        / f"albaraka_taksitlio_refresh_{stamp}"
    )
    backup_dir.mkdir(parents=True, exist_ok=True)

    for path in (DB_PATH, INDEX_PATH, snapshot_path):
        if path.exists():
            try:
                relative = path.relative_to(PROJECT_ROOT)
            except ValueError:
                relative = Path(path.name)
            destination = backup_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)

    return backup_dir


def save_snapshot_and_index(snapshot) -> None:
    rows = load_json_list(INDEX_PATH)
    row_index, existing = find_existing_index_row(rows)
    snapshot_path = snapshot_path_for(existing)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    snapshot_dict = asdict(snapshot)
    snapshot_path.write_text(
        json.dumps(
            snapshot_dict,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    index_row = dict(snapshot_dict)
    index_row.pop("raw_text", None)
    index_row.pop("clean_text", None)

    try:
        relative_snapshot = snapshot_path.relative_to(PROJECT_ROOT)
        index_row["snapshot_file"] = relative_snapshot.as_posix()
    except ValueError:
        index_row["snapshot_file"] = snapshot_path.as_posix()

    if row_index is None:
        rows.append(index_row)
    else:
        rows[row_index] = index_row

    rows.sort(
        key=lambda item: (
            str(item.get("bank_name") or ""),
            canonicalize_url(
                str(
                    item.get("requested_url")
                    or item.get("url")
                    or ""
                )
            ),
        )
    )

    INDEX_PATH.write_text(
        json.dumps(
            rows,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def update_live_campaign(snapshot, discovery: dict) -> set[str]:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        ensure_schema(connection)
        with connection:
            changes, unavailable = upsert_campaign(
                connection,
                bank_name=BANK_NAME,
                discovery=discovery,
                snapshot=asdict(snapshot),
            )

        if unavailable:
            raise RuntimeError(
                "Canlı sayfa başarıyla çekildiği halde snapshot unavailable "
                "olarak işaretlendi."
            )
        return changes
    finally:
        connection.close()


def run_post_processing() -> None:
    commands = [
        [
            sys.executable,
            "scripts/classify_campaign_records.py",
            "--bank",
            BANK_NAME,
        ],
        [
            sys.executable,
            "scripts/apply_campaign_classification_overrides.py",
            "--bank",
            BANK_NAME,
        ],
        [
            sys.executable,
            "scripts/extract_comparison_fields.py",
            "--bank",
            BANK_NAME,
            "--report",
            "data/albaraka_comparison_extraction_report.json",
        ],
    ]

    for command in commands:
        print("\n>", " ".join(command))
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Post-processing başarısız oldu: "
                + " ".join(command)
            )


def current_db_rate() -> tuple[float | None, float | None, str | None]:
    connection = sqlite3.connect(DB_PATH)
    try:
        row = connection.execute(
            """
            SELECT
                finance.profit_share_rate_min,
                finance.profit_share_rate_max,
                finance.profit_share_rate_text
            FROM live_campaigns AS campaign
            LEFT JOIN live_campaign_finance_details AS finance
              ON finance.campaign_id = campaign.id
            WHERE campaign.bank_name = ?
              AND campaign.source_url = ?
              AND campaign.is_current = 1
            LIMIT 1
            """,
            (BANK_NAME, canonicalize_url(TARGET_URL)),
        ).fetchone()

        if row is None:
            raise RuntimeError(
                "Taksitlio kampanyası veritabanında bulunamadı."
            )

        return row[0], row[1], row[2]
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Albaraka Türk Taksitlio kampanyasını yalnızca kendi URL'sinden "
            "canlı yeniler; diğer kampanyaları eklemez, silmez veya pasife "
            "almaz. Ardından Streamlit karşılaştırma alanlarını yeniden üretir."
        )
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    discovery = find_discovery_row()
    config = bank_config()

    index_rows = load_json_list(INDEX_PATH)
    _, existing_index = find_existing_index_row(index_rows)
    snapshot_path = snapshot_path_for(existing_index)
    backup_dir = backup_files(snapshot_path)

    print("=" * 80)
    print("ALBARAKA TÜRK - TAKSİTLİO CANLI YENİLEME")
    print("=" * 80)
    print("URL:", canonicalize_url(TARGET_URL))
    print("Yedek:", backup_dir)

    page = {
        "bank_name": BANK_NAME,
        "url": canonicalize_url(TARGET_URL),
        "source_page": discovery.get(
            "source_page",
            "https://albaraka.com.tr/tr/kampanyalar",
        ),
        "page_type": discovery.get(
            "page_type",
            "campaign_detail",
        ),
        "discovery_mode": "targeted_live_refresh",
        "source_group": discovery.get(
            "source_group",
            "Genel Kampanyalar",
        ),
        "listing_status": discovery.get(
            "listing_status",
            "unknown",
        ),
        "status_evidence": discovery.get(
            "status_evidence",
            "",
        ),
        "listing_text": discovery.get(
            "listing_text",
            "Taksitlio.com Alışveriş Finansmanı",
        ),
    }

    with HttpClient(
        timeout=args.timeout,
        delay_seconds=0.1,
    ) as client:
        snapshot = fetch_page(
            page,
            client,
            bank_config=config,
            browser_fallback=True,
            headless=not args.headed,
        )

    if snapshot.fetch_status not in {"ok", "short_content"}:
        raise RuntimeError(
            "Canlı sayfa güvenilir biçimde çekilemedi. "
            f"fetch_status={snapshot.fetch_status!r}"
        )

    if TARGET_TITLE_KEY not in snapshot.title.casefold():
        raise RuntimeError(
            "Beklenmeyen sayfa başlığı alındı: "
            f"{snapshot.title!r}"
        )

    extracted_live = extract_finance_fields(
        snapshot.title,
        snapshot.clean_text,
    )

    if extracted_live.profit_share_rate_min is None:
        raise RuntimeError(
            "Canlı sayfada açık kâr oranı bulunamadı; DB güncellenmedi."
        )

    old_min, old_max, old_text = current_db_rate()

    save_snapshot_and_index(snapshot)
    changes = update_live_campaign(snapshot, discovery)
    run_post_processing()

    new_min, new_max, new_text = current_db_rate()

    if (
        new_min != extracted_live.profit_share_rate_min
        or new_max != extracted_live.profit_share_rate_max
    ):
        raise RuntimeError(
            "Canlı sayfa ile DB kâr oranı eşleşmedi. "
            f"canlı={extracted_live.profit_share_rate_text}, "
            f"db={new_text}"
        )

    print("\n" + "=" * 80)
    print("DOĞRULAMA BAŞARILI")
    print("=" * 80)
    print("Önceki DB kâr oranı:", old_text or "Belirtilmemiş")
    print(
        "Canlı sayfadan bulunan kâr oranı:",
        extracted_live.profit_share_rate_text,
    )
    print("Yeni DB / Streamlit kâr oranı:", new_text)
    print("İçerik değişiklikleri:", ", ".join(sorted(changes)))
    print("Son kontrol:", now_iso())
    print(
        "\nBu işlem yalnızca Taksitlio kampanyasını canlı yeniledi; "
        "diğer Albaraka kampanyalarını kaldırmadı."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
