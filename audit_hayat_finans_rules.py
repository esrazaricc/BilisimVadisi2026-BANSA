from __future__ import annotations

import sqlite3
from pathlib import Path


DB = Path("data") / "campaigns.db"


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    print("=" * 100)
    print("HAYAT FİNANS — STANDART ÜRÜN / KURAL DENETİMİ")
    print("=" * 100)

    products = con.execute(
        """
        SELECT
            c.id,
            d.product_name,
            d.product_family,
            d.scope,
            c.source_url
        FROM live_campaigns AS c
        JOIN live_standard_product_details AS d
            ON d.product_id=c.id
        WHERE c.bank_name='Hayat Finans'
          AND c.record_kind='standard_product'
          AND c.is_current=1
        ORDER BY d.product_family, d.product_name
        """
    ).fetchall()

    print("Aktif ürün:", len(products))
    for row in products:
        print(
            f"- {row['product_family']} | "
            f"{row['product_name']} | {row['scope']}"
        )

    tables = {
        "Kategori": "live_product_category_rules",
        "Tutar-vade": "live_product_amount_maturity_rules",
        "Fiyatlama": "live_product_pricing_tiers",
        "Masraf": "live_product_fee_rules",
        "Özel koşul": "live_product_offer_rules",
    }

    print()
    print("KURAL SAYILARI")
    for label, table in tables.items():
        try:
            count = con.execute(
                f"""
                SELECT COUNT(*)
                FROM {table} AS r
                JOIN live_campaigns AS c
                    ON c.id=r.product_id
                WHERE c.bank_name='Hayat Finans'
                  AND c.record_kind='standard_product'
                  AND c.is_current=1
                """
            ).fetchone()[0]
        except sqlite3.OperationalError:
            count = "TABLO YOK"
        print(f"{label}: {count}")

    print()
    print("BANA BUNU AL — KRİTİK KURALLAR")

    row = con.execute(
        """
        SELECT c.id
        FROM live_campaigns AS c
        JOIN live_standard_product_details AS d
            ON d.product_id=c.id
        WHERE c.bank_name='Hayat Finans'
          AND d.product_name LIKE '%Bana Bunu Al%'
          AND d.product_name NOT LIKE '%İş Ortağım%'
          AND c.is_current=1
        LIMIT 1
        """
    ).fetchone()

    if row:
        pid = int(row["id"])

        cats = con.execute(
            """
            SELECT
                category_label,
                min_amount,
                max_amount,
                max_installments,
                max_maturity_months
            FROM live_product_category_rules
            WHERE product_id=?
            ORDER BY category_label, min_amount
            """,
            (pid,),
        ).fetchall()

        print("Kategori kuralı:", len(cats))
        for item in cats:
            print(
                " ",
                item["category_label"],
                "| min=", item["min_amount"],
                "| max=", item["max_amount"],
                "| taksit=", item["max_installments"],
                "| vade=", item["max_maturity_months"],
            )

        amounts = con.execute(
            """
            SELECT
                min_amount,
                max_amount,
                max_maturity_months
            FROM live_product_amount_maturity_rules
            WHERE product_id=?
            ORDER BY min_amount
            """,
            (pid,),
        ).fetchall()

        print("Tutar-vade:")
        for item in amounts:
            print(
                " ",
                item["min_amount"],
                "→",
                item["max_amount"],
                "=",
                item["max_maturity_months"],
                "ay",
            )

        pricing = con.execute(
            """
            SELECT
                maturity_months,
                profit_share_rate,
                allocation_fee_rate,
                monthly_total_cost_rate,
                annual_total_cost_rate
            FROM live_product_pricing_tiers
            WHERE product_id=?
            ORDER BY maturity_months
            """,
            (pid,),
        ).fetchall()

        print("Fiyatlama:")
        for item in pricing:
            print(
                " ",
                item["maturity_months"],
                "ay | oran=",
                item["profit_share_rate"],
                "| tahsis=",
                item["allocation_fee_rate"],
                "| aylık=",
                item["monthly_total_cost_rate"],
                "| yıllık=",
                item["annual_total_cost_rate"],
            )

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
