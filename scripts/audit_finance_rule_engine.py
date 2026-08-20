from __future__ import annotations

import sqlite3
from pathlib import Path


DB = Path("data") / "campaigns.db"


def count(con, table):
    try:
        return con.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        return None


def main() -> int:
    con = sqlite3.connect(DB)

    print("=" * 80)
    print("FİNANSMAN KURAL MOTORU DENETİMİ")
    print("=" * 80)

    for table in (
        "live_product_category_rules",
        "live_product_amount_maturity_rules",
        "live_product_pricing_tiers",
        "live_product_fee_rules",
        "live_product_offer_rules",
    ):
        print(
            f"{table}:",
            count(con, table),
        )

    print()
    print("BANKA BAZLI KURAL SAYILARI")

    query = """
        SELECT
            c.bank_name,
            COUNT(DISTINCT cr.id) AS category_rules,
            COUNT(DISTINCT am.id) AS amount_rules,
            COUNT(DISTINCT pt.id) AS pricing_tiers,
            COUNT(DISTINCT fr.id) AS fee_rules,
            COUNT(DISTINCT ofr.id) AS offer_rules
        FROM live_campaigns AS c
        JOIN live_standard_product_details AS d
            ON d.product_id=c.id
        LEFT JOIN live_product_category_rules AS cr
            ON cr.product_id=c.id
        LEFT JOIN live_product_amount_maturity_rules AS am
            ON am.product_id=c.id
        LEFT JOIN live_product_pricing_tiers AS pt
            ON pt.product_id=c.id
        LEFT JOIN live_product_fee_rules AS fr
            ON fr.product_id=c.id
        LEFT JOIN live_product_offer_rules AS ofr
            ON ofr.product_id=c.id
        WHERE c.record_kind='standard_product'
          AND c.is_current=1
        GROUP BY c.bank_name
        ORDER BY c.bank_name
    """

    for row in con.execute(query):
        print(
            row[0],
            "| kategori:", row[1],
            "| tutar-vade:", row[2],
            "| fiyatlama:", row[3],
            "| masraf:", row[4],
            "| özel koşul:", row[5],
        )

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
