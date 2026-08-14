from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def display(value, suffix=""):
    if value in (None, ""):
        return "Belirtilmemiş"
    return f"{value}{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", default=None)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data") / "campaigns.db",
    )
    args = parser.parse_args()

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute(
            """
            SELECT
                bank_name,
                campaign_name,
                finance_type,
                profit_share_rate_text,
                financing_amount_text,
                maturity_text,
                grace_period_months,
                campaign_advantage,
                allocation_fee_amount,
                allocation_fee_rate,
                allocation_fee_status,
                expense_status,
                start_date,
                end_date,
                current_status
            FROM live_campaign_comparison
            WHERE campaign_category = 'finance_campaign'
              AND (? IS NULL OR bank_name = ?)
            ORDER BY
                finance_type,
                bank_name,
                campaign_name
            """,
            (args.bank, args.bank),
        ).fetchall()

        print("Finansman karşılaştırma kaydı:", len(rows))

        for row in rows:
            print("\n" + "=" * 72)
            print("Banka:", row["bank_name"])
            print("Kampanya:", row["campaign_name"])
            print("Finansman türü:", row["finance_type"])
            print(
                "Kâr payı:",
                display(row["profit_share_rate_text"]),
            )
            print(
                "Finansman tutarı:",
                display(row["financing_amount_text"]),
            )
            print(
                "Vade:",
                display(row["maturity_text"]),
            )
            print(
                "Ödemesiz dönem:",
                (
                    f"{row['grace_period_months']} ay"
                    if row["grace_period_months"]
                    else "Belirtilmemiş"
                ),
            )
            print(
                "Kampanya avantajı:",
                display(row["campaign_advantage"]),
            )

            allocation_display = "Belirtilmemiş"
            if row["allocation_fee_rate"] is not None:
                allocation_display = (
                    "%"
                    + str(row["allocation_fee_rate"]).replace(
                        ".",
                        ",",
                    )
                )
            elif row["allocation_fee_amount"] is not None:
                allocation_display = (
                    f"{row['allocation_fee_amount']:,.0f} TL"
                    .replace(",", ".")
                )
            elif row["allocation_fee_status"]:
                allocation_display = row["allocation_fee_status"]

            print("Tahsis ücreti:", allocation_display)
            print(
                "Masraf durumu:",
                display(row["expense_status"]),
            )
            print(
                "Kampanya süresi:",
                (
                    f"{display(row['start_date'])} - "
                    f"{display(row['end_date'])}"
                ),
            )
            print("Durum:", row["current_status"])

        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())