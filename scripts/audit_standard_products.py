from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data") / "campaigns.db",
    )
    args = parser.parse_args()

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row

    exists = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table'
          AND name='live_standard_product_details'
        """
    ).fetchone()

    if not exists:
        print("Standart ürün detay tablosu henüz yok.")
        return 1

    rows = connection.execute(
        """
        SELECT
            c.bank_name,
            d.product_family,
            d.product_name,
            d.minimum_financing_amount,
            d.maximum_financing_amount,
            d.minimum_maturity_months,
            d.maximum_maturity_months,
            d.profit_share_rate_text,
            d.interest_free_text
        FROM live_campaigns AS c
        JOIN live_standard_product_details AS d
            ON d.product_id = c.id
        WHERE c.record_kind='standard_product'
          AND c.is_current=1
        ORDER BY
            c.bank_name,
            d.product_family,
            d.product_name
        """
    ).fetchall()

    print("=" * 80)
    print("STANDART ÜRÜN DB DENETİMİ")
    print("=" * 80)
    print("Güncel standart ürün:", len(rows))

    current = None
    for row in rows:
        group = (
            row["bank_name"],
            row["product_family"],
        )
        if group != current:
            current = group
            print()
            print(
                f"{row['bank_name']} | "
                f"{row['product_family']}"
            )

        print("  -", row["product_name"])
        print(
            "    Tutar:",
            row["minimum_financing_amount"],
            "→",
            row["maximum_financing_amount"],
        )
        print(
            "    Vade:",
            row["minimum_maturity_months"],
            "→",
            row["maximum_maturity_months"],
        )
        print(
            "    Kâr payı:",
            row["profit_share_rate_text"],
            "|",
            row["interest_free_text"],
        )

    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
