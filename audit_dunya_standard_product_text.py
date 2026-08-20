from __future__ import annotations

import sqlite3
from pathlib import Path


DB_PATH = Path("data") / "campaigns.db"


def main() -> int:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    rows = con.execute(
        """
        SELECT
            c.title,
            c.clean_text,
            d.product_family,
            d.product_name,
            d.minimum_financing_amount,
            d.maximum_financing_amount,
            d.minimum_maturity_months,
            d.maximum_maturity_months,
            d.profit_share_rate_text,
            d.interest_free_text,
            c.source_url
        FROM live_campaigns AS c
        JOIN live_standard_product_details AS d
            ON d.product_id = c.id
        WHERE c.record_kind='standard_product'
          AND c.is_current=1
          AND c.bank_name='Dünya Katılım'
          AND (
                d.product_name LIKE '%Enerya%'
                OR d.product_name='İhtiyaç Finansmanı'
              )
        ORDER BY d.product_name
        """
    ).fetchall()

    print("=" * 100)
    print("DÜNYA KATILIM — İHTİYAÇ FİNANSMANI DETAY DENETİMİ")
    print("=" * 100)

    for row in rows:
        print()
        print("ÜRÜN :", row["product_name"])
        print("AİLE :", row["product_family"])
        print(
            "TUTAR:",
            row["minimum_financing_amount"],
            "→",
            row["maximum_financing_amount"],
        )
        print(
            "VADE :",
            row["minimum_maturity_months"],
            "→",
            row["maximum_maturity_months"],
        )
        print(
            "ORAN :",
            row["profit_share_rate_text"],
            "|",
            row["interest_free_text"],
        )
        print("URL  :", row["source_url"])
        print()
        print("KAYNAK METİN:")
        print(row["clean_text"] or "")
        print("-" * 100)

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
