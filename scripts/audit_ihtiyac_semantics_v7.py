from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "campaigns.db"
DASHBOARD = PROJECT_ROOT / "pages" / "4_Finansman_Karşılaştırması.py"


def product(con: sqlite3.Connection, bank: str, name: str):
    return con.execute(
        """
        SELECT d.product_id,d.minimum_financing_amount,d.maximum_financing_amount,
               d.maximum_maturity_months
        FROM live_standard_product_details d
        JOIN live_campaigns c ON c.id=d.product_id
        WHERE c.is_current=1 AND c.record_kind='standard_product'
          AND d.bank_name=? AND d.product_name=?
        """,
        (bank, name),
    ).fetchone()


def main() -> int:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    warnings: list[str] = []

    print("=" * 88)
    print("İHTİYAÇ FİNANSMANI — SEMANTİK / UI AUDIT V7")
    print("=" * 88)

    jet = product(con, "Albaraka Türk", "Jet Finansman")
    if not jet:
        warnings.append("Jet Finansman bulunamadı")
    else:
        bands = con.execute(
            "SELECT min_amount,max_amount,max_maturity_months FROM live_product_amount_maturity_rules WHERE product_id=? ORDER BY COALESCE(min_amount,-1)",
            (jet["product_id"],),
        ).fetchall()
        actual = {(r[0], r[1], r[2]) for r in bands}
        expected = {
            (None, 50000.0, 36),
            (50000.0, 100000.0, 24),
            (100000.0, None, 12),
        }
        print("Jet limit:", jet["minimum_financing_amount"], "-", jet["maximum_financing_amount"])
        print("Jet genel vade bantları:", sorted(actual, key=lambda x: (-1 if x[0] is None else x[0])))
        if jet["minimum_financing_amount"] != 1000.0 or jet["maximum_financing_amount"] != 60000.0:
            warnings.append("Jet ürün limiti 1.000-60.000 TL değil")
        if not expected.issubset(actual):
            warnings.append("Jet 36/24/12 genel vade bantları eksik")

    pratik = product(con, "Albaraka Türk", "Pratik Finansman Kart")
    if not pratik:
        warnings.append("Pratik Finansman Kart bulunamadı")
    else:
        repayment = con.execute(
            "SELECT feature_value FROM live_product_features WHERE product_id=? AND feature_key='repayment_structure'",
            (pratik["product_id"],),
        ).fetchone()
        repayment_text = str(repayment[0] if repayment else "")
        print("Pratik ödeme/kullanım:", repayment_text or "YOK")
        if "İlk taksit 2 ay sonraya otomatik atanır" not in repayment_text:
            warnings.append("Pratik ilk taksit 2 ay bilgisi eksik")
        if "toplamda 3 aya kadar ötelenebilir" not in repayment_text:
            warnings.append("Pratik toplam 3 aya kadar öteleme bilgisi eksik")

    extra = product(con, "Türkiye Finans", "eXtra Limit")
    if not extra:
        warnings.append("eXtra Limit bulunamadı")
    else:
        print("eXtra maksimum limit:", extra["maximum_financing_amount"])
        if extra["maximum_financing_amount"] != 120000.0:
            warnings.append("eXtra maksimum limit 120.000 TL değil")
        if extra["minimum_financing_amount"] is not None:
            warnings.append("eXtra 100 TL yanlışlıkla minimum finansman tutarı olmuş")

        pricing = con.execute(
            "SELECT maturity_months,profit_share_rate,allocation_fee_rate FROM live_product_pricing_tiers WHERE product_id=? ORDER BY maturity_months",
            (extra["product_id"],),
        ).fetchall()
        actual_pricing = {(r[0], r[1], r[2]) for r in pricing}
        expected_pricing = {
            (3, 4.29, 0.5),
            (12, 4.19, 0.5),
            (24, 4.14, 0.5),
            (36, 4.09, 0.5),
        }
        print("eXtra fiyatlama:", sorted(actual_pricing))
        if not expected_pricing.issubset(actual_pricing):
            warnings.append("eXtra 3/12/24/36 ay kâr payı tablosu eksik")

        cats = con.execute(
            "SELECT category_key,min_amount,max_amount,max_installments FROM live_product_category_rules WHERE product_id=?",
            (extra["product_id"],),
        ).fetchall()
        actual_cats = {(r[0], r[1], r[2], r[3]) for r in cats}
        if ("bilgisayar", None, None, 12) not in actual_cats:
            warnings.append("eXtra Bilgisayar => 12 taksit kuralı eksik")

        repayment = con.execute(
            "SELECT feature_value FROM live_product_features WHERE product_id=? AND feature_key='repayment_structure'",
            (extra["product_id"],),
        ).fetchone()
        repayment_text = str(repayment[0] if repayment else "")
        print("eXtra ödeme/kullanım:", repayment_text or "YOK")
        for expected in (
            "Döner limit",
            "standart taksit sayısına otomatik bölünür",
            "limit yeniden kullanıma açılır",
        ):
            if expected.casefold() not in repayment_text.casefold():
                warnings.append(f"eXtra ödeme/kullanım eksik: {expected}")

        offers = con.execute(
            "SELECT condition_text FROM live_product_offer_rules WHERE product_id=?",
            (extra["product_id"],),
        ).fetchall()
        offer_text = " | ".join(str(r[0] or "") for r in offers)
        if "Minimum taksitlendirme tutarı 100 TL" not in offer_text:
            warnings.append("eXtra 100 TL minimum taksitlendirme koşulu eksik")

    dash = DASHBOARD.read_text(encoding="utf-8")
    for token in (
        '"Genel Vade / Vade Bantları"',
        '"Seçili Kategori Taksit Sınırı"',
        "ay: {rate_text",
    ):
        if token not in dash:
            warnings.append(f"Dashboard V7 semantik ayrımı eksik: {token}")

    print("Uyarı:", len(warnings))
    for warning in warnings:
        print(" -", warning)
    print("SONUÇ:", "OK" if not warnings else "KONTROL GEREKİYOR")
    con.close()
    return 0 if not warnings else 1


if __name__ == "__main__":
    raise SystemExit(main())
