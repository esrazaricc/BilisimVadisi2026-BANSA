from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.finance_data_quality import apply_finance_data_quality_overrides
from src.albaraka_standard_product_overrides import apply_albaraka_standard_product_overrides
from src.housing_verified_source_overrides import apply_verified_housing_product_overrides

DEFAULT_DB = PROJECT_ROOT / "data" / "campaigns.db"

UPDATE_FIELDS = (
    "minimum_financing_amount",
    "maximum_financing_amount",
    "maximum_maturity_months",
    "profit_share_rate",
    "profit_share_rate_text",
    "interest_free",
    "interest_free_text",
    "maturity_rules_text",
    "financing_ratio_rules_text",
    "maximum_financing_ratio",
    "housing_first_home_rules_text",
    "housing_additional_home_rules_text",
    "housing_finance_rules_json",
    "vehicle_finance_rules_text",
    "vehicle_age_rules_text",

    # FINANCE_ACCURACY_WRITER_COMPLETENESS_V2
    "shopping_general_limit_amount",
    "shopping_general_max_maturity_months",
    "shopping_phone_rule_text",
    "shopping_tablet_max_maturity_months",
    "shopping_computer_max_maturity_months",
    "shopping_finance_rules_text",

    "finance_rules_json",
)


def _sync_category_rules(
    con,
    product_id: int,
    finance_rules_json: object,
) -> None:
    """
    finance_rules_json.category_rules ile
    live_product_category_rules tablosunu ayni kaynaktan
    yeniden kurar.

    Yalniz canonical apply sirasinda degisen urunlerde cagrilir.
    """

    try:
        rules = json.loads(
            str(finance_rules_json or "{}")
        )
    except Exception:
        rules = {}

    if not isinstance(rules, dict):
        rules = {}

    category_rules = rules.get(
        "category_rules",
        [],
    )

    if not isinstance(category_rules, list):
        category_rules = []

    con.execute(
        """
        DELETE FROM live_product_category_rules
        WHERE product_id=?
        """,
        (int(product_id),),
    )

    for row in category_rules:

        if not isinstance(row, dict):
            continue

        con.execute(
            """
            INSERT INTO live_product_category_rules
            (
                product_id,
                category_key,
                category_label,
                min_amount,
                max_amount,
                min_inclusive,
                max_inclusive,
                max_installments,
                max_maturity_months,
                condition_text,
                source_text,
                updated_at
            )
            VALUES
            (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                CURRENT_TIMESTAMP
            )
            """,
            (
                int(product_id),
                row.get("category_key"),
                row.get("category_label"),
                row.get("min_amount"),
                row.get("max_amount"),
                int(
                    bool(
                        row.get(
                            "min_inclusive",
                            False,
                        )
                    )
                ),
                int(
                    bool(
                        row.get(
                            "max_inclusive",
                            True,
                        )
                    )
                ),
                row.get("max_installments"),
                row.get("max_maturity_months"),
                row.get("condition_text"),
                row.get("source_text"),
            ),
        )



# FINANCE_ACCURACY_FEE_WRITER_V1
def _sync_fee_rules(
    con,
    product_id: int,
    finance_rules_json: object,
) -> None:
    try:
        rules = json.loads(
            str(finance_rules_json or "{}")
        )
    except Exception:
        return

    if not isinstance(rules, dict):
        return

    # Sadece canonical JSON fee_rules anahtarini tasiyorsa
    # normalize tabloyu yeniden kur.
    if "fee_rules" not in rules:
        return

    rows = rules.get("fee_rules")

    if not isinstance(rows, list):
        return

    con.execute(
        """
        DELETE FROM live_product_fee_rules
        WHERE product_id=?
        """,
        (product_id,),
    )

    for row in rows:
        if not isinstance(row, dict):
            continue

        con.execute(
            """
            INSERT INTO live_product_fee_rules (
                product_id,
                fee_type,
                fee_label,
                waived,
                amount,
                rate,
                note,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                product_id,
                row.get("fee_type"),
                row.get("fee_label"),
                1 if bool(row.get("waived")) else 0,
                row.get("amount"),
                row.get("rate"),
                row.get("note"),
            ),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT c.id AS product_id,c.bank_name,c.source_url,d.*
        FROM live_campaigns c
        JOIN live_standard_product_details d ON d.product_id=c.id
        WHERE c.record_kind='standard_product' AND c.is_current=1
        ORDER BY c.bank_name,d.product_name
        """
    ).fetchall()

    changed = 0
    with con:
        for dbrow in rows:
            before = dict(dbrow)
            payload = dict(before)
            payload["url"] = before.get("source_url")
            payload["source_page"] = before.get("source_page") or before.get("source_url")
            after = apply_albaraka_standard_product_overrides(payload)
            after = apply_verified_housing_product_overrides(after)
            after = apply_finance_data_quality_overrides(after)
            updates = {field: after.get(field) for field in UPDATE_FIELDS}
            if any(before.get(field) != value for field, value in updates.items()):
                con.execute(
                    """
                    UPDATE live_standard_product_details
                    SET minimum_financing_amount=?, maximum_financing_amount=?,
                        maximum_maturity_months=?, profit_share_rate=?,
                        profit_share_rate_text=?, interest_free=?, interest_free_text=?, maturity_rules_text=?,
                        financing_ratio_rules_text=?, maximum_financing_ratio=?,
                        housing_first_home_rules_text=?, housing_additional_home_rules_text=?,
                        housing_finance_rules_json=?, vehicle_finance_rules_text=?, vehicle_age_rules_text=?,

                        shopping_general_limit_amount=?,
                        shopping_general_max_maturity_months=?,
                        shopping_phone_rule_text=?,
                        shopping_tablet_max_maturity_months=?,
                        shopping_computer_max_maturity_months=?,
                        shopping_finance_rules_text=?,

                        finance_rules_json=?
                    WHERE product_id=?
                    """,
                    tuple(updates[field] for field in UPDATE_FIELDS) + (int(before["product_id"]),),
                )

                # finance_rules_json canonical kaynaktir.
                # Normalize category tablosu da ayni sonuc ile
                # atomik olarak senkronlanir.
                _sync_category_rules(
                    con,
                    int(before["product_id"]),
                    updates.get("finance_rules_json"),
                )

                _sync_fee_rules(
                    con,
                    int(before["product_id"]),
                    updates.get("finance_rules_json"),
                )

                changed += 1

    con.close()
    print(f"Finansman Veri Doğruluk V2: {changed} ürün canonical/evidence kurallarıyla güncellendi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
