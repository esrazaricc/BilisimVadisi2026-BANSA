from __future__ import annotations

import sqlite3
from pathlib import Path


DB = Path("data") / "campaigns.db"


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    print("=" * 100)
    print("TÜRKİYE FİNANS — SEMANTİK V2 DENETİMİ")
    print("=" * 100)

    need = con.execute(
        """
        SELECT c.id, d.product_name
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

    print()
    print("İHTİYAÇ FİNANSMANI")

    if need:
        rows = con.execute(
            """
            SELECT
                pricing_variant,
                maturity_months,
                profit_share_rate,
                allocation_fee_rate,
                monthly_total_cost_rate,
                annual_total_cost_rate
            FROM live_product_pricing_tiers
            WHERE product_id=?
            ORDER BY pricing_variant, maturity_months
            """,
            (need["id"],),
        ).fetchall()

        variants = {}

        for row in rows:
            variants.setdefault(
                row["pricing_variant"],
                [],
            ).append(row)

        for variant, group in variants.items():
            print(f"- {variant}: {len(group)} satır")
            for row in group:
                print(
                    "   ",
                    row["maturity_months"],
                    "ay | kâr=",
                    row["profit_share_rate"],
                    "| tahsis=",
                    row["allocation_fee_rate"],
                    "| aylık=",
                    row["monthly_total_cost_rate"],
                    "| yıllık=",
                    row["annual_total_cost_rate"],
                )

    print()
    print("ARAÇ AİLESİ")

    vehicles = con.execute(
        """
        SELECT
            c.id,
            d.product_name,
            d.maximum_maturity_months,
            d.maturity_rules_text,
            d.financing_ratio_rules_text,
            d.vehicle_finance_rules_text
        FROM live_campaigns c
        JOIN live_standard_product_details d
          ON d.product_id=c.id
        WHERE c.bank_name='Türkiye Finans'
          AND c.record_kind='standard_product'
          AND c.is_current=1
          AND d.product_family='Araç Finansmanı'
        ORDER BY d.product_name
        """
    ).fetchall()

    for row in vehicles:
        print()
        print(row["product_name"])
        print("  max vade:", row["maximum_maturity_months"])
        print("  vade bantları:", row["maturity_rules_text"])
        print(
            "  oran bantları:",
            row["financing_ratio_rules_text"],
        )
        print(
            "  birleşik:",
            row["vehicle_finance_rules_text"],
        )

        tiers = con.execute(
            """
            SELECT pricing_variant, COUNT(*) AS n
            FROM live_product_pricing_tiers
            WHERE product_id=?
            GROUP BY pricing_variant
            ORDER BY pricing_variant
            """,
            (row["id"],),
        ).fetchall()

        for tier in tiers:
            print(
                "   fiyatlama:",
                tier["pricing_variant"],
                "|", tier["n"], "satır",
            )

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
