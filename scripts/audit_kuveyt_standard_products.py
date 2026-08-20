from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            Path("data")
            / "standard_products"
            / "kuveyt_turk.json"
        ),
    )
    args = parser.parse_args()

    data = json.loads(
        args.input.read_text(encoding="utf-8")
    )

    rows = list(data.get("products", []))
    errors = list(data.get("errors", []))

    print("=" * 90)
    print("KUVEYT TÜRK — STANDART ÜRÜN TARAMA DENETİMİ")
    print("=" * 90)
    print("Ürün:", len(rows))
    print("Hata:", len(errors))

    by_family = defaultdict(list)
    by_url = Counter()

    for row in rows:
        by_family[str(row.get("product_family"))].append(row)
        by_url[str(row.get("url"))] += 1

    print()
    print("ÜRÜN AİLELERİ")
    for family in sorted(by_family):
        print()
        print(f"{family}: {len(by_family[family])}")
        for row in sorted(
            by_family[family],
            key=lambda item: str(item.get("product_name", "")),
        ):
            print(
                "  -",
                row.get("product_name"),
                "|",
                row.get("scope"),
            )
            print(
                "    Tutar:",
                row.get("minimum_financing_amount"),
                "→",
                row.get("maximum_financing_amount"),
            )
            print(
                "    Vade:",
                row.get("minimum_maturity_months"),
                "→",
                row.get("maximum_maturity_months"),
            )
            print(
                "    Kâr:",
                row.get("profit_share_rate_text"),
                "| Vade farksız:",
                row.get("interest_free_text"),
            )
            if row.get("maturity_rules_text"):
                print(
                    "    Vade kademeleri:",
                    row.get("maturity_rules_text"),
                )

    duplicates = [
        url for url, count in by_url.items()
        if url and count > 1
    ]

    print()
    print("Mükerrer final URL:", len(duplicates))
    for url in duplicates:
        print("  -", url)

    if errors:
        print()
        print("HATALAR")
        for error in errors:
            print(
                "-",
                error.get("url"),
                "|",
                error.get("error_type"),
                "|",
                error.get("message"),
            )

    return 1 if errors or duplicates else 0


if __name__ == "__main__":
    raise SystemExit(main())
