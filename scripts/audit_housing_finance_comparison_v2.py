from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB = PROJECT_ROOT / "data" / "campaigns.db"
PAGE = PROJECT_ROOT / "pages" / "4_Finansman_Karşılaştırması.py"
CONFIG = PROJECT_ROOT / "config" / "standard_product_sources.json"

EXPECTED_HOUSING = {
    ("Albaraka Türk", "Konut Finansmanı"),
    ("Dünya Katılım", "Konut Finansmanı"),
    ("Kuveyt Türk", "Gurbetten Sılaya Gayrimenkul Finansmanı"),
    ("Kuveyt Türk", "Konut Finansmanı"),
    ("Kuveyt Türk", "Yeşil Konut Finansmanı"),
    ("Kuveyt Türk", "İlk Evim Konut Finansmanı"),
    ("Türkiye Finans", "Konut Finansmanı (Konut Kredisi)"),
}

RECLASS = {
    ("Kuveyt Türk", "2B Finansmanı"): ("arsa_finansmani", "Arsa Finansmanı"),
    ("Kuveyt Türk", "Arsa Finansmanı"): ("arsa_finansmani", "Arsa Finansmanı"),
    ("Kuveyt Türk", "İş Yeri Finansmanı"): ("isyeri_finansmani", "İş Yeri Finansmanı"),
}

checks: list[tuple[bool, str]] = []


def check(condition: bool, label: str) -> None:
    checks.append((bool(condition), label))
    print(("PASS" if condition else "FAIL") + " | " + label)


def norm(value: object) -> str:
    return str(value or "").strip().rstrip("*").strip()


def sqlite_audit() -> None:
    if not DB.exists():
        check(False, f"SQLite mevcut: {DB}")
        return

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """SELECT product_id,bank_name,product_family_key,product_family,
                      product_name,maximum_maturity_months,maximum_financing_ratio,
                      profit_share_rate,profit_share_rate_text,
                      housing_finance_rules_json
               FROM live_standard_product_details"""
        ).fetchall()

        actual_housing = {
            (r["bank_name"], norm(r["product_name"]))
            for r in rows
            if r["product_family"] == "Konut Finansmanı"
        }
        check(
            actual_housing == EXPECTED_HOUSING,
            "Konut ailesinde yalnız gerçek konut ürünleri var",
        )

        by_key = {
            (r["bank_name"], norm(r["product_name"])): r
            for r in rows
        }
        for key, expected_family in RECLASS.items():
            row = by_key.get(key)
            check(row is not None, f"Ürün mevcut: {key[1]}")
            if row:
                check(
                    (row["product_family_key"], row["product_family"]) == expected_family,
                    f"{key[1]} doğru ailede: {expected_family[1]}",
                )

        tf = by_key[("Türkiye Finans", "Konut Finansmanı (Konut Kredisi)")]
        tf_id = int(tf["product_id"])
        tf_fees = con.execute(
            """SELECT fee_type,fee_label,waived,amount,rate,note
               FROM live_product_fee_rules WHERE product_id=?""",
            (tf_id,),
        ).fetchall()
        fee_types = {r["fee_type"] for r in tf_fees}
        check(
            {"allocation", "appraisal", "mortgage_establishment"}.issubset(fee_types),
            "Türkiye Finans tahsis + ekspertiz + ipotek ücretleri mevcut",
        )
        check(
            not any(r["fee_type"] == "general_expense" and int(r["waived"] or 0) == 1 for r in tf_fees),
            "Türkiye Finans stale 'Masraf: Alınmıyor' kaydı yok",
        )
        allocation = next(r for r in tf_fees if r["fee_type"] == "allocation")
        appraisal = next(r for r in tf_fees if r["fee_type"] == "appraisal")
        mortgage = next(r for r in tf_fees if r["fee_type"] == "mortgage_establishment")
        check(abs(float(allocation["rate"]) - 0.5) < 1e-9, "Türkiye Finans tahsis ücreti %0,50")
        check(abs(float(appraisal["amount"]) - 16500.0) < 1e-9, "Türkiye Finans örnek ekspertiz 16.500 TL")
        check("100.000 tl örnek" in str(appraisal["note"]).casefold(), "Türkiye Finans ekspertiz tutarı örnek senaryoya açıkça bağlı")
        check("değiş" in str(appraisal["note"]).casefold(), "Türkiye Finans ekspertiz değişkenlik notu korunuyor")
        check(abs(float(mortgage["amount"]) - 3000.0) < 1e-9, "Türkiye Finans örnek ipotek 3.000 TL")
        check("100.000 tl örnek" in str(mortgage["note"]).casefold(), "Türkiye Finans ipotek tutarı örnek senaryoya açıkça bağlı")
        check("faturalandır" in str(mortgage["note"]).casefold(), "Türkiye Finans gerçek ipotek maliyeti açıklaması korunuyor")
        check(
            con.execute("SELECT COUNT(*) FROM live_product_pricing_tiers WHERE product_id=?", (tf_id,)).fetchone()[0] == 40,
            "Türkiye Finans 40 fiyatlama satırı korunuyor",
        )
        tf_offer_labels = {
            r[0] for r in con.execute(
                "SELECT rule_label FROM live_product_offer_rules WHERE product_id=?",
                (tf_id,),
            )
        }
        check("Maliyet Tablosu Fiyatlama Koşulu" in tf_offer_labels, "Türkiye Finans paket fiyatlama koşulu mevcut")
        check("Ekspertiz Ücreti ve Bloke Koşulu" in tf_offer_labels, "Türkiye Finans ekspertiz/bloke koşulu mevcut")
        check("Sigorta Primlerinin Değişkenliği" in tf_offer_labels, "Türkiye Finans sigorta değişkenlik koşulu mevcut")

        al = by_key[("Albaraka Türk", "Konut Finansmanı")]
        al_id = int(al["product_id"])
        check(
            con.execute("SELECT COUNT(*) FROM live_product_pricing_tiers WHERE product_id=?", (al_id,)).fetchone()[0] == 0,
            "Albaraka örnek maliyet oranı müşteri fiyatlama tablosuna alınmıyor",
        )
        check(
            al["profit_share_rate"] is None,
            "Albaraka Konut için doğrulanmış güncel tek oran uydurulmuyor",
        )

        dunya = by_key[("Dünya Katılım", "Konut Finansmanı")]
        dunya_id = int(dunya["product_id"])
        dunya_fees = {
            r["fee_type"]: r for r in con.execute(
                "SELECT fee_type,amount,rate,note FROM live_product_fee_rules WHERE product_id=?",
                (dunya_id,),
            )
        }
        check(abs(float(dunya_fees["allocation"]["rate"]) - 0.5) < 1e-9, "Dünya tahsis %0,50")
        check(abs(float(dunya_fees["appraisal"]["amount"]) - 20778.0) < 1e-9, "Dünya ekspertiz asgari 20.778 TL")
        check("asgari" in str(dunya_fees["appraisal"]["note"]).casefold(), "Dünya ekspertiz tutarı asgari olarak işaretli")
        check("ürün sayfasında bu sayısal ücret yayımlanmıyor" in str(dunya_fees["appraisal"]["note"]).casefold(), "Dünya ekspertiz ürün sayfasına yanlış bağlanmıyor")
        check(abs(float(dunya_fees["mortgage_establishment"]["amount"]) - 3000.0) < 1e-9, "Dünya ipotek tesis asgari 3.000 TL")
        check("asgari" in str(dunya_fees["mortgage_establishment"]["note"]).casefold(), "Dünya ipotek tutarı asgari olarak işaretli")
        check("ürün sayfasında bu sayısal ücret yayımlanmıyor" in str(dunya_fees["mortgage_establishment"]["note"]).casefold(), "Dünya ipotek ürün sayfasına yanlış bağlanmıyor")
        check(dunya["maximum_maturity_months"] is None, "Dünya için doğrulanmayan azami vade uydurulmuyor")

        for product_name in (
            "Konut Finansmanı",
            "İlk Evim Konut Finansmanı",
            "Yeşil Konut Finansmanı",
            "Gurbetten Sılaya Gayrimenkul Finansmanı",
        ):
            row = by_key[("Kuveyt Türk", product_name)]
            fees = con.execute(
                "SELECT fee_type,waived,amount,rate,note FROM live_product_fee_rules WHERE product_id=?",
                (int(row["product_id"]),),
            ).fetchall()
            check(
                not any(r["fee_type"] == "general_expense" and int(r["waived"] or 0) == 1 for r in fees),
                f"Kuveyt {product_name}: generic 'Masraf alınmıyor' yok",
            )
            fee_map = {r["fee_type"]: r for r in fees}
            check("allocation" in fee_map, f"Kuveyt {product_name}: tahsis kaydı mevcut")
            check(
                abs(float(fee_map["allocation"]["rate"]) - 0.5) < 1e-9,
                f"Kuveyt {product_name}: tahsis %0,50",
            )
            appraisal_row = fee_map["appraisal"]
            mortgage_row = fee_map["mortgage_establishment"]
            appraisal_note = str(appraisal_row["note"] or "").casefold()
            mortgage_note = str(mortgage_row["note"] or "").casefold()
            check(
                abs(float(appraisal_row["amount"]) - 23645.0) < 1e-9,
                f"Kuveyt {product_name}: ücret tarifesi ekspertiz asgari 23.645 TL",
            )
            check(
                "resmî kaynaklar birbiriyle farklı" in appraisal_note
                and "29.07.2026" in appraisal_note,
                f"Kuveyt {product_name}: ürün sayfası/tarife çelişkisi açıkça işaretli",
            )
            check(
                "23.203" in appraisal_note and "23.645" in appraisal_note,
                f"Kuveyt {product_name}: 23.203 ürün / 23.645 tarife farkı gizlenmiyor",
            )
            check(
                "örnek" not in appraisal_note and "hesaplama aracı" not in appraisal_note,
                f"Kuveyt {product_name}: ekspertiz örnek hesap gibi etiketlenmiyor",
            )
            check(
                abs(float(mortgage_row["amount"]) - 4500.0) < 1e-9,
                f"Kuveyt {product_name}: ücret tarifesi ipotek asgari 4.500 TL",
            )
            check(
                "sayısal bir ipotek tesis tutarı yayımlamaz" in mortgage_note
                and "asgari 4.500" in mortgage_note
                and "gerçek masraf" in mortgage_note,
                f"Kuveyt {product_name}: ürün sayfası sayısal ipotek vermiyor; 4.500 genel tarifeye bağlandı",
            )
            check(
                "örnek" not in mortgage_note and "hesaplama aracı" not in mortgage_note,
                f"Kuveyt {product_name}: ipotek örnek hesap gibi etiketlenmiyor",
            )

        green = by_key[("Kuveyt Türk", "Yeşil Konut Finansmanı")]
        green_labels = {
            r[0] for r in con.execute(
                "SELECT rule_label FROM live_product_offer_rules WHERE product_id=?",
                (int(green["product_id"]),),
            )
        }
        check("Web Kâr Oranı Geçerlilik Sınırı" in green_labels, "Yeşil Konut 3 milyon web fiyatlama sınırı detayda")

    finally:
        con.close()


def config_audit() -> None:
    if not CONFIG.exists():
        check(False, "standard_product_sources.json mevcut")
        return
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    kuveyt = next(b for b in data["banks"] if b.get("name") == "Kuveyt Türk")
    rules = kuveyt.get("family_rules") or []
    idx_housing = next(i for i,r in enumerate(rules) if r.get("family_key") == "konut_finansmani")
    idx_arsa = next(i for i,r in enumerate(rules) if r.get("family_key") == "arsa_finansmani")
    idx_work = next(i for i,r in enumerate(rules) if r.get("family_key") == "isyeri_finansmani")
    check(idx_arsa < idx_housing, "Kuveyt Arsa exact rule generic Konut rule'dan önce")
    check(idx_work < idx_housing, "Kuveyt İş Yeri exact rule generic Konut rule'dan önce")


def page_audit() -> None:
    if not PAGE.exists():
        check(False, "Finansman karşılaştırma sayfası mevcut")
        return
    text = PAGE.read_text(encoding="utf-8")
    for required in (
        '"Kâr Payı / Fiyatlama"',
        '"Azami Vade"',
        '"Finansman Oranı"',
        '"Tahsis Ücreti"',
        '"Ekspertiz Ücreti"',
        '"İpotek Tesis Ücreti"',
        'st.markdown("#### Masraf ve Maliyet Detayı")',
        'st.markdown("#### Fiyatlama ve Önemli Koşullar")',
        'detail_property_value_raw = st.text_input(',
    ):
        check(required in text, f"UI içeriyor: {required[:55]}")

    check(
        '"Ürün Kaynağı"' in text and '"Ücret Kaynağı"' in text,
        "Konut UI ürün kaynağı ve ücret kaynağını ayrı sütunlarda gösteriyor",
    )
    check(
        "Ürün sayfası: asgari 23.203 TL" in text
        and "Ücret tarifesi: asgari 23.645 TL" in text,
        "Kuveyt ekspertiz kaynak çelişkisi ana tabloda iki değerle açık",
    )
    check(
        "Ürün sayfası: maliyet kadar" in text
        and "Ücret tarifesi: asgari 4.500 TL" in text,
        "Kuveyt ipotek ürün/tarife ayrımı ana tabloda açık",
    )

    # V3+ UI artık ana tablo sütunlarını sabit bir housing bloğunda değil,
    # kategoriye özel finance_column_profiles üzerinden seçiyor. Eski exact
    # source-code substring kontrolü yeni mimaride kırılgandı. Konut profilini
    # doğrudan doğrula.
    from src.finance_column_profiles import get_profile

    housing_profile = get_profile("bireysel", "Konut Finansmanı")
    housing_columns = set(housing_profile.preferred_columns)
    for forbidden in (
        "Taksit Sayısı",
        "Finansman Tutarı",
        "Masraf Bilgisi",
        "Gayrimenkul / Ekspertiz Değeri",
        "Orana Göre Finansman Tutarı",
    ):
        check(
            forbidden not in housing_columns,
            f"Konut ana tabloda yok: {forbidden}",
        )

    check(
        "select_main_table_columns(" in text
        and "get_finance_column_profile(" in text,
        "Konut ana tablo kategoriye özel sütun profilini kullanıyor",
    )

    check(
        '("Kuveyt Türk", "2B Finansmanı")' in text
        and '("Kuveyt Türk", "Arsa Finansmanı")' in text
        and '("Kuveyt Türk", "İş Yeri Finansmanı")' in text,
        "UI guard eski DB olsa bile konut dışı Kuveyt ürünlerini gizliyor",
    )
    check(
        'bank_name == "Türkiye Finans"' in text
        and 'Koşullu fiyatlama tablosu · Sigortalı/Sigortasız ve vadeye göre' in text,
        "Türkiye Finans ana tabloda örnek oran yerine koşullu fiyatlama bağlamı gösteriliyor",
    )


def main() -> int:
    print("=" * 88)
    print("BANSA — KONUT FİNANSMANI KARŞILAŞTIRMA AUDIT V2")
    print("=" * 88)
    sqlite_audit()
    config_audit()
    page_audit()
    passed = sum(1 for ok,_ in checks if ok)
    failed = sum(1 for ok,_ in checks if not ok)
    print("\n" + "=" * 88)
    print(f"SONUÇ: PASS={passed} FAIL={failed}")
    print("=" * 88)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
