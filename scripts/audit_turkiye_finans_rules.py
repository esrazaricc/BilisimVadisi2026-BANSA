from __future__ import annotations

import sqlite3
from pathlib import Path


DB = Path("data") / "campaigns.db"


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    print("=" * 100)
    print("TÜRKİYE FİNANS — STANDART ÜRÜN / KURAL DENETİMİ")
    print("=" * 100)

    products = con.execute(
        """
        SELECT
            c.id,
            d.product_name,
            d.product_family,
            d.scope,
            d.minimum_financing_amount,
            d.maximum_financing_amount,
            d.maximum_maturity_months,
            d.vehicle_finance_rules_text,
            c.source_url
        FROM live_campaigns AS c
        JOIN live_standard_product_details AS d
            ON d.product_id=c.id
        WHERE c.bank_name='Türkiye Finans'
          AND c.record_kind='standard_product'
          AND c.is_current=1
        ORDER BY d.product_family, d.product_name
        """
    ).fetchall()

    print("Aktif ürün:", len(products))

    for row in products:
        print(
            f"- {row['product_family']} | "
            f"{row['product_name']} | {row['scope']} | "
            f"tutar={row['minimum_financing_amount']}→"
            f"{row['maximum_financing_amount']} | "
            f"vade={row['maximum_maturity_months']}"
        )

    print()
    print("KURAL SAYILARI")

    for label, table in {
        "Kategori": "live_product_category_rules",
        "Tutar-vade": "live_product_amount_maturity_rules",
        "Fiyatlama": "live_product_pricing_tiers",
        "Masraf": "live_product_fee_rules",
        "Özel koşul": "live_product_offer_rules",
    }.items():
        count = con.execute(
            f"""
            SELECT COUNT(*)
            FROM {table} AS r
            JOIN live_campaigns AS c
                ON c.id=r.product_id
            WHERE c.bank_name='Türkiye Finans'
              AND c.record_kind='standard_product'
              AND c.is_current=1
            """
        ).fetchone()[0]
        print(f"{label}: {count}")

    print()
    print("=" * 100)
    print("İHTİYAÇ FİNANSMANI — FİYATLAMA")
    print("=" * 100)

    rows = con.execute(
        """
        SELECT
            r.pricing_variant,
            r.maturity_months,
            r.profit_share_rate,
            r.allocation_fee_rate,
            r.monthly_total_cost_rate,
            r.annual_total_cost_rate
        FROM live_product_pricing_tiers AS r
        JOIN live_campaigns AS c
            ON c.id=r.product_id
        JOIN live_standard_product_details AS d
            ON d.product_id=r.product_id
        WHERE c.bank_name='Türkiye Finans'
          AND d.product_name LIKE '%İhtiyaç Finansmanı%'
          AND d.product_name NOT LIKE '%Dijital%'
        ORDER BY
            r.pricing_variant,
            r.maturity_months
        """
    ).fetchall()

    for row in rows:
        print(
            row["pricing_variant"],
            "|", row["maturity_months"], "ay",
            "| kâr=", row["profit_share_rate"],
            "| tahsis=", row["allocation_fee_rate"],
            "| aylık=", row["monthly_total_cost_rate"],
            "| yıllık=", row["annual_total_cost_rate"],
        )

    print()
    print("=" * 100)
    print("ARAÇ FİNANSMANI — KRİTİK KURALLAR")
    print("=" * 100)

    vehicle = [
        row
        for row in products
        if row["product_name"]
        in {"Taşıt Finansmanı", "Araç Finansmanı"}
        or (
            row["product_family"] == "Araç Finansmanı"
            and "Dijital" not in row["product_name"]
        )
    ]

    for row in vehicle[:2]:
        print(row["product_name"])
        print("  vade:", row["maximum_maturity_months"])
        print("  araç kuralı:", row["vehicle_finance_rules_text"])

        price_rows = con.execute(
            """
            SELECT
                pricing_variant,
                COUNT(*) AS n,
                MIN(profit_share_rate) AS min_rate,
                MAX(profit_share_rate) AS max_rate
            FROM live_product_pricing_tiers
            WHERE product_id=?
            GROUP BY pricing_variant
            ORDER BY pricing_variant
            """,
            (row["id"],),
        ).fetchall()

        for p in price_rows:
            print(
                " ",
                p["pricing_variant"],
                "| satır=", p["n"],
                "| kâr=", p["min_rate"],
                "→", p["max_rate"],
            )

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
