from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.finance_data_quality import is_generic_ziraat_product_name

CONFIG = PROJECT_ROOT / "config" / "standard_product_sources.json"
DEFAULT_DB = PROJECT_ROOT / "data" / "campaigns.db"

EXPECTED_MIN = {
    "tarim_finansmani": 14,
    "ihtiyac_finansmani": 8,
    "arac_finansmani": 3,   # standart + TOGG + Yeşil Taşıt
    "konut_finansmani": 3,  # konut + kentsel + Yeşil Ev
    "arsa_finansmani": 1,
    "isyeri_finansmani": 1,
    "leasing": 2,
    "gayri_nakdi_finansman": 4,
    "ticari_finansman": 4,
}


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(("PASS" if ok else "FAIL") + " | " + label + (f" | {detail}" if detail else ""))
    return ok


def config_rows() -> list[dict]:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    bank = next(b for b in data["banks"] if b["name"] == "Ziraat Katılım")
    rows = []
    for page in bank.get("embedded_product_pages", []):
        for product in page.get("products", []):
            rows.append(
                {
                    "product_name": product["product_name"],
                    "product_family_key": product.get("product_family_key") or page.get("product_family_key"),
                    "scope": product.get("scope") or page.get("scope"),
                }
            )
    return rows


def audit_config() -> tuple[int, int]:
    rows = config_rows()
    counts = Counter(r["product_family_key"] for r in rows)
    passed = failed = 0
    tests = [
        ("Config: hiçbir Ziraat ürün adı banka genel başlığı değil", all(not is_generic_ziraat_product_name(r["product_name"]) for r in rows), f"ürün={len(rows)}"),
        ("Config: Tarım 14 ayrı resmî ürün", counts["tarim_finansmani"] >= 14, str(counts["tarim_finansmani"])),
        ("Config: İhtiyaç 8 ayrı ürün", counts["ihtiyac_finansmani"] >= 8, str(counts["ihtiyac_finansmani"])),
        ("Config: Konut karşılaştırmasında en az 3 ürün", counts["konut_finansmani"] >= 3, str(counts["konut_finansmani"])),
        ("Config: Araç karşılaştırmasında en az 3 ürün", counts["arac_finansmani"] >= 3, str(counts["arac_finansmani"])),
        ("Config: Leasing 2 ayrı ürün", counts["leasing"] >= 2, str(counts["leasing"])),
        ("Config: Gayri nakdi en az 4 ürün", counts["gayri_nakdi_finansman"] >= 4, str(counts["gayri_nakdi_finansman"])),
    ]
    for label, ok, detail in tests:
        if check(label, ok, detail): passed += 1
        else: failed += 1
    return passed, failed


def sqlite_products(db: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT lc.id, lc.is_current, d.product_name, d.product_family_key,
               d.product_family, d.profit_share_rate, d.profit_share_rate_text,
               d.source_page, d.finance_rules_json
        FROM live_campaigns lc
        JOIN live_standard_product_details d ON d.product_id=lc.id
        WHERE d.bank_name='Ziraat Katılım' AND lc.is_current=1
        """
    ).fetchall()
    conn.close()
    return rows


def audit_live_rows(rows, label_prefix: str) -> tuple[int, int]:
    passed = failed = 0
    names = [str(r["product_name"]) for r in rows]
    counts = Counter(str(r["product_family_key"]) for r in rows)
    tests = [
        (f"{label_prefix}: generic 'Ziraat Katılım Bankası' ürünü yok", all(not is_generic_ziraat_product_name(n) for n in names), f"current={len(rows)}"),
    ]
    for key, minimum in EXPECTED_MIN.items():
        tests.append((f"{label_prefix}: {key} minimum ürün sayısı", counts[key] >= minimum, f"{counts[key]} >= {minimum}"))
    tarim_bad = []
    for r in rows:
        if str(r["product_family_key"]) != "tarim_finansmani":
            continue
        rate = r["profit_share_rate"]
        if rate is not None:
            tarim_bad.append((r["product_name"], rate))
    tests.append((f"{label_prefix}: devlet destek yüzdeleri Tarım kâr payına sızmıyor", not tarim_bad, repr(tarim_bad[:3])))
    for label, ok, detail in tests:
        if check(label, ok, detail): passed += 1
        else: failed += 1
    return passed, failed


def pg_products() -> list[dict]:
    dsn = os.getenv("POSTGRES_DSN", "").strip()
    if not dsn:
        raise RuntimeError("POSTGRES_DSN tanımlı değil")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError('Çalıştırın: python -m pip install "psycopg[binary]"') from exc
    conn = psycopg.connect(dsn, row_factory=dict_row, application_name="bansa_ziraat_catalog_audit_v2")
    with conn.cursor() as cur:
        cur.execute("SET search_path TO bansa, public")
        cur.execute(
            """
            SELECT sp.product_name, pf.family_key AS product_family_key,
                   pf.family_name AS product_family, sp.profit_share_rate,
                   sp.profit_share_rate_text, sp.finance_rules
            FROM standard_products sp
            JOIN banks b ON b.id=sp.bank_id
            JOIN product_families pf ON pf.id=sp.family_id
            WHERE b.name='Ziraat Katılım' AND sp.is_current=TRUE
            """
        )
        rows = list(cur.fetchall())
    conn.close()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--sqlite", action="store_true")
    parser.add_argument("--postgres", action="store_true")
    args = parser.parse_args()

    total_pass = total_fail = 0
    p, f = audit_config(); total_pass += p; total_fail += f
    if args.sqlite:
        p, f = audit_live_rows(sqlite_products(args.db), "SQLITE"); total_pass += p; total_fail += f
    if args.postgres:
        p, f = audit_live_rows(pg_products(), "POSTGRESQL"); total_pass += p; total_fail += f
    print("=" * 72)
    print(f"ZIRAAT URUN KATALOG V2 AUDIT: PASS={total_pass} FAIL={total_fail}")
    print("=" * 72)
    return 1 if total_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
