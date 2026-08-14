from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "campaigns.db"


def rows(connection, table, product_id):
    return connection.execute(
        f"SELECT * FROM {table} WHERE product_id=? ORDER BY COALESCE(min_amount,-1), COALESCE(max_amount,999999999999)",
        (product_id,),
    ).fetchall()


def main() -> int:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    print("=" * 80)
    print("İHTİYAÇ FİNANSMANI — LİMİT / VADE / KATEGORİ AUDIT V6")
    print("=" * 80)

    warnings = []

    extra = con.execute(
        """
        SELECT d.product_id,d.minimum_financing_amount,d.maximum_financing_amount
        FROM live_standard_product_details d
        JOIN live_campaigns c ON c.id=d.product_id
        WHERE c.is_current=1 AND c.record_kind='standard_product'
          AND d.bank_name='Türkiye Finans' AND d.product_name='eXtra Limit'
        """
    ).fetchone()
    if not extra:
        warnings.append("eXtra Limit bulunamadı")
    else:
        print("eXtra Limit maksimum limit:", extra["maximum_financing_amount"])
        print("eXtra Limit minimum finansman:", extra["minimum_financing_amount"])
        if extra["maximum_financing_amount"] != 120000.0:
            warnings.append("eXtra Limit maksimum limit 120.000 TL değil")
        if extra["minimum_financing_amount"] is not None:
            warnings.append("100 TL yanlışlıkla minimum finansman tutarına yazılmış")
        offers = con.execute(
            "SELECT condition_text FROM live_product_offer_rules WHERE product_id=?",
            (extra["product_id"],),
        ).fetchall()
        offer_text = " | ".join(str(r[0] or "") for r in offers)
        print("eXtra Limit özel koşul:", offer_text or "YOK")
        if "Minimum taksitlendirme tutarı 100 TL" not in offer_text:
            warnings.append("eXtra Limit 100 TL minimum taksitlendirme koşulu yok")

    jet = con.execute(
        """
        SELECT d.product_id,d.minimum_financing_amount,d.maximum_financing_amount
        FROM live_standard_product_details d
        JOIN live_campaigns c ON c.id=d.product_id
        WHERE c.is_current=1 AND c.record_kind='standard_product'
          AND d.bank_name='Albaraka Türk' AND d.product_name='Jet Finansman'
        """
    ).fetchone()
    if not jet:
        warnings.append("Jet Finansman bulunamadı")
    else:
        bands = rows(con, "live_product_amount_maturity_rules", jet["product_id"])
        print("Jet Finansman ürün limiti:", jet["minimum_financing_amount"], "-", jet["maximum_financing_amount"])
        print("Jet Finansman bant sayısı:", len(bands))
        for band in bands:
            print(
                " -",
                band["min_amount"],
                band["max_amount"],
                "=>",
                band["max_maturity_months"],
                "ay",
            )
        expected = {
            (None, 50000.0, 36),
            (50000.0, 100000.0, 24),
            (100000.0, None, 12),
        }
        actual = {
            (r["min_amount"], r["max_amount"], r["max_maturity_months"])
            for r in bands
        }
        if not expected.issubset(actual):
            warnings.append("Jet Finansman 36/24/12 tutar-vade bantları eksik")

        jet_categories = con.execute(
            """
            SELECT category_key,min_amount,max_amount,max_installments
            FROM live_product_category_rules
            WHERE product_id=?
            """,
            (jet["product_id"],),
        ).fetchall()
        jet_actual_categories = {
            (r["category_key"], r["min_amount"], r["max_amount"], r["max_installments"])
            for r in jet_categories
        }
        jet_expected_categories = {
            ("cep_telefonu", None, 20000.0, 12),
            ("cep_telefonu", 20000.0, None, 3),
            ("bilgisayar", None, None, 12),
            ("tablet", None, None, 6),
        }
        if not jet_expected_categories.issubset(jet_actual_categories):
            warnings.append("Jet Finansman teknoloji kategori/taksit kuralları eksik")


    pratik = con.execute(
        """
        SELECT d.product_id,d.minimum_financing_amount,d.maximum_financing_amount
        FROM live_standard_product_details d
        JOIN live_campaigns c ON c.id=d.product_id
        WHERE c.is_current=1 AND c.record_kind='standard_product'
          AND d.bank_name='Albaraka Türk' AND d.product_name='Pratik Finansman Kart'
        """
    ).fetchone()
    if not pratik:
        warnings.append("Pratik Finansman Kart bulunamadı")
    else:
        categories = con.execute(
            """
            SELECT category_key,category_label,min_amount,max_amount,max_installments
            FROM live_product_category_rules
            WHERE product_id=?
            ORDER BY category_key, COALESCE(min_amount,-1), COALESCE(max_amount,999999999999)
            """,
            (pratik["product_id"],),
        ).fetchall()
        print("Pratik Finansman Kart kategori kuralı:", len(categories))
        for row in categories:
            print(
                " -", row["category_label"], row["min_amount"], row["max_amount"],
                "=>", row["max_installments"], "taksit"
            )
        actual_categories = {
            (r["category_key"], r["min_amount"], r["max_amount"], r["max_installments"])
            for r in categories
        }
        expected_categories = {
            ("cep_telefonu", None, 20000.0, 12),
            ("cep_telefonu", 20000.0, None, 3),
            ("bilgisayar", None, None, 12),
            ("tablet", None, None, 6),
        }
        if not expected_categories.issubset(actual_categories):
            warnings.append("Pratik Finansman Kart teknoloji kategori/taksit kuralları eksik")

    print("Uyarı:", len(warnings))
    for warning in warnings:
        print(" -", warning)
    print("SONUÇ:", "OK" if not warnings else "KONTROL GEREKİYOR")
    con.close()
    return 0 if not warnings else 1


if __name__ == "__main__":
    raise SystemExit(main())
