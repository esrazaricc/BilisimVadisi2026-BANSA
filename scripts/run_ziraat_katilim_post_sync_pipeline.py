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


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "campaigns.db"
BANKS_CONFIG = ROOT / "config" / "banks.json"
OVERRIDES_CONFIG = (
    ROOT / "config" / "campaign_classification_overrides.json"
)
REPORT_PATH = (
    ROOT / "data" / "ziraat_katilim_post_sync_pipeline_report.json"
)

BANK = "Ziraat Katılım"

EXPECTED_CURRENT = 72
EXPECTED_BENEFITS = 87
EXPECTED_AUDIENCES = 121
EXPECTED_DISTRIBUTION = {
    "card_campaign": 56,
    "discount_campaign": 10,
    "points_campaign": 5,
    "new_customer_campaign": 1,
}

REQUIRED_ZIRAAT_OVERRIDE_URLS = {
    "https://ziraatkatilim.com.tr/kart-kampanyalari/aile-karta-ozel-2000-tlye-varan-bankkart-lira-1",
    "https://ziraatkatilim.com.tr/kart-kampanyalari/akaryakit-harcamalariniza-400-tl-bankkart-lira-2",
    "https://ziraatkatilim.com.tr/kart-kampanyalari/bagimsiz-karta-ozel-5000-tlye-varan-bankkart-lira-1",
    "https://ziraatkatilim.com.tr/kart-kampanyalari/elektrikli-arac-sarj-istasyonlarinda-750-tl-bankkart-lira-0",
    "https://ziraatkatilim.com.tr/kart-kampanyalari/ziraat-katilim-avantajli-bankkart-kampanyalari",
    "https://ziraatkatilim.com.tr/kart-kampanyalari/ilk-bankkart-kredi-kartiniza-5000-tl-bankkart-lira-1",
    "https://ziraatkatilim.com.tr/kart-kampanyalari/hava-yolu-bilet-aliminiza-1500-tl-bankkart-lira-2",
    "https://ziraatkatilim.com.tr/kart-kampanyalari/turk-hava-yollarinda-6-taksit",
}


class PipelineError(RuntimeError):
    pass


def find_project_file(name: str, folders: Iterable[str]) -> Path:
    for folder in folders:
        candidate = ROOT / folder / name if folder else ROOT / name
        if candidate.exists():
            return candidate

    searched = ", ".join(
        str(ROOT / folder / name if folder else ROOT / name)
        for folder in folders
    )
    raise PipelineError(
        f"Gerekli dosya bulunamadı: {name}\nAranan yerler: {searched}"
    )


def run_step(
    title: str,
    command: list[str],
) -> dict[str, object]:
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
        check=False,
    )

    if completed.stdout:
        print(completed.stdout.rstrip())

    if completed.stderr:
        print(completed.stderr.rstrip(), file=sys.stderr)

    if completed.returncode != 0:
        raise PipelineError(
            f"{title} başarısız oldu. Çıkış kodu: "
            f"{completed.returncode}"
        )

    return {
        "title": title,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def table_exists(
    conn: sqlite3.Connection,
    table: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table,),
    ).fetchone()
    return row is not None


def other_banks_digest(
    conn: sqlite3.Connection,
) -> str:
    payload: dict[str, list[tuple]] = {}

    if table_exists(conn, "live_campaigns"):
        payload["live_campaigns"] = [
            tuple(row)
            for row in conn.execute(
                """
                SELECT *
                FROM live_campaigns
                WHERE bank_name <> ?
                ORDER BY rowid
                """,
                (BANK,),
            ).fetchall()
        ]

    for table in (
        "live_campaign_benefits",
        "live_campaign_audiences",
        "live_campaign_finance_details",
    ):
        if not table_exists(conn, table):
            continue

        columns = {
            row[1]
            for row in conn.execute(
                f"PRAGMA table_info({quote(table)})"
            )
        }

        if "campaign_id" not in columns:
            continue

        payload[table] = [
            tuple(row)
            for row in conn.execute(
                f"""
                SELECT d.*
                FROM {quote(table)} d
                JOIN live_campaigns c
                  ON c.id = d.campaign_id
                WHERE c.bank_name <> ?
                ORDER BY d.rowid
                """,
                (BANK,),
            ).fetchall()
        ]

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_banks() -> tuple[object, list[dict]]:
    data = json.loads(
        BANKS_CONFIG.read_text(encoding="utf-8")
    )

    if isinstance(data, list):
        return data, data

    if isinstance(data, dict) and isinstance(data.get("banks"), list):
        return data, data["banks"]

    raise PipelineError(
        "banks.json yapısı desteklenmiyor."
    )


def set_scanner_ready(value: bool) -> None:
    data, banks = read_banks()
    matches = [
        bank
        for bank in banks
        if bank.get("name") == BANK
    ]

    if len(matches) != 1:
        raise PipelineError(
            f"{BANK} kaydı tekil değil: {len(matches)}"
        )

    matches[0]["scanner_ready"] = value

    BANKS_CONFIG.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def scanner_ready_value() -> bool:
    _, banks = read_banks()

    for bank in banks:
        if bank.get("name") == BANK:
            return bank.get("scanner_ready") is True

    return False


def validate_override_config() -> dict[str, object]:
    data = json.loads(
        OVERRIDES_CONFIG.read_text(encoding="utf-8")
    )

    if not isinstance(data, list):
        raise PipelineError(
            "Sınıflandırma override dosyası liste olmalıdır."
        )

    ziraat = [
        item
        for item in data
        if isinstance(item, dict)
        and item.get("bank_name") == BANK
    ]

    urls = [
        item.get("source_url")
        for item in ziraat
    ]

    if len(urls) != len(set(urls)):
        raise PipelineError(
            "Ziraat Katılım override kayıtlarında tekrarlı URL var."
        )

    missing = REQUIRED_ZIRAAT_OVERRIDE_URLS - set(urls)

    if missing:
        raise PipelineError(
            "Eksik Ziraat Katılım override URL'leri:\n- "
            + "\n- ".join(sorted(missing))
        )

    return {
        "override_count": len(ziraat),
        "required_override_count": len(
            REQUIRED_ZIRAAT_OVERRIDE_URLS
        ),
    }


def validate_database() -> dict[str, object]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        current_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM live_campaigns
            WHERE bank_name = ?
              AND is_current = 1
            """,
            (BANK,),
        ).fetchone()[0]

        distribution = {
            row["campaign_category"]: row["count"]
            for row in conn.execute(
                """
                SELECT
                    campaign_category,
                    COUNT(*) AS count
                FROM live_campaigns
                WHERE bank_name = ?
                  AND is_current = 1
                GROUP BY campaign_category
                """,
                (BANK,),
            ).fetchall()
        }

        benefit_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM live_campaign_benefits b
            JOIN live_campaigns c
              ON c.id = b.campaign_id
            WHERE c.bank_name = ?
              AND c.is_current = 1
            """,
            (BANK,),
        ).fetchone()[0]

        audience_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM live_campaign_audiences a
            JOIN live_campaigns c
              ON c.id = a.campaign_id
            WHERE c.bank_name = ?
              AND c.is_current = 1
            """,
            (BANK,),
        ).fetchone()[0]

        missing_benefits = conn.execute(
            """
            SELECT COUNT(*)
            FROM live_campaigns c
            WHERE c.bank_name = ?
              AND c.is_current = 1
              AND NOT EXISTS (
                  SELECT 1
                  FROM live_campaign_benefits b
                  WHERE b.campaign_id = c.id
              )
            """,
            (BANK,),
        ).fetchone()[0]

        missing_audiences = conn.execute(
            """
            SELECT COUNT(*)
            FROM live_campaigns c
            WHERE c.bank_name = ?
              AND c.is_current = 1
              AND NOT EXISTS (
                  SELECT 1
                  FROM live_campaign_audiences a
                  WHERE a.campaign_id = c.id
              )
            """,
            (BANK,),
        ).fetchone()[0]

        special_rate_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM live_campaign_benefits b
            JOIN live_campaigns c
              ON c.id = b.campaign_id
            WHERE c.bank_name = ?
              AND c.is_current = 1
              AND b.benefit_type = 'special_rate'
            """,
            (BANK,),
        ).fetchone()[0]

    finally:
        conn.close()

    checks = {
        "current_count": (
            current_count,
            EXPECTED_CURRENT,
        ),
        "benefit_count": (
            benefit_count,
            EXPECTED_BENEFITS,
        ),
        "audience_count": (
            audience_count,
            EXPECTED_AUDIENCES,
        ),
        "distribution": (
            distribution,
            EXPECTED_DISTRIBUTION,
        ),
        "missing_benefits": (
            missing_benefits,
            0,
        ),
        "missing_audiences": (
            missing_audiences,
            0,
        ),
        "special_rate_count": (
            special_rate_count,
            0,
        ),
    }

    failures = [
        f"{name}: gerçek={actual!r}, beklenen={expected!r}"
        for name, (actual, expected) in checks.items()
        if actual != expected
    ]

    if failures:
        raise PipelineError(
            "Nihai veritabanı doğrulaması başarısız:\n- "
            + "\n- ".join(failures)
        )

    return {
        "current_campaigns": current_count,
        "benefits": benefit_count,
        "audiences": audience_count,
        "distribution": distribution,
        "missing_benefits": missing_benefits,
        "missing_audiences": missing_audiences,
        "special_rate_records": special_rate_count,
    }


def copy_backup(
    source: Path,
    destination: Path,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(source, destination)


def restore_backup(
    backup: Path,
    destination: Path,
) -> None:
    if backup.exists():
        shutil.copy2(backup, destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Ziraat Katılım için sınıflandırma, override, "
            "karşılaştırma alanı çıkarımı ve kalite "
            "doğrulamasını güvenli sırayla çalıştırır."
        )
    )
    parser.add_argument(
        "--keep-scanner-disabled",
        action="store_true",
        help=(
            "Pipeline başarılı olsa bile scanner_ready "
            "değerini true yapmaz."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    required_files = (
        DB_PATH,
        BANKS_CONFIG,
        OVERRIDES_CONFIG,
    )

    for path in required_files:
        if not path.exists():
            raise FileNotFoundError(
                f"Gerekli dosya bulunamadı: {path}"
            )

    classify_script = find_project_file(
        "classify_campaign_records.py",
        ("scripts", ""),
    )
    apply_overrides_script = find_project_file(
        "apply_ziraat_katilim_classification_overrides.py",
        ("", "scripts"),
    )
    extract_script = find_project_file(
        "extract_comparison_fields.py",
        ("scripts", ""),
    )
    guardrail_script = find_project_file(
        "finalize_ziraat_katilim_extraction_guardrails.py",
        ("", "scripts"),
    )
    audit_script = find_project_file(
        "audit_ziraat_katilim_final_quality.py",
        ("", "scripts"),
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    backup_dir = (
        ROOT
        / "data"
        / "backups"
        / f"ziraat_post_sync_pipeline_{stamp}"
    )
    db_backup = backup_dir / "campaigns.db"
    banks_backup = backup_dir / "banks.json"
    overrides_backup = (
        backup_dir
        / "campaign_classification_overrides.json"
    )

    copy_backup(DB_PATH, db_backup)
    copy_backup(BANKS_CONFIG, banks_backup)
    copy_backup(OVERRIDES_CONFIG, overrides_backup)

    conn = sqlite3.connect(DB_PATH)
    try:
        before_other_digest = other_banks_digest(
            conn
        )
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
        # Otomatik süreç sırasında banka, tüm doğrulamalar
        # tamamlanana kadar taramaya hazır kabul edilmez.
        set_scanner_ready(False)

        steps.append(
            run_step(
                "1/5 — Ziraat Katılım sınıflandırması",
                [
                    sys.executable,
                    str(classify_script),
                    "--bank",
                    BANK,
                ],
            )
        )

        steps.append(
            run_step(
                "2/5 — Ziraat Katılım sınıflandırma override'ları",
                [
                    sys.executable,
                    str(apply_overrides_script),
                ],
            )
        )

        extraction_report = (
            ROOT
            / "data"
            / "ziraat_katilim_comparison_extraction_report.json"
        )
        steps.append(
            run_step(
                "3/5 — Ziraat Katılım karşılaştırma alanları",
                [
                    sys.executable,
                    str(extract_script),
                    "--bank",
                    BANK,
                    "--report",
                    str(extraction_report),
                ],
            )
        )

        steps.append(
            run_step(
                "4/5 — Ziraat Katılım extraction guardrail",
                [
                    sys.executable,
                    str(guardrail_script),
                ],
            )
        )

        steps.append(
            run_step(
                "5/5 — Ziraat Katılım nihai kalite denetimi",
                [
                    sys.executable,
                    str(audit_script),
                ],
            )
        )

        override_validation = (
            validate_override_config()
        )
        database_validation = validate_database()

        conn = sqlite3.connect(DB_PATH)
        try:
            after_other_digest = other_banks_digest(
                conn
            )
        finally:
            conn.close()

        if before_other_digest != after_other_digest:
            raise PipelineError(
                "Diğer bankaların verileri değişti."
            )

        if not args.keep_scanner_disabled:
            set_scanner_ready(True)

            if not scanner_ready_value():
                raise PipelineError(
                    "scanner_ready=true doğrulanamadı."
                )

        report.update(
            {
                "status": "success",
                "finished_at": datetime.now().isoformat(),
                "scanner_ready": scanner_ready_value(),
                "other_banks_unchanged": True,
                "override_validation": override_validation,
                "database_validation": database_validation,
            }
        )

        REPORT_PATH.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        print()
        print("=" * 90)
        print("ZİRAAT KATILIM POST-SYNC PIPELINE BAŞARILI")
        print("=" * 90)
        print(
            "scanner_ready:",
            scanner_ready_value(),
        )
        print(
            "Güncel kampanya:",
            database_validation["current_campaigns"],
        )
        print(
            "Avantaj:",
            database_validation["benefits"],
        )
        print(
            "Hedef kitle:",
            database_validation["audiences"],
        )
        print("Diğer bankalar: değişmedi")
        print("Rapor:", REPORT_PATH)

        return 0

    except Exception as exc:
        restore_backup(db_backup, DB_PATH)
        restore_backup(
            banks_backup,
            BANKS_CONFIG,
        )
        restore_backup(
            overrides_backup,
            OVERRIDES_CONFIG,
        )

        report.update(
            {
                "status": "failed",
                "finished_at": datetime.now().isoformat(),
                "error": str(exc),
                "rollback_completed": True,
            }
        )

        REPORT_PATH.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        print()
        print("=" * 90)
        print("PIPELINE BAŞARISIZ — GERİ ALMA TAMAMLANDI")
        print("=" * 90)
        print("Hata:", exc)
        print("Veritabanı ve config dosyaları geri yüklendi.")
        print("Rapor:", REPORT_PATH)

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
