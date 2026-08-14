from __future__ import annotations

import sqlite3
from pathlib import Path


DB = Path("data") / "campaigns.db"


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    product = con.execute(
        """
        SELECT
            c.id,
            d.product_name,
            d.vehicle_finance_rules_text
        FROM live_campaigns c
        JOIN live_standard_product_details d
          ON d.product_id=c.id
        WHERE c.bank_name='Türkiye Finans'
          AND c.record_kind='standard_product'
          AND c.is_current=1
          AND d.product_name LIKE 'İhtiyaç Finansmanı (%'
        LIMIT 1
        """
    ).fetchone()

    print("=" * 90)
    print("DASHBOARD SEMANTİK DOĞRULAMA")
    print("=" * 90)

    if not product:
        print("İhtiyaç Finansmanı bulunamadı.")
        return 1

    pid = product["id"]

    print("Ürün:", product["product_name"])
    print(
        "Araç finansman kuralı:",
        product["vehicle_finance_rules_text"],
    )

    print()
    print("TUTAR / VADE")
    rows = con.execute(
        """
        SELECT
            min_amount,
            max_amount,
            max_maturity_months
        FROM live_product_amount_maturity_rules
        WHERE product_id=?
        ORDER BY
          CASE
            WHEN min_amount IS NULL THEN -1
            ELSE min_amount
          END
        """,
        (pid,),
    ).fetchall()

    for row in rows:
        print(
            row["min_amount"],
            "→",
            row["max_amount"],
            "=",
            row["max_maturity_months"],
            "ay",
        )

    print()
    print("MASRAF")
    for row in con.execute(
        """
        SELECT
            fee_type,
            fee_label,
            waived,
            rate,
            amount
        FROM live_product_fee_rules
        WHERE product_id=?
        ORDER BY fee_type
        """,
        (pid,),
    ):
        print(dict(row))

    print()
    print("FİYATLAMA TAHSİS ORANLARI")
    values = con.execute(
        """
        SELECT DISTINCT allocation_fee_rate
        FROM live_product_pricing_tiers
        WHERE product_id=?
          AND allocation_fee_rate IS NOT NULL
        ORDER BY allocation_fee_rate
        """,
        (pid,),
    ).fetchall()

    print(
        [
            row["allocation_fee_rate"]
            for row in values
        ]
    )

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
