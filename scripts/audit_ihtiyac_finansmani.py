from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path


DB = Path("data") / "campaigns.db"


def clean(value) -> str:
    return str(value or "").strip()


def main() -> int:
    if not DB.exists():
        raise SystemExit(f"DB bulunamadı: {DB}")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    products = con.execute(
        """
        SELECT
            c.id AS product_id,
            c.bank_name,
            c.source_url,
            c.clean_text,
            d.product_name,
            d.product_family,
            d.scope,
            d.minimum_financing_amount,
            d.maximum_financing_amount,
            d.minimum_maturity_months,
            d.maximum_maturity_months,
            d.profit_share_rate,
            d.profit_share_rate_text
        FROM live_campaigns c
        JOIN live_standard_product_details d
            ON d.product_id = c.id
        WHERE
            c.is_current = 1
            AND c.record_kind = 'standard_product'
            AND LOWER(COALESCE(d.product_family, ''))
                LIKE '%ihtiyaç%'
        ORDER BY
            c.bank_name,
            d.product_name
        """
    ).fetchall()

    feature_rows = con.execute(
        """
        SELECT
            product_id,
            feature_key,
            feature_label,
            feature_value,
            source_text
        FROM live_product_features
        ORDER BY
            product_id,
            feature_label
        """
    ).fetchall()

    feature_map = defaultdict(list)
    for row in feature_rows:
        feature_map[int(row["product_id"])].append(row)

    print("=" * 110)
    print("İHTİYAÇ FİNANSMANI — GENEL AUDIT")
    print("=" * 110)
    print("Ürün:", len(products))
    print()

    warning_count = 0

    for p in products:
        pid = int(p["product_id"])

        print("-" * 110)
        print(
            f'{p["bank_name"]} | '
            f'{p["product_name"]}'
        )
        print("Kaynak:", clean(p["source_url"]))

        print(
            "Ana kayıt:"
            f" Min tutar={p['minimum_financing_amount']}"
            f" | Max tutar={p['maximum_financing_amount']}"
            f" | Min vade={p['minimum_maturity_months']}"
            f" | Max vade={p['maximum_maturity_months']}"
            f" | Kâr payı={p['profit_share_rate']}"
            f" | Kâr payı metni={clean(p['profit_share_rate_text']) or None}"
        )

        amount_rules = con.execute(
            """
            SELECT
                min_amount,
                max_amount,
                min_maturity_months,
                max_maturity_months,
                rule_text
            FROM live_product_amount_maturity_rules
            WHERE product_id = ?
            ORDER BY
                COALESCE(min_amount, -1),
                COALESCE(max_amount, 999999999999),
                COALESCE(max_maturity_months, 9999)
            """,
            (pid,),
        ).fetchall()

        if amount_rules:
            print("Tutar/Vade Kuralları:")
            for row in amount_rules:
                print(
                    "  - "
                    f"{row['min_amount']} → {row['max_amount']} TL"
                    f" | {row['min_maturity_months']} → "
                    f"{row['max_maturity_months']} ay"
                )
                if clean(row["rule_text"]):
                    print(
                        "    Kaynak:",
                        clean(row["rule_text"])[:420],
                    )
        else:
            print("Tutar/Vade Kuralları: yok")

        offer_rules = con.execute(
            """
            SELECT *
            FROM live_product_offer_rules
            WHERE product_id = ?
            ORDER BY rowid
            """,
            (pid,),
        ).fetchall()

        if offer_rules:
            print("Ürüne Özel Koşullar:")
            for row in offer_rules:
                print("  -", dict(row))
        else:
            print("Ürüne Özel Koşullar: yok")

        pricing = con.execute(
            """
            SELECT *
            FROM live_product_pricing_tiers
            WHERE product_id = ?
            ORDER BY rowid
            """,
            (pid,),
        ).fetchall()

        if pricing:
            print("Fiyatlama:")
            for row in pricing[:15]:
                print("  -", dict(row))
            if len(pricing) > 15:
                print(f"  ... toplam {len(pricing)} kayıt")
        else:
            print("Fiyatlama: yok")

        features = feature_map.get(pid, [])

        if features:
            print("Nitel:")
            for row in features:
                print(
                    f"  - {clean(row['feature_label'])}: "
                    f"{clean(row['feature_value'])}"
                )
                evidence = clean(row["source_text"])
                if evidence:
                    print(
                        "    Kaynak dayanağı:",
                        evidence[:420],
                    )
                else:
                    print(
                        "    UYARI: Kaynak dayanağı boş."
                    )
                    warning_count += 1
        else:
            print("Nitel: yok")

        # Basic consistency signals.
        max_amount = p["maximum_financing_amount"]
        max_maturity = p["maximum_maturity_months"]

        if max_amount is None and not amount_rules:
            print(
                "UYARI: Ana tutar limiti ve tutar kuralı yok."
            )
            warning_count += 1

        if max_maturity is None and not amount_rules:
            print(
                "UYARI: Ana vade limiti ve vade kuralı yok."
            )
            warning_count += 1

        # Show numeric snippets to detect subsection contamination.
        source = clean(p["clean_text"])
        if source:
            terms = [
                "36 ay",
                "24 ay",
                "18 ay",
                "12 ay",
                "250.000",
                "125.000",
                "70.000",
                "50.000",
                "vade",
                "tutar",
                "taksit",
                "kâr payı",
                "kar payı",
            ]

            lower = source.casefold()
            snippets = []

            for term in terms:
                pos = 0
                while True:
                    idx = lower.find(term.casefold(), pos)
                    if idx == -1:
                        break

                    s = max(0, idx - 160)
                    e = min(
                        len(source),
                        idx + len(term) + 210,
                    )
                    snippet = clean(source[s:e])

                    if snippet not in snippets:
                        snippets.append(snippet)

                    pos = idx + len(term)

            if snippets:
                print("Kaynakta Sayısal Bağlam:")
                for snippet in snippets[:12]:
                    print("  •", snippet)

        print()

    print("=" * 110)
    print("ÖZET")
    print("=" * 110)
    print("İhtiyaç Finansmanı ürün:", len(products))
    print("Audit uyarısı:", warning_count)
    print()
    print(
        "Not: Uyarı sayısı yalnız kalite sinyalidir. "
        "Kaynakta gerçekten tutar/vade yayımlanmamışsa "
        "bu otomatik olarak veri hatası anlamına gelmez."
    )

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
