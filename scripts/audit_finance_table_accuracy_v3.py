from __future__ import annotations

import argparse
import ast
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
DEFAULT_DB = PROJECT_ROOT / "data" / "campaigns.db"
PAGE = PROJECT_ROOT / "pages" / "4_Finansman_Karşılaştırması.py"


def _load_vehicle_parser():
    source = PAGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"has_value", "parse_scaled_amount", "parse_vehicle_rules_text"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    module = ast.Module(body=nodes, type_ignores=[])
    ns: dict[str, Any] = {"re": re, "pd": pd}
    exec(compile(module, str(PAGE), "exec"), ns)
    return ns["parse_vehicle_rules_text"]


def _vehicle_parser_ok() -> tuple[bool, str]:
    parse = _load_vehicle_parser()
    rules = parse(
        "≤ 400.000 TL: %70 / 48 ay · 400.001–800.000 TL: %50 / 36 ay · "
        "800.001–1.200.000 TL: %30 / 24 ay · 1.200.001–2.000.000 TL: %20 / 12 ay · "
        "> 2.000.000 TL: kullandırım yok"
    )
    values = [(r.get("min_amount"), r.get("max_amount"), r.get("ratio"), r.get("max_maturity_months"), r.get("blocked")) for r in rules]
    ok = (
        len(rules) == 5
        and [r.get("max_amount") for r in rules[:4]] == [400000.0, 800000.0, 1200000.0, 2000000.0]
        and rules[3].get("min_amount") == 1200001.0
        and rules[4].get("min_amount") == 2000000.0
        and bool(rules[4].get("blocked"))
    )
    return ok, str(values)


def _feature_map_sqlite(con: sqlite3.Connection, pid: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in con.execute("SELECT feature_key, feature_value FROM live_product_features WHERE product_id=?", (pid,)):
        out.setdefault(str(row[0]), []).append(str(row[1] or ""))
    return out


def _product_sqlite(con: sqlite3.Connection, bank: str, name: str, scope: str | None = None):
    sql = """
        SELECT c.id, c.bank_name, d.*
        FROM live_campaigns c
        JOIN live_standard_product_details d ON d.product_id=c.id
        WHERE c.is_current=1 AND c.bank_name=? AND d.product_name=?
    """
    params: list[Any] = [bank, name]
    if scope:
        sql += " AND d.scope=?"
        params.append(scope)
    sql += " ORDER BY c.id DESC LIMIT 1"
    return con.execute(sql, params).fetchone()


def sqlite_audit(db: Path) -> tuple[int, int]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    passed = failed = 0

    def check(label: str, ok: bool, detail: str = ""):
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"PASS | {label}")
        else:
            failed += 1
            print(f"FAIL | {label} | {detail}")

    ok, detail = _vehicle_parser_ok()
    check("Taşıt parser 1.200.000 / 2.000.000 tutarlarını kırpmıyor", ok, detail)

    canonical_vehicle = [
        ("Albaraka Türk", "Dijital Araç Finansmanı"),
        ("Albaraka Türk", "Taşıt Finansmanı"),
        ("Dünya Katılım", "Araç Finansmanı"),
        ("Kuveyt Türk", "Araç Finansmanı"),
        ("Türkiye Finans", "Dijital Taşıt Finansmanı"),
    ]
    for bank, name in canonical_vehicle:
        row = _product_sqlite(con, bank, name, "bireysel")
        if not row:
            check(f"{bank} / {name} bulundu", False)
            continue
        rr = con.execute(
            "SELECT min_amount,max_amount,max_maturity_months FROM live_product_amount_maturity_rules WHERE product_id=? ORDER BY coalesce(min_amount,-1)",
            (row["id"],),
        ).fetchall()
        sig = [(r["min_amount"], r["max_amount"], r["max_maturity_months"]) for r in rr]
        expected = [(None, 400000.0, 48), (400000.0, 800000.0, 36), (800000.0, 1200000.0, 24), (1200000.0, 2000000.0, 12)]
        check(f"{bank} / {name}: %70 headline max + 4 değer/vade bandı", row["maximum_financing_ratio"] == 70 and sig == expected, f"ratio={row['maximum_financing_ratio']} bands={sig}")

    row = _product_sqlite(con, "Albaraka Türk", "Hac ve Umre Finansmanı", "bireysel")
    if row:
        rr = con.execute("SELECT min_amount,max_amount,max_maturity_months FROM live_product_amount_maturity_rules WHERE product_id=? ORDER BY coalesce(min_amount,-1)", (row["id"],)).fetchall()
        sig = [(r[0], r[1], r[2]) for r in rr]
        check("Albaraka Hac/Umre: 125/250 bin TL ürün limiti değil vade bandı", row["minimum_financing_amount"] is None and row["maximum_financing_amount"] is None and sig == [(None,125000.0,36),(125000.0,250000.0,24),(250000.0,None,12)], str(sig))
    else:
        check("Albaraka Hac/Umre bulundu", False)

    row = _product_sqlite(con, "Albaraka Türk", "Jet Finansman", "bireysel")
    if row:
        rr = con.execute("SELECT min_amount,max_amount,max_maturity_months FROM live_product_amount_maturity_rules WHERE product_id=? ORDER BY coalesce(min_amount,-1)", (row["id"],)).fetchall()
        sig = [(r[0], r[1], r[2]) for r in rr]
        feats = _feature_map_sqlite(con, row["id"])
        payment = " ".join(feats.get("repayment_structure", []))
        check("Albaraka Jet: 1.000-60.000 TL sınırıyla kesişen yalnız 2 vade bandı", row["minimum_financing_amount"] == 1000 and row["maximum_financing_amount"] == 60000 and sig == [(1000.0,50000.0,36),(50000.0,60000.0,24)], str(sig))
        check("Albaraka Jet: ilk taksit 45 gün bilgisi korunuyor", "45" in payment, payment)

    row = con.execute("""
        SELECT c.id,d.* FROM live_campaigns c JOIN live_standard_product_details d ON d.product_id=c.id
        WHERE c.is_current=1 AND c.bank_name='Türkiye Finans' AND d.scope='bireysel'
          AND d.product_name LIKE 'İhtiyaç Finansmanı%'
        ORDER BY c.id DESC LIMIT 1
    """).fetchone()
    if row:
        rr = con.execute("SELECT min_amount,max_amount,max_maturity_months FROM live_product_amount_maturity_rules WHERE product_id=? ORDER BY coalesce(min_amount,-1)", (row["id"],)).fetchall()
        sig = [(r[0], r[1], r[2]) for r in rr]
        check("Türkiye Finans İhtiyaç: tekrar etmeyen 3 canonical vade bandı", sig == [(None,125000.0,36),(125000.0,250000.0,24),(250000.0,None,12)], str(sig))
    else:
        check("Türkiye Finans İhtiyaç ürünü bulundu", False)

    row = _product_sqlite(con, "Türkiye Finans", "Trendyol Alışveriş Finansmanı", "bireysel")
    check("Türkiye Finans Trendyol: 1.000-70.000 TL / 36 ay ürün-özel sınır", bool(row) and row["minimum_financing_amount"] == 1000 and row["maximum_financing_amount"] == 70000 and row["maximum_maturity_months"] == 36, str(dict(row) if row else None))
    if row:
        n = con.execute("SELECT count(*) FROM live_product_amount_maturity_rules WHERE product_id=?", (row["id"],)).fetchone()[0]
        check("Türkiye Finans Trendyol: genel ihtiyaç vade bantları ürüne sızmıyor", n == 0, f"rules={n}")

    row = _product_sqlite(con, "Kuveyt Türk", "LC Waikiki Alışveriş Finansmanı", "bireysel")
    if row:
        feats = _feature_map_sqlite(con, row["id"])
        channel = " ".join(feats.get("application_channel", []))
        check("LC Waikiki: 5.000 TL / 3 ay / vade farksız ana alanlara taşındı", row["maximum_financing_amount"] == 5000 and row["maximum_maturity_months"] == 3 and row["interest_free"] == 1 and row["interest_free_text"] == "Vade farksız", str(dict(row)))
        check("LC Waikiki: kullanım kanalı ürün-özel", "LC Waikiki" in channel, channel)

    row = _product_sqlite(con, "Albaraka Türk", "Jet Ticari Finansman", "ticari")
    if row:
        feats = _feature_map_sqlite(con, row["id"])
        repayment = " ".join(feats.get("repayment_structure", []))
        check("Jet Ticari: 2.000.000 TL finansman limiti", row["maximum_financing_amount"] == 2000000, str(row["maximum_financing_amount"]))
        check("Jet Ticari: ilk taksit azami 60 gün", "60" in repayment, repayment)

    general = _product_sqlite(con, "Kuveyt Türk", "Tarım ve Hayvancılık Finansmanı", "ticari")
    elus = _product_sqlite(con, "Kuveyt Türk", "Elektronik Ürün Senedi (ELÜS) Teminatlı Finansman", "ticari")
    if general:
        feats = _feature_map_sqlite(con, general["id"])
        all_sec = " ".join(feats.get("security_type", []))
        purpose = " ".join(feats.get("usage_purpose", []))
        currency = " ".join(feats.get("currency", []))
        repayment = " ".join(feats.get("repayment_structure", []))
        check("Kuveyt genel Tarım ürünü ELÜS teminatıyla yanlış birleşmiyor", "ELÜS" not in all_sec and "mal/hizmet" in purpose and "USD" in currency and "esnek" in repayment, str(feats))
    else:
        check("Kuveyt genel Tarım ürünü bulundu", False)
    if elus:
        feats = _feature_map_sqlite(con, elus["id"])
        security = " ".join(feats.get("security_type", []))
        check("Kuveyt ELÜS ayrı ürün ve %100 teminat bilgisi onda", "%100" in security and "ELÜS" in security, str(feats))
    else:
        check("Kuveyt ELÜS ayrı ürün olarak bulundu", False)

    row = _product_sqlite(con, "Kuveyt Türk", "Akreditifler", "ticari")
    if row:
        feats = _feature_map_sqlite(con, row["id"])
        purpose = " ".join(feats.get("usage_purpose", []))
        structure = " ".join(feats.get("transaction_structure", []))
        check("Kuveyt Akreditif generic nakdi amaç yerine gerçek gayri nakdi kullanımını gösteriyor", "Uluslararası ticaret" in purpose and "Akreditif" in structure, str(feats))

    for bank, name, expected_ratio, expected_months in [
        ("Albaraka Türk", "Leasing - Finansal Kiralama", 100, None),
        ("Kuveyt Türk", "Leasing", 100, None),
        ("Türkiye Finans", "Leasing", 100, 60),
    ]:
        row = _product_sqlite(con, bank, name, "ticari")
        if not row:
            check(f"{bank} Leasing bulundu", False)
            continue
        feats = _feature_map_sqlite(con, row["id"])
        cost = " ".join(feats.get("cost_advantage", []))
        ok = row["maximum_financing_ratio"] == expected_ratio and (expected_months is None or row["maximum_maturity_months"] == expected_months)
        check(f"{bank} Leasing: doğrulanmış oran/vade ana alanları", ok, str(dict(row)))
        if bank == "Kuveyt Türk":
            check("Kuveyt Leasing: KDV tek %1'e genellenmiyor", all(x in cost for x in ("%1", "%10", "%20")) and "2. el" in cost, cost)
        if bank == "Türkiye Finans":
            check("Türkiye Finans Leasing: %1 KDV koşullu/uygun varlık olarak etiketli", "koşula bağlı" in cost or "uygun" in cost, cost)

    row = _product_sqlite(con, "Kuveyt Türk", "Çatı GES Finansmanı", "ticari")
    if row:
        feats = _feature_map_sqlite(con, row["id"])
        check("Ticari Çatı GES: yalnız kaynak satırı değil karar alanlarıyla zengin", all(feats.get(k) for k in ("usage_purpose", "transaction_structure", "repayment_structure", "application_channel")), str(feats))

    # UI sütun politikasının kritik riskli alanları tekrar ana tabloya sokmadığını doğrula.
    from src.finance_column_profiles import get_profile
    check("Ticari ana profilde Dış Ticaret yok", "Dış Ticaret" not in get_profile("ticari", "Ticari Finansman").preferred_columns)
    check("Gayri Nakdi ana profilde Dış Ticaret/Teminat yok", "Dış Ticaret" not in get_profile("ticari", "Gayri Nakdi Finansman").preferred_columns and "Teminat / Güvence" not in get_profile("ticari", "Gayri Nakdi Finansman").preferred_columns)
    check("Leasing ana profilde Dış Ticaret yok", "Dış Ticaret" not in get_profile("ticari", "Leasing / Finansal Kiralama").preferred_columns)

    con.close()
    print(f"Finansman Tablo Doğruluk V3 SQLite audit: PASS={passed} FAIL={failed}")
    return passed, failed


def postgres_audit() -> tuple[int, int]:
    dsn = os.getenv("POSTGRES_DSN", "").strip()
    if not dsn:
        print("PostgreSQL audit: POSTGRES_DSN yok, atlandı.")
        return 0, 0
    import psycopg

    pg = psycopg.connect(dsn, application_name="bansa_finance_table_accuracy_v3_audit")
    passed = failed = 0

    def check(label: str, ok: bool, detail: str = ""):
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"PASS | PG | {label}")
        else:
            failed += 1
            print(f"FAIL | PG | {label} | {detail}")

    def product(cur, bank: str, name: str, scope: str | None = None):
        sql = """
            SELECT s.id,s.minimum_financing_amount,s.maximum_financing_amount,s.maximum_maturity_months,
                   s.maximum_financing_ratio,s.interest_free,s.interest_free_text,sp.url
            FROM standard_products s JOIN banks b ON b.id=s.bank_id
            LEFT JOIN source_pages sp ON sp.id=s.source_page_id
            WHERE s.is_current=true AND b.name=%s AND s.product_name=%s
        """
        params: list[Any] = [bank, name]
        if scope:
            sql += " AND s.scope=%s"
            params.append(scope)
        sql += " ORDER BY s.id DESC LIMIT 1"
        cur.execute(sql, params)
        return cur.fetchone()

    def features(cur, pid: int) -> dict[str, list[str]]:
        cur.execute("SELECT feature_key,feature_value FROM product_features WHERE product_id=%s", (pid,))
        out: dict[str, list[str]] = {}
        for key, value in cur.fetchall():
            out.setdefault(str(key), []).append(str(value or ""))
        return out

    with pg.cursor() as cur:
        cur.execute("SET search_path TO bansa, public")

        for bank, name in [
            ("Albaraka Türk", "Dijital Araç Finansmanı"),
            ("Albaraka Türk", "Taşıt Finansmanı"),
            ("Dünya Katılım", "Araç Finansmanı"),
            ("Kuveyt Türk", "Araç Finansmanı"),
            ("Türkiye Finans", "Dijital Taşıt Finansmanı"),
        ]:
            row = product(cur, bank, name, "bireysel")
            if not row:
                check(f"{bank} / {name} bulundu", False)
                continue
            pid, _, _, _, ratio, *_ = row
            cur.execute("SELECT min_amount,max_amount,max_maturity_months FROM product_amount_maturity_rules WHERE product_id=%s ORDER BY coalesce(min_amount,-1)", (pid,))
            sig = [(float(a) if a is not None else None, float(b) if b is not None else None, int(m)) for a,b,m in cur.fetchall()]
            expected = [(None,400000.0,48),(400000.0,800000.0,36),(800000.0,1200000.0,24),(1200000.0,2000000.0,12)]
            check(f"{bank} / {name}: %70 + 4 taşıt bandı", float(ratio or 0) == 70.0 and sig == expected, f"ratio={ratio} bands={sig}")

        row = product(cur, "Albaraka Türk", "Hac ve Umre Finansmanı", "bireysel")
        if row:
            pid, low, high, *_ = row
            cur.execute("SELECT min_amount,max_amount,max_maturity_months FROM product_amount_maturity_rules WHERE product_id=%s ORDER BY coalesce(min_amount,-1)", (pid,))
            sig = [(float(a) if a is not None else None,float(b) if b is not None else None,int(m)) for a,b,m in cur.fetchall()]
            check("Hac/Umre fake ürün limiti yok", low is None and high is None and sig == [(None,125000.0,36),(125000.0,250000.0,24),(250000.0,None,12)], str(sig))

        row = product(cur, "Albaraka Türk", "Jet Finansman", "bireysel")
        if row:
            pid, low, high, *_ = row
            cur.execute("SELECT min_amount,max_amount,max_maturity_months FROM product_amount_maturity_rules WHERE product_id=%s ORDER BY coalesce(min_amount,-1)", (pid,))
            sig = [(float(a) if a is not None else None,float(b) if b is not None else None,int(m)) for a,b,m in cur.fetchall()]
            check("Jet 60.000 TL dışına vade bandı taşmıyor", float(low or 0)==1000 and float(high or 0)==60000 and sig==[(1000.0,50000.0,36),(50000.0,60000.0,24)], str(sig))

        cur.execute("""
            SELECT s.id FROM standard_products s JOIN banks b ON b.id=s.bank_id
            WHERE s.is_current=true AND b.name='Türkiye Finans' AND s.scope='bireysel'
              AND s.product_name LIKE 'İhtiyaç Finansmanı%' ORDER BY s.id DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            cur.execute("SELECT min_amount,max_amount,max_maturity_months FROM product_amount_maturity_rules WHERE product_id=%s ORDER BY coalesce(min_amount,-1)", (row[0],))
            sig = [(float(a) if a is not None else None,float(b) if b is not None else None,int(m)) for a,b,m in cur.fetchall()]
            check("TF İhtiyaç 3 canonical bant", sig==[(None,125000.0,36),(125000.0,250000.0,24),(250000.0,None,12)], str(sig))
        else:
            check("TF İhtiyaç ürünü bulundu", False)

        row = product(cur, "Türkiye Finans", "Trendyol Alışveriş Finansmanı", "bireysel")
        if row:
            pid, low, high, months, *_ = row
            check("TF Trendyol 1.000-70.000 / 36 ay", float(low or 0)==1000 and float(high or 0)==70000 and int(months or 0)==36, str(row))
            cur.execute("SELECT count(*) FROM product_amount_maturity_rules WHERE product_id=%s", (pid,))
            check("TF Trendyol generic ihtiyaç vade bandı taşımıyor", cur.fetchone()[0]==0)

        row = product(cur, "Kuveyt Türk", "LC Waikiki Alışveriş Finansmanı", "bireysel")
        if row:
            pid, _, high, months, _, interest_free, interest_text, _ = row
            feats = features(cur, pid)
            check("LC 5.000 / 3 ay / vade farksız", float(high or 0)==5000 and int(months or 0)==3 and bool(interest_free) and interest_text=="Vade farksız", str(row))
            check("LC kanal doğru", "LC Waikiki" in " ".join(feats.get("application_channel", [])), str(feats))

        general = product(cur, "Kuveyt Türk", "Tarım ve Hayvancılık Finansmanı", "ticari")
        elus = product(cur, "Kuveyt Türk", "Elektronik Ürün Senedi (ELÜS) Teminatlı Finansman", "ticari")
        if general:
            feats = features(cur, general[0])
            check("Kuveyt genel Tarım ELÜS ile birleşmiyor", "ELÜS" not in " ".join(feats.get("security_type", [])) and "USD" in " ".join(feats.get("currency", [])), str(feats))
        else:
            check("Kuveyt genel Tarım bulundu", False)
        if elus:
            feats = features(cur, elus[0])
            sec = " ".join(feats.get("security_type", []))
            check("Kuveyt ELÜS ayrı ürün", "%100" in sec and "ELÜS" in sec, str(feats))
        else:
            check("Kuveyt ELÜS ayrı ürün bulundu", False)

        row = product(cur, "Kuveyt Türk", "Akreditifler", "ticari")
        if row:
            feats = features(cur, row[0])
            check("Kuveyt Akreditif gerçek gayri nakdi kullanım", "Uluslararası ticaret" in " ".join(feats.get("usage_purpose", [])), str(feats))

        for bank, name, ratio_expected, months_expected in [
            ("Albaraka Türk","Leasing - Finansal Kiralama",100,None),
            ("Kuveyt Türk","Leasing",100,None),
            ("Türkiye Finans","Leasing",100,60),
        ]:
            row = product(cur, bank, name, "ticari")
            if not row:
                check(f"{bank} Leasing bulundu", False)
                continue
            pid, _, _, months, ratio, *_ = row
            ok = float(ratio or 0)==float(ratio_expected) and (months_expected is None or int(months or 0)==months_expected)
            check(f"{bank} Leasing doğrulanmış ana alanlar", ok, str(row))
            feats = features(cur, pid)
            if bank == "Kuveyt Türk":
                cost = " ".join(feats.get("cost_advantage", []))
                check("Kuveyt Leasing KDV değişken", all(x in cost for x in ("%1","%10","%20")), cost)

        row = product(cur, "Kuveyt Türk", "Çatı GES Finansmanı", "ticari")
        if row:
            feats = features(cur, row[0])
            check("Ticari GES karar alanları dolu", all(feats.get(k) for k in ("usage_purpose","transaction_structure","repayment_structure","application_channel")), str(feats))

    pg.close()
    print(f"Finansman Tablo Doğruluk V3 PostgreSQL audit: PASS={passed} FAIL={failed}")
    return passed, failed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    _, sf = sqlite_audit(args.db)
    _, pf = postgres_audit()
    return 1 if sf or pf else 0


if __name__ == "__main__":
    raise SystemExit(main())
