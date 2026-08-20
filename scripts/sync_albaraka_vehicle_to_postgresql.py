from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

try:
    import psycopg
except ImportError as exc:
    raise SystemExit(
        'psycopg kurulu değil. Önce: python -m pip install "psycopg[binary]"'
    ) from exc

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE = PROJECT_ROOT / "data" / "campaigns.db"

TARGET_PRODUCTS = {
    "Deniz Taşıtları Finansmanı",
    "Dijital Araç Finansmanı",
    "Taşıt Finansmanı",
    "Taşıt Kiralama Finansmanı",
    "Togg Finansmanı",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Albaraka Araç Finansmanı ürünlerini ve fiyatlama kademelerini "
            "SQLite kaynak verisinden PostgreSQL'e güvenli biçimde eşitler."
        )
    )
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE))
    parser.add_argument("--dsn", default=os.getenv("POSTGRES_DSN"))
    return parser.parse_args()


def _json_or_none(value):
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    try:
        parsed = json.loads(str(value))
    except Exception:
        parsed = {"raw": str(value)}
    return json.dumps(parsed, ensure_ascii=False)


def main() -> int:
    args = parse_args()
    if not args.dsn:
        raise SystemExit("POSTGRES_DSN tanımlı değil veya --dsn verilmedi.")

    sqlite_path = Path(args.sqlite).resolve()
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite bulunamadı: {sqlite_path}")

    sq = sqlite3.connect(sqlite_path)
    sq.row_factory = sqlite3.Row
    pg = psycopg.connect(args.dsn)

    try:
        rows = sq.execute(
            """
            SELECT
                c.id AS legacy_live_id,
                c.bank_name,
                c.title,
                c.source_url,
                c.updated_at AS campaign_updated_at,
                d.*
            FROM live_campaigns AS c
            JOIN live_standard_product_details AS d
                ON d.product_id = c.id
            WHERE c.bank_name = 'Albaraka Türk'
              AND d.product_family = 'Araç Finansmanı'
            ORDER BY d.product_name
            """
        ).fetchall()

        selected = [r for r in rows if r["product_name"] in TARGET_PRODUCTS]
        found = {r["product_name"] for r in selected}
        missing = sorted(TARGET_PRODUCTS - found)
        if missing:
            raise RuntimeError(
                "SQLite'da beklenen Albaraka araç ürünleri eksik: "
                + ", ".join(missing)
            )

        with pg.cursor() as cur:
            cur.execute("SET search_path TO bansa, public")
            # Eski şemalarda financing_amount yoktu. Mevcut DB'yi yerinde yükselt.
            cur.execute(
                """
                ALTER TABLE product_pricing_tiers
                ADD COLUMN IF NOT EXISTS financing_amount NUMERIC(18,2)
                """
            )

            pg_ids: dict[int, int] = {}

            for r in selected:
                cur.execute(
                    """
                    UPDATE standard_products
                    SET
                        minimum_financing_amount = %s,
                        maximum_financing_amount = %s,
                        minimum_maturity_months = %s,
                        maximum_maturity_months = %s,
                        profit_share_rate = %s,
                        profit_share_rate_text = %s,
                        interest_free = %s,
                        interest_free_text = %s,
                        maturity_rules_text = %s,
                        maturity_reference_upper_amount = %s,
                        financing_ratio_rules_text = %s,
                        maximum_financing_ratio = %s,
                        vehicle_finance_rules_text = %s,
                        vehicle_age_rules_text = %s,
                        finance_rules = %s::jsonb,
                        checked_at = %s,
                        extracted_at = %s,
                        updated_at = NOW()
                    WHERE legacy_live_id = %s
                    RETURNING id
                    """,
                    (
                        r["minimum_financing_amount"],
                        r["maximum_financing_amount"],
                        r["minimum_maturity_months"],
                        r["maximum_maturity_months"],
                        r["profit_share_rate"],
                        r["profit_share_rate_text"],
                        bool(r["interest_free"]) if r["interest_free"] is not None else None,
                        r["interest_free_text"],
                        r["maturity_rules_text"],
                        r["maturity_reference_upper_amount"],
                        r["financing_ratio_rules_text"],
                        r["maximum_financing_ratio"],
                        r["vehicle_finance_rules_text"],
                        r["vehicle_age_rules_text"],
                        _json_or_none(r["finance_rules_json"]),
                        r["checked_at"],
                        r["extracted_at"],
                        int(r["legacy_live_id"]),
                    ),
                )
                result = cur.fetchone()
                if not result:
                    raise RuntimeError(
                        "PostgreSQL standard_products kaydı bulunamadı: "
                        f"{r['product_name']} (legacy_live_id={r['legacy_live_id']})"
                    )
                pg_ids[int(r["legacy_live_id"])] = int(result[0])

            # Normalize fiyatlama kademelerini de SQLite ile eşitle.
            for legacy_id, pg_product_id in pg_ids.items():
                cur.execute(
                    "DELETE FROM product_pricing_tiers WHERE product_id = %s",
                    (pg_product_id,),
                )
                tiers = sq.execute(
                    """
                    SELECT *
                    FROM live_product_pricing_tiers
                    WHERE product_id = ?
                    ORDER BY id
                    """,
                    (legacy_id,),
                ).fetchall()

                for tier in tiers:
                    cur.execute(
                        """
                        INSERT INTO product_pricing_tiers(
                            legacy_id,
                            product_id,
                            financing_amount,
                            maturity_months,
                            profit_share_rate,
                            allocation_fee_rate,
                            monthly_total_cost_rate,
                            annual_total_cost_rate,
                            pricing_variant,
                            source_text,
                            updated_at
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            int(tier["id"]),
                            pg_product_id,
                            tier["financing_amount"],
                            tier["maturity_months"],
                            tier["profit_share_rate"],
                            tier["allocation_fee_rate"],
                            tier["monthly_total_cost_rate"],
                            tier["annual_total_cost_rate"],
                            tier["pricing_variant"],
                            tier["source_text"],
                            tier["updated_at"],
                        ),
                    )

        pg.commit()

        print("=" * 88)
        print("ALBARAKA ARAÇ FİNANSMANI → POSTGRESQL SENKRONİZASYONU TAMAMLANDI")
        print("=" * 88)
        for r in selected:
            tier_count = sq.execute(
                "SELECT COUNT(*) FROM live_product_pricing_tiers WHERE product_id=?",
                (int(r["legacy_live_id"]),),
            ).fetchone()[0]
            print(
                f"- {r['product_name']}: "
                f"vade={r['maximum_maturity_months']} · "
                f"oran={r['maximum_financing_ratio']} · "
                f"fiyatlama={tier_count}"
            )
        return 0
    finally:
        sq.close()
        pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
