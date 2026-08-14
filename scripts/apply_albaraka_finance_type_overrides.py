from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "campaigns.db"
REPORT_PATH = ROOT / "data" / "albaraka_finance_type_override_report.json"

BANK = "Albaraka Türk"
URL = (
    "https://albaraka.com.tr/tr/kampanyalar/detay/"
    "taksitliocom-alisveris-finansmani"
)
TITLE = "Taksitlio.com Alışveriş Finansmanı"
FINANCE_TYPE = "Alışveriş Finansmanı"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Veritabanı bulunamadı: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    report = {
        "bank": BANK,
        "url": URL,
        "expected_finance_type": FINANCE_TYPE,
        "started_at": now_iso(),
    }

    try:
        row = conn.execute(
            """
            SELECT
                c.id AS campaign_id,
                c.title,
                c.record_kind,
                f.finance_type
            FROM live_campaigns AS c
            JOIN live_campaign_finance_details AS f
              ON f.campaign_id = c.id
            WHERE c.bank_name = ?
              AND c.source_url = ?
              AND c.is_current = 1
            """,
            (BANK, URL),
        ).fetchone()

        if row is None:
            raise RuntimeError("Hedef Taksitlio kaydı bulunamadı.")
        if row["title"] != TITLE:
            raise RuntimeError(
                f"Beklenmeyen başlık: {row['title']!r}"
            )
        if row["record_kind"] != "campaign":
            raise RuntimeError(
                f"Kayıt türü kampanya değil: {row['record_kind']!r}"
            )

        before = row["finance_type"]

        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """
            UPDATE live_campaign_finance_details
            SET
                finance_type = ?,
                extracted_at = CURRENT_TIMESTAMP
            WHERE campaign_id = ?
              AND COALESCE(finance_type, '') <> ?
            """,
            (FINANCE_TYPE, row["campaign_id"], FINANCE_TYPE),
        )

        after = conn.execute(
            """
            SELECT finance_type
            FROM live_campaign_finance_details
            WHERE campaign_id = ?
            """,
            (row["campaign_id"],),
        ).fetchone()

        if after is None or after["finance_type"] != FINANCE_TYPE:
            raise RuntimeError("Finansman türü doğrulanamadı.")

        conn.commit()

        report.update(
            {
                "status": "success",
                "finished_at": now_iso(),
                "campaign_id": row["campaign_id"],
                "title": row["title"],
                "before_finance_type": before,
                "after_finance_type": after["finance_type"],
                "changed_rows": cursor.rowcount,
            }
        )

        print("=" * 80)
        print("ALBARAKA FİNANSMAN TÜRÜ OVERRIDE BAŞARILI")
        print("=" * 80)
        print("Kampanya:", row["title"])
        print("Önceki tür:", before)
        print("Yeni tür:", after["finance_type"])
        print("Değiştirilen kayıt:", cursor.rowcount)

    except Exception as exc:
        conn.rollback()
        report.update(
            {
                "status": "failed",
                "finished_at": now_iso(),
                "error": str(exc),
            }
        )
        raise

    finally:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        conn.close()

    print("Rapor:", REPORT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
