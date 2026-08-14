from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path("data") / "campaigns.db"


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    print("=" * 100)
    print("ARAÇ FİNANSMANI — DASHBOARD VERİ DENETİMİ")
    print("=" * 100)

    rows = con.execute(
        """
        SELECT
            c.bank_name,
            d.product_name,
            d.profit_share_rate_text,
            d.maximum_maturity_months,
            d.vehicle_finance_rules_text,
            c.source_url
        FROM live_campaigns AS c
        JOIN live_standard_product_details AS d
            ON d.product_id=c.id
        WHERE c.record_kind='standard_product'
          AND c.is_current=1
          AND d.product_family='Araç Finansmanı'
        ORDER BY c.bank_name, d.product_name
        """
    ).fetchall()

    for row in rows:
        print()
        print(row["bank_name"], "|", row["product_name"])
        print("Kâr:", row["profit_share_rate_text"])
        print("Genel max vade:", row["maximum_maturity_months"])
        print("Araç kuralı:", row["vehicle_finance_rules_text"])

        fee = con.execute(
            """
            SELECT fee_label, waived, rate, amount, note
            FROM live_product_fee_rules
            WHERE product_id=(
                SELECT c2.id
                FROM live_campaigns AS c2
                JOIN live_standard_product_details AS d2
                    ON d2.product_id=c2.id
                WHERE c2.bank_name=?
                  AND d2.product_name=?
                  AND c2.is_current=1
                LIMIT 1
            )
            ORDER BY fee_label
            """,
            (
                row["bank_name"],
                row["product_name"],
            ),
        ).fetchall()

        for item in fee:
            print(
                "Masraf:",
                item["fee_label"],
                "| waived=", item["waived"],
                "| rate=", item["rate"],
                "| amount=", item["amount"],
            )

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
