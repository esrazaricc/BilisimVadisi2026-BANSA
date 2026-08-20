from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

try:
    import psycopg
except ImportError as exc:
    raise SystemExit('Önce: pip install "psycopg[binary]"') from exc

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sqlite", default=str(PROJECT_ROOT / "data" / "campaigns.db"))
    p.add_argument("--dsn", default=os.getenv("POSTGRES_DSN"))
    args = p.parse_args()
    if not args.dsn:
        raise SystemExit("POSTGRES_DSN yok.")

    sq = sqlite3.connect(args.sqlite)
    pg = psycopg.connect(args.dsn)
    try:
        sqlite_campaigns = sq.execute("SELECT COUNT(*) FROM live_campaigns WHERE record_kind='campaign'").fetchone()[0]
        sqlite_products = sq.execute("SELECT COUNT(*) FROM live_standard_product_details").fetchone()[0]
        sqlite_current_campaigns = sq.execute("SELECT COUNT(*) FROM live_campaigns WHERE record_kind='campaign' AND is_current=1").fetchone()[0]
        sqlite_current_products = sq.execute("SELECT COUNT(*) FROM live_campaigns WHERE record_kind='standard_product' AND is_current=1").fetchone()[0]

        with pg.cursor() as cur:
            cur.execute("SET search_path TO bansa, public")
            checks = {}
            for label, sql in {
                "pg_campaigns": "SELECT COUNT(*) FROM campaigns",
                "pg_products": "SELECT COUNT(*) FROM standard_products",
                "pg_current_campaigns": "SELECT COUNT(*) FROM campaigns WHERE is_current=TRUE",
                "pg_current_products": "SELECT COUNT(*) FROM standard_products WHERE is_current=TRUE",
                "pg_banks": "SELECT COUNT(*) FROM banks",
                "pg_source_pages": "SELECT COUNT(*) FROM source_pages",
                "pg_campaign_benefits": "SELECT COUNT(*) FROM campaign_benefits",
                "pg_campaign_audiences": "SELECT COUNT(*) FROM campaign_audiences",
                "pg_product_features": "SELECT COUNT(*) FROM product_features",
                "pg_product_changes": "SELECT COUNT(*) FROM product_change_events",
            }.items():
                cur.execute(sql)
                checks[label] = cur.fetchone()[0]

        warnings = []
        pairs = [
            ("campaigns", sqlite_campaigns, checks["pg_campaigns"]),
            ("products", sqlite_products, checks["pg_products"]),
            ("current_campaigns", sqlite_current_campaigns, checks["pg_current_campaigns"]),
            ("current_products", sqlite_current_products, checks["pg_current_products"]),
        ]
        print("=" * 88)
        print("BANSA POSTGRESQL MIGRATION AUDIT")
        print("=" * 88)
        for name, old, new in pairs:
            ok = old == new
            print(f"{name}: SQLite={old} | PostgreSQL={new} | {'OK' if ok else 'FARK'}")
            if not ok:
                warnings.append(name)
        print(f"banks: {checks['pg_banks']}")
        print(f"source_pages: {checks['pg_source_pages']}")
        print(f"campaign_benefits: {checks['pg_campaign_benefits']}")
        print(f"campaign_audiences: {checks['pg_campaign_audiences']}")
        print(f"product_features: {checks['pg_product_features']}")
        print(f"product_changes: {checks['pg_product_changes']}")
        print(f"Uyarı: {len(warnings)}")
        print("SONUÇ: OK" if not warnings else "SONUÇ: KONTROL GEREKİYOR")
        return 0 if not warnings else 2
    finally:
        sq.close()
        pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
