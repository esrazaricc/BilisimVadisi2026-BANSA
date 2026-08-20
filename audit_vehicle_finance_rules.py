from __future__ import annotations

import json
import sqlite3
from pathlib import Path


SCAN = Path("data") / "standard_products" / "dunya_katilim.json"
DB = Path("data") / "campaigns.db"


def main() -> int:
    data = json.loads(SCAN.read_text(encoding="utf-8"))

    product = next(
        (
            row
            for row in data.get("products", [])
            if row.get("product_name") == "Araç Finansmanı"
        ),
        None,
    )

    print("=" * 80)
    print("SCAN JSON — ARAÇ FİNANSMANI")
    print("=" * 80)
    if product is None:
        print("Araç Finansmanı JSON'da bulunamadı.")
    else:
        for key in (
            "minimum_financing_amount",
            "maximum_financing_amount",
            "minimum_maturity_months",
            "maximum_maturity_months",
            "maturity_reference_upper_amount",
            "maturity_rules_text",
            "maximum_financing_ratio",
            "financing_ratio_rules_text",
        ):
            print(f"{key}: {product.get(key)}")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    row = con.execute(
        """
        SELECT
            d.minimum_financing_amount,
            d.maximum_financing_amount,
            d.minimum_maturity_months,
            d.maximum_maturity_months,
            d.maturity_reference_upper_amount,
            d.maturity_rules_text,
            d.maximum_financing_ratio,
            d.financing_ratio_rules_text
        FROM live_campaigns AS c
        JOIN live_standard_product_details AS d
            ON d.product_id = c.id
        WHERE c.bank_name='Dünya Katılım'
          AND c.record_kind='standard_product'
          AND d.product_name='Araç Finansmanı'
          AND c.is_current=1
        LIMIT 1
        """
    ).fetchone()

    print()
    print("=" * 80)
    print("DB — ARAÇ FİNANSMANI")
    print("=" * 80)

    if row is None:
        print("Araç Finansmanı DB'de bulunamadı.")
    else:
        for key in row.keys():
            print(f"{key}: {row[key]}")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
