from __future__ import annotations

import argparse
from decimal import Decimal

from src.bansa_v40_finance_catalog import canonical_scenario_products
from src.finance_official_calculator_service import is_live_capable_row
from src.finance_runtime_repository import get_standard_products
from src.finance_user_scenario_resolver import resolve_user_scenarios

FAMILIES = {
    "konut": "konut_finansmani",
    "tasit": "arac_finansmani",
    "taşıt": "arac_finansmani",
    "ihtiyac": "ihtiyac_finansmani",
    "ihtiyaç": "ihtiyac_finansmani",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="BANSA V45 exact official live scenario smoke test")
    parser.add_argument("--family", default="konut", choices=tuple(FAMILIES))
    parser.add_argument("--amount", type=Decimal, default=Decimal("500000"))
    parser.add_argument("--maturity", type=int, default=120)
    args = parser.parse_args()

    family = FAMILIES[args.family]
    products = get_standard_products().copy()
    products = products[products["product_family_key"].astype(str).eq(family)].copy()
    products = canonical_scenario_products(products, family)

    print(f"Family={family} | exact amount={args.amount} | exact maturity={args.maturity}")
    print("\nOfficial live mappings:")
    for _, row in products.iterrows():
        if is_live_capable_row(row):
            print(f"  - {row['bank_name']} | id={row['id']} | {row['product_name']}")

    print("\nExact resolver results:")
    resolved = resolve_user_scenarios(products, args.amount, args.maturity)
    for _, row in products.iterrows():
        pid = int(row["id"])
        result = resolved.get(pid)
        if result is None:
            continue
        if result.mode == "live":
            for rec in result.live_records:
                print(
                    f"[VERIFIED LIVE] {rec['bank_name']} | {rec['variant']} | "
                    f"rate={rec['rate']} | monthly={rec['monthly']} | total={rec['total']} | "
                    f"checked_at={rec['checked_at']} | source={rec['source_url']}"
                )
        elif result.mode == "live_unavailable":
            print(f"[LIVE UNAVAILABLE / STALE FALLBACK BLOCKED] {row['bank_name']}")
        elif result.mode == "model":
            for rec in result.projections:
                print(
                    f"[VERIFIED MODEL] {rec.bank_name} | {rec.variant} | "
                    f"rate={rec.profit_share_rate} | monthly={rec.monthly_installment} | "
                    f"total={rec.installment_total} | source={rec.source_url}"
                )
        else:
            print(f"[NO VERIFIED NUMERIC] {row['bank_name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
