from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.repair_housing_finance_audit_v1 import PRODUCTS, normalize_product_name


def almost(value: Any, expected: float, tol: float = 1e-9) -> bool:
    try:
        return abs(float(value) - expected) <= tol
    except (TypeError, ValueError):
        return False


def parse_housing(raw: Any) -> dict[str, list[dict[str, Any]]]:
    try:
        obj = raw if isinstance(raw, dict) else json.loads(str(raw or "{}"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def audit_sqlite() -> tuple[int, int]:
    db = PROJECT_ROOT / "data" / "campaigns.db"
    if not db.exists():
        print("[SQLite] campaigns.db yok")
        return 0, 1

    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    passed = failed = 0

    def check(ok: bool, label: str) -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
            print("[PASS]", label)
        else:
            failed += 1
            print("[FAIL]", label)

    try:
        rows = con.execute(
            """SELECT * FROM live_standard_product_details
               WHERE product_family='Konut Finansmanı'"""
        ).fetchall()
        found = {
            (row["bank_name"], normalize_product_name(row["product_name"])): row
            for row in rows
        }
        check(len(found) == 10, f"Konut/Gayrimenkul ürün sayısı = 10 (gerçek {len(found)})")

        for key, cfg in PRODUCTS.items():
            row = found.get(key)
            check(row is not None, f"Ürün mevcut: {key[0]} | {key[1]}")
            if row is None:
                continue
            pid = int(row["product_id"])

            check(
                row["maximum_maturity_months"] == cfg.get("max_maturity"),
                f"{key[1]} azami vade kaynakla uyumlu: {cfg.get('max_maturity')}",
            )

            expected_ratio = cfg.get("ratio")
            if expected_ratio is None:
                check(
                    row["maximum_financing_ratio"] is None,
                    f"{key[1]} için sabit oran uydurulmamış",
                )
            else:
                check(
                    almost(row["maximum_financing_ratio"], float(expected_ratio)),
                    f"{key[1]} sabit finansman oranı %{expected_ratio:g}",
                )

            housing_cfg = cfg.get("housing")
            housing = parse_housing(row["housing_finance_rules_json"])
            if housing_cfg is not None:
                std, add = housing_cfg
                check(
                    bool(housing.get("standard_home")) is bool(std),
                    f"{key[1]} standard_home matrisi",
                )
                check(
                    bool(housing.get("additional_home")) is bool(add),
                    f"{key[1]} additional_home matrisi",
                )
            elif cfg.get("housing_clear"):
                check(
                    not housing,
                    f"{key[1]} için doğrulanmamış konut oran matrisi saklanmıyor",
                )

            fee = cfg.get("fee")
            fee_rows = con.execute(
                """SELECT fee_label,rate,note FROM live_product_fee_rules
                   WHERE product_id=? AND (fee_type='allocation' OR lower(fee_label) LIKE '%tahsis%')""",
                (pid,),
            ).fetchall()
            if fee is None:
                check(not fee_rows, f"{key[1]} tahsis oranı doğrulanmadıysa boş")
            else:
                check(len(fee_rows) == 1, f"{key[1]} tek tahsis ücreti kuralı")
                if fee_rows:
                    check(almost(fee_rows[0]["rate"], float(fee["rate"])), f"{key[1]} tahsis oranı %{fee['rate']:g}")
                    if "Azami" in fee["fee_label"]:
                        check("Azami" in fee_rows[0]["fee_label"], f"{key[1]} tahsis ücreti azami olarak etiketli")

            purpose = con.execute(
                """SELECT feature_value FROM live_product_features
                   WHERE product_id=? AND feature_key='usage_purpose'""",
                (pid,),
            ).fetchone()
            check(
                purpose is not None and purpose["feature_value"] == cfg["purpose"],
                f"{key[1]} amaç alanı ürün kimliğiyle uyumlu",
            )

        # Ürüne özel kritik kontroller
        alb = found[("Albaraka Türk", "Konut Finansmanı")]
        sample = con.execute(
            """SELECT maturity_months,financing_amount,profit_share_rate,allocation_fee_rate
               FROM live_product_pricing_tiers
               WHERE product_id=? AND pricing_variant='Resmî maliyet örneği · 100.000 TL'""",
            (int(alb["product_id"]),),
        ).fetchall()
        check(len(sample) == 0, "Albaraka örnek maliyet oranı müşteri fiyatlama tablosuna alınmıyor")

        tf = found[("Türkiye Finans", "Konut Finansmanı (Konut Kredisi)")]
        tf_count = con.execute(
            "SELECT COUNT(*) FROM live_product_pricing_tiers WHERE product_id=?",
            (int(tf["product_id"]),),
        ).fetchone()[0]
        check(tf_count >= 40, f"Türkiye Finans fiyatlama matrisi korunmuş (satır {tf_count})")

        green = found[("Kuveyt Türk", "Yeşil Konut Finansmanı")]
        green_offer = con.execute(
            """SELECT max_amount,condition_text FROM live_product_offer_rules
               WHERE product_id=? AND rule_label='Web Kâr Oranı Geçerlilik Sınırı'""",
            (int(green["product_id"]),),
        ).fetchone()
        check(green_offer is not None and almost(green_offer["max_amount"], 3_000_000.0), "Yeşil Konut 3.000.000 TL web kâr oranı geçerlilik sınırı doğru kavramda")

    finally:
        con.close()

    print("\nSQLite Audit Özeti:", f"PASS={passed}", f"FAIL={failed}")
    return passed, failed


def audit_postgres() -> tuple[int, int]:
    dsn = os.getenv("POSTGRES_DSN", "").strip()
    if not dsn:
        print("\n[PostgreSQL] POSTGRES_DSN tanımlı değil; PG audit atlandı.")
        return 0, 0
    try:
        import psycopg
    except ImportError:
        print("[PostgreSQL][FAIL] psycopg kurulu değil")
        return 0, 1

    passed = failed = 0
    with psycopg.connect(dsn) as con:
        with con.cursor() as cur:
            cur.execute("SET search_path TO bansa, public")
            cur.execute(
                """SELECT b.name,p.product_name,p.maximum_maturity_months,
                          p.maximum_financing_ratio,p.housing_finance_rules,p.id
                   FROM standard_products p
                   JOIN banks b ON b.id=p.bank_id
                   JOIN product_families f ON f.id=p.family_id
                   WHERE p.is_current=TRUE AND f.family_name='Konut Finansmanı'"""
            )
            rows = cur.fetchall()
            found = {
                (bank, normalize_product_name(name)): (maturity, ratio, housing, pid)
                for bank, name, maturity, ratio, housing, pid in rows
            }
            for key, cfg in PRODUCTS.items():
                row = found.get(key)
                if row is None:
                    failed += 1
                    print("[PG FAIL] Ürün yok:", key)
                    continue
                maturity, ratio, housing, pid = row
                ok = maturity == cfg.get("max_maturity")
                passed += int(ok); failed += int(not ok)
                print("[PG PASS]" if ok else "[PG FAIL]", key, "vade", maturity)
                expected_ratio = cfg.get("ratio")
                ok = (ratio is None) if expected_ratio is None else almost(ratio, expected_ratio)
                passed += int(ok); failed += int(not ok)
                print("[PG PASS]" if ok else "[PG FAIL]", key, "oran", ratio)
    print("PostgreSQL Audit Özeti:", f"PASS={passed}", f"FAIL={failed}")
    return passed, failed


def main() -> int:
    print("=" * 90)
    print("BANSA — KONUT / GAYRİMENKUL FİNANSMANI AUDIT V1")
    print("=" * 90)
    _, sqlite_failed = audit_sqlite()
    _, pg_failed = audit_postgres()
    return 0 if sqlite_failed + pg_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
