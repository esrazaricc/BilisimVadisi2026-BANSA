from __future__ import annotations

import json
import sqlite3
from pathlib import Path


DB = Path("data") / "campaigns.db"
SCAN_JSON = (
    Path("data")
    / "standard_products"
    / "hayat_finans.json"
)


def pretty(value):
    if value is None:
        return "None"
    return str(value)


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    product = con.execute(
        """
        SELECT
            c.id,
            d.product_name,
            d.finance_rules_json,
            d.maximum_maturity_months,
            c.source_url
        FROM live_campaigns AS c
        JOIN live_standard_product_details AS d
            ON d.product_id=c.id
        WHERE c.bank_name='Hayat Finans'
          AND c.record_kind='standard_product'
          AND c.is_current=1
          AND d.product_name='Bana Bunu Al'
        LIMIT 1
        """
    ).fetchone()

    print("=" * 100)
    print("HAYAT FİNANS — SEMANTİK KAYNAK DENETİMİ")
    print("=" * 100)

    if product is None:
        print("Bana Bunu Al DB'de bulunamadı.")
        return 1

    pid = int(product["id"])

    print("ÜRÜN:", product["product_name"])
    print("MAX VADE:", product["maximum_maturity_months"])
    print("URL:", product["source_url"])

    print()
    print("=" * 100)
    print("1) BİLGİSAYAR KATEGORİ KAYITLARI — SOURCE_TEXT")
    print("=" * 100)

    rows = con.execute(
        """
        SELECT
            category_label,
            max_installments,
            max_maturity_months,
            condition_text,
            source_text
        FROM live_product_category_rules
        WHERE product_id=?
          AND category_label='Bilgisayar'
        ORDER BY id
        """,
        (pid,),
    ).fetchall()

    for row in rows:
        print()
        print(
            "taksit=",
            row["max_installments"],
            "| vade=",
            row["max_maturity_months"],
        )
        print("koşul:", row["condition_text"])
        print("SOURCE_TEXT:")
        print(row["source_text"])

    print()
    print("=" * 100)
    print("2) PRICING JSON")
    print("=" * 100)

    payload = {}
    raw_rules = product["finance_rules_json"]

    if raw_rules:
        try:
            payload = json.loads(raw_rules)
        except json.JSONDecodeError as exc:
            print("finance_rules_json parse hatası:", exc)

    tiers = payload.get("pricing_tiers", [])
    print("pricing_tiers:", len(tiers))

    for tier in tiers:
        print()
        print(json.dumps(
            tier,
            ensure_ascii=False,
            indent=2,
        ))

    con.close()

    print()
    print("=" * 100)
    print("3) SCAN JSON'DAKİ BANA BUNU AL KAYDI")
    print("=" * 100)

    if not SCAN_JSON.exists():
        print("Scan JSON bulunamadı:", SCAN_JSON)
        return 0

    data = json.loads(
        SCAN_JSON.read_text(encoding="utf-8")
    )

    items = (
        data.get("products")
        if isinstance(data, dict)
        else data
    )

    if not isinstance(items, list):
        print(
            "Beklenmeyen JSON yapısı:",
            type(items).__name__,
        )
        return 0

    found = None

    for item in items:
        name = str(
            item.get("product_name", "")
        ).strip()
        if name == "Bana Bunu Al":
            found = item
            break

    if found is None:
        print("Scan JSON'da Bana Bunu Al bulunamadı.")
        return 0

    print("Alanlar:")
    for key in sorted(found):
        if key in {
            "html",
            "raw_html",
            "page_html",
        }:
            value = found.get(key)
            print(
                f"- {key}:",
                f"<{len(str(value))} karakter>"
                if value
                else "None",
            )
        elif key in {
            "clean_text",
            "finance_rules_json",
            "maximum_maturity_months",
        }:
            print()
            print(f"--- {key} ---")
            print(pretty(found.get(key)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
