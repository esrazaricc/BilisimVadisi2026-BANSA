from __future__ import annotations

import sqlite3
from pathlib import Path


DB = Path("data") / "campaigns.db"


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    rows = con.execute(
        """
        SELECT
            d.product_name,
            r.min_amount,
            r.max_amount,
            r.max_installments,
            r.max_maturity_months,
            r.interest_free,
            r.condition_text,
            r.source_text,
            c.source_url
        FROM live_product_offer_rules AS r
        JOIN live_campaigns AS c
            ON c.id=r.product_id
        JOIN live_standard_product_details AS d
            ON d.product_id=r.product_id
        WHERE c.bank_name='Kuveyt Türk'
          AND c.record_kind='standard_product'
          AND c.is_current=1
        ORDER BY d.product_name, r.max_amount
        """
    ).fetchall()

    print("=" * 100)
    print("KUVEYT TÜRK — ÜRÜNE ÖZEL FİNANSMAN KOŞULLARI")
    print("=" * 100)
    print("Kural:", len(rows))

    for row in rows:
        print()
        print("ÜRÜN :", row["product_name"])
        print("MAX  :", row["max_amount"])
        print("TAKSİT:", row["max_installments"])
        print("VADE :", row["max_maturity_months"])
        print(
            "VADE FARKSIZ:",
            bool(row["interest_free"]),
        )
        print("KOŞUL:", row["condition_text"])
        print("KAYNAK METİN:", row["source_text"])
        print("URL:", row["source_url"])

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
