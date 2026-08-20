from __future__ import annotations
import json
from pathlib import Path

SCAN = Path("data") / "standard_products" / "kuveyt_turk.json"

def main() -> int:
    data = json.loads(SCAN.read_text(encoding="utf-8"))
    rows = [
        row for row in data.get("products", [])
        if row.get("fee_waiver_text")
    ]

    print("=" * 90)
    print("KUVEYT TÜRK — ÜCRET MUAFİYETİ DENETİMİ")
    print("=" * 90)
    print("Muafiyet bulunan ürün:", len(rows))

    for row in rows:
        print()
        print("ÜRÜN :", row.get("product_name"))
        print("ÖZET :", row.get("fee_waiver_text"))
        print("URL  :", row.get("url"))

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
