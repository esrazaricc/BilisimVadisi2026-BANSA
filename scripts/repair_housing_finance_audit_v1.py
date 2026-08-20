from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.housing_verified_source_overrides import (
    ADDITIONAL_HOME_RULES,
    ALBARAKA_COST_PDF,
    DUNYA_FEE_PDF,
    KUVEYT_GREEN_3M_TEXT,
    STANDARD_HOME_RULES,
    canonical_housing_json,
    canonical_housing_text,
)
from src.pricing_guardrails import authoritative_pricing_rows

NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

KT_REGULAR_URL = "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/konut-finansmani"
KT_FIRST_URL = "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/ilk-evim-konut-finansmani"
KT_2B_URL = "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/2b-finansmani"
KT_ARSA_URL = "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/arsa-finansmani"
KT_GURBET_URL = "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/gurbetten-silaya-gayrimenkul-finansmani"
KT_WORK_URL = "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/is-yeri-finansmani"
KT_GREEN_URL = "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/surdurulebilir-finansmanlar/yesil-konut-finansmani"
TF_URL = "https://www.turkiyefinans.com.tr/tr-tr/bireysel/konut-finansmani/sayfalar/konut-finansmani.aspx"
ALBARAKA_URL = "https://www.albaraka.com.tr/tr/bireysel/finansmanlar/konut-finansmani/konut-finansmani"
DUNYA_URL = "https://dunyakatilim.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/konut-finansmani"

KEEP = object()


def _fee(rate: float, *, maximum: bool = False, source: str) -> dict[str, Any]:
    return {
        "fee_type": "allocation",
        "fee_label": "Azami Tahsis Ücreti" if maximum else "Tahsis Ücreti",
        "waived": False,
        "amount": None,
        "rate": rate,
        "note": (
            f"Resmî kaynakta finansman tutarı üzerinden maksimum %{rate:.2f} olarak yayımlanıyor. Kaynak: {source}"
            if maximum
            else f"Resmî kaynakta finansman tutarının %{rate:.2f}'si olarak yayımlanıyor. Kaynak: {source}"
        ),
    }


def _offer(rule_type: str, label: str, condition: str, source: str, *, max_amount: float | None = None) -> dict[str, Any]:
    return {
        "rule_type": rule_type,
        "rule_label": label,
        "min_amount": None,
        "max_amount": max_amount,
        "min_inclusive": False,
        "max_inclusive": True,
        "max_installments": None,
        "max_maturity_months": None,
        "interest_free": False,
        "condition_text": condition,
        "source_text": source,
    }


def _ownership_offer(source: str) -> dict[str, Any]:
    return _offer(
        "ownership_condition",
        "Mevcut Konut Sahipliği Koşulu",
        "Kendisinin/eşinin/18 yaş altı çocuklarının malik olduğu en az bir konut varsa kullanılabilecek finansman tutarı %75 oranında azalır.",
        source,
    )



STANDARD_TEXT, ADDITIONAL_TEXT = canonical_housing_text(standard=True, additional=True)
FIRST_ONLY_TEXT, _ = canonical_housing_text(standard=True, additional=False)
_, ADDITIONAL_ONLY_TEXT = canonical_housing_text(standard=False, additional=True)

PRODUCTS: dict[tuple[str, str], dict[str, Any]] = {
    ("Albaraka Türk", "Konut Finansmanı"): {
        "max_maturity": 120,
        "ratio": None,
        "housing": (True, True),
        "fee": _fee(0.50, source=ALBARAKA_COST_PDF),
        "pricing": "block_example_only",
        "offers": [],
        "purpose": "Konut ediniminin finansmanı",
        "source": ALBARAKA_URL,
    },
    ("Dünya Katılım", "Konut Finansmanı"): {
        "max_maturity": None,  # güncel ürün sayfasında sayısal azami vade doğrulanmadı
        "ratio": None,
        "housing": (True, True),
        "fee": _fee(0.50, source=DUNYA_FEE_PDF),
        "pricing": KEEP,
        "offers": [],
        "purpose": "Konut ediniminin finansmanı",
        "source": DUNYA_URL,
    },
    ("Kuveyt Türk", "Konut Finansmanı"): {
        "max_maturity": 120,
        "ratio": None,
        "housing": (False, True),
        "fee": _fee(0.50, source=KT_REGULAR_URL),
        "pricing": KEEP,
        "offers": [_ownership_offer(KT_REGULAR_URL)],
        "purpose": "Konut ediniminin finansmanı",
        "source": KT_REGULAR_URL,
    },
    ("Kuveyt Türk", "İlk Evim Konut Finansmanı"): {
        "max_maturity": 120,
        "ratio": None,
        "housing": (True, False),
        "fee": _fee(0.50, source=KT_FIRST_URL),
        "pricing": KEEP,
        "offers": [],
        "purpose": "İlk konut ediniminin finansmanı",
        "source": KT_FIRST_URL,
    },
    ("Kuveyt Türk", "Yeşil Konut Finansmanı"): {
        "max_maturity": 120,
        "ratio": None,
        "housing": None,
        "housing_clear": True,
        "fee": None,  # sayısal tahsis oranı güncel sayfada doğrulanmadan uydurulmaz
        "pricing": KEEP,
        "ratio_text": (
            "Finansman tutarı ekspertiz değeri, konutun sıfır/2. el durumu, enerji sınıfı "
            "ve mevcut konut sahipliğine göre değişir; mevcut konut varsa kullanılabilir "
            "finansman tutarı %75 azalır."
        ),
        "offers": [
            _ownership_offer(KT_GREEN_URL),
            _offer(
                "pricing_validity",
                "Web Kâr Oranı Geçerlilik Sınırı",
                KUVEYT_GREEN_3M_TEXT,
                KUVEYT_GREEN_3M_TEXT,
                max_amount=3_000_000.0,
            ),
        ],
        "purpose": "Enerji verimli konut ediniminin finansmanı",
        "source": KT_GREEN_URL,
    },
    ("Kuveyt Türk", "Gurbetten Sılaya Gayrimenkul Finansmanı"): {
        "max_maturity": None,  # güncel ürün sayfasında sayısal azami vade doğrulanmadı
        "ratio": 50.0,
        "housing": None,
        "housing_clear": True,
        "fee": _fee(0.50, source=KT_GURBET_URL),
        "pricing": KEEP,
        "ratio_text": "Ekspertiz değerinin %50'si tutarında finansman kullanılabilir.",
        "offers": [_ownership_offer(KT_GURBET_URL)],
        "purpose": "Türkiye'de konut ediniminin finansmanı",
        "source": KT_GURBET_URL,
    },
    ("Kuveyt Türk", "2B Finansmanı"): {
        "max_maturity": 60,
        "ratio": 100.0,
        "housing": None,
        "housing_clear": True,
        "fee": _fee(1.10, maximum=True, source=KT_2B_URL),
        "pricing": KEEP,
        "ratio_text": "Arazi değerinin %100'üne kadar finansman kullanılabilir.",
        "offers": [],
        "purpose": "2B statüsündeki arazinin satın alınmasının finansmanı",
        "source": KT_2B_URL,
    },
    ("Kuveyt Türk", "Arsa Finansmanı"): {
        "max_maturity": 60,
        "ratio": None,  # güncel sayfada sabit finansman oranı yayımlanmıyor
        "housing": None,
        "housing_clear": True,
        "fee": _fee(1.10, maximum=True, source=KT_ARSA_URL),
        "pricing": KEEP,
        "ratio_text": None,
        "offers": [],
        "purpose": "Arsa ediniminin finansmanı",
        "source": KT_ARSA_URL,
    },
    ("Kuveyt Türk", "İş Yeri Finansmanı"): {
        "max_maturity": 60,
        "ratio": None,
        "housing": None,
        "housing_clear": True,
        "fee": _fee(1.10, maximum=True, source=KT_WORK_URL),
        "pricing": KEEP,
        "ratio_text": None,
        "offers": [],
        "purpose": "İş yeri / ticari gayrimenkul ediniminin finansmanı",
        "source": KT_WORK_URL,
    },
    ("Türkiye Finans", "Konut Finansmanı (Konut Kredisi)"): {
        "max_maturity": 120,
        "ratio": None,
        "housing": (True, True),
        "fee": _fee(0.50, source=TF_URL),
        "pricing": KEEP,  # mevcut resmî 40 fiyatlama satırı korunur
        "offers": KEEP,   # mevcut vade/ürün koşulları korunur
        "purpose": "Konut ediniminin finansmanı",
        "source": TF_URL,
    },
}


def normalize_product_name(value: str) -> str:
    return str(value or "").strip().rstrip("*").strip()


def load_rules(raw: object) -> dict[str, list[dict[str, Any]]]:
    try:
        obj = raw if isinstance(raw, dict) else json.loads(str(raw or "{}"))
    except Exception:
        obj = {}
    if not isinstance(obj, dict):
        obj = {}
    for key in ("category_rules", "amount_maturity_rules", "pricing_tiers", "fee_rules", "offer_rules"):
        if not isinstance(obj.get(key), list):
            obj[key] = []
    return obj


def patched_rules(current: object, cfg: dict[str, Any]) -> dict[str, Any]:
    rules = load_rules(current)

    # Tahsis ücreti: sadece allocation/tahsis satırını yeniden kur; diğer masraflar korunur.
    rules["fee_rules"] = [
        row for row in rules["fee_rules"]
        if str(row.get("fee_type") or "").casefold() != "allocation"
        and "tahsis" not in str(row.get("fee_label") or "").casefold()
    ]
    if cfg.get("fee") is not None:
        rules["fee_rules"].append(deepcopy(cfg["fee"]))

    pricing_cfg = cfg.get("pricing", KEEP)
    if pricing_cfg == "block_example_only":
        # Eski V1 scripti çalıştırılsa bile örnek/temsili maliyet satırları
        # güncel ürün fiyatlaması olarak yeniden üretilemez.
        rules["pricing_tiers"] = authoritative_pricing_rows(
            rules["pricing_tiers"]
        )
    elif pricing_cfg is not KEEP:
        rules["pricing_tiers"] = authoritative_pricing_rows(
            deepcopy(pricing_cfg or [])
        )

    offers_cfg = cfg.get("offers", KEEP)
    verified_labels = {
        "Mevcut Konut Sahipliği Koşulu",
        "Web Kâr Oranı Geçerlilik Sınırı",
    }
    rules["offer_rules"] = [
        row for row in rules["offer_rules"]
        if str(row.get("rule_label") or "") not in verified_labels
    ]
    if offers_cfg is not KEEP:
        rules["offer_rules"].extend(deepcopy(offers_cfg or []))

    return rules


def canonical_housing_values(cfg: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    housing = cfg.get("housing")
    if housing is not None:
        standard, additional = housing
        first_text, additional_text = canonical_housing_text(
            standard=bool(standard), additional=bool(additional)
        )
        return first_text, additional_text, canonical_housing_json(
            standard=bool(standard), additional=bool(additional)
        )
    if cfg.get("housing_clear"):
        return None, None, None
    return KEEP, KEEP, KEEP  # type: ignore[return-value]


def sqlite_sync_rules(con: sqlite3.Connection, product_id: int, rules: dict[str, Any]) -> None:
    # Alt kuralların tamamını finance_rules_json ile aynı kaynaktan yeniden kuruyoruz.
    for table in (
        "live_product_category_rules",
        "live_product_amount_maturity_rules",
        "live_product_pricing_tiers",
        "live_product_fee_rules",
        "live_product_offer_rules",
    ):
        con.execute(f"DELETE FROM {table} WHERE product_id=?", (product_id,))

    for row in rules.get("category_rules", []):
        con.execute(
            """INSERT INTO live_product_category_rules
            (product_id,category_key,category_label,min_amount,max_amount,min_inclusive,max_inclusive,max_installments,max_maturity_months,condition_text,source_text,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (product_id,row.get("category_key"),row.get("category_label"),row.get("min_amount"),row.get("max_amount"),int(bool(row.get("min_inclusive"))),int(bool(row.get("max_inclusive",True))),row.get("max_installments"),row.get("max_maturity_months"),row.get("condition_text"),row.get("source_text"),NOW),
        )
    for row in rules.get("amount_maturity_rules", []):
        con.execute(
            """INSERT INTO live_product_amount_maturity_rules
            (product_id,min_amount,max_amount,min_inclusive,max_inclusive,max_maturity_months,source_text,updated_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (product_id,row.get("min_amount"),row.get("max_amount"),int(bool(row.get("min_inclusive"))),int(bool(row.get("max_inclusive",True))),row.get("max_maturity_months"),row.get("source_text"),NOW),
        )
    for row in rules.get("pricing_tiers", []):
        con.execute(
            """INSERT INTO live_product_pricing_tiers
            (product_id,pricing_variant,financing_amount,maturity_months,profit_share_rate,allocation_fee_rate,monthly_total_cost_rate,annual_total_cost_rate,source_text,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (product_id,row.get("pricing_variant","Standart"),row.get("financing_amount"),row.get("maturity_months"),row.get("profit_share_rate"),row.get("allocation_fee_rate"),row.get("monthly_total_cost_rate"),row.get("annual_total_cost_rate"),row.get("source_text"),NOW),
        )
    for row in rules.get("fee_rules", []):
        con.execute(
            """INSERT INTO live_product_fee_rules
            (product_id,fee_type,fee_label,waived,amount,rate,note,updated_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (product_id,row.get("fee_type"),row.get("fee_label"),int(bool(row.get("waived"))),row.get("amount"),row.get("rate"),row.get("note"),NOW),
        )
    for row in rules.get("offer_rules", []):
        con.execute(
            """INSERT INTO live_product_offer_rules
            (product_id,rule_type,rule_label,min_amount,max_amount,min_inclusive,max_inclusive,max_installments,max_maturity_months,interest_free,condition_text,source_text,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (product_id,row.get("rule_type","product_offer"),row.get("rule_label","Ürüne Özel Finansman Koşulu"),row.get("min_amount"),row.get("max_amount"),int(bool(row.get("min_inclusive"))),int(bool(row.get("max_inclusive",True))),row.get("max_installments"),row.get("max_maturity_months"),int(bool(row.get("interest_free"))),row.get("condition_text"),row.get("source_text"),NOW),
        )


def repair_sqlite() -> tuple[int, Path | None]:
    db = PROJECT_ROOT / "data" / "campaigns.db"
    if not db.exists():
        print("[SQLite] campaigns.db bulunamadı; atlandı.")
        return 0, None

    backup_dir = PROJECT_ROOT / "data" / "backups" / "housing_finance_audit"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"campaigns_before_housing_audit_{stamp}.db"
    shutil.copy2(db, backup)
    print("[SQLite] Yedek:", backup)

    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    changed = 0
    try:
        rows = con.execute(
            """SELECT d.product_id,d.bank_name,d.product_name,d.finance_rules_json
               FROM live_standard_product_details d
               WHERE d.product_family='Konut Finansmanı'"""
        ).fetchall()

        for row in rows:
            key = (row["bank_name"], normalize_product_name(row["product_name"]))
            cfg = PRODUCTS.get(key)
            if not cfg:
                print("[SQLite][WARN] Audit matrisi dışında:", key)
                continue

            pid = int(row["product_id"])
            rules = patched_rules(row["finance_rules_json"], cfg)
            first_text, additional_text, housing_json = canonical_housing_values(cfg)

            sets = [
                "maximum_maturity_months=?",
                "maximum_financing_ratio=?",
                "financing_ratio_rules_text=?",
                "finance_rules_json=?",
            ]
            values: list[Any] = [
                cfg.get("max_maturity"),
                cfg.get("ratio"),
                cfg.get("ratio_text"),
                json.dumps(rules, ensure_ascii=False, sort_keys=True),
            ]
            if first_text is not KEEP:
                sets += [
                    "housing_first_home_rules_text=?",
                    "housing_additional_home_rules_text=?",
                    "housing_finance_rules_json=?",
                ]
                values += [first_text, additional_text, housing_json]
            values.append(pid)
            con.execute(
                f"UPDATE live_standard_product_details SET {', '.join(sets)} WHERE product_id=?",
                values,
            )
            sqlite_sync_rules(con, pid, rules)

            con.execute(
                """INSERT INTO live_product_features
                   (product_id,feature_key,feature_label,feature_value,source_text,extraction_method,updated_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(product_id,feature_key) DO UPDATE SET
                     feature_label=excluded.feature_label,
                     feature_value=excluded.feature_value,
                     source_text=excluded.source_text,
                     extraction_method=excluded.extraction_method,
                     updated_at=excluded.updated_at""",
                (pid,"usage_purpose","Amaç",cfg["purpose"],cfg["source"],"verified_housing_audit_v1",NOW),
            )
            changed += 1
            print(f"[SQLite][OK] {key[0]} | {key[1]}")

        con.commit()
    finally:
        con.close()
    return changed, backup


def pg_sync_rules(cur, product_id: int, rules: dict[str, Any]) -> None:
    for table in (
        "product_category_rules",
        "product_amount_maturity_rules",
        "product_pricing_tiers",
        "product_fee_rules",
        "product_offer_rules",
    ):
        cur.execute(f"DELETE FROM {table} WHERE product_id=%s", (product_id,))

    for row in rules.get("category_rules", []):
        cur.execute(
            """INSERT INTO product_category_rules
            (product_id,category_key,category_label,min_amount,max_amount,min_inclusive,max_inclusive,max_installments,max_maturity_months,condition_text,source_text,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
            (product_id,row.get("category_key"),row.get("category_label"),row.get("min_amount"),row.get("max_amount"),bool(row.get("min_inclusive")),bool(row.get("max_inclusive",True)),row.get("max_installments"),row.get("max_maturity_months"),row.get("condition_text"),row.get("source_text")),
        )
    for row in rules.get("amount_maturity_rules", []):
        cur.execute(
            """INSERT INTO product_amount_maturity_rules
            (product_id,min_amount,max_amount,min_inclusive,max_inclusive,max_maturity_months,source_text,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())""",
            (product_id,row.get("min_amount"),row.get("max_amount"),bool(row.get("min_inclusive")),bool(row.get("max_inclusive",True)),row.get("max_maturity_months"),row.get("source_text")),
        )
    for row in rules.get("pricing_tiers", []):
        cur.execute(
            """INSERT INTO product_pricing_tiers
            (product_id,pricing_variant,financing_amount,maturity_months,profit_share_rate,allocation_fee_rate,monthly_total_cost_rate,annual_total_cost_rate,source_text,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
            (product_id,row.get("pricing_variant","Standart"),row.get("financing_amount"),row.get("maturity_months"),row.get("profit_share_rate"),row.get("allocation_fee_rate"),row.get("monthly_total_cost_rate"),row.get("annual_total_cost_rate"),row.get("source_text")),
        )
    for row in rules.get("fee_rules", []):
        cur.execute(
            """INSERT INTO product_fee_rules
            (product_id,fee_type,fee_label,waived,amount,rate,note,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())""",
            (product_id,row.get("fee_type"),row.get("fee_label"),bool(row.get("waived")),row.get("amount"),row.get("rate"),row.get("note")),
        )
    for row in rules.get("offer_rules", []):
        cur.execute(
            """INSERT INTO product_offer_rules
            (product_id,rule_type,rule_label,min_amount,max_amount,min_inclusive,max_inclusive,max_installments,max_maturity_months,interest_free,condition_text,source_text,updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
            (product_id,row.get("rule_type","product_offer"),row.get("rule_label","Ürüne Özel Finansman Koşulu"),row.get("min_amount"),row.get("max_amount"),bool(row.get("min_inclusive")),bool(row.get("max_inclusive",True)),row.get("max_installments"),row.get("max_maturity_months"),bool(row.get("interest_free")),row.get("condition_text"),row.get("source_text")),
        )


def repair_postgres() -> int:
    dsn = os.getenv("POSTGRES_DSN", "").strip()
    if not dsn:
        print("[PostgreSQL] POSTGRES_DSN tanımlı değil; atlandı.")
        return 0
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError('psycopg kurulu değil: python -m pip install "psycopg[binary]"') from exc

    changed = 0
    with psycopg.connect(dsn) as con:
        with con.cursor() as cur:
            cur.execute("SET search_path TO bansa, public")
            cur.execute(
                "ALTER TABLE bansa.product_pricing_tiers ADD COLUMN IF NOT EXISTS financing_amount NUMERIC(18,2)"
            )
            cur.execute(
                """SELECT p.id,b.name,p.product_name,p.finance_rules
                   FROM standard_products p
                   JOIN banks b ON b.id=p.bank_id
                   JOIN product_families f ON f.id=p.family_id
                   WHERE p.is_current=TRUE AND f.family_name='Konut Finansmanı'"""
            )
            rows = cur.fetchall()
            for pid, bank, product_name, finance_rules in rows:
                key = (bank, normalize_product_name(product_name))
                cfg = PRODUCTS.get(key)
                if not cfg:
                    print("[PostgreSQL][WARN] Audit matrisi dışında:", key)
                    continue
                rules = patched_rules(finance_rules, cfg)
                first_text, additional_text, housing_json = canonical_housing_values(cfg)

                if first_text is KEEP:
                    cur.execute(
                        """UPDATE standard_products SET
                           maximum_maturity_months=%s,
                           maximum_financing_ratio=%s,
                           financing_ratio_rules_text=%s,
                           finance_rules=%s::jsonb,
                           updated_at=NOW()
                           WHERE id=%s""",
                        (cfg.get("max_maturity"),cfg.get("ratio"),cfg.get("ratio_text"),json.dumps(rules,ensure_ascii=False),pid),
                    )
                else:
                    cur.execute(
                        """UPDATE standard_products SET
                           maximum_maturity_months=%s,
                           maximum_financing_ratio=%s,
                           financing_ratio_rules_text=%s,
                           housing_first_home_rules_text=%s,
                           housing_additional_home_rules_text=%s,
                           housing_finance_rules=%s::jsonb,
                           finance_rules=%s::jsonb,
                           updated_at=NOW()
                           WHERE id=%s""",
                        (cfg.get("max_maturity"),cfg.get("ratio"),cfg.get("ratio_text"),first_text,additional_text,housing_json,json.dumps(rules,ensure_ascii=False),pid),
                    )
                pg_sync_rules(cur, int(pid), rules)
                cur.execute(
                    """INSERT INTO product_features
                       (product_id,feature_key,feature_label,feature_value,source_text,extraction_method,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,NOW())
                       ON CONFLICT(product_id,feature_key) DO UPDATE SET
                         feature_label=EXCLUDED.feature_label,
                         feature_value=EXCLUDED.feature_value,
                         source_text=EXCLUDED.source_text,
                         extraction_method=EXCLUDED.extraction_method,
                         updated_at=EXCLUDED.updated_at""",
                    (pid,"usage_purpose","Amaç",cfg["purpose"],cfg["source"],"verified_housing_audit_v1"),
                )
                changed += 1
                print(f"[PostgreSQL][OK] {bank} | {key[1]}")
        con.commit()
    return changed


def main() -> int:
    print("=" * 90)
    print("BANSA — KONUT / GAYRİMENKUL FİNANSMANI TAM AUDIT REPAIR V1")
    print("=" * 90)
    sqlite_count, backup = repair_sqlite()
    pg_count = repair_postgres()
    print("\nSONUÇ")
    print("SQLite düzeltilen ürün:", sqlite_count)
    print("PostgreSQL düzeltilen ürün:", pg_count)
    if backup:
        print("SQLite yedek:", backup)
    if sqlite_count == 0:
        return 2
    if os.getenv("POSTGRES_DSN", "").strip() and pg_count == 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
