from __future__ import annotations

import sqlite3
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
                LIKE '%ticari%'
            AND LOWER(COALESCE(d.product_family, ''))
                NOT LIKE '%gayri%'
        ORDER BY
            c.bank_name,
            d.product_name
        """
    ).fetchall()

    print("=" * 110)
    print("TİCARİ / NAKDİ FİNANSMAN — SAYISAL ALAN AUDIT")
    print("=" * 110)
    print("Ürün:", len(products))
    print()

    numeric_products = 0

    for p in products:
        values = {
            "min_tutar": p["minimum_financing_amount"],
            "max_tutar": p["maximum_financing_amount"],
            "min_vade": p["minimum_maturity_months"],
            "max_vade": p["maximum_maturity_months"],
            "kar_payi": p["profit_share_rate"],
            "kar_payi_text": clean(
                p["profit_share_rate_text"]
            ),
        }

        has_numeric = any(
            v is not None and v != ""
            for v in values.values()
        )

        if not has_numeric:
            continue

        numeric_products += 1

        print("-" * 110)
        print(
            f'{p["bank_name"]} | '
            f'{p["product_family"]} | '
            f'{p["product_name"]}'
        )
        print("Kaynak:", clean(p["source_url"]))

        print(
            "Ana kayıt:",
            " | ".join(
                [
                    f"Min tutar={values['min_tutar']}",
                    f"Max tutar={values['max_tutar']}",
                    f"Min vade={values['min_vade']}",
                    f"Max vade={values['max_vade']}",
                    f"Kâr payı={values['kar_payi']}",
                    f"Kâr payı metni={values['kar_payi_text'] or None}",
                ]
            )
        )

        # Amount / maturity rules
        am = con.execute(
            """
            SELECT *
            FROM live_product_amount_maturity_rules
            WHERE product_id = ?
            ORDER BY
                COALESCE(min_amount, -1),
                COALESCE(max_amount, 999999999999),
                COALESCE(max_maturity_months, 9999)
            """,
            (p["product_id"],),
        ).fetchall()

        if am:
            print("Tutar/Vade kuralları:")
            for row in am:
                print(
                    "  -",
                    dict(row),
                )
        else:
            print("Tutar/Vade kuralları: yok")

        pricing = con.execute(
            """
            SELECT *
            FROM live_product_pricing_tiers
            WHERE product_id = ?
            ORDER BY rowid
            """,
            (p["product_id"],),
        ).fetchall()

        if pricing:
            print("Fiyatlama kademeleri:")
            for row in pricing[:12]:
                print(
                    "  -",
                    dict(row),
                )
            if len(pricing) > 12:
                print(
                    f"  ... toplam {len(pricing)} kademe"
                )
        else:
            print("Fiyatlama kademeleri: yok")

        # Show only clean_text fragments around numeric terms.
        source = clean(p["clean_text"])

        if source:
            terms = [
                "18 ay",
                "12 ay",
                "24 ay",
                "36 ay",
                "48 ay",
                "60 ay",
                "milyon",
                "kâr payı",
                "kar payı",
                "komisyon",
                "vade",
            ]

            lowered = source.casefold()
            hits = []

            for term in terms:
                start = 0

                while True:
                    idx = lowered.find(
                        term.casefold(),
                        start,
                    )

                    if idx == -1:
                        break

                    s = max(0, idx - 180)
                    e = min(
                        len(source),
                        idx + len(term) + 220,
                    )
                    snippet = clean(source[s:e])

                    if snippet not in hits:
                        hits.append(snippet)

                    start = idx + len(term)

            if hits:
                print("Kaynakta sayısal bağlam:")
                for snippet in hits[:10]:
                    print("  •", snippet)
            else:
                print(
                    "Kaynakta sayısal bağlam: "
                    "eşleşen ifade bulunamadı"
                )

        print()

    print("=" * 110)
    print("ÖZET")
    print("=" * 110)
    print("Toplam Ticari/Nakdi ürün:", len(products))
    print("Sayısal ana kaydı bulunan ürün:", numeric_products)
    print()
    print(
        "Amaç: Ana ürün seviyesindeki sayısal alanların "
        "gerçekten genel ürün koşulu mu, yoksa alt varyant/"
        "bölüm koşulu mu olduğunu kaynak metniyle denetlemek."
    )

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
