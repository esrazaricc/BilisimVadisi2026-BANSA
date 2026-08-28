from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import psycopg
except ImportError as exc:
    raise RuntimeError('Çalıştırın: python -m pip install "psycopg[binary]"') from exc


def main() -> int:
    dsn = os.getenv("POSTGRES_DSN", "").strip()
    if not dsn:
        raise RuntimeError("POSTGRES_DSN tanımlı değil")

    rows = json.loads((ROOT / "config" / "banks.json").read_text(encoding="utf-8"))
    pg = psycopg.connect(dsn, application_name="bansa_ensure_finance_banks")
    with pg.cursor() as cur:
        cur.execute("SET search_path TO bansa, public")
        for row in rows:
            cur.execute(
                """
                INSERT INTO banks(name,slug,legal_name,official_url,is_active,updated_at)
                VALUES (%s,%s,%s,%s,TRUE,NOW())
                ON CONFLICT(name) DO UPDATE SET
                    slug=EXCLUDED.slug,
                    legal_name=EXCLUDED.legal_name,
                    official_url=EXCLUDED.official_url,
                    is_active=TRUE,
                    updated_at=NOW()
                """,
                (row["name"], row.get("slug"), row.get("legal_name"), row.get("base_url")),
            )
    pg.commit()
    pg.close()
    print(f"PostgreSQL banka kapsamı hazır: {len(rows)} banka upsert edildi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
