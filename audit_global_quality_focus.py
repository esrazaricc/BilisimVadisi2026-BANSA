from __future__ import annotations

import json
import sqlite3
from pathlib import Path


DB = Path("data") / "campaigns.db"


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    print("=" * 110)
    print("GLOBAL KALİTE — ODAKLI TEŞHİS")
    print("=" * 110)

    # ------------------------------------------------------------------
    # 1) Hayat Finans — Bana Bunu Al
    # ------------------------------------------------------------------
    print()
    print("=" * 110)
    print("1) HAYAT FİNANS — BANA BUNU AL")
    print("=" * 110)

    hayat = con.execute(
        """
        SELECT
            c.id,
            c.source_url,
            d.product_name,
            d.finance_rules_json
        FROM live_campaigns c
        JOIN live_standard_product_details d
          ON d.product_id=c.id
        WHERE c.bank_name='Hayat Finans'
          AND c.record_kind='standard_product'
          AND c.is_current=1
          AND d.product_name='Bana Bunu Al'
        LIMIT 1
        """
    ).fetchone()

    if hayat:
        pid = int(hayat["id"])
        print("ID :", pid)
        print("URL:", hayat["source_url"])

        print()
        print("DB fee_rules:")
        for row in con.execute(
            """
            SELECT
                fee_type,
                fee_label,
                waived,
                rate,
                amount,
                note
            FROM live_product_fee_rules
            WHERE product_id=?
            ORDER BY fee_type, fee_label
            """,
            (pid,),
        ):
            print(dict(row))

        print()
        print("DB pricing_tiers:")
        for row in con.execute(
            """
            SELECT
                pricing_variant,
                maturity_months,
                profit_share_rate,
                allocation_fee_rate,
                monthly_total_cost_rate,
                annual_total_cost_rate,
                source_text
            FROM live_product_pricing_tiers
            WHERE product_id=?
            ORDER BY pricing_variant, maturity_months
            """,
            (pid,),
        ):
            print(dict(row))

        print()
        print("finance_rules_json fee_rules:")
        try:
            payload = json.loads(
                hayat["finance_rules_json"] or "{}"
            )
            for row in payload.get("fee_rules", []):
                print(row)
        except Exception as exc:
            print("JSON parse hatası:", exc)
    else:
        print("Bana Bunu Al bulunamadı.")

    # ------------------------------------------------------------------
    # 2) Kuveyt Türk — Çatı GES Finansmanı duplicate
    # ------------------------------------------------------------------
    print()
    print("=" * 110)
    print("2) KUVEYT TÜRK — ÇATI GES FİNANSMANI")
    print("=" * 110)

    rows = con.execute(
        """
        SELECT
            c.id,
            c.source_url,
            d.product_name,
            d.product_family,
            d.scope,
            d.maximum_financing_amount,
            d.maximum_maturity_months,
            d.profit_share_rate,
            d.profit_share_rate_text
        FROM live_campaigns c
        JOIN live_standard_product_details d
          ON d.product_id=c.id
        WHERE c.bank_name='Kuveyt Türk'
          AND c.record_kind='standard_product'
          AND c.is_current=1
          AND d.product_name='Çatı GES Finansmanı'
        ORDER BY c.id
        """
    ).fetchall()

    print("Aktif kayıt:", len(rows))
    for row in rows:
        print()
        print("ID      :", row["id"])
        print("URL     :", row["source_url"])
        print("Aile    :", row["product_family"])
        print("Kapsam  :", row["scope"])
        print(
            "Tutar   :",
            row["maximum_financing_amount"],
        )
        print(
            "Vade    :",
            row["maximum_maturity_months"],
        )
        print(
            "Kâr     :",
            row["profit_share_rate"],
            "|",
            row["profit_share_rate_text"],
        )

    # ------------------------------------------------------------------
    # 3) Türkiye Finans — Konut pricing conflicts
    # ------------------------------------------------------------------
    print()
    print("=" * 110)
    print("3) TÜRKİYE FİNANS — KONUT FİYATLAMA ÇAKIŞMALARI")
    print("=" * 110)

    konut = con.execute(
        """
        SELECT
            c.id,
            c.source_url,
            d.product_name
        FROM live_campaigns c
        JOIN live_standard_product_details d
          ON d.product_id=c.id
        WHERE c.bank_name='Türkiye Finans'
          AND c.record_kind='standard_product'
          AND c.is_current=1
          AND d.product_name LIKE 'Konut Finansmanı (%'
        LIMIT 1
        """
    ).fetchone()

    if not konut:
        print("Konut Finansmanı bulunamadı.")
    else:
        pid = int(konut["id"])
        print("ID :", pid)
        print("URL:", konut["source_url"])

        rows = con.execute(
            """
            SELECT
                pricing_variant,
                maturity_months,
                profit_share_rate,
                allocation_fee_rate,
                monthly_total_cost_rate,
                annual_total_cost_rate,
                source_text
            FROM live_product_pricing_tiers
            WHERE product_id=?
            ORDER BY
                pricing_variant,
                maturity_months,
                profit_share_rate,
                annual_total_cost_rate
            """,
            (pid,),
        ).fetchall()

        groups = {}
        for row in rows:
            key = (
                row["pricing_variant"],
                row["maturity_months"],
            )
            groups.setdefault(key, []).append(row)

        conflicts = {
            key: group
            for key, group in groups.items()
            if len({
                (
                    r["profit_share_rate"],
                    r["allocation_fee_rate"],
                    r["monthly_total_cost_rate"],
                    r["annual_total_cost_rate"],
                )
                for r in group
            }) > 1
        }

        print("Toplam pricing satırı:", len(rows))
        print("Çakışan variant/vade:", len(conflicts))

        for (variant, maturity), group in conflicts.items():
            print()
            print("-" * 110)
            print(
                f"{variant} | {maturity} ay | "
                f"{len(group)} kayıt"
            )
            print("-" * 110)

            for i, row in enumerate(group, 1):
                print(
                    f"[{i}] "
                    f"kâr={row['profit_share_rate']} | "
                    f"tahsis={row['allocation_fee_rate']} | "
                    f"aylık={row['monthly_total_cost_rate']} | "
                    f"yıllık={row['annual_total_cost_rate']}"
                )
                print(
                    "    source_text:",
                    row["source_text"],
                )

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
