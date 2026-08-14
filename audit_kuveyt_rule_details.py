from __future__ import annotations

import sqlite3
from pathlib import Path


DB = Path("data") / "campaigns.db"


def print_rows(title: str, rows, formatter):
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)

    if not rows:
        print("Kayıt yok.")
        return

    for row in rows:
        print(formatter(row))


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    category = con.execute(
        """
        SELECT
            d.product_name,
            r.category_label,
            r.min_amount,
            r.max_amount,
            r.min_inclusive,
            r.max_inclusive,
            r.max_installments,
            r.max_maturity_months,
            r.condition_text
        FROM live_product_category_rules AS r
        JOIN live_campaigns AS c
            ON c.id=r.product_id
        JOIN live_standard_product_details AS d
            ON d.product_id=r.product_id
        WHERE c.bank_name='Kuveyt Türk'
          AND c.record_kind='standard_product'
          AND c.is_current=1
        ORDER BY
            d.product_name,
            r.category_label,
            r.min_amount,
            r.max_amount
        """
    ).fetchall()

    pricing = con.execute(
        """
        SELECT
            d.product_name,
            r.maturity_months,
            r.profit_share_rate,
            r.allocation_fee_rate,
            r.monthly_total_cost_rate,
            r.annual_total_cost_rate
        FROM live_product_pricing_tiers AS r
        JOIN live_campaigns AS c
            ON c.id=r.product_id
        JOIN live_standard_product_details AS d
            ON d.product_id=r.product_id
        WHERE c.bank_name='Kuveyt Türk'
          AND c.record_kind='standard_product'
          AND c.is_current=1
        ORDER BY
            d.product_name,
            r.maturity_months
        """
    ).fetchall()

    fees = con.execute(
        """
        SELECT
            d.product_name,
            r.fee_label,
            r.waived,
            r.amount,
            r.rate,
            r.note
        FROM live_product_fee_rules AS r
        JOIN live_campaigns AS c
            ON c.id=r.product_id
        JOIN live_standard_product_details AS d
            ON d.product_id=r.product_id
        WHERE c.bank_name='Kuveyt Türk'
          AND c.record_kind='standard_product'
          AND c.is_current=1
        ORDER BY
            d.product_name,
            r.fee_label
        """
    ).fetchall()

    print_rows(
        "KUVEYT TÜRK — KATEGORİ KURALLARI",
        category,
        lambda r: (
            f"{r['product_name']} | {r['category_label']} | "
            f"min={r['min_amount']} | max={r['max_amount']} | "
            f"taksit={r['max_installments']} | "
            f"vade={r['max_maturity_months']} | "
            f"koşul={r['condition_text']}"
        ),
    )

    print_rows(
        "KUVEYT TÜRK — FİYATLAMA KADEMELERİ",
        pricing,
        lambda r: (
            f"{r['product_name']} | "
            f"{r['maturity_months']} ay | "
            f"kâr={r['profit_share_rate']} | "
            f"tahsis={r['allocation_fee_rate']} | "
            f"aylık maliyet={r['monthly_total_cost_rate']} | "
            f"yıllık maliyet={r['annual_total_cost_rate']}"
        ),
    )

    print_rows(
        "KUVEYT TÜRK — MASRAF KURALLARI",
        fees,
        lambda r: (
            f"{r['product_name']} | {r['fee_label']} | "
            f"durum={'Alınmıyor' if r['waived'] else 'Var'} | "
            f"tutar={r['amount']} | oran={r['rate']} | "
            f"not={r['note']}"
        ),
    )

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
