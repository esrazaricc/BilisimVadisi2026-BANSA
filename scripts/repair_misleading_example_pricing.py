from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pricing_guardrails import (
    authoritative_pricing_rows,
    is_example_only_pricing_row,
    text_marks_example_only,
)

DEFAULT_DB = PROJECT_ROOT / "data" / "campaigns.db"


def _clean_rules_json(value: object) -> tuple[str | None, int]:
    if value is None:
        return None, 0

    if isinstance(value, dict):
        rules = dict(value)
    else:
        text = str(value).strip()
        if not text:
            return text, 0
        try:
            rules = json.loads(text)
        except json.JSONDecodeError:
            return text, 0

    if not isinstance(rules, dict):
        return json.dumps(rules, ensure_ascii=False, sort_keys=True), 0

    rows = rules.get("pricing_tiers", [])
    if not isinstance(rows, list):
        return json.dumps(rules, ensure_ascii=False, sort_keys=True), 0

    kept = authoritative_pricing_rows(
        row for row in rows if isinstance(row, dict)
    )
    removed = len([row for row in rows if isinstance(row, dict)]) - len(kept)
    if removed:
        rules["pricing_tiers"] = kept

    return json.dumps(rules, ensure_ascii=False, sort_keys=True), removed


def repair_sqlite(db_path: Path) -> dict[str, int]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    deleted_tiers = 0
    cleaned_json_rows = 0
    cleaned_json_tiers = 0
    cleared_product_rates = 0

    with con:
        tier_rows = con.execute(
            """
            SELECT id, pricing_variant, source_text
            FROM live_product_pricing_tiers
            """
        ).fetchall()
        unsafe_ids = [
            int(row["id"])
            for row in tier_rows
            if is_example_only_pricing_row(row)
        ]
        for row_id in unsafe_ids:
            con.execute(
                "DELETE FROM live_product_pricing_tiers WHERE id=?",
                (row_id,),
            )
        deleted_tiers = len(unsafe_ids)

        details = con.execute(
            """
            SELECT product_id, profit_share_rate, profit_share_rate_text,
                   finance_rules_json
            FROM live_standard_product_details
            """
        ).fetchall()

        for row in details:
            cleaned_json, removed = _clean_rules_json(row["finance_rules_json"])
            clear_rate = (
                row["profit_share_rate"] is not None
                and text_marks_example_only(row["profit_share_rate_text"])
            )
            if not removed and not clear_rate:
                continue

            con.execute(
                """
                UPDATE live_standard_product_details
                SET finance_rules_json=?,
                    profit_share_rate=CASE WHEN ? THEN NULL ELSE profit_share_rate END
                WHERE product_id=?
                """,
                (cleaned_json, 1 if clear_rate else 0, int(row["product_id"])),
            )
            if removed:
                cleaned_json_rows += 1
                cleaned_json_tiers += removed
            if clear_rate:
                cleared_product_rates += 1

        # Albaraka Konut için eski örnek %2,95 hiçbir koşulda ürün seviyesi
        # güncel oran olarak kalmasın. Güncel oran yalnız hesaplama aracından
        # belirlenebildiği için sayısal alan bilinçli olarak NULL tutulur.
        con.execute(
            """
            UPDATE live_standard_product_details
            SET profit_share_rate=NULL,
                profit_share_rate_text='Güncel oran hesaplama aracında belirlenir'
            WHERE bank_name='Albaraka Türk'
              AND TRIM(REPLACE(product_name, '*', ''))='Konut Finansmanı'
            """
        )

    con.close()
    return {
        "deleted_tiers": deleted_tiers,
        "cleaned_json_rows": cleaned_json_rows,
        "cleaned_json_tiers": cleaned_json_tiers,
        "cleared_product_rates": cleared_product_rates,
    }


def repair_postgresql(dsn: str) -> dict[str, int]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            'PostgreSQL sürücüsü eksik. Çalıştırın: python -m pip install "psycopg[binary]"'
        ) from exc

    deleted_tiers = 0
    cleaned_json_rows = 0
    cleaned_json_tiers = 0
    cleared_product_rates = 0

    with psycopg.connect(dsn, row_factory=dict_row) as con:
        with con.cursor() as cur:
            cur.execute("SET search_path TO bansa, public")
            cur.execute(
                """
                SELECT id, pricing_variant, source_text
                FROM product_pricing_tiers
                """
            )
            rows = cur.fetchall()
            unsafe_ids = [
                int(row["id"])
                for row in rows
                if is_example_only_pricing_row(row)
            ]
            for row_id in unsafe_ids:
                cur.execute(
                    "DELETE FROM product_pricing_tiers WHERE id=%s",
                    (row_id,),
                )
            deleted_tiers = len(unsafe_ids)

            cur.execute(
                """
                SELECT id, profit_share_rate, profit_share_rate_text, finance_rules
                FROM standard_products
                WHERE is_current = TRUE
                """
            )
            products = cur.fetchall()
            for row in products:
                cleaned_json, removed = _clean_rules_json(row["finance_rules"])
                clear_rate = (
                    row["profit_share_rate"] is not None
                    and text_marks_example_only(row["profit_share_rate_text"])
                )
                if not removed and not clear_rate:
                    continue

                parsed_rules: Any = None
                if cleaned_json:
                    parsed_rules = json.loads(cleaned_json)

                cur.execute(
                    """
                    UPDATE standard_products
                    SET finance_rules=%s::jsonb,
                        profit_share_rate=CASE WHEN %s THEN NULL ELSE profit_share_rate END,
                        updated_at=NOW()
                    WHERE id=%s
                    """,
                    (json.dumps(parsed_rules, ensure_ascii=False) if parsed_rules is not None else None,
                     clear_rate,
                     int(row["id"])),
                )
                if removed:
                    cleaned_json_rows += 1
                    cleaned_json_tiers += removed
                if clear_rate:
                    cleared_product_rates += 1

            cur.execute(
                """
                UPDATE standard_products AS p
                SET profit_share_rate=NULL,
                    profit_share_rate_text='Güncel oran hesaplama aracında belirlenir',
                    updated_at=NOW()
                FROM banks AS b
                WHERE p.bank_id=b.id
                  AND b.name='Albaraka Türk'
                  AND TRIM(REPLACE(p.product_name, '*', ''))='Konut Finansmanı'
                """
            )

    return {
        "deleted_tiers": deleted_tiers,
        "cleaned_json_rows": cleaned_json_rows,
        "cleaned_json_tiers": cleaned_json_tiers,
        "cleared_product_rates": cleared_product_rates,
    }


def audit_sqlite(db_path: Path) -> list[dict[str, Any]]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT r.id, c.bank_name, c.title, r.pricing_variant, r.source_text,
               r.profit_share_rate, r.maturity_months
        FROM live_product_pricing_tiers AS r
        JOIN live_campaigns AS c ON c.id=r.product_id
        """
    ).fetchall()
    con.close()
    return [dict(row) for row in rows if is_example_only_pricing_row(row)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Örnek/temsili fiyatları güncel ürün oranı olmaktan çıkarır."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--sqlite-only",
        action="store_true",
        help="POSTGRES_DSN olsa bile yalnız SQLite temizliği yap.",
    )
    args = parser.parse_args()

    print("=" * 88)
    print("FİYATLAMA KANITI GUARDRAIL ONARIMI")
    print("=" * 88)

    sqlite_result = repair_sqlite(args.db)
    print("[SQLite]", sqlite_result)

    remaining = audit_sqlite(args.db)
    if remaining:
        print(f"[FAIL] SQLite'ta {len(remaining)} örnek/temsili fiyat satırı kaldı.")
        for row in remaining[:20]:
            print(" -", row)
        return 2
    print("[PASS] SQLite customer-pricing tablolarında örnek/temsili fiyat satırı yok.")

    if not args.sqlite_only:
        dsn = os.getenv("POSTGRES_DSN", "").strip()
        if dsn:
            pg_result = repair_postgresql(dsn)
            print("[PostgreSQL]", pg_result)
            print("[PASS] PostgreSQL temizliği tamamlandı.")
        else:
            print("[INFO] POSTGRES_DSN yok; PostgreSQL temizliği atlandı.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
