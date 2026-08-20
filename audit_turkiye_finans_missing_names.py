from __future__ import annotations

import json
from pathlib import Path


SCAN = (
    Path("data")
    / "standard_products"
    / "turkiye_finans.json"
)


def short(value, limit=500):
    text = str(value or "").strip()
    text = " ".join(text.split())
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def main() -> int:
    print("=" * 100)
    print("TÜRKİYE FİNANS — EKSİK ÜRÜN ADI DENETİMİ")
    print("=" * 100)

    if not SCAN.exists():
        print("Dosya bulunamadı:", SCAN)
        return 1

    data = json.loads(
        SCAN.read_text(encoding="utf-8")
    )

    products = data.get("products", [])

    print("bank_name     :", data.get("bank_name"))
    print("product_count :", data.get("product_count"))
    print("error_count   :", data.get("error_count"))
    print("products      :", len(products))

    missing = [
        row
        for row in products
        if not str(
            row.get("product_name") or ""
        ).strip()
    ]

    print("adı boş kayıt :", len(missing))
    print()

    if not missing:
        print(
            "Ürün adı boş kayıt bulunamadı. "
            "Bu durumda JSON ile sync arasında farklı "
            "bir dosya okunuyor olabilir."
        )
        return 0

    for i, row in enumerate(missing, 1):
        print("-" * 100)
        print(f"EKSİK KAYIT #{i}")
        print("-" * 100)
        print(
            "family       :",
            row.get("product_family"),
        )
        print(
            "family_key   :",
            row.get("product_family_key"),
        )
        print(
            "scope        :",
            row.get("scope"),
        )
        print(
            "url          :",
            row.get("url"),
        )
        print(
            "discovered   :",
            row.get("discovered_url"),
        )
        print(
            "source_page  :",
            row.get("source_page"),
        )
        print(
            "http_status  :",
            row.get("http_status"),
        )
        print(
            "fetch_mode   :",
            row.get("fetch_mode"),
        )
        print(
            "checked_at   :",
            row.get("checked_at"),
        )

        for key in (
            "page_title",
            "title",
            "h1",
            "clean_text",
        ):
            if key in row:
                print()
                print(f"{key}:")
                print(short(row.get(key)))

    print()
    print("=" * 100)
    print("TÜM KEŞFEDİLEN URL'LER")
    print("=" * 100)

    for i, row in enumerate(products, 1):
        name = str(
            row.get("product_name") or ""
        ).strip() or "<BOŞ>"
        print(
            f"{i:02d}. "
            f"{row.get('product_family')} | "
            f"{name}"
        )
        print("    ", row.get("url"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
