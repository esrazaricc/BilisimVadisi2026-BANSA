from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.extraction.comparison_field_extractor import (
    extract_audiences,
    extract_benefits,
    extract_finance_fields,
)
from src.extraction.finance_extraction_override import (
    apply_finance_override,
)


DEFAULT_DB = Path("data") / "campaigns.db"
DEFAULT_REPORT = Path("data") / "comparison_extraction_report.json"


def now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS live_campaign_finance_details (
            campaign_id INTEGER PRIMARY KEY,
            finance_type TEXT NOT NULL,
            profit_share_rate_min REAL,
            profit_share_rate_max REAL,
            profit_share_rate_text TEXT,
            financing_amount_min REAL,
            financing_amount_max REAL,
            financing_amount_text TEXT,
            maturity_min_months INTEGER,
            maturity_max_months INTEGER,
            maturity_text TEXT,
            grace_period_months INTEGER,
            installment_count INTEGER,
            allocation_fee_amount REAL,
            allocation_fee_rate REAL,
            allocation_fee_status TEXT,
            expense_status TEXT,
            expense_details TEXT,
            campaign_advantage TEXT,
            evidence_text TEXT,
            extraction_confidence REAL NOT NULL DEFAULT 0,
            extracted_at TEXT NOT NULL,
            FOREIGN KEY(campaign_id)
                REFERENCES live_campaigns(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS live_campaign_benefits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            benefit_type TEXT NOT NULL,
            amount REAL,
            rate REAL,
            points REAL,
            minimum_spending REAL,
            maximum_benefit REAL,
            description TEXT NOT NULL,
            evidence TEXT,
            extracted_at TEXT NOT NULL,
            FOREIGN KEY(campaign_id)
                REFERENCES live_campaigns(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_live_benefits_campaign
        ON live_campaign_benefits(campaign_id);

        CREATE TABLE IF NOT EXISTS live_campaign_audiences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            audience_type TEXT NOT NULL,
            audience_label TEXT NOT NULL,
            details TEXT,
            extracted_at TEXT NOT NULL,
            FOREIGN KEY(campaign_id)
                REFERENCES live_campaigns(id)
                ON DELETE CASCADE,
            UNIQUE(campaign_id, audience_type, audience_label)
        );

        CREATE INDEX IF NOT EXISTS idx_live_audiences_campaign
        ON live_campaign_audiences(campaign_id);
        """
    )

    finance_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(live_campaign_finance_details)"
        ).fetchall()
    }
    if "grace_period_months" not in finance_columns:
        connection.execute(
            "ALTER TABLE live_campaign_finance_details "
            "ADD COLUMN grace_period_months INTEGER"
        )

    connection.execute(
        "DROP VIEW IF EXISTS live_campaign_comparison"
    )
    connection.execute(
        """
        CREATE VIEW live_campaign_comparison AS
        SELECT
            campaign.id AS campaign_id,
            campaign.bank_name,
            campaign.title AS campaign_name,
            campaign.source_url,
            campaign.current_status,
            campaign.record_kind,
            campaign.campaign_category,
            campaign.start_date,
            campaign.end_date,
            finance.finance_type,
            finance.profit_share_rate_min,
            finance.profit_share_rate_max,
            finance.profit_share_rate_text,
            finance.financing_amount_min,
            finance.financing_amount_max,
            finance.financing_amount_text,
            finance.maturity_min_months,
            finance.maturity_max_months,
            finance.maturity_text,
            finance.grace_period_months,
            finance.installment_count AS finance_installment_count,
            finance.allocation_fee_amount,
            finance.allocation_fee_rate,
            finance.allocation_fee_status,
            finance.expense_status,
            finance.expense_details,
            finance.campaign_advantage,
            finance.extraction_confidence,
            MAX(
                CASE
                    WHEN benefit.benefit_type = 'reward'
                    THEN benefit.amount
                END
            ) AS reward_amount,
            MAX(
                CASE
                    WHEN benefit.benefit_type = 'discount'
                    THEN benefit.rate
                END
            ) AS discount_rate,
            MAX(
                CASE
                    WHEN benefit.benefit_type = 'cashback'
                    THEN COALESCE(benefit.amount, benefit.rate)
                END
            ) AS cashback_value,
            MAX(
                CASE
                    WHEN benefit.benefit_type = 'shopping_points'
                    THEN benefit.points
                END
            ) AS shopping_points,
            MAX(
                CASE
                    WHEN benefit.benefit_type = 'installment'
                    THEN CAST(
                        REPLACE(benefit.description, ' taksit', '')
                        AS INTEGER
                    )
                END
            ) AS campaign_installment_count,
            MAX(benefit.minimum_spending) AS minimum_spending,
            MAX(benefit.maximum_benefit) AS maximum_benefit
        FROM live_campaigns AS campaign
        LEFT JOIN live_campaign_finance_details AS finance
            ON finance.campaign_id = campaign.id
        LEFT JOIN live_campaign_benefits AS benefit
            ON benefit.campaign_id = campaign.id
        GROUP BY campaign.id
        """
    )


def upsert_finance(
    connection: sqlite3.Connection,
    campaign_id: int,
    extraction,
    timestamp: str,
) -> None:
    connection.execute(
        """
        INSERT INTO live_campaign_finance_details (
            campaign_id,
            finance_type,
            profit_share_rate_min,
            profit_share_rate_max,
            profit_share_rate_text,
            financing_amount_min,
            financing_amount_max,
            financing_amount_text,
            maturity_min_months,
            maturity_max_months,
            maturity_text,
            grace_period_months,
            installment_count,
            allocation_fee_amount,
            allocation_fee_rate,
            allocation_fee_status,
            expense_status,
            expense_details,
            campaign_advantage,
            evidence_text,
            extraction_confidence,
            extracted_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT(campaign_id) DO UPDATE SET
            finance_type = excluded.finance_type,
            profit_share_rate_min = excluded.profit_share_rate_min,
            profit_share_rate_max = excluded.profit_share_rate_max,
            profit_share_rate_text = excluded.profit_share_rate_text,
            financing_amount_min = excluded.financing_amount_min,
            financing_amount_max = excluded.financing_amount_max,
            financing_amount_text = excluded.financing_amount_text,
            maturity_min_months = excluded.maturity_min_months,
            maturity_max_months = excluded.maturity_max_months,
            maturity_text = excluded.maturity_text,
            grace_period_months = excluded.grace_period_months,
            installment_count = excluded.installment_count,
            allocation_fee_amount = excluded.allocation_fee_amount,
            allocation_fee_rate = excluded.allocation_fee_rate,
            allocation_fee_status = excluded.allocation_fee_status,
            expense_status = excluded.expense_status,
            expense_details = excluded.expense_details,
            campaign_advantage = excluded.campaign_advantage,
            evidence_text = excluded.evidence_text,
            extraction_confidence = excluded.extraction_confidence,
            extracted_at = excluded.extracted_at
        """,
        (
            campaign_id,
            extraction.finance_type,
            extraction.profit_share_rate_min,
            extraction.profit_share_rate_max,
            extraction.profit_share_rate_text,
            extraction.financing_amount_min,
            extraction.financing_amount_max,
            extraction.financing_amount_text,
            extraction.maturity_min_months,
            extraction.maturity_max_months,
            extraction.maturity_text,
            extraction.grace_period_months,
            extraction.installment_count,
            extraction.allocation_fee_amount,
            extraction.allocation_fee_rate,
            extraction.allocation_fee_status,
            extraction.expense_status,
            extraction.expense_details,
            extraction.campaign_advantage,
            extraction.evidence_text,
            extraction.extraction_confidence,
            timestamp,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Kampanya metinlerinden dashboard karşılaştırma "
            "alanlarını çıkarır."
        )
    )
    parser.add_argument("--bank", default=None)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
    )
    args = parser.parse_args()

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row

    try:
        ensure_schema(connection)

        where = "WHERE record_kind = 'campaign'"
        parameters: list[str] = []

        if args.bank:
            where += " AND bank_name = ?"
            parameters.append(args.bank)

        rows = connection.execute(
            f"""
            SELECT
                id,
                bank_name,
                title,
                source_url,
                source_group,
                clean_text,
                campaign_category,
                current_status
            FROM live_campaigns
            {where}
            ORDER BY bank_name, title
            """,
            parameters,
        ).fetchall()

        timestamp = now_iso()
        finance_count = 0
        finance_override_count = 0
        benefit_count = 0
        audience_count = 0
        review_items: list[dict] = []

        with connection:
            for row in rows:
                campaign_id = int(row["id"])
                title = row["title"] or ""
                clean_text = row["clean_text"] or ""
                category = row["campaign_category"] or ""

                connection.execute(
                    "DELETE FROM live_campaign_benefits "
                    "WHERE campaign_id = ?",
                    (campaign_id,),
                )
                connection.execute(
                    "DELETE FROM live_campaign_audiences "
                    "WHERE campaign_id = ?",
                    (campaign_id,),
                )

                if category == "finance_campaign":
                    finance = extract_finance_fields(
                        title,
                        clean_text,
                    )
                    finance, override_applied = (
                        apply_finance_override(
                            finance,
                            bank_name=row["bank_name"],
                            source_url=row["source_url"],
                        )
                    )
                    if override_applied:
                        finance_override_count += 1

                    upsert_finance(
                        connection,
                        campaign_id,
                        finance,
                        timestamp,
                    )
                    finance_count += 1

                    review_reasons = []

                    if finance.finance_type == "Diğer Finansman":
                        review_reasons.append(
                            "finansman türü belirlenemedi"
                        )
                    if finance.campaign_advantage is None:
                        review_reasons.append(
                            "kampanya avantajı çıkarılamadı"
                        )
                    if finance.extraction_confidence < 0.60:
                        review_reasons.append(
                            "alan çıkarım güveni düşük"
                        )

                    # Kâr payı, tutar, vade ve masraf her
                    # kampanyada bulunmak zorunda değildir.
                    if review_reasons:
                        review_items.append(
                            {
                                "campaign_id": campaign_id,
                                "bank_name": row["bank_name"],
                                "title": title,
                                "finance_type": finance.finance_type,
                                "review_reasons": review_reasons,
                                "confidence": (
                                    finance.extraction_confidence
                                ),
                            }
                        )
                else:
                    connection.execute(
                        "DELETE FROM live_campaign_finance_details "
                        "WHERE campaign_id = ?",
                        (campaign_id,),
                    )

                benefits = extract_benefits(title, clean_text)
                for benefit in benefits:
                    connection.execute(
                        """
                        INSERT INTO live_campaign_benefits (
                            campaign_id,
                            benefit_type,
                            amount,
                            rate,
                            points,
                            minimum_spending,
                            maximum_benefit,
                            description,
                            evidence,
                            extracted_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            campaign_id,
                            benefit.benefit_type,
                            benefit.amount,
                            benefit.rate,
                            benefit.points,
                            benefit.minimum_spending,
                            benefit.maximum_benefit,
                            benefit.description,
                            benefit.evidence,
                            timestamp,
                        ),
                    )
                    benefit_count += 1

                audiences = extract_audiences(
                    title,
                    clean_text,
                    source_group=row["source_group"] or "",
                    campaign_category=category,
                )
                for audience in audiences:
                    connection.execute(
                        """
                        INSERT INTO live_campaign_audiences (
                            campaign_id,
                            audience_type,
                            audience_label,
                            details,
                            extracted_at
                        )
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(
                            campaign_id,
                            audience_type,
                            audience_label
                        ) DO UPDATE SET
                            details = excluded.details,
                            extracted_at = excluded.extracted_at
                        """,
                        (
                            campaign_id,
                            audience.audience_type,
                            audience.audience_label,
                            audience.details,
                            timestamp,
                        ),
                    )
                    audience_count += 1

        report = {
            "database": str(args.db),
            "bank_name": args.bank,
            "processed_campaigns": len(rows),
            "finance_campaigns": finance_count,
            "finance_override_rows": finance_override_count,
            "benefit_rows": benefit_count,
            "audience_rows": audience_count,
            "manual_review_count": len(review_items),
            "manual_review": review_items,
            "generated_at": timestamp,
        }

        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print("Karşılaştırma alanları çıkarıldı.")
        print(
            "Banka:",
            args.bank or "Tüm bankalar",
        )
        print("İşlenen kampanya:", len(rows))
        print("Finansman kampanyası:", finance_count)
        print(
            "Doğrulanmış finansman düzeltmesi:",
            finance_override_count,
        )
        print("Avantaj kaydı:", benefit_count)
        print("Hedef kitle kaydı:", audience_count)
        print(
            "Finansman manuel kontrol:",
            len(review_items),
        )

        print("\nFinansman ön izlemesi:")
        preview = connection.execute(
            """
            SELECT
                bank_name,
                campaign_name,
                finance_type,
                profit_share_rate_text,
                financing_amount_text,
                maturity_text,
                grace_period_months,
                allocation_fee_amount,
                allocation_fee_rate,
                allocation_fee_status,
                expense_status,
                campaign_advantage,
                current_status
            FROM live_campaign_comparison
            WHERE campaign_category = 'finance_campaign'
              AND (? IS NULL OR bank_name = ?)
            ORDER BY bank_name, campaign_name
            """,
            (args.bank, args.bank),
        ).fetchall()

        for item in preview:
            print("\nBanka:", item["bank_name"])
            print("Kampanya:", item["campaign_name"])
            print("Finansman türü:", item["finance_type"])
            print(
                "Kâr payı:",
                item["profit_share_rate_text"]
                or "Belirtilmemiş",
            )
            print(
                "Finansman tutarı:",
                item["financing_amount_text"]
                or "Belirtilmemiş",
            )
            print(
                "Vade:",
                item["maturity_text"]
                or "Belirtilmemiş",
            )
            print(
                "Ödemesiz dönem:",
                (
                    f"{item['grace_period_months']} ay"
                    if item["grace_period_months"]
                    else "Belirtilmemiş"
                ),
            )

            allocation_display = "Belirtilmemiş"
            if item["allocation_fee_rate"] is not None:
                allocation_display = (
                    "%"
                    + str(item["allocation_fee_rate"]).replace(
                        ".",
                        ",",
                    )
                )
            elif item["allocation_fee_amount"] is not None:
                allocation_display = (
                    f"{item['allocation_fee_amount']:,.0f} TL"
                    .replace(",", ".")
                )
            elif item["allocation_fee_status"]:
                allocation_display = item["allocation_fee_status"]

            print("Tahsis ücreti:", allocation_display)
            print(
                "Masraf:",
                item["expense_status"]
                or "Belirtilmemiş",
            )
            print(
                "Avantaj:",
                item["campaign_advantage"]
                or "Belirtilmemiş",
            )
            print("Durum:", item["current_status"])

        print("\nRapor:", args.report)
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())