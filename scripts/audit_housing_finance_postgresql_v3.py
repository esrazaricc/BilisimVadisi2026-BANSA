from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

EXPECTED_HOUSING = {
    ("Albaraka Türk", "Konut Finansmanı"),
    ("Dünya Katılım", "Konut Finansmanı"),
    ("Kuveyt Türk", "Gurbetten Sılaya Gayrimenkul Finansmanı"),
    ("Kuveyt Türk", "Konut Finansmanı"),
    ("Kuveyt Türk", "Yeşil Konut Finansmanı"),
    ("Kuveyt Türk", "İlk Evim Konut Finansmanı"),
    ("Türkiye Finans", "Konut Finansmanı (Konut Kredisi)"),
}

checks: list[tuple[bool, str]] = []


def norm(value: object) -> str:
    return str(value or "").strip().rstrip("*").strip()


def check(condition: bool, label: str) -> None:
    checks.append((bool(condition), label))
    print(("PASS" if condition else "FAIL") + " | " + label)


def _fee_map(cur: Any, product_id: int) -> dict[str, dict[str, Any]]:
    cur.execute(
        """
        SELECT fee_type, fee_label, waived, amount, rate, note
        FROM product_fee_rules
        WHERE product_id=%s
        """,
        (product_id,),
    )
    return {str(row["fee_type"]): row for row in cur.fetchall()}


def main() -> int:
    dsn = os.getenv("POSTGRES_DSN", "").strip()
    if not dsn:
        print("FAIL | POSTGRES_DSN tanımlı değil")
        return 2

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            'PostgreSQL sürücüsü eksik. Çalıştırın: python -m pip install "psycopg[binary]"'
        ) from exc

    print("=" * 96)
    print("BANSA — KONUT FİNANSMANI POSTGRESQL AUDIT V3")
    print("=" * 96)

    with psycopg.connect(dsn, row_factory=dict_row) as con:
        with con.cursor() as cur:
            cur.execute("SET search_path TO bansa, public")
            cur.execute(
                """
                SELECT p.id, b.name AS bank_name, p.product_name,
                       f.family_key, f.family_name,
                       p.profit_share_rate, p.profit_share_rate_text
                FROM standard_products AS p
                JOIN banks AS b ON b.id=p.bank_id
                JOIN product_families AS f ON f.id=p.family_id
                WHERE p.is_current=TRUE
                """
            )
            rows = cur.fetchall()
            by_key = {
                (str(row["bank_name"]), norm(row["product_name"])): row
                for row in rows
            }

            actual_housing = {
                key
                for key, row in by_key.items()
                if str(row["family_key"]) == "konut_finansmani"
                and key in EXPECTED_HOUSING
            }
            check(
                actual_housing == EXPECTED_HOUSING,
                "PostgreSQL'de beklenen 7 konut ürünü mevcut ve konut ailesinde",
            )

            al = by_key.get(("Albaraka Türk", "Konut Finansmanı"))
            check(al is not None, "Albaraka Konut ürünü mevcut")
            if al:
                al_id = int(al["id"])
                cur.execute(
                    "SELECT COUNT(*) AS n FROM product_pricing_tiers WHERE product_id=%s",
                    (al_id,),
                )
                check(
                    int(cur.fetchone()["n"]) == 0,
                    "Albaraka örnek %2,95 PostgreSQL fiyatlama tablosunda yok",
                )
                check(
                    al["profit_share_rate"] is None,
                    "Albaraka ürün seviyesinde sabit güncel oran uydurulmuyor",
                )

            dunya = by_key.get(("Dünya Katılım", "Konut Finansmanı"))
            check(dunya is not None, "Dünya Katılım Konut ürünü mevcut")
            if dunya:
                fees = _fee_map(cur, int(dunya["id"]))
                appraisal = fees.get("appraisal", {})
                mortgage = fees.get("mortgage_establishment", {})
                check(
                    float(appraisal.get("amount") or 0) == 20_778.0
                    and "asgari" in str(appraisal.get("note") or "").casefold(),
                    "Dünya ekspertiz asgari 20.778 TL",
                )
                check(
                    float(mortgage.get("amount") or 0) == 3_000.0
                    and "asgari" in str(mortgage.get("note") or "").casefold(),
                    "Dünya ipotek tesis asgari 3.000 TL",
                )

            for product_name in (
                "Konut Finansmanı",
                "İlk Evim Konut Finansmanı",
                "Yeşil Konut Finansmanı",
                "Gurbetten Sılaya Gayrimenkul Finansmanı",
            ):
                row = by_key.get(("Kuveyt Türk", product_name))
                check(row is not None, f"Kuveyt {product_name}: ürün mevcut")
                if not row:
                    continue
                fees = _fee_map(cur, int(row["id"]))
                allocation = fees.get("allocation", {})
                appraisal = fees.get("appraisal", {})
                mortgage = fees.get("mortgage_establishment", {})
                appraisal_note = str(appraisal.get("note") or "").casefold()
                mortgage_note = str(mortgage.get("note") or "").casefold()
                check(
                    float(allocation.get("rate") or 0) == 0.5,
                    f"Kuveyt {product_name}: tahsis %0,50",
                )
                check(
                    float(appraisal.get("amount") or 0) == 23_645.0
                    and "asgari" in appraisal_note
                    and "29.07.2026" in appraisal_note
                    and "23.203" in appraisal_note
                    and "örnek" not in appraisal_note
                    and "hesaplama aracı" not in appraisal_note,
                    f"Kuveyt {product_name}: ekspertiz 23.645 asgari, kaynak farkı açık, örnek etiketi yok",
                )
                check(
                    float(mortgage.get("amount") or 0) == 4_500.0
                    and "asgari" in mortgage_note
                    and "gerçek masraf" in mortgage_note
                    and "örnek" not in mortgage_note
                    and "hesaplama aracı" not in mortgage_note,
                    f"Kuveyt {product_name}: ipotek 4.500 asgari, gerçek maliyet açıklaması var",
                )

            tf = by_key.get(("Türkiye Finans", "Konut Finansmanı (Konut Kredisi)"))
            check(tf is not None, "Türkiye Finans Konut ürünü mevcut")
            if tf:
                tf_id = int(tf["id"])
                fees = _fee_map(cur, tf_id)
                appraisal = fees.get("appraisal", {})
                mortgage = fees.get("mortgage_establishment", {})
                check(
                    float(appraisal.get("amount") or 0) == 16_500.0
                    and "100.000 tl örnek" in str(appraisal.get("note") or "").casefold(),
                    "Türkiye Finans 16.500 TL ekspertiz örnek senaryoya açıkça bağlı",
                )
                check(
                    float(mortgage.get("amount") or 0) == 3_000.0
                    and "100.000 tl örnek" in str(mortgage.get("note") or "").casefold()
                    and "faturalandır" in str(mortgage.get("note") or "").casefold(),
                    "Türkiye Finans 3.000 TL ipotek örnek + gerçek maliyet açıklamasıyla tutuluyor",
                )
                cur.execute(
                    "SELECT COUNT(*) AS n FROM product_pricing_tiers WHERE product_id=%s",
                    (tf_id,),
                )
                check(
                    int(cur.fetchone()["n"]) == 40,
                    "Türkiye Finans 40 koşullu fiyatlama satırı PostgreSQL'de korunuyor",
                )

    passed = sum(1 for ok, _ in checks if ok)
    failed = sum(1 for ok, _ in checks if not ok)
    print("\n" + "=" * 96)
    print(f"SONUÇ: PASS={passed} FAIL={failed}")
    print("=" * 96)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
