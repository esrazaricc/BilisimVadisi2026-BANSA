from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.finance_data_quality import is_generic_ziraat_product_name

DEFAULT_DB = PROJECT_ROOT / "data" / "campaigns.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def cleanup_sqlite(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT lc.id, d.product_name
        FROM live_campaigns lc
        JOIN live_standard_product_details d ON d.product_id = lc.id
        WHERE d.bank_name = 'Ziraat Katılım' AND lc.is_current = 1
        """
    ).fetchall()
    ids = [int(r["id"]) for r in rows if is_generic_ziraat_product_name(r["product_name"])]
    ts = now_iso()
    for product_id in ids:
        conn.execute(
            """
            UPDATE live_campaigns
            SET is_current=0,
                comparison_eligible=0,
                current_status='removed',
                listing_status='removed',
                removed_at=COALESCE(removed_at, ?),
                updated_at=?
            WHERE id=?
            """,
            (ts, ts, product_id),
        )
    conn.commit()
    conn.close()
    print(f"SQLite Ziraat generic ürün pasife alındı: {len(ids)}")
    return len(ids)


def cleanup_postgresql() -> int:
    dsn = os.getenv("POSTGRES_DSN", "").strip()
    if not dsn:
        raise RuntimeError("POSTGRES_DSN tanımlı değil")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError('Çalıştırın: python -m pip install "psycopg[binary]"') from exc

    conn = psycopg.connect(dsn, application_name="bansa_ziraat_catalog_cleanup_v2")
    ids: list[int] = []
    with conn.cursor() as cur:
        cur.execute("SET search_path TO bansa, public")
        cur.execute(
            """
            SELECT sp.id, sp.product_name
            FROM standard_products sp
            JOIN banks b ON b.id=sp.bank_id
            WHERE b.name='Ziraat Katılım' AND sp.is_current=TRUE
            """
        )
        ids = [int(pid) for pid, name in cur.fetchall() if is_generic_ziraat_product_name(name)]
        for pid in ids:
            cur.execute(
                """
                UPDATE standard_products
                SET is_current=FALSE,
                    current_status='removed',
                    updated_at=NOW()
                WHERE id=%s
                """,
                (pid,),
            )
    conn.commit()
    conn.close()
    print(f"PostgreSQL Ziraat generic ürün pasife alındı: {len(ids)}")
    return len(ids)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--sqlite-only", action="store_true")
    parser.add_argument("--postgres-only", action="store_true")
    args = parser.parse_args()

    if args.sqlite_only and args.postgres_only:
        parser.error("--sqlite-only ve --postgres-only birlikte kullanılamaz")

    if not args.postgres_only:
        cleanup_sqlite(args.db)
    if not args.sqlite_only:
        cleanup_postgresql()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
