from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path


DEFAULT_DB = Path("data") / "campaigns.db"


def clean(value) -> str:
    return str(value or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
    )
    parser.add_argument(
        "--bank",
        default="",
    )
    args = parser.parse_args()

    db_path = Path(args.db)

    if not db_path.exists():
        raise SystemExit(
            f"DB bulunamadı: {db_path}"
        )

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    where_bank = ""
    params = []

    if clean(args.bank):
        where_bank = "AND c.bank_name = ?"
        params.append(clean(args.bank))

    products = con.execute(
        f"""
        SELECT
            c.id AS product_id,
            c.bank_name,
            c.source_url,
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
            c.record_kind = 'standard_product'
            AND c.is_current = 1
            AND (
                LOWER(COALESCE(d.product_family, ''))
                    LIKE '%ticari%'
                OR LOWER(COALESCE(d.product_family, ''))
                    LIKE '%nakdi%'
            )
            AND LOWER(COALESCE(d.product_family, ''))
                NOT LIKE '%gayri%'
            {where_bank}
        ORDER BY
            c.bank_name,
            d.product_family,
            d.product_name
        """,
        params,
    ).fetchall()

    if not products:
        print(
            "Ticari/Nakdi ürün bulunamadı."
        )
        con.close()
        return 0

    feature_rows = con.execute(
        """
        SELECT
            product_id,
            feature_key,
            feature_label,
            feature_value,
            source_text,
            extraction_method
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
    print("TİCARİ / NAKDİ FİNANSMAN — NİTEL ÖZELLİK AUDIT")
    print("=" * 110)
    print("Ürün sayısı:", len(products))
    print()

    warning_count = 0

    for product in products:
        product_id = int(product["product_id"])
        rows = feature_map.get(product_id, [])

        print("-" * 110)
        print(
            f'{product["bank_name"]} | '
            f'{product["product_family"]} | '
            f'{product["product_name"]}'
        )
        print(
            "Kaynak:",
            clean(product["source_url"])
            or "Belirtilmedi",
        )

        numeric_parts = []

        if product["minimum_financing_amount"] is not None:
            numeric_parts.append(
                f'Min tutar={product["minimum_financing_amount"]}'
            )

        if product["maximum_financing_amount"] is not None:
            numeric_parts.append(
                f'Max tutar={product["maximum_financing_amount"]}'
            )

        if product["minimum_maturity_months"] is not None:
            numeric_parts.append(
                f'Min vade={product["minimum_maturity_months"]}'
            )

        if product["maximum_maturity_months"] is not None:
            numeric_parts.append(
                f'Max vade={product["maximum_maturity_months"]}'
            )

        if product["profit_share_rate"] is not None:
            numeric_parts.append(
                f'Kâr payı={product["profit_share_rate"]}'
            )
        elif clean(product["profit_share_rate_text"]):
            numeric_parts.append(
                "Kâr payı="
                + clean(product["profit_share_rate_text"])
            )

        print(
            "Sayısal:",
            " | ".join(numeric_parts)
            if numeric_parts
            else "Kaynakta sayısal değer yok / çıkarılmamış",
        )

        if not rows:
            print("Nitel: BELİRTİLMEDİ")
            print(
                "UYARI: Bu ürün için nitel özellik kaydı yok."
            )
            warning_count += 1
            continue

        print("Nitel:")

        purpose_found = False

        for row in rows:
            label = clean(row["feature_label"])
            value = clean(row["feature_value"])
            evidence = clean(row["source_text"])

            if row["feature_key"] == "usage_purpose":
                purpose_found = True

            print(
                f"  - {label}: {value}"
            )

            if evidence:
                print(
                    f"    Kaynak dayanağı: {evidence[:350]}"
                )
            else:
                print(
                    "    UYARI: Kaynak dayanağı boş."
                )
                warning_count += 1

        if not purpose_found:
            print(
                "  UYARI: Kullanım Amacı çıkarılmamış."
            )
            warning_count += 1

    print()
    print("=" * 110)
    print("ÖZET")
    print("=" * 110)
    print("Ürün:", len(products))
    print("Uyarı:", warning_count)
    print()
    print(
        "Not: Uyarı sayısı otomatik kalite sinyalidir; "
        "tek başına ürün verisinin yanlış olduğu anlamına gelmez."
    )

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
