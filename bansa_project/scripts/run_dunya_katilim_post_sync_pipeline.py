from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

BANK = "Dünya Katılım"
ALLOWED_CATEGORIES = {
    "card_campaign",
    "discount_campaign",
    "finance_campaign",
    "new_customer_campaign",
    "points_campaign",
    "other_campaign",
    "service_information",
}
SERVICE_URLS = {
    "https://dunyakatilim.com.tr/kampanyalar/avantajli-kurlar",
    "https://dunyakatilim.com.tr/kampanyalar/tahsile-cek",
}
EXPECTED_OVERRIDES = {
    "https://dunyakatilim.com.tr/kampanyalar/pazarama-paraf": (
        "campaign", "card_campaign"
    ),
    "https://dunyakatilim.com.tr/kampanyalar/altin-kesemTicari": (
        "campaign", "points_campaign"
    ),
    "https://dunyakatilim.com.tr/kampanyalar/avantajli-kurlar": (
        "service_information", "service_information"
    ),
    "https://dunyakatilim.com.tr/kampanyalar/tahsile-cek": (
        "service_information", "service_information"
    ),
}


class PipelineError(RuntimeError):
    pass


def find_root() -> Path:
    start = Path(__file__).resolve().parent
    for candidate in (start, *start.parents):
        if (candidate / "data" / "campaigns.db").is_file() and (
            candidate / "config" / "banks.json"
        ).is_file():
            return candidate
    raise FileNotFoundError("Proje kökü bulunamadı.")


ROOT = find_root()
DB_PATH = ROOT / "data" / "campaigns.db"
BANKS_CONFIG = ROOT / "config" / "banks.json"
OVERRIDES_CONFIG = (
    ROOT / "config" / "campaign_classification_overrides.json"
)
REPORT_PATH = (
    ROOT / "data" / "dunya_katilim_post_sync_pipeline_report.json"
)


def find_project_file(name: str, folders: Iterable[str]) -> Path:
    for folder in folders:
        candidate = ROOT / folder / name if folder else ROOT / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Gerekli dosya bulunamadı: {name}")


def run_step(title: str, command: list[str]) -> dict[str, object]:
    print()
    print("=" * 90)
    print(title)
    print("=" * 90)
    print("Komut:", " ".join(command))
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.stdout:
        print(completed.stdout.rstrip())
    if completed.stderr:
        print(completed.stderr.rstrip(), file=sys.stderr)
    result = {
        "title": title,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode != 0:
        raise PipelineError(
            f"{title} başarısız oldu (kod={completed.returncode})."
        )
    return result


def read_banks() -> tuple[object, list[dict[str, object]]]:
    data = json.loads(BANKS_CONFIG.read_text(encoding="utf-8"))
    banks = data if isinstance(data, list) else data.get("banks", [])
    if not isinstance(banks, list):
        raise PipelineError("banks.json içindeki banks alanı list değil.")
    return data, banks


def set_scanner_ready(value: bool) -> None:
    data, banks = read_banks()
    matches = [bank for bank in banks if bank.get("name") == BANK]
    if len(matches) != 1:
        raise PipelineError(
            f"banks.json içinde {BANK!r} kaydı tekil değil: {len(matches)}"
        )
    matches[0]["scanner_ready"] = value
    BANKS_CONFIG.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def scanner_ready_value() -> bool:
    _, banks = read_banks()
    for bank in banks:
        if bank.get("name") == BANK:
            return bank.get("scanner_ready") is True
    return False


def campaign_fk(conn: sqlite3.Connection, table: str) -> str:
    for row in conn.execute(
        f'PRAGMA foreign_key_list("{table}")'
    ).fetchall():
        if row["table"] == "live_campaigns":
            return row["from"]
    columns = {
        row["name"]
        for row in conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    }
    for candidate in ("campaign_id", "live_campaign_id", "live_id"):
        if candidate in columns:
            return candidate
    raise PipelineError(f"{table} için kampanya bağlantı alanı bulunamadı.")


def rows_digest(rows: list[sqlite3.Row]) -> str:
    payload = [{key: row[key] for key in row.keys()} for row in rows]
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def other_banks_digest(conn: sqlite3.Connection) -> dict[str, str]:
    result = {
        "live_campaigns": rows_digest(
            conn.execute(
                '''SELECT * FROM live_campaigns
                   WHERE bank_name <> ? ORDER BY id''',
                (BANK,),
            ).fetchall()
        )
    }
    for table in (
        "live_campaign_benefits",
        "live_campaign_audiences",
        "live_campaign_finance_details",
    ):
        fk = campaign_fk(conn, table)
        rows = conn.execute(
            f'''SELECT child.*
                FROM "{table}" AS child
                JOIN live_campaigns AS campaign
                  ON campaign.id = child."{fk}"
                WHERE campaign.bank_name <> ?
                ORDER BY child.rowid''',
            (BANK,),
        ).fetchall()
        result[table] = rows_digest(rows)
    return result


def validate_overrides() -> dict[str, object]:
    data = json.loads(OVERRIDES_CONFIG.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise PipelineError("Override config üst veri türü list değil.")
    matches = [item for item in data if item.get("bank_name") == BANK]
    if len(matches) != 4:
        raise PipelineError(
            f"Dünya Katılım override sayısı {len(matches)}; beklenen 4."
        )
    by_url = {str(item.get("source_url") or ""): item for item in matches}
    if set(by_url) != set(EXPECTED_OVERRIDES):
        raise PipelineError("Dünya Katılım override URL'leri hatalı.")
    for url, (record_kind, category) in EXPECTED_OVERRIDES.items():
        item = by_url[url]
        if item.get("record_kind") != record_kind:
            raise PipelineError(f"Override record_kind hatalı: {url}")
        if item.get("campaign_category") != category:
            raise PipelineError(f"Override kategori hatalı: {url}")
    return {"count": len(matches), "urls": sorted(by_url)}


def child_count(conn: sqlite3.Connection, table: str) -> int:
    fk = campaign_fk(conn, table)
    return conn.execute(
        f'''SELECT COUNT(*) AS count
            FROM "{table}" AS child
            JOIN live_campaigns AS campaign
              ON campaign.id = child."{fk}"
            WHERE campaign.bank_name = ?
              AND campaign.is_current = 1''',
        (BANK,),
    ).fetchone()["count"]


def missing_child_count(conn: sqlite3.Connection, table: str) -> int:
    fk = campaign_fk(conn, table)
    return conn.execute(
        f'''SELECT COUNT(*) AS count
            FROM live_campaigns AS campaign
            WHERE campaign.bank_name = ?
              AND campaign.is_current = 1
              AND campaign.record_kind = 'campaign'
              AND campaign.comparison_eligible = 1
              AND NOT EXISTS (
                  SELECT 1 FROM "{table}" AS child
                  WHERE child."{fk}" = campaign.id
              )''',
        (BANK,),
    ).fetchone()["count"]


def validate_database() -> dict[str, object]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT * FROM live_campaigns
               WHERE bank_name = ? AND is_current = 1""",
            (BANK,),
        ).fetchall()

        if not rows:
            raise PipelineError("Dünya Katılım için güncel kayıt bulunamadı.")

        distribution: dict[str, int] = {}
        for row in rows:
            category = str(row["campaign_category"] or "NULL")
            distribution[category] = distribution.get(category, 0) + 1

        current_campaigns = [
            row for row in rows if row["record_kind"] == "campaign"
        ]
        service_rows = [
            row for row in rows
            if row["record_kind"] == "service_information"
        ]
        actual_service_urls = {
            str(row["source_url"] or "") for row in service_rows
        }

        failures: list[str] = []

        invalid_kinds = [
            row for row in rows
            if row["record_kind"] not in {"campaign", "service_information"}
        ]
        if invalid_kinds:
            failures.append(
                "Beklenmeyen record_kind: "
                + ", ".join(
                    f"{row['title']}={row['record_kind']}"
                    for row in invalid_kinds[:5]
                )
            )

        unknown_categories = sorted(
            category for category in distribution
            if category not in ALLOWED_CATEGORIES
        )
        if unknown_categories:
            failures.append(
                "Beklenmeyen/unclassified kategori: "
                + ", ".join(unknown_categories)
            )

        by_url = {str(row["source_url"] or ""): row for row in rows}
        known_service_misclassified = [
            url for url in SERVICE_URLS
            if url in by_url
            and by_url[url]["record_kind"] != "service_information"
        ]
        if known_service_misclassified:
            failures.append(
                "Bilinen hizmet URL'leri yanlış sınıflandırılmış: "
                + ", ".join(sorted(known_service_misclassified))
            )

        open_services = [
            row for row in service_rows
            if int(row["comparison_eligible"] or 0) != 0
        ]
        if open_services:
            failures.append(
                "Hizmet kaydı karşılaştırmaya açık: "
                + ", ".join(str(row["title"]) for row in open_services)
            )

        closed_campaigns = [
            row for row in current_campaigns
            if int(row["comparison_eligible"] or 0) != 1
        ]
        if closed_campaigns:
            failures.append(
                "Gerçek kampanya karşılaştırmaya kapalı: "
                + ", ".join(str(row["title"]) for row in closed_campaigns[:5])
            )

        non_active = [
            row for row in rows
            if str(row["current_status"] or "") != "active"
        ]
        if non_active:
            failures.append(
                "is_current=1 fakat active olmayan kayıt: "
                + ", ".join(
                    f"{row['title']}={row['current_status']}"
                    for row in non_active[:5]
                )
            )

        benefits = child_count(conn, "live_campaign_benefits")
        audiences = child_count(conn, "live_campaign_audiences")
        finance_details = child_count(
            conn, "live_campaign_finance_details"
        )
        missing_benefits = missing_child_count(
            conn, "live_campaign_benefits"
        )
        missing_audiences = missing_child_count(
            conn, "live_campaign_audiences"
        )

        missing_finance = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM live_campaigns AS campaign
            WHERE campaign.bank_name = ?
              AND campaign.is_current = 1
              AND campaign.record_kind = 'campaign'
              AND campaign.comparison_eligible = 1
              AND campaign.campaign_category = 'finance_campaign'
              AND NOT EXISTS (
                  SELECT 1
                  FROM live_campaign_finance_details AS finance
                  WHERE finance.campaign_id = campaign.id
              )
            """,
            (BANK,),
        ).fetchone()["count"]
        if missing_finance:
            failures.append(
                f"Finansman detayı eksik kampanya sayısı: {missing_finance}"
            )

        warnings: list[str] = []
        if missing_benefits:
            warnings.append(
                f"{missing_benefits} kampanyada yapılandırılmış avantaj kaydı yok."
            )
        if missing_audiences:
            warnings.append(
                f"{missing_audiences} kampanyada yapılandırılmış hedef kitle kaydı yok."
            )

        values = {
            "current_records": len(rows),
            "current_campaigns": len(current_campaigns),
            "service_information": len(service_rows),
            "comparison_eligible": sum(
                int(row["comparison_eligible"] or 0) == 1 for row in rows
            ),
            "active": sum(
                str(row["current_status"] or "") == "active" for row in rows
            ),
            "benefits": benefits,
            "audiences": audiences,
            "finance_details": finance_details,
            "missing_finance_details": missing_finance,
            "distribution": distribution,
            "missing_benefits": missing_benefits,
            "missing_audiences": missing_audiences,
            "warnings": warnings,
        }

        if failures:
            raise PipelineError(
                "Veritabanı doğrulaması başarısız:\n- "
                + "\n- ".join(failures)
            )

        return values
    finally:
        conn.close()


def copy_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def restore_backup(backup: Path, destination: Path) -> None:
    if backup.exists():
        shutil.copy2(backup, destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dünya Katılım post-sync adımlarını güvenli biçimde çalıştırır."
        )
    )
    parser.add_argument(
        "--keep-scanner-disabled",
        action="store_true",
        help=(
            "Pipeline başarılı olsa bile scanner_ready değerini true yapmaz."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    classify_script = find_project_file(
        "classify_campaign_records.py", ("scripts", "")
    )
    override_script = find_project_file(
        "apply_campaign_classification_overrides.py", ("scripts", "")
    )
    extract_script = find_project_file(
        "extract_comparison_fields.py", ("scripts", "")
    )
    guardrail_script = find_project_file(
        "finalize_dunya_katilim_extraction_guardrails.py",
        ("", "scripts"),
    )
    audit_script = find_project_file(
        "audit_dunya_katilim_final_quality.py", ("", "scripts")
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = (
        ROOT / "data" / "backups" / f"dunya_post_sync_pipeline_{stamp}"
    )
    db_backup = backup_dir / "campaigns.db"
    banks_backup = backup_dir / "banks.json"
    overrides_backup = backup_dir / "campaign_classification_overrides.json"
    copy_backup(DB_PATH, db_backup)
    copy_backup(BANKS_CONFIG, banks_backup)
    copy_backup(OVERRIDES_CONFIG, overrides_backup)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        before_other_digest = other_banks_digest(conn)
    finally:
        conn.close()

    steps: list[dict[str, object]] = []
    report: dict[str, object] = {
        "bank": BANK,
        "started_at": datetime.now().isoformat(),
        "status": "running",
        "backup_dir": str(backup_dir),
        "steps": steps,
    }

    try:
        set_scanner_ready(False)
        steps.append(run_step(
            "1/5 — Dünya Katılım sınıflandırması",
            [sys.executable, str(classify_script), "--bank", BANK],
        ))
        steps.append(run_step(
            "2/5 — Dünya Katılım sınıflandırma override'ları",
            [sys.executable, str(override_script), "--bank", BANK],
        ))

        extraction_report = (
            ROOT / "data" / "dunya_katilim_comparison_extraction_report.json"
        )
        steps.append(run_step(
            "3/5 — Dünya Katılım karşılaştırma alanları",
            [
                sys.executable,
                str(extract_script),
                "--bank",
                BANK,
                "--report",
                str(extraction_report),
            ],
        ))
        steps.append(run_step(
            "4/5 — Dünya Katılım extraction guardrail",
            [sys.executable, str(guardrail_script)],
        ))
        steps.append(run_step(
            "5/5 — Dünya Katılım nihai kalite denetimi",
            [sys.executable, str(audit_script)],
        ))

        override_validation = validate_overrides()
        database_validation = validate_database()

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            after_other_digest = other_banks_digest(conn)
        finally:
            conn.close()

        if before_other_digest != after_other_digest:
            raise PipelineError(
                "Diğer bankaların verilerinde değişiklik tespit edildi."
            )

        if not args.keep_scanner_disabled:
            set_scanner_ready(True)
            if not scanner_ready_value():
                raise PipelineError("scanner_ready=true doğrulanamadı.")

        report.update({
            "status": "success",
            "finished_at": datetime.now().isoformat(),
            "scanner_ready": scanner_ready_value(),
            "other_banks_unchanged": True,
            "override_validation": override_validation,
            "database_validation": database_validation,
        })
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print()
        print("=" * 90)
        print("DÜNYA KATILIM POST-SYNC PIPELINE BAŞARILI")
        print("=" * 90)
        print("scanner_ready:", scanner_ready_value())
        print("Güncel kayıt:", database_validation["current_records"])
        print("Gerçek kampanya:", database_validation["current_campaigns"])
        print("Hizmet bilgisi:", database_validation["service_information"])
        print("Avantaj:", database_validation["benefits"])
        print("Hedef kitle:", database_validation["audiences"])
        print("Finansman detayı:", database_validation["finance_details"])
        print("Diğer bankalar: değişmedi")
        print("Rapor:", REPORT_PATH)
        return 0

    except Exception as exc:
        restore_backup(db_backup, DB_PATH)
        restore_backup(banks_backup, BANKS_CONFIG)
        restore_backup(overrides_backup, OVERRIDES_CONFIG)
        report.update({
            "status": "failed",
            "finished_at": datetime.now().isoformat(),
            "error": str(exc),
            "rollback_completed": True,
        })
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print()
        print("=" * 90)
        print("DÜNYA KATILIM POST-SYNC PIPELINE BAŞARISIZ")
        print("=" * 90)
        print("Hata:", exc)
        print("Rollback: tamamlandı")
        print("Rapor:", REPORT_PATH)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
