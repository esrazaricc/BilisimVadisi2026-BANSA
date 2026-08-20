from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "campaigns.db"

ELUS_URL = "https://www.kuveytturk.com.tr/isim-icin/tarim-bankaciligi/elektronik-urun-senedi-elus-teminatli-finansman"
ELUS_NAME = "Elektronik Ürün Senedi (ELÜS) Teminatlı Finansman"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def product_id(con: sqlite3.Connection, bank: str, name: str, scope: str | None = None) -> int | None:
    sql = """
        SELECT c.id
        FROM live_campaigns c
        JOIN live_standard_product_details d ON d.product_id=c.id
        WHERE c.bank_name=? AND d.product_name=? AND c.is_current=1
    """
    params: list[object] = [bank, name]
    if scope:
        sql += " AND d.scope=?"
        params.append(scope)
    sql += " ORDER BY c.id DESC LIMIT 1"
    row = con.execute(sql, tuple(params)).fetchone()
    return int(row[0]) if row else None


def set_feature(con: sqlite3.Connection, pid: int, key: str, label: str, value: str | None, source_text: str) -> None:
    con.execute("DELETE FROM live_product_features WHERE product_id=? AND feature_key=?", (pid, key))
    if value is None:
        return
    con.execute(
        """
        INSERT INTO live_product_features(product_id,feature_key,feature_label,feature_value,source_text,extraction_method,updated_at)
        VALUES (?,?,?,?,?,'verified_manual_override',?)
        """,
        (pid, key, label, value, source_text, now_iso()),
    )


def set_core_values(con: sqlite3.Connection, pid: int, **values: object) -> None:
    allowed = {
        "source_page", "maximum_financing_ratio", "maximum_maturity_months",
        "minimum_financing_amount", "maximum_financing_amount",
        "profit_share_rate", "profit_share_rate_text", "interest_free", "interest_free_text",
    }
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"Desteklenmeyen core alanlar: {sorted(unknown)}")
    if not values:
        return
    assignments = ", ".join(f"{key}=?" for key in values)
    con.execute(
        f"UPDATE live_standard_product_details SET {assignments} WHERE product_id=?",
        tuple(values.values()) + (pid,),
    )
    if "source_page" in values and values["source_page"]:
        con.execute("UPDATE live_campaigns SET source_url=?, updated_at=? WHERE id=?", (values["source_page"], now_iso(), pid))


def ensure_elus_product(con: sqlite3.Connection) -> int:
    existing = product_id(con, "Kuveyt Türk", ELUS_NAME)
    if existing:
        return existing

    text = (
        "ELÜS Teminatlı Finansman tarım sektöründe faaliyet gösteren müşterilerin, "
        "lisanslı depolardaki ürünleri karşılığında oluşturulan Elektronik Ürün Senedi'ni "
        "teminat vererek finansman kullanmasına yöneliktir. Resmî sayfada ELÜS değerinin "
        "%100'ü oranında teminatla finansmandan yararlanılabildiği ve başvurunun şubeden "
        "yapıldığı belirtilmektedir."
    )
    ts = now_iso()
    cur = con.execute(
        """
        INSERT INTO live_campaigns(
            bank_name,source_url,source_group,title,clean_text,content_hash,
            current_status,listing_status,fetch_status,first_seen_at,last_seen_at,last_checked_at,
            is_current,created_at,updated_at,record_kind,campaign_category,comparison_eligible,
            classification_confidence,classification_reason
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "Kuveyt Türk", ELUS_URL, "Tarım Finansmanı", ELUS_NAME, text,
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "active", "active", "verified_manual", ts, ts, ts, 1, ts, ts,
            "standard_product", "standard_product", 1, 1.0,
            "Resmî Kuveyt Türk Tarım Bankacılığı ürün sayfasından doğrulandı.",
        ),
    )
    pid = int(cur.lastrowid)
    empty_rules = json.dumps(
        {"amount_maturity_rules": [], "category_rules": [], "fee_rules": [], "offer_rules": [], "pricing_tiers": [], "display_metadata": {}},
        ensure_ascii=False,
        sort_keys=True,
    )
    con.execute(
        """
        INSERT INTO live_standard_product_details(
            product_id,bank_name,product_family_key,product_family,product_name,scope,source_page,
            checked_at,extracted_at,finance_rules_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (pid, "Kuveyt Türk", "tarim_finansmani", "Tarım Finansmanı", ELUS_NAME, "ticari", ELUS_URL, ts, ts, empty_rules),
    )
    set_feature(con, pid, "target_segment", "Hedef Kitle", "Ticari · Çiftçiler", "Tarım sektöründe faaliyet gösteren Kuveyt Türk müşterileri yararlanabilir.")
    set_feature(con, pid, "usage_purpose", "Kullanım Amacı", "ELÜS teminatıyla tarım sektöründeki nakit ihtiyacının karşılanması", "ELÜS teminatıyla nakit ihtiyacının karşılanmasına yönelik resmî ürün açıklaması.")
    set_feature(con, pid, "security_type", "Teminat / Güvence", "ELÜS · %100 teminat", "Resmî ürün sayfasında ELÜS değerinin %100'ü oranında teminatla yararlanılabildiği belirtilir.")
    set_feature(con, pid, "application_channel", "Başvuru / Kanal", "Şube", "Başvuru en yakın Kuveyt Türk şubesi aracılığıyla yapılır.")
    return pid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    changed = 0
    with con:
        # Albaraka Jet: ürün limitini aşan genel vade bandı nitel özetinden de çıkarılır.
        pid = product_id(con, "Albaraka Türk", "Jet Finansman")
        if pid:
            set_core_values(con, pid, source_page="https://www.albaraka.com.tr/tr/bireysel/finansmanlar/ihtiyac/jet-finansman")
            set_feature(
                con, pid, "repayment_structure", "Ödeme / Kullanım Yapısı",
                "1.000–50.000 TL → 36 ay · 50.001–60.000 TL → 24 ay · İlk taksit en geç 45 gün sonra",
                "Resmî Jet Finansman ürün limiti 1.000–60.000 TL ile resmî vade bantlarının kesişimi; ilk taksit en geç 45 gün sonra.",
            )
            changed += 1

        # Hac/Umre: 125/250 bin TL yalnız vade bandıdır; ürün sayfası da
        # exact kaynağa bağlanır.
        pid = product_id(con, "Albaraka Türk", "Hac ve Umre Finansmanı", "bireysel")
        if pid:
            set_core_values(con, pid, source_page="https://www.albaraka.com.tr/tr/bireysel/finansmanlar/ihtiyac/hac-ve-umre-finansmani")
            changed += 1

        # Doğrulanmış standart taşıt sayfaları exact ürün URL'sine bağlanır.
        for name, url in (
            ("Dijital Araç Finansmanı", "https://www.albaraka.com.tr/tr/bireysel/finansmanlar/tasit-finansmani/dijital-arac-finansmani"),
            ("Taşıt Finansmanı", "https://www.albaraka.com.tr/tr/bireysel/finansmanlar/tasit-finansmani/tasit-finansmani"),
        ):
            pid = product_id(con, "Albaraka Türk", name, "bireysel")
            if pid:
                set_core_values(con, pid, source_page=url)
                changed += 1

        # Jet Ticari: karar verdiren ödeme bilgisi ana tabloya taşınır.
        pid = product_id(con, "Albaraka Türk", "Jet Ticari Finansman")
        if pid:
            set_feature(
                con, pid, "repayment_structure", "Ödeme / Kullanım Yapısı",
                "İlk taksit finansman kullandırımından azami 60 gün sonra seçilebilir",
                "Resmî Jet Ticari Finansman ürün detayları.",
            )
            changed += 1

        # Kuveyt genel tarım ürünü ELÜS değildir.
        pid = product_id(con, "Kuveyt Türk", "Tarım ve Hayvancılık Finansmanı")
        if pid:
            set_core_values(con, pid, source_page="https://www.kuveytturk.com.tr/isim-icin/tarim-bankaciligi/tarim-ve-hayvancilik-finansmani")
            set_feature(
                con, pid, "usage_purpose", "Kullanım Amacı",
                "Tarım ve hayvancılık faaliyetlerinde mal/hizmet, işletme ve yatırım finansmanı",
                "Resmî ürün sayfası mal/hizmet alımı ile taksitli ticari ve yatırım finansmanını açıklar.",
            )
            set_feature(
                con, pid, "repayment_structure", "Ödeme / Kullanım Yapısı",
                "Nakit akışına / hasat dönemine uygun esnek ödeme",
                "Resmî ürün sayfası esnek geri ödeme ve alt ürünlerde hasat dönemine uygun ödeme seçeneklerini açıklar.",
            )
            set_feature(con, pid, "currency", "Para Birimi", "TL / USD / EUR", "Resmî ürün sayfasında TL, Dolar ve Euro cinsinden finansman belirtilir.")
            set_feature(con, pid, "security_type", "Teminat / Güvence", None, "ELÜS teminatı genel Tarım ve Hayvancılık Finansmanı'na ait değildir.")
            set_feature(con, pid, "application_channel", "Başvuru / Kanal", "Şube · Web ön başvuru", "Resmî ürün sayfasında şube başvurusu ve internet sitesi üzerinden ön başvuru belirtilir.")
            changed += 1

        # Kuveyt Türk LC Waikiki: ürünün resmî karar alanlarını doğru sütunlara taşı.
        pid = product_id(con, "Kuveyt Türk", "LC Waikiki Alışveriş Finansmanı", "bireysel")
        if pid:
            set_core_values(con, pid, source_page="https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/alisveris-finansmanlari/lc-waikiki-alisveris-finansmani")
            set_feature(con, pid, "application_channel", "Başvuru / Kanal", "LC Waikiki uygulaması / web sitesi", "Resmî ürün sayfasında sepet ödeme adımında LC Waikiki uygulaması ve web sitesi belirtilir.")
            set_feature(con, pid, "cost_advantage", "Maliyet / Avantaj", "5.000 TL'ye kadar 3 ay vade farksız", "Resmî ürün sayfasında 5.000 TL'ye kadar 3 ay vade farksız kullanım belirtilir.")
            changed += 1

        # Türkiye Finans ürün-özel vade/limit düzeltmelerini exact kaynaklara bağla.
        pid = product_id(con, "Türkiye Finans", "Trendyol Alışveriş Finansmanı", "bireysel")
        if pid:
            set_core_values(con, pid, source_page="https://www.turkiyefinans.com.tr/tr-tr/bireysel/hizli-finansman/sayfalar/trendyol-alisveris-finansmani.aspx")
            changed += 1

        pid = product_id(con, "Türkiye Finans", "İhtiyaç Finansmanı (İhtiyaç Kredisi)*", "bireysel")
        if pid:
            set_core_values(con, pid, source_page="https://www.turkiyefinans.com.tr/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/ihtiyac-finansmani.aspx")
            changed += 1

        pid = product_id(con, "Türkiye Finans", "Dijital Taşıt Finansmanı", "bireysel")
        if pid:
            set_core_values(con, pid, source_page="https://www.turkiyefinans.com.tr/tr-tr/bireysel/tasit-finansmani/sayfalar/dijital-tasit-finansmani.aspx")
            changed += 1

        pid = product_id(con, "Kuveyt Türk", "Araç Finansmanı", "bireysel")
        if pid:
            set_core_values(con, pid, source_page="https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/arac-finansmanlari/arac-finansmani")
            changed += 1

        # Kuveyt Türk akreditif: generic 'işletme finansman ihtiyacı' yerine
        # ürünün gerçek gayri nakdi/dış ticaret işlevi gösterilir.
        pid = product_id(con, "Kuveyt Türk", "Akreditifler", "ticari")
        if pid:
            set_core_values(con, pid, source_page="https://www.kuveytturk.com.tr/isim-icin/finansman-urunleri/gayri-nakdi-finansman/akreditifler")
            set_feature(con, pid, "usage_purpose", "Kullanım Amacı", "Uluslararası ticarette belgelerin ibrazına bağlı şartlı banka ödeme taahhüdü", "Resmî akreditif ürün tanımı ve ithalat akreditif ödeme açıklaması.")
            set_feature(con, pid, "transaction_structure", "İşlem / Finansman Yapısı", "Akreditif · şartlı banka finansmanı", "Resmî sayfada akreditif şartlı banka finansmanı olarak tanımlanır.")
            set_feature(con, pid, "application_channel", "Başvuru / Kanal", "İnternet Şubesi", "Resmî sayfa akreditif başvuru ve ithalat ödeme işlemlerinin İnternet Şubesi üzerinden yapılabildiğini belirtir.")
            changed += 1

        # Leasing: Dış Ticaret Evet/Hayır yerine karar verdiren varlık, vade,
        # finansman oranı, para birimi ve koşullu KDV yapısı gösterilir.
        pid = product_id(con, "Albaraka Türk", "Leasing - Finansal Kiralama", "ticari")
        if pid:
            set_core_values(con, pid, source_page="https://www.albaraka.com.tr/tr/kobi/finansmanlar/leasing-finansal-kiralama", maximum_financing_ratio=100.0)
            set_feature(con, pid, "usage_purpose", "Kullanım Amacı", "İş yatırımı, teknoloji, makine ve ekipman finansmanı", "Resmî Albaraka leasing ürün açıklaması.")
            set_feature(con, pid, "repayment_structure", "Ödeme / Kullanım Yapısı", "Nakit akışına uygun esnek geri ödeme · sözleşme boyunca sabit kira", "Resmî ürün sayfasında esnek geri ödeme ve sabit kira açıklanır.")
            set_feature(con, pid, "currency", "Para Birimi", "TL / USD / EUR", "Resmî ürün sayfasında TL ve döviz (USD/EUR) ile borçlanma imkânı belirtilir.")
            set_feature(con, pid, "cost_advantage", "Maliyet / Avantaj", "%1 KDV imkânı · resmî KDV tebliği koşullarına bağlı", "Resmî ürün sayfası leasinge özgü %1 KDV imkânını KDV Tebligatı referansıyla belirtir.")
            set_feature(con, pid, "application_channel", "Başvuru / Kanal", "Şube", "Resmî ürün sayfası başvuru için Albaraka Türk şubelerine yönlendirir.")
            changed += 1

        pid = product_id(con, "Kuveyt Türk", "Leasing", "ticari")
        if pid:
            set_core_values(con, pid, source_page="https://www.kuveytturk.com.tr/isim-icin/leasing/leasing-sureci-ve-hesaplama-araci", maximum_financing_ratio=100.0)
            set_feature(con, pid, "usage_purpose", "Kullanım Amacı", "Yatırım malı niteliğindeki taşınır/taşınmaz varlıkların finansal kiralama ile edinimi", "Resmî leasing SSS ve süreç sayfaları yatırım mallarını leasing konusu olarak açıklar.")
            set_feature(con, pid, "repayment_structure", "Ödeme / Kullanım Yapısı", "Orta/uzun vadeli esnek kira ödeme planı · sözleşme boyunca sabit kira imkânı", "Resmî Leasing SSS sayfasındaki faydalar.")
            set_feature(con, pid, "cost_advantage", "Maliyet / Avantaj", "KDV varlık/GTİP koşuluna göre %1, %10 veya %20 · 2. elde KDV avantajı yok", "Resmî Kuveyt Türk KDV tablosu ve Leasing SSS; tek bir KDV oranı genellenmez.")
            set_feature(con, pid, "application_channel", "Başvuru / Kanal", "Şube", "Resmî leasing süreç sayfasında başvurunun Kuveyt Türk şubeleri aracılığıyla yapılabileceği belirtilir.")
            set_feature(con, pid, "foreign_trade", "Dış Ticaret", None, "Leasing ana karşılaştırmasında dış ticaret evet/hayır karar metriği değildir.")
            changed += 1

        pid = product_id(con, "Türkiye Finans", "Leasing", "ticari")
        if pid:
            set_core_values(con, pid, source_page="https://www.turkiyefinans.com.tr/tr-tr/ticari/nakdi-finansman/Sayfalar/leasing.aspx", maximum_financing_ratio=100.0, maximum_maturity_months=60)
            set_feature(con, pid, "usage_purpose", "Kullanım Amacı", "Taşınır/taşınmaz yatırım malları ve sabit kıymetlerin finansal kiralama ile edinimi", "Resmî Türkiye Finans Leasing ürün sayfası.")
            set_feature(con, pid, "repayment_structure", "Ödeme / Kullanım Yapısı", "60 aya kadar · nakit akışına uygun esnek ödeme", "Resmî ürün sayfasında 60 aya varan vade ve esnek geri ödeme açıklanır.")
            set_feature(con, pid, "cost_advantage", "Maliyet / Avantaj", "%1 KDV yalnız istisna/uygun sabit kıymetlerde · koşula bağlı", "Resmî ürün sayfası %1 KDV avantajını istisna kapsamındaki sabit kıymetler için belirtir.")
            set_feature(con, pid, "application_channel", "Başvuru / Kanal", "Şube / İnternet sitesi", "Resmî ürün sayfası leasing başvurusunun şube veya internet sitesi üzerinden yapılabildiğini belirtir.")
            set_feature(con, pid, "foreign_trade", "Dış Ticaret", None, "Leasing ana karşılaştırmasında dış ticaret evet/hayır karar metriği değildir.")
            changed += 1

        # Ticari Çatı GES: tek başına kaynak satırı değil, doğrulanmış karar
        # alanlarıyla anlamlı bir ürün karşılaştırması olsun.
        pid = product_id(con, "Kuveyt Türk", "Çatı GES Finansmanı", "ticari")
        if pid:
            set_core_values(con, pid, source_page="https://www.kuveytturk.com.tr/isim-icin/finansman-urunleri/cati-ges-finansmani")
            set_feature(con, pid, "usage_purpose", "Kullanım Amacı", "İşletmenin öz tüketimi için çatı güneş enerjisi santrali yatırımı", "Resmî Çatı GES Finansmanı ürün tanımı.")
            set_feature(con, pid, "transaction_structure", "İşlem / Finansman Yapısı", "Çatı GES yatırım finansmanı", "Resmî ürün adı ve kullanım amacı.")
            set_feature(con, pid, "repayment_structure", "Ödeme / Kullanım Yapısı", "Elektrik faturası ve proje yapısına uyumlu taksitler", "Resmî ürün sayfasındaki avantaj açıklaması.")
            set_feature(con, pid, "application_channel", "Başvuru / Kanal", "Şube", "Resmî ürün sayfasında başvuru için en yakın Kuveyt Türk şubesi belirtilir.")
            changed += 1

        elus_pid = ensure_elus_product(con)
        set_feature(con, elus_pid, "target_segment", "Hedef Kitle", "Ticari · Çiftçiler", "Tarım sektöründe faaliyet gösteren Kuveyt Türk müşterileri yararlanabilir.")
        set_feature(con, elus_pid, "usage_purpose", "Kullanım Amacı", "ELÜS teminatıyla tarım sektöründeki nakit ihtiyacının karşılanması", "Resmî ürün sayfası ELÜS teminatıyla nakit ihtiyacının karşılanmasını açıklar.")
        set_feature(con, elus_pid, "transaction_structure", "Finansman Yapısı", "ELÜS teminatlı finansman", "Resmî ürün adı ve ürün açıklaması.")
        set_feature(con, elus_pid, "security_type", "Teminat / Güvence", "ELÜS · %100 teminat", "Resmî ürün sayfasında ELÜS değerinin %100'ü oranında teminatla yararlanılabildiği belirtilir.")
        set_feature(con, elus_pid, "application_channel", "Başvuru / Kanal", "Şube", "Başvuru en yakın Kuveyt Türk şubesi aracılığıyla yapılır.")
        changed += 1

    con.close()
    print(f"Finansman semantik düzeltmeleri V3 uygulandı: {changed} ürün/grup güncellendi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
