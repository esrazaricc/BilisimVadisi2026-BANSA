from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIG_PATH = ROOT / "config" / "standard_product_sources.json"
BDDK_PATH = ROOT / "config" / "bddk_participation_bank_scope.json"
DB_PATH = ROOT / "data" / "campaigns.db"

REMAINING_BANKS = (
    "Adil Katılım",
    "T.O.M. Katılım",
    "Türkiye Emlak Katılım",
    "Vakıf Katılım",
    "Ziraat Katılım",
)

EXPECTED_BDDK = (
    "Adil Katılım",
    "Albaraka Türk",
    "Dünya Katılım",
    "Hayat Finans",
    "Kuveyt Türk",
    "T.O.M. Katılım",
    "Türkiye Emlak Katılım",
    "Türkiye Finans",
    "Vakıf Katılım",
    "Ziraat Katılım",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _banks_from_config() -> list[dict[str, Any]]:
    payload = _load_json(CONFIG_PATH)
    return list(payload.get("banks", []))


def _bank(rows: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for row in rows:
        if str(row.get("name")) == name:
            return row
    raise AssertionError(f"Config bankası bulunamadı: {name}")


def _exact_paths(bank: dict[str, Any], family_key: str | None = None) -> set[str]:
    paths: set[str] = set()
    for rule in bank.get("family_rules", []):
        if family_key is not None and str(rule.get("family_key")) != family_key:
            continue
        paths.update(str(x) for x in rule.get("exact_paths", []) if str(x).strip())
    return paths


def _family_keys(bank: dict[str, Any]) -> set[str]:
    return {str(rule.get("family_key")) for rule in bank.get("family_rules", [])}


def structural_audit() -> tuple[int, int]:
    rows = _banks_from_config()
    bddk = _load_json(BDDK_PATH)
    # The scope file has historically existed in two simple shapes; support both.
    if isinstance(bddk, dict):
        raw_scope = bddk.get("banks") or bddk.get("bank_names") or bddk.get("scope") or []
    else:
        raw_scope = bddk
    scope_names = []
    for item in raw_scope:
        if isinstance(item, dict):
            scope_names.append(str(item.get("name") or item.get("bank_name") or ""))
        else:
            scope_names.append(str(item))

    passed = failed = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"PASS | STRUCT | {label}")
        else:
            failed += 1
            print(f"FAIL | STRUCT | {label} | {detail}")

    config_names = [str(x.get("name")) for x in rows]
    check(
        "Standart finansman config'i BDDK kapsamındaki 10 bankayı içeriyor",
        tuple(config_names) == EXPECTED_BDDK,
        str(config_names),
    )
    check(
        "BDDK kapsam config'i 10 katılım bankasını içeriyor",
        set(scope_names) == set(EXPECTED_BDDK) and len(set(scope_names)) == 10,
        str(scope_names),
    )
    check(
        "Kalan beş banka standard_product_sources içinde eksiksiz",
        all(name in config_names for name in REMAINING_BANKS),
        str(config_names),
    )

    # Adil: only official generic individual/commercial descriptions, no invented families/metrics.
    adil = _bank(rows, "Adil Katılım")
    embedded = adil.get("embedded_product_pages", [])
    products = embedded[0].get("products", []) if embedded else []
    adil_sig = {
        (str(p.get("product_name")), str(p.get("scope") or embedded[0].get("scope")), str(p.get("product_family_key") or embedded[0].get("product_family_key")))
        for p in products
    } if embedded else set()
    check(
        "Adil yalnız doğrulanmış Bireysel Finansman + Ticari Finansman başlıklarını embed ediyor",
        adil_sig == {
            ("Bireysel Finansman", "bireysel", "ihtiyac_finansmani"),
            ("Ticari Finansman", "ticari", "ticari_finansman"),
        },
        str(adil_sig),
    )
    check(
        "Adil sayfa altındaki ilgisiz bölümler stop heading ile kesiliyor",
        bool(embedded) and {"Katılma Hesapları", "Kurumsal"}.issubset(set(embedded[0].get("stop_headings", []))),
        str(embedded[0].get("stop_headings", []) if embedded else []),
    )

    # TOM: public finance catalog is shopping credit only.
    tom = _bank(rows, "T.O.M. Katılım")
    tom_exact = _exact_paths(tom, "alisveris_finansmani")
    check(
        "T.O.M. üç resmî alışveriş finansmanı URL'siyle entegre",
        tom_exact == {"/veresiye.html", "/taksitle.html", "/magazadan-alisveris-kredisi.html"},
        str(sorted(tom_exact)),
    )
    check(
        "T.O.M. için doğrulanmamış iş/ticari finansman ailesi üretilmiyor",
        _family_keys(tom) == {"alisveris_finansmani"},
        str(_family_keys(tom)),
    )

    # Emlak: retail + business + leasing, explicit TOKİ exclusion, safe embedded extraction.
    emlak = _bank(rows, "Türkiye Emlak Katılım")
    emlak_embedded = emlak.get("embedded_product_pages", [])
    need_page = next((p for p in emlak_embedded if p.get("product_family_key") == "ihtiyac_finansmani"), None)
    housing_page = next((p for p in emlak_embedded if p.get("product_family_key") == "konut_finansmani"), None)
    need_products = list(need_page.get("products", [])) if need_page else []
    check(
        "Emlak İhtiyaç ortak sayfası 16 gerçek alt ürüne ayrılıyor",
        len(need_products) == 16,
        f"count={len(need_products)} names={[p.get('product_name') for p in need_products]}",
    )
    devre = next((p for p in need_products if p.get("product_name") == "Devre Mülk Finansmanı"), None)
    check(
        "Emlak Devre Mülk, İhtiyaç yerine Gayrimenkul karşılaştırmasına map ediliyor",
        bool(devre) and devre.get("product_family_key") == "gayrimenkul_finansmani",
        str(devre),
    )
    check(
        "Emlak ortak ihtiyaç örnek tablosu alt ürünlere sızmaması için stop heading mevcut",
        bool(need_page) and "Örnek İhtiyaç Finansmanı Tablosu" in need_page.get("stop_headings", []),
        str(need_page.get("stop_headings", []) if need_page else []),
    )
    check(
        "Emlak Konut ortak sayfası üç gömülü konut varyantını ayrı ürün yapıyor",
        bool(housing_page) and {p.get("product_name") for p in housing_page.get("products", [])} == {
            "Birlikte Konut Finansmanı", "Çevreci Konut Finansmanı", "Memlekette Konut Finansmanı"
        },
        str([p.get("product_name") for p in housing_page.get("products", [])] if housing_page else []),
    )
    check(
        "Emlak TOKİ işlemleri finansman ürünü olarak discovery'ye alınmıyor",
        "/tr/bireysel/finansmanlar/toki-islemleri" in set(emlak.get("exclude_exact_paths", [])),
        str(emlak.get("exclude_exact_paths", [])),
    )
    check(
        "Emlak bireysel + ticari + leasing kaynak kapsamı var",
        {p.get("scope") for p in emlak.get("listing_pages", [])} == {"bireysel", "ticari"}
        and {"ticari_finansman", "gayri_nakdi_finansman", "leasing"}.issubset(_family_keys(emlak)),
        str(_family_keys(emlak)),
    )

    # Vakif: eight public retail products + all major business finance families.
    vakif = _bank(rows, "Vakıf Katılım")
    vakif_retail = set().union(
        _exact_paths(vakif, "konut_finansmani"),
        _exact_paths(vakif, "arac_finansmani"),
        _exact_paths(vakif, "ihtiyac_finansmani"),
        _exact_paths(vakif, "arsa_finansmani"),
        _exact_paths(vakif, "isyeri_finansmani"),
    )
    check(
        "Vakıf Katılım sekiz resmî bireysel finansman ürününü exact seed ediyor",
        len(vakif_retail) == 8,
        str(sorted(vakif_retail)),
    )
    check(
        "Vakıf Katılım iş/ticari aileleri: ticari + gayri nakdi + tarım + leasing",
        {"ticari_finansman", "gayri_nakdi_finansman", "tarim_finansmani", "leasing"}.issubset(_family_keys(vakif)),
        str(_family_keys(vakif)),
    )

    # Ziraat: retail + commercial + agriculture + leasing roots are all covered.
    ziraat = _bank(rows, "Ziraat Katılım")
    z_urls = [str(p.get("url")) for p in ziraat.get("listing_pages", [])]
    check(
        "Ziraat Katılım bireysel, ticari, tarım ve leasing kaynaklarını ayrı tarıyor",
        any("/bireysel/" in x for x in z_urls)
        and any("/ticari/finansman-urunleri/" in x for x in z_urls)
        and any("/tarim/" in x for x in z_urls)
        and any("/ticari/finansal-kiralama-leasing" in x for x in z_urls),
        str(z_urls),
    )
    check(
        "Ziraat Katılım taksonomisinde konut/taşıt/ihtiyaç + ticari/gayri/tarım/leasing aileleri var",
        {"konut_finansmani", "arac_finansmani", "ihtiyac_finansmani", "ticari_finansman", "gayri_nakdi_finansman", "tarim_finansmani", "leasing"}.issubset(_family_keys(ziraat)),
        str(_family_keys(ziraat)),
    )

    print(f"STRUCTURAL audit: PASS={passed} FAIL={failed}")
    return passed, failed


def sqlite_audit(db_path: Path) -> tuple[int, int]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    passed = failed = 0

    def one(sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        return con.execute(sql, params).fetchone()

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"PASS | SQLITE | {label}")
        else:
            failed += 1
            print(f"FAIL | SQLITE | {label} | {detail}")

    # Every remaining BDDK bank must actually have live standard products after integration.
    for name in REMAINING_BANKS:
        r = one(
            """
            SELECT COUNT(*) n
            FROM live_campaigns c
            JOIN live_standard_product_details d ON d.product_id=c.id
            WHERE c.bank_name=? AND c.record_kind='standard_product' AND c.is_current=1
            """,
            (name,),
        )
        n = int(r["n"] if r else 0)
        check(f"{name}: canlı standart finansman ürünü var", n > 0, f"count={n}")

    # Adil: exactly the two public generic finance definitions; no hallucinated numeric terms.
    rows = con.execute(
        """
        SELECT d.* FROM live_campaigns c
        JOIN live_standard_product_details d ON d.product_id=c.id
        WHERE c.bank_name='Adil Katılım' AND c.record_kind='standard_product' AND c.is_current=1
        ORDER BY d.product_name
        """
    ).fetchall()
    names = {str(r["product_name"]) for r in rows}
    check("Adil: Bireysel Finansman + Ticari Finansman canlı", {"Bireysel Finansman", "Ticari Finansman"}.issubset(names), str(sorted(names)))
    numeric_cols = (
        "minimum_financing_amount", "maximum_financing_amount", "minimum_maturity_months",
        "maximum_maturity_months", "profit_share_rate", "maximum_financing_ratio",
    )
    bad = [dict(r) for r in rows if any(r[col] is not None for col in numeric_cols)]
    check("Adil: resmî sayfada olmayan sayısal limit/vade/oran üretilmemiş", not bad, str(bad[:3]))

    # TOM: three shopping products and no business scope.
    rows = con.execute(
        """
        SELECT d.* FROM live_campaigns c
        JOIN live_standard_product_details d ON d.product_id=c.id
        WHERE c.bank_name='T.O.M. Katılım' AND c.record_kind='standard_product' AND c.is_current=1
        """
    ).fetchall()
    check("T.O.M.: en az üç alışveriş finansmanı ürünü canlı", len(rows) >= 3, f"count={len(rows)} names={[r['product_name'] for r in rows]}")
    check("T.O.M.: kamuya açık katalogdan ticari scope uydurulmamış", all(str(r["scope"]) == "bireysel" for r in rows), str([(r["product_name"], r["scope"]) for r in rows]))
    veresiye = next((r for r in rows if "veresiye" in str(r["product_name"]).casefold() or "/veresiye.html" in str(r["source_page"] or "").casefold()), None)
    check(
        "T.O.M. Veresiye: %3,99 sabit genel oran değil, 'başlayan' minimum olarak gösteriliyor",
        bool(veresiye) and veresiye["profit_share_rate"] is None and "başlayan" in str(veresiye["profit_share_rate_text"] or "").casefold(),
        str(dict(veresiye) if veresiye else None),
    )
    magaza = next((r for r in rows if "mağazadan" in str(r["product_name"]).casefold() or "/magazadan-alisveris-kredisi.html" in str(r["source_page"] or "").casefold()), None)
    check(
        "T.O.M. Mağazadan: 1.000–200.000 TL / 36 ay ürün-özel sınır",
        bool(magaza) and float(magaza["minimum_financing_amount"] or 0) == 1000.0
        and float(magaza["maximum_financing_amount"] or 0) == 200000.0
        and int(magaza["maximum_maturity_months"] or 0) == 36,
        str(dict(magaza) if magaza else None),
    )

    # Emlak: need embedded products, retail + business + leasing, no shared 1.69 leakage.
    rows = con.execute(
        """
        SELECT d.* FROM live_campaigns c
        JOIN live_standard_product_details d ON d.product_id=c.id
        WHERE c.bank_name='Türkiye Emlak Katılım' AND c.record_kind='standard_product' AND c.is_current=1
        """
    ).fetchall()
    check("Emlak: bireysel ve ticari scope ürünleri canlı", {str(r["scope"]) for r in rows} >= {"bireysel", "ticari"}, str(sorted({str(r['scope']) for r in rows})))
    families = {str(r["product_family_key"]) for r in rows}
    check("Emlak: canlı katalogda ticari/gayri nakdi/leasing ailesi var", {"ticari_finansman", "gayri_nakdi_finansman", "leasing"}.issubset(families), str(sorted(families)))
    need_source_rows = [r for r in rows if "/tr/bireysel/finansmanlar/ihtiyac-finansmani" in str(r["source_page"] or "") and str(r["product_name"]) != "İhtiyaç Finansmanı"]
    check("Emlak: ortak ihtiyaç sayfasından en az 16 alt ürün ayrılmış", len(need_source_rows) >= 16, f"count={len(need_source_rows)} names={[r['product_name'] for r in need_source_rows]}")
    bad = [dict(r) for r in need_source_rows if r["profit_share_rate"] is not None]
    check("Emlak: ortak %1,69 örnek tablosu alt ürünlerin güncel oranına sızmıyor", not bad, str([(r['product_name'], r['profit_share_rate']) for r in bad]))
    konut = next((r for r in rows if str(r["product_name"]) == "Konut Finansmanı"), None)
    check(
        "Emlak Konut: yalnız ana açıklamadaki doğrulanmış azami %80 kullanılıyor",
        bool(konut) and float(konut["maximum_financing_ratio"] or 0) == 80.0 and not str(konut["housing_finance_rules_json"] or "").strip(),
        str(dict(konut) if konut else None),
    )

    # Vakif: retail eight and business family coverage; anomalous 150 is suppressed.
    rows = con.execute(
        """
        SELECT d.* FROM live_campaigns c
        JOIN live_standard_product_details d ON d.product_id=c.id
        WHERE c.bank_name='Vakıf Katılım' AND c.record_kind='standard_product' AND c.is_current=1
        """
    ).fetchall()
    retail = [r for r in rows if str(r["scope"]) == "bireysel"]
    check("Vakıf: en az 8 doğrulanmış bireysel finansman ürünü canlı", len(retail) >= 8, f"count={len(retail)} names={[r['product_name'] for r in retail]}")
    families = {str(r["product_family_key"]) for r in rows if str(r["scope"]) == "ticari"}
    check("Vakıf: ticari + gayri nakdi + tarım + leasing aileleri canlı", {"ticari_finansman", "gayri_nakdi_finansman", "tarim_finansmani", "leasing"}.issubset(families), str(sorted(families)))
    konut = next((r for r in rows if str(r["product_name"]) == "Konut Finansmanı"), None)
    check(
        "Vakıf Konut: şüpheli %150 tablo hücresi headline/rule olarak kullanılmıyor",
        bool(konut) and float(konut["maximum_financing_ratio"] or 0) <= 100.0
        and float(konut["maximum_financing_ratio"] or 0) == 90.0
        and not str(konut["housing_finance_rules_json"] or "").strip(),
        str(dict(konut) if konut else None),
    )

    # Ziraat: all major scopes/families and calculator default 0.99 suppressed.
    rows = con.execute(
        """
        SELECT d.* FROM live_campaigns c
        JOIN live_standard_product_details d ON d.product_id=c.id
        WHERE c.bank_name='Ziraat Katılım' AND c.record_kind='standard_product' AND c.is_current=1
        """
    ).fetchall()
    scopes = {str(r["scope"]) for r in rows}
    families = {str(r["product_family_key"]) for r in rows}
    check("Ziraat: bireysel + ticari scope canlı", scopes >= {"bireysel", "ticari"}, str(sorted(scopes)))
    check("Ziraat: ticari/gayri nakdi/tarım/leasing aileleri canlı", {"ticari_finansman", "gayri_nakdi_finansman", "tarim_finansmani", "leasing"}.issubset(families), str(sorted(families)))
    bad = [dict(r) for r in rows if r["profit_share_rate"] is not None and abs(float(r["profit_share_rate"]) - 0.99) < 1e-9]
    check("Ziraat: ortak hesaplama aracındaki bilgi amaçlı %0,99 ürün fiyatlaması yapılmıyor", not bad, str([(r['product_name'], r['profit_share_rate']) for r in bad]))

    con.close()
    print(f"SQLITE audit: PASS={passed} FAIL={failed}")
    return passed, failed


def postgres_audit() -> tuple[int, int]:
    dsn = os.getenv("POSTGRES_DSN", "").strip()
    if not dsn:
        print("PostgreSQL audit: POSTGRES_DSN tanımlı değil.")
        return 0, 1
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError('Çalıştırın: python -m pip install "psycopg[binary]"') from exc

    pg = psycopg.connect(dsn, application_name="bansa_remaining_finance_audit")
    passed = failed = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"PASS | PG | {label}")
        else:
            failed += 1
            print(f"FAIL | PG | {label} | {detail}")

    with pg.cursor() as cur:
        cur.execute("SET search_path TO bansa, public")
        cur.execute("SELECT name FROM banks WHERE is_active=TRUE ORDER BY name")
        bank_names = {str(r[0]) for r in cur.fetchall()}
        check("PostgreSQL banks tablosunda BDDK kapsamındaki 10 banka var", set(EXPECTED_BDDK).issubset(bank_names), str(sorted(bank_names)))
        for name in REMAINING_BANKS:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM standard_products s
                JOIN banks b ON b.id=s.bank_id
                WHERE b.name=%s AND s.is_current=TRUE
                """,
                (name,),
            )
            n = int(cur.fetchone()[0])
            check(f"{name}: PostgreSQL'de canlı standart finansman ürünü var", n > 0, f"count={n}")
        cur.execute(
            """
            SELECT COUNT(*)
            FROM standard_products s JOIN banks b ON b.id=s.bank_id
            WHERE b.name='Ziraat Katılım' AND s.is_current=TRUE AND s.profit_share_rate=0.99
            """
        )
        check("PostgreSQL Ziraat ürünlerinde %0,99 default oran sızıntısı yok", int(cur.fetchone()[0]) == 0)
        cur.execute(
            """
            SELECT COUNT(*)
            FROM standard_products s JOIN banks b ON b.id=s.bank_id
            WHERE b.name='Adil Katılım' AND s.is_current=TRUE AND (
                s.minimum_financing_amount IS NOT NULL OR s.maximum_financing_amount IS NOT NULL OR
                s.minimum_maturity_months IS NOT NULL OR s.maximum_maturity_months IS NOT NULL OR
                s.profit_share_rate IS NOT NULL OR s.maximum_financing_ratio IS NOT NULL
            )
            """
        )
        check("PostgreSQL Adil ürünlerinde kaynakta olmayan sayısal finansman metriği yok", int(cur.fetchone()[0]) == 0)

    pg.close()
    print(f"POSTGRES audit: PASS={passed} FAIL={failed}")
    return passed, failed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", action="store_true", help="Canlı SQLite entegrasyonunu da doğrula")
    parser.add_argument("--postgres", action="store_true", help="POSTGRES_DSN üzerinden PostgreSQL'i de doğrula")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()

    passed = failed = 0
    p, f = structural_audit(); passed += p; failed += f
    if args.sqlite:
        p, f = sqlite_audit(args.db); passed += p; failed += f
    if args.postgres:
        p, f = postgres_audit(); passed += p; failed += f

    print("=" * 72)
    print(f"KALAN BANKALAR FİNANSMAN ENTEGRASYON AUDIT: PASS={passed} FAIL={failed}")
    print("=" * 72)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
