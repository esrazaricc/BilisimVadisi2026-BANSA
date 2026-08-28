from __future__ import annotations

import json
import sqlite3
from pathlib import Path


DB = Path("data") / "campaigns.db"


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    row = con.execute(
        """
        SELECT
            c.id,
            c.bank_name,
            d.product_name,
            d.finance_rules_json,
            c.source_url
        FROM live_campaigns AS c
        JOIN live_standard_product_details AS d
            ON d.product_id=c.id
        WHERE c.bank_name='Kuveyt Türk'
          AND c.record_kind='standard_product'
          AND c.is_current=1
          AND d.product_name LIKE '%LC Waikiki%'
        LIMIT 1
        """
    ).fetchone()

    print("=" * 90)
    print("LC WAIKIKI — FINANCE RULE DENETİMİ")
    print("=" * 90)

    if row is None:
        print("LC Waikiki ürünü DB'de bulunamadı.")
        con.close()
        return 1

    print("ÜRÜN:", row["product_name"])
    print("URL :", row["source_url"])

    payload = {}
    if row["finance_rules_json"]:
        try:
            payload = json.loads(row["finance_rules_json"])
        except json.JSONDecodeError:
            print("finance_rules_json geçersiz JSON.")

    offers = payload.get("offer_rules", [])
    print()
    print("JSON offer_rules:", len(offers))
    for item in offers:
        print(" -", item.get("condition_text"))

    table_exists = con.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table'
          AND name='live_product_offer_rules'
        """
    ).fetchone()

    if table_exists is None:
        print()
        print("live_product_offer_rules tablosu yok.")
        con.close()
        return 2

    db_offers = con.execute(
        """
        SELECT
            max_amount,
            max_installments,
            max_maturity_months,
            interest_free,
            condition_text
        FROM live_product_offer_rules
        WHERE product_id=?
        ORDER BY id
        """,
        (row["id"],),
    ).fetchall()

    print()
    print("DB normalize offer rules:", len(db_offers))

    for item in db_offers:
        print(
            " - max=", item["max_amount"],
            "| taksit=", item["max_installments"],
            "| vade=", item["max_maturity_months"],
            "| vade_farksiz=", bool(item["interest_free"]),
            "| koşul=", item["condition_text"],
        )

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
