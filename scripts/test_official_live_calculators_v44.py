from __future__ import annotations

import argparse
from decimal import Decimal

from src.bansa_v40_finance_catalog import canonical_scenario_products
from src.finance_official_calculator_service import (
    is_live_capable_row,
    live_records_for_rows,
)
from src.finance_runtime_repository import get_standard_products

FAMILIES = {
    "konut": "konut_finansmani",
    "tasit": "arac_finansmani",
    "taşıt": "arac_finansmani",
    "ihtiyac": "ihtiyac_finansmani",
    "ihtiyaç": "ihtiyac_finansmani",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="BANSA V44 official live calculator smoke test")
    parser.add_argument("--family", default="konut", choices=tuple(FAMILIES))
    parser.add_argument("--amount", type=Decimal, default=Decimal("100000"))
    parser.add_argument("--maturity", type=int, default=36)
    args = parser.parse_args()

    family = FAMILIES[args.family]
    products = get_standard_products().copy()
    products = products[products["product_family_key"].astype(str).eq(family)].copy()
    products = canonical_scenario_products(products, family)
    mapped = products[products.apply(is_live_capable_row, axis=1)].copy()

    print(f"Family: {family} | amount={args.amount} | maturity={args.maturity}")
    print("Mapped official calculator banks:")
    for _, row in mapped.iterrows():
        print(f"  - {row['bank_name']} | id={row['id']} | {row['product_name']}")

    print("\nCalling official calculators...")
    resolved = live_records_for_rows(mapped, args.amount, args.maturity)
    for _, row in mapped.iterrows():
        pid = int(row["id"])
        records = resolved.get(pid, [])
        if not records:
            print(f"[UNVERIFIED] {row['bank_name']} | no exact live output")
            continue
        for rec in records:
            print(
                f"[VERIFIED] {rec['bank_name']} | {rec['variant']} | "
                f"rate={rec['rate']} | monthly={rec['monthly']} | total={rec['total']} | "
                f"source={rec['source_url']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
