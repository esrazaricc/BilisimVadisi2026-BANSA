from __future__ import annotations

import json
from pathlib import Path


SCAN = (
    Path("data")
    / "standard_products"
    / "dunya_katilim.json"
)


def main() -> int:
    data = json.loads(
        SCAN.read_text(encoding="utf-8")
    )

    row = next(
        (
            item
            for item in data.get("products", [])
            if item.get("product_name") == "Araç Finansmanı"
        ),
        None,
    )

    if row is None:
        print("Araç Finansmanı bulunamadı.")
        return 1

    text = str(row.get("clean_text") or "")

    print("=" * 80)
    print("DÜNYA ARAÇ FİNANSMANI — FETCH / CLEAN TEXT KONTROLÜ")
    print("=" * 80)
    print("fetch_mode:", row.get("fetch_mode"))
    print("clean_text_length:", len(text))
    print("'400.000' var mı:", "400.000" in text)
    print("'48 ay' var mı:", "48 ay" in text.casefold())
    print(
        "'Nihai fatura' var mı:",
        "nihai fatura" in text.casefold(),
    )
    print(
        "'Sıkça Sorulan Sorular' var mı:",
        "sıkça sorulan sorular" in text.casefold(),
    )
    print()
    print(
        "maximum_maturity_months:",
        row.get("maximum_maturity_months"),
    )
    print(
        "maturity_reference_upper_amount:",
        row.get("maturity_reference_upper_amount"),
    )
    print(
        "maturity_rules_text:",
        row.get("maturity_rules_text"),
    )
    print(
        "maximum_financing_ratio:",
        row.get("maximum_financing_ratio"),
    )
    print(
        "financing_ratio_rules_text:",
        row.get("financing_ratio_rules_text"),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
