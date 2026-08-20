from __future__ import annotations

import os
import sys

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError as exc:
    raise SystemExit(
        'psycopg kurulu değil. Önce: python -m pip install "psycopg[binary]"'
    ) from exc

EXPECTED = {
    "Deniz Taşıtları Finansmanı": {"maturity": 36},
    "Dijital Araç Finansmanı": {"maturity": 48, "ratio": 70.0, "age": ("2. El", "10 yaş")},
    "Taşıt Finansmanı": {"maturity": 48, "ratio": 70.0, "age": ("0 km", "2. El", "10 yaş")},
    "Taşıt Kiralama Finansmanı": {"maturity": 36},
    "Togg Finansmanı": {"maturity": 48, "ratio": 70.0, "age": ("0 km",)},
}


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)
    print("[FAIL]", message)


def main() -> int:
    dsn = os.getenv("POSTGRES_DSN", "").strip()
    if not dsn:
        raise SystemExit("POSTGRES_DSN tanımlı değil.")

    con = psycopg.connect(dsn, row_factory=dict_row)
    errors: list[str] = []

    try:
        with con.cursor() as cur:
            cur.execute("SET search_path TO bansa, public")
            cur.execute(
                """
                SELECT
                    p.id,
                    p.product_name,
                    p.maximum_maturity_months,
                    p.maximum_financing_ratio,
                    p.vehicle_finance_rules_text,
                    p.vehicle_age_rules_text
                FROM standard_products p
                JOIN banks b ON b.id = p.bank_id
                JOIN product_families f ON f.id = p.family_id
                WHERE b.name = 'Albaraka Türk'
                  AND f.family_name = 'Araç Finansmanı'
                  AND p.is_current = TRUE
                ORDER BY p.product_name
                """
            )
            products = cur.fetchall()

            print("=" * 88)
            print("ALBARAKA ARAÇ FİNANSMANI — POSTGRESQL AUDIT")
            print("=" * 88)
            print("Ürün:", len(products))

            by_name = {r["product_name"]: r for r in products}
            for name, spec in EXPECTED.items():
                row = by_name.get(name)
                if not row:
                    fail(f"Eksik ürün: {name}", errors)
                    continue

                if row["maximum_maturity_months"] != spec["maturity"]:
                    fail(
                        f"{name}: vade {row['maximum_maturity_months']} != {spec['maturity']}",
                        errors,
                    )

                if "ratio" in spec:
                    ratio = float(row["maximum_financing_ratio"]) if row["maximum_financing_ratio"] is not None else None
                    if ratio != spec["ratio"]:
                        fail(f"{name}: oran {ratio} != {spec['ratio']}", errors)

                for token in spec.get("age", ()):
                    if token.casefold() not in str(row["vehicle_age_rules_text"] or "").casefold():
                        fail(
                            f"{name}: araç durumu/yaş kuralında '{token}' yok: "
                            f"{row['vehicle_age_rules_text']!r}",
                            errors,
                        )

                if name in {"Taşıt Finansmanı", "Dijital Araç Finansmanı"}:
                    rule = str(row["vehicle_finance_rules_text"] or "")
                    for token in ("%70", "%50", "%30", "%20", "Kullandırım yok"):
                        if token.casefold() not in rule.casefold():
                            fail(f"{name}: araç kuralında '{token}' yok", errors)

                print(
                    f"[OK] {name}: vade={row['maximum_maturity_months']} · "
                    f"oran={row['maximum_financing_ratio']} · "
                    f"araç={row['vehicle_age_rules_text'] or '—'}"
                )

            togg = by_name.get("Togg Finansmanı")
            if togg:
                cur.execute(
                    """
                    SELECT pricing_variant, financing_amount, maturity_months, profit_share_rate
                    FROM product_pricing_tiers
                    WHERE product_id = %s
                    ORDER BY pricing_variant, maturity_months, financing_amount
                    """,
                    (togg["id"],),
                )
                tiers = cur.fetchall()
                if len(tiers) != 6:
                    fail(f"Togg fiyatlama satırı {len(tiers)} != 6", errors)
                if any(r["financing_amount"] is None for r in tiers):
                    fail("Togg fiyatlama tablosunda boş financing_amount var", errors)
                print("Togg fiyatlama satırı:", len(tiers))
                for r in tiers:
                    print(
                        "  -",
                        r["pricing_variant"],
                        f"{r['maturity_months']} ay",
                        f"{r['financing_amount']} TL",
                        f"%{r['profit_share_rate']}",
                    )

        print("-" * 88)
        if errors:
            print("SONUÇ: HATA")
            print("Uyarı:", len(errors))
            return 1

        print("SONUÇ: OK")
        print("Uyarı: 0")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
