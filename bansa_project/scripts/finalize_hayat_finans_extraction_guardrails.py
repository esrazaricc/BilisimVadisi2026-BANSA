from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BANK_NAME = "Hayat Finans"

OVERRIDES = {
    "https://hayatfinans.com.tr/kampanyalar/bana-bunu-al-is-ortagim-ile-troy-magaza-firsatlari": {
        "finance_type": "Alışveriş Finansmanı",
        "financing_amount_max": 80000.0,
        "financing_amount_text": "80.000 TL'ye kadar",
        "maturity_max_months": 3,
        "maturity_text": "3 aya kadar",
        "installment_count": 3,
        "campaign_advantage": (
            "Hayat Finanslılara özel Troy mağazalarında "
            "80.000 TL'ye kadar, 3 aya varan alışveriş finansmanı fırsatı."
        ),
        "evidence_text": (
            "Hayat Finanslılara özel Troy mağazalarında 3 aya varan "
            "taksit fırsatı Bana Bunu Al İş Ortağımda! "
            "Kampanya üst limiti 80.000 TL'dir."
        ),
    },
    "https://hayatfinans.com.tr/kampanyalar/xiaomi-urunlerinde-finansman-avantaji": {
        "finance_type": "Alışveriş Finansmanı",
        "financing_amount_max": 40000.0,
        "financing_amount_text": "40.000 TL'ye kadar",
        "maturity_max_months": 3,
        "maturity_text": "3 aya kadar",
        "installment_count": 3,
        "campaign_advantage": (
            "Hayat Finanslılara özel Xiaomi mağazalarında "
            "40.000 TL'ye kadar, 3 aya varan alışveriş finansmanı fırsatı."
        ),
        "evidence_text": (
            "Hayat Finanslılara özel Xiaomi mağazalarında 3 aya varan "
            "taksit fırsatı Bana Bunu Al İş Ortağımda! "
            "Kampanya üst limiti 40.000 TL'dir."
        ),
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hayat Finans doğrulanmış finansman alanlarını URL bazlı düzeltir."
    )
    parser.add_argument("--bank", default=BANK_NAME)
    parser.add_argument("--db", type=Path, default=Path("data/campaigns.db"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("data/hayat_finans_extraction_guardrail_report.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.bank != BANK_NAME:
        raise SystemExit(f"Bu script yalnızca {BANK_NAME!r} için çalışır.")

    db_path = args.db.resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"Veritabanı bulunamadı: {db_path}")

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"campaigns_before_hayat_extraction_guardrail_{stamp}.db"
    shutil.copy2(db_path, backup_path)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    timestamp = now_iso()
    report_rows: list[dict] = []

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")

        with connection:
            for url, values in OVERRIDES.items():
                campaign = connection.execute(
                    """
                    SELECT id, title, campaign_category, record_kind,
                           is_current, current_status
                    FROM live_campaigns
                    WHERE bank_name = ?
                      AND RTRIM(source_url, '/') = ?
                    """,
                    (BANK_NAME, url.rstrip("/")),
                ).fetchone()

                if campaign is None:
                    raise RuntimeError("Beklenen kampanya bulunamadı: " + url)
                if campaign["record_kind"] != "campaign":
                    raise RuntimeError(f"Kayıt türü campaign değil: {campaign['title']}")
                if campaign["campaign_category"] != "finance_campaign":
                    raise RuntimeError(
                        f"finance_campaign değil: {campaign['title']} "
                        f"({campaign['campaign_category']})"
                    )
                if int(campaign["is_current"] or 0) != 1:
                    raise RuntimeError(f"Kampanya güncel değil: {campaign['title']}")

                campaign_id = int(campaign["id"])
                connection.execute(
                    """
                    INSERT INTO live_campaign_finance_details (
                        campaign_id, finance_type,
                        profit_share_rate_min, profit_share_rate_max,
                        profit_share_rate_text,
                        financing_amount_min, financing_amount_max,
                        financing_amount_text,
                        maturity_min_months, maturity_max_months,
                        maturity_text, grace_period_months,
                        installment_count,
                        allocation_fee_amount, allocation_fee_rate,
                        allocation_fee_status, expense_status,
                        expense_details, campaign_advantage,
                        evidence_text, extraction_confidence, extracted_at
                    ) VALUES (
                        ?, ?, NULL, NULL, NULL,
                        NULL, ?, ?, NULL, ?, ?, NULL, ?,
                        NULL, NULL, NULL, NULL, NULL, ?, ?, 0.99, ?
                    )
                    ON CONFLICT(campaign_id) DO UPDATE SET
                        finance_type = excluded.finance_type,
                        profit_share_rate_min = NULL,
                        profit_share_rate_max = NULL,
                        profit_share_rate_text = NULL,
                        financing_amount_min = NULL,
                        financing_amount_max = excluded.financing_amount_max,
                        financing_amount_text = excluded.financing_amount_text,
                        maturity_min_months = NULL,
                        maturity_max_months = excluded.maturity_max_months,
                        maturity_text = excluded.maturity_text,
                        grace_period_months = NULL,
                        installment_count = excluded.installment_count,
                        allocation_fee_amount = NULL,
                        allocation_fee_rate = NULL,
                        allocation_fee_status = NULL,
                        expense_status = NULL,
                        expense_details = NULL,
                        campaign_advantage = excluded.campaign_advantage,
                        evidence_text = excluded.evidence_text,
                        extraction_confidence = 0.99,
                        extracted_at = excluded.extracted_at
                    """,
                    (
                        campaign_id,
                        values["finance_type"],
                        values["financing_amount_max"],
                        values["financing_amount_text"],
                        values["maturity_max_months"],
                        values["maturity_text"],
                        values["installment_count"],
                        values["campaign_advantage"],
                        values["evidence_text"],
                        timestamp,
                    ),
                )

                verified = connection.execute(
                    """
                    SELECT finance_type, financing_amount_max,
                           financing_amount_text, maturity_max_months,
                           maturity_text, installment_count,
                           extraction_confidence
                    FROM live_campaign_finance_details
                    WHERE campaign_id = ?
                    """,
                    (campaign_id,),
                ).fetchone()

                expected = {
                    "finance_type": values["finance_type"],
                    "financing_amount_max": values["financing_amount_max"],
                    "financing_amount_text": values["financing_amount_text"],
                    "maturity_max_months": values["maturity_max_months"],
                    "maturity_text": values["maturity_text"],
                    "installment_count": values["installment_count"],
                }
                for key, expected_value in expected.items():
                    if verified[key] != expected_value:
                        raise RuntimeError(
                            f"Doğrulama başarısız: {campaign['title']} / {key} / "
                            f"beklenen={expected_value!r}, mevcut={verified[key]!r}"
                        )

                report_rows.append(
                    {
                        "campaign_id": campaign_id,
                        "title": campaign["title"],
                        "url": url,
                        "current_status": campaign["current_status"],
                        "finance_type": verified["finance_type"],
                        "financing_amount_text": verified["financing_amount_text"],
                        "maturity_text": verified["maturity_text"],
                        "installment_count": verified["installment_count"],
                        "extraction_confidence": verified["extraction_confidence"],
                    }
                )

        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(
                {
                    "bank_name": BANK_NAME,
                    "database": str(db_path),
                    "backup": str(backup_path),
                    "guardrail_count": len(report_rows),
                    "rows": report_rows,
                    "generated_at": timestamp,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print("=" * 92)
        print("HAYAT FİNANS FİNANSMAN ÇIKARIM DÜZELTMELERİ UYGULANDI")
        print("=" * 92)
        print("Düzeltilen finansman:", len(report_rows))
        print("Yedek:", backup_path)
        for row in report_rows:
            print()
            print("Kampanya:", row["title"])
            print("Finansman türü:", row["finance_type"])
            print("Finansman tutarı:", row["financing_amount_text"])
            print("Vade:", row["maturity_text"])
            print("Taksit:", row["installment_count"])
            print("Durum:", row["current_status"])
        print()
        print("Rapor:", args.report)
        print("HAYAT FİNANS FİNANSMAN ÇIKARIM KONTROLÜ BAŞARILI")
        return 0

    except Exception:
        connection.rollback()
        connection.close()
        shutil.copy2(backup_path, db_path)
        print("Hata nedeniyle veritabanı geri yüklendi:", backup_path)
        raise
    finally:
        try:
            connection.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
