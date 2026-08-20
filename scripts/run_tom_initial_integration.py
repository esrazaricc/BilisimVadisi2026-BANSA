from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.live_campaign_sync import canonicalize_url
from src.scraping.campaign_status import evaluate_campaign_status


BANK = "T.O.M. Katılım"
DB_PATH = PROJECT_ROOT / "data" / "campaigns.db"
DISCOVERY_PATH = PROJECT_ROOT / "data" / "discovered_campaign_pages.json"
INDEX_PATH = PROJECT_ROOT / "data" / "campaign_page_index.json"
FETCH_ERRORS_PATH = PROJECT_ROOT / "data" / "campaign_page_fetch_errors.json"
DISCOVERY_ERRORS_PATH = PROJECT_ROOT / "data" / "campaign_discovery_errors.json"
REPORT_PATH = PROJECT_ROOT / "data" / "tom_katilim_initial_integration_report.json"


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run(command: list[str], label: str) -> None:
    print("\n" + "=" * 78)
    print(label)
    print("=" * 78)
    print("Komut:", " ".join(command))
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env={
            **__import__("os").environ,
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        },
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"{label} başarısız oldu (kod={completed.returncode})."
        )


def bank_rows(path: Path) -> list[dict]:
    value = load_json(path, [])
    if not isinstance(value, list):
        raise RuntimeError(f"JSON kökü liste değil: {path}")
    return [
        row for row in value
        if isinstance(row, dict)
        and str(row.get("bank_name") or "") == BANK
    ]


def repair_snapshot_statuses() -> dict[str, int]:
    """
    Daha önce çekilmiş 75 T.O.M. snapshot'ını yeniden internete çıkmadan
    güncel durum kurallarıyla değerlendirir. Özellikle
    '(GEÇMİŞ KAMPANYA)' başlıklı kayıtlar expired olur.
    """
    rows = load_json(INDEX_PATH, [])
    if not isinstance(rows, list):
        raise RuntimeError("campaign_page_index.json liste değil.")

    matched = 0
    updated = 0
    status_counts: Counter[str] = Counter()

    for row in rows:
        if (
            not isinstance(row, dict)
            or str(row.get("bank_name") or "") != BANK
        ):
            continue

        matched += 1
        snapshot_value = str(row.get("snapshot_file") or "").strip()
        if not snapshot_value:
            raise RuntimeError(
                "T.O.M. indeks kaydında snapshot_file boş: "
                + str(row.get("requested_url") or row.get("url") or "")
            )

        snapshot_path = Path(snapshot_value)
        if not snapshot_path.is_absolute():
            snapshot_path = PROJECT_ROOT / snapshot_path

        if not snapshot_path.exists():
            raise RuntimeError(
                f"Snapshot bulunamadı: {snapshot_path}"
            )

        snapshot = load_json(snapshot_path, {})
        if not isinstance(snapshot, dict):
            raise RuntimeError(
                f"Snapshot JSON nesne değil: {snapshot_path}"
            )

        result = evaluate_campaign_status(
            text=(
                f"{snapshot.get('title') or ''} "
                f"{snapshot.get('clean_text') or ''}"
            ),
            listing_status=str(
                snapshot.get("listing_status") or "unknown"
            ),
            listing_evidence=str(
                snapshot.get("listing_status_evidence") or ""
            ),
        )

        before = str(snapshot.get("current_status") or "unknown")

        updates = {
            "campaign_start_date": result.start_date,
            "campaign_end_date": result.end_date,
            "current_status": result.status,
            "status_reason": result.reason,
            "status_evidence": result.evidence,
            "status_checked_at": result.checked_at,
        }
        snapshot.update(updates)
        row.update(updates)

        if before != result.status:
            updated += 1

        status_counts[result.status] += 1
        save_json(snapshot_path, snapshot)

    save_json(INDEX_PATH, rows)

    return {
        "matched_snapshots": matched,
        "status_updated": updated,
        **{
            f"snapshot_status_{key}": value
            for key, value in sorted(status_counts.items())
        },
    }


def validate_source_files(expected: int | None) -> dict[str, int]:
    discovered = bank_rows(DISCOVERY_PATH)
    fetched = bank_rows(INDEX_PATH)
    discovery_errors = bank_rows(DISCOVERY_ERRORS_PATH)
    fetch_errors = bank_rows(FETCH_ERRORS_PATH)

    discovered_urls = {
        canonicalize_url(row.get("url"))
        for row in discovered
        if canonicalize_url(row.get("url"))
    }

    fetched_urls = {
        canonicalize_url(
            row.get("requested_url") or row.get("url")
        )
        for row in fetched
        if canonicalize_url(
            row.get("requested_url") or row.get("url")
        )
    }

    if expected is not None and len(discovered_urls) != expected:
        raise RuntimeError(
            f"Keşif sayısı {len(discovered_urls)}; beklenen {expected}."
        )

    if discovery_errors:
        raise RuntimeError(
            f"T.O.M. keşif hata kaydı var: {len(discovery_errors)}"
        )
    if fetch_errors:
        raise RuntimeError(
            f"T.O.M. fetch hata kaydı var: {len(fetch_errors)}"
        )

    missing_fetch = discovered_urls - fetched_urls
    if missing_fetch:
        raise RuntimeError(
            f"{len(missing_fetch)} keşif URL'sinin fetch snapshot'ı yok."
        )

    return {
        "discovered": len(discovered_urls),
        "fetched": len(fetched_urls),
        "discovery_errors": len(discovery_errors),
        "fetch_errors": len(fetch_errors),
    }


def make_backup() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = (
        PROJECT_ROOT
        / "data"
        / "backups"
        / f"campaigns_before_tom_initial_{stamp}.db"
    )
    backup.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        source = sqlite3.connect(DB_PATH)
        target = sqlite3.connect(backup)
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()
    return backup


def db_quality() -> dict:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT
                id,
                title,
                source_url,
                current_status,
                is_current,
                record_kind,
                campaign_category,
                comparison_eligible
            FROM live_campaigns
            WHERE bank_name = ?
            ORDER BY id
            """,
            (BANK,),
        ).fetchall()

        if not rows:
            raise RuntimeError("DB'de T.O.M. kaydı oluşmadı.")

        statuses = Counter(
            str(row["current_status"] or "unknown")
            for row in rows
        )
        kinds = Counter(
            str(row["record_kind"] or "unclassified")
            for row in rows
        )
        categories = Counter(
            str(row["campaign_category"] or "unclassified")
            for row in rows
        )

        review = [
            {
                "title": str(row["title"] or ""),
                "url": str(row["source_url"] or ""),
                "record_kind": str(row["record_kind"] or ""),
                "category": str(row["campaign_category"] or ""),
                "status": str(row["current_status"] or ""),
            }
            for row in rows
            if str(row["record_kind"] or "") != "campaign"
            or str(row["campaign_category"] or "") in {
                "",
                "unclassified",
            }
        ]

        duplicate_urls = connection.execute(
            """
            SELECT source_url, COUNT(*)
            FROM live_campaigns
            WHERE bank_name = ?
            GROUP BY source_url
            HAVING COUNT(*) > 1
            """,
            (BANK,),
        ).fetchall()

        finance_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM live_campaign_finance_details AS f
            JOIN live_campaigns AS c
              ON c.id = f.campaign_id
            WHERE c.bank_name = ?
            """,
            (BANK,),
        ).fetchone()[0]

        benefit_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM live_campaign_benefits AS b
            JOIN live_campaigns AS c
              ON c.id = b.campaign_id
            WHERE c.bank_name = ?
            """,
            (BANK,),
        ).fetchone()[0]

        audience_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM live_campaign_audiences AS a
            JOIN live_campaigns AS c
              ON c.id = a.campaign_id
            WHERE c.bank_name = ?
            """,
            (BANK,),
        ).fetchone()[0]

        return {
            "db_records": len(rows),
            "current_records": sum(
                int(row["is_current"] or 0) == 1
                for row in rows
            ),
            "statuses": dict(statuses),
            "record_kinds": dict(kinds),
            "categories": dict(categories),
            "finance_detail_rows": int(finance_count or 0),
            "benefit_rows": int(benefit_count or 0),
            "audience_rows": int(audience_count or 0),
            "duplicate_url_groups": len(duplicate_urls),
            "review_count": len(review),
            "review": review[:30],
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "T.O.M. Katılım'ın daha önce keşfedilip fetch edilmiş "
            "kampanyalarını güvenli biçimde ilk kez DB/dashboard "
            "pipeline'ına alır. Otomatik taramayı henüz açmaz."
        )
    )
    parser.add_argument(
        "--expected",
        type=int,
        default=75,
        help="Bu ilk entegrasyonda beklenen benzersiz keşif sayısı.",
    )
    args = parser.parse_args()

    print("=" * 78)
    print("T.O.M. KATILIM — İLK DASHBOARD ENTEGRASYONU")
    print("=" * 78)
    print("Bu işlem yeni web taraması yapmaz.")
    print("Mevcut keşif + 75 fetch snapshot'ını kullanır.")
    print("Kaldırma/pasife alma yapmaz.")
    print("scanner_ready değerini değiştirmez.")

    source_check = validate_source_files(args.expected)
    print("\nKaynak kontrolü:", source_check)

    status_repair = repair_snapshot_statuses()
    print("Snapshot durum düzeltmesi:", status_repair)

    backup = make_backup()
    print("DB yedeği:", backup)

    try:
        run(
            [
                sys.executable,
                "scripts/sync_campaigns_to_db.py",
                "--bank",
                BANK,
                "--no-mark-removed",
            ],
            "1/4 — Güvenli DB senkronizasyonu",
        )

        run(
            [
                sys.executable,
                "scripts/classify_campaign_records.py",
                "--bank",
                BANK,
            ],
            "2/4 — Kampanya sınıflandırması",
        )

        run(
            [
                sys.executable,
                "scripts/apply_campaign_classification_overrides.py",
                "--bank",
                BANK,
            ],
            "3/4 — Doğrulanmış sınıflandırma override'ları",
        )

        run(
            [
                sys.executable,
                "scripts/extract_comparison_fields.py",
                "--bank",
                BANK,
                "--report",
                "data/tom_katilim_comparison_extraction_report.json",
            ],
            "4/4 — Dashboard karşılaştırma alanları",
        )

        quality = db_quality()

        if quality["db_records"] != source_check["discovered"]:
            raise RuntimeError(
                "DB kayıt sayısı keşifle eşleşmiyor: "
                f"DB={quality['db_records']}, "
                f"keşif={source_check['discovered']}"
            )
        if quality["duplicate_url_groups"]:
            raise RuntimeError(
                "DB'de T.O.M. mükerrer URL grubu bulundu."
            )

        report = {
            "bank_name": BANK,
            "source": source_check,
            "snapshot_status_repair": status_repair,
            "database_quality": quality,
            "backup_path": str(backup.relative_to(PROJECT_ROOT)),
            "scanner_ready_enabled": False,
            "next_step": (
                "review_count=0 veya doğrulanmış override'lardan sonra "
                "scanner_ready=true yapılıp all-bank canlı updater'a dahil edilecek."
            ),
        }
        save_json(REPORT_PATH, report)

        print("\n" + "=" * 78)
        print("T.O.M. İLK ENTEGRASYON TAMAMLANDI")
        print("=" * 78)
        print("DB kayıt:", quality["db_records"])
        print("Durumlar:", quality["statuses"])
        print("Kayıt türleri:", quality["record_kinds"])
        print("Kategoriler:", quality["categories"])
        print("Finansman detay kaydı:", quality["finance_detail_rows"])
        print("Avantaj kaydı:", quality["benefit_rows"])
        print("Hedef kitle kaydı:", quality["audience_rows"])
        print("Kontrol gereken:", quality["review_count"])
        print("Mükerrer URL grubu:", quality["duplicate_url_groups"])
        print("Rapor:", REPORT_PATH)
        print()
        print("NOT: scanner_ready hâlâ false.")
        print("Bu çıktıyı kontrol ettikten sonra canlı otomasyonu açacağız.")
        return 0
    except Exception:
        if backup.exists():
            source = sqlite3.connect(backup)
            target = sqlite3.connect(DB_PATH)
            try:
                source.backup(target)
            finally:
                source.close()
                target.close()
            print("\nHATA: DB yedeği geri yüklendi:", backup)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
