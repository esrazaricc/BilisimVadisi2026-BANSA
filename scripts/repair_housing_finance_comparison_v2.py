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
    VERIFIED_FEES,
    VERIFIED_OFFERS,
    apply_verified_housing_product_overrides,
    normalize_product_name,
)

NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

KUVEYT_2B_URL = (
    "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/"
    "konut-finansmanlari/2b-finansmani"
)
KUVEYT_ARSA_URL = (
    "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/"
    "konut-finansmanlari/arsa-finansmani"
)
KUVEYT_WORK_URL = (
    "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/"
    "konut-finansmanlari/is-yeri-finansmani"
)

RECLASSIFIED_PRODUCTS: dict[tuple[str, str], dict[str, Any]] = {
    ("Kuveyt Türk", "2B Finansmanı"): {
        "family_key": "arsa_finansmani",
        "family_name": "Arsa Finansmanı",
        "maximum_maturity_months": 60,
        "maximum_financing_ratio": 100.0,
        "financing_ratio_rules_text": (
            "Arazi değerinin %100'üne kadar finansman kullanılabilir."
        ),
        "allocation_fee_rate": 1.10,
        "allocation_fee_label": "Azami Tahsis Ücreti",
        "source": KUVEYT_2B_URL,
    },
    ("Kuveyt Türk", "Arsa Finansmanı"): {
        "family_key": "arsa_finansmani",
        "family_name": "Arsa Finansmanı",
        "maximum_maturity_months": 60,
        "maximum_financing_ratio": None,
        "financing_ratio_rules_text": None,
        "allocation_fee_rate": 1.10,
        "allocation_fee_label": "Azami Tahsis Ücreti",
        "source": KUVEYT_ARSA_URL,
    },
    ("Kuveyt Türk", "İş Yeri Finansmanı"): {
        "family_key": "isyeri_finansmani",
        "family_name": "İş Yeri Finansmanı",
        "maximum_maturity_months": 60,
        "maximum_financing_ratio": None,
        "financing_ratio_rules_text": None,
        "allocation_fee_rate": 1.10,
        "allocation_fee_label": "Azami Tahsis Ücreti",
        "source": KUVEYT_WORK_URL,
    },
}

STALE_GENERIC_OFFER = "Ürüne Özel Finansman Koşulu"


def _load_rules(raw: object) -> dict[str, list[dict[str, Any]]]:
    if isinstance(raw, dict):
        value = deepcopy(raw)
    else:
        try:
            value = json.loads(str(raw or "{}"))
        except Exception:
            value = {}
    if not isinstance(value, dict):
        value = {}
    for key in (
        "category_rules",
        "amount_maturity_rules",
        "pricing_tiers",
        "fee_rules",
        "offer_rules",
    ):
        if not isinstance(value.get(key), list):
            value[key] = []
    return value


def _clean_verified_rules(rules: dict[str, Any], key: tuple[str, str]) -> dict[str, Any]:
    """Remove stale generic artifacts after verified override is applied."""
    out = deepcopy(rules)

    if key in VERIFIED_FEES:
        # Audited products use a closed, source-verified fee set. This is what
        # eliminates stale rows such as Türkiye Finans general_expense/waived=1.
        out["fee_rules"] = deepcopy(VERIFIED_FEES[key])

    if key in VERIFIED_OFFERS:
        verified_labels = {row["rule_label"] for row in VERIFIED_OFFERS[key]}
        retained = []
        for row in out.get("offer_rules", []):
            label = str(row.get("rule_label") or "").strip()
            condition = str(row.get("condition_text") or "").strip().casefold()
            if label in verified_labels:
                continue
            if label == STALE_GENERIC_OFFER and condition.startswith("genel azami vade"):
                continue
            retained.append(row)
        retained.extend(deepcopy(VERIFIED_OFFERS[key]))
        out["offer_rules"] = retained

    return out


def _patch_config() -> Path | None:
    path = PROJECT_ROOT / "config" / "standard_product_sources.json"
    if not path.exists():
        print("[Config] standard_product_sources.json bulunamadı; atlandı.")
        return None

    data = json.loads(path.read_text(encoding="utf-8"))
    banks = data.get("banks") or []
    kuveyt = next((b for b in banks if b.get("name") == "Kuveyt Türk"), None)
    if not kuveyt:
        print("[Config] Kuveyt Türk kaydı bulunamadı; atlandı.")
        return None

    exact_rules = [
        {
            "family_key": "arsa_finansmani",
            "family_label": "Arsa Finansmanı",
            "path_contains": [],
            "exact_paths": [
                "/kendim-icin/finansmanlar/konut-finansmanlari/2b-finansmani",
                "/kendim-icin/finansmanlar/konut-finansmanlari/arsa-finansmani",
            ],
        },
        {
            "family_key": "isyeri_finansmani",
            "family_label": "İş Yeri Finansmanı",
            "path_contains": [],
            "exact_paths": [
                "/kendim-icin/finansmanlar/konut-finansmanlari/is-yeri-finansmani",
            ],
        },
    ]

    rules = list(kuveyt.get("family_rules") or [])
    special_keys = {"arsa_finansmani", "isyeri_finansmani"}
    rules = [r for r in rules if r.get("family_key") not in special_keys]

    generic_index = next(
        (
            i for i, r in enumerate(rules)
            if r.get("family_key") == "konut_finansmani"
        ),
        0,
    )
    kuveyt["family_rules"] = rules[:generic_index] + exact_rules + rules[generic_index:]

    backup_dir = PROJECT_ROOT / "config" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"standard_product_sources_before_housing_v2_{stamp}.json"
    shutil.copy2(path, backup)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("[Config][OK] Kuveyt 2B/Arsa/İş Yeri exact family kuralları eklendi.")
    print("[Config] Yedek:", backup)
    return backup


def _sync_sqlite_rules(
    con: sqlite3.Connection,
    product_id: int,
    rules: dict[str, Any],
) -> None:
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
               (product_id,category_key,category_label,min_amount,max_amount,
                min_inclusive,max_inclusive,max_installments,max_maturity_months,
                condition_text,source_text,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                product_id,
                row.get("category_key"),
                row.get("category_label"),
                row.get("min_amount"),
                row.get("max_amount"),
                int(bool(row.get("min_inclusive"))),
                int(bool(row.get("max_inclusive", True))),
                row.get("max_installments"),
                row.get("max_maturity_months"),
                row.get("condition_text"),
                row.get("source_text"),
                NOW,
            ),
        )

    for row in rules.get("amount_maturity_rules", []):
        if row.get("max_maturity_months") is None:
            continue
        con.execute(
            """INSERT INTO live_product_amount_maturity_rules
               (product_id,min_amount,max_amount,min_inclusive,max_inclusive,
                max_maturity_months,source_text,updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                product_id,
                row.get("min_amount"),
                row.get("max_amount"),
                int(bool(row.get("min_inclusive"))),
                int(bool(row.get("max_inclusive", True))),
                row.get("max_maturity_months"),
                row.get("source_text"),
                NOW,
            ),
        )

    for row in rules.get("pricing_tiers", []):
        if row.get("maturity_months") is None:
            continue
        con.execute(
            """INSERT INTO live_product_pricing_tiers
               (product_id,pricing_variant,financing_amount,maturity_months,
                profit_share_rate,allocation_fee_rate,monthly_total_cost_rate,
                annual_total_cost_rate,source_text,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                product_id,
                row.get("pricing_variant") or "Standart",
                row.get("financing_amount"),
                row.get("maturity_months"),
                row.get("profit_share_rate"),
                row.get("allocation_fee_rate"),
                row.get("monthly_total_cost_rate"),
                row.get("annual_total_cost_rate"),
                row.get("source_text"),
                NOW,
            ),
        )

    for row in rules.get("fee_rules", []):
        con.execute(
            """INSERT INTO live_product_fee_rules
               (product_id,fee_type,fee_label,waived,amount,rate,note,updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                product_id,
                row.get("fee_type"),
                row.get("fee_label"),
                int(bool(row.get("waived"))),
                row.get("amount"),
                row.get("rate"),
                row.get("note"),
                NOW,
            ),
        )

    for row in rules.get("offer_rules", []):
        con.execute(
            """INSERT INTO live_product_offer_rules
               (product_id,rule_type,rule_label,min_amount,max_amount,min_inclusive,
                max_inclusive,max_installments,max_maturity_months,interest_free,
                condition_text,source_text,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                product_id,
                row.get("rule_type") or "product_offer",
                row.get("rule_label") or "Ürüne Özel Finansman Koşulu",
                row.get("min_amount"),
                row.get("max_amount"),
                int(bool(row.get("min_inclusive"))),
                int(bool(row.get("max_inclusive", True))),
                row.get("max_installments"),
                row.get("max_maturity_months"),
                int(bool(row.get("interest_free"))),
                row.get("condition_text"),
                row.get("source_text"),
                NOW,
            ),
        )


def _reclassified_rules(current: object, cfg: dict[str, Any]) -> dict[str, Any]:
    rules = _load_rules(current)
    rules["fee_rules"] = [
        row for row in rules["fee_rules"]
        if str(row.get("fee_type") or "").casefold() != "allocation"
        and "tahsis" not in str(row.get("fee_label") or "").casefold()
        and str(row.get("fee_type") or "").casefold() != "general_expense"
    ]
    rules["fee_rules"].append(
        {
            "fee_type": "allocation",
            "fee_label": cfg["allocation_fee_label"],
            "waived": False,
            "amount": None,
            "rate": cfg["allocation_fee_rate"],
            "note": (
                "Resmî kaynakta ticari/gayrimenkul finansmanı için tahsis ücreti "
                f"azami %{cfg['allocation_fee_rate']:.2f} olarak yayımlanır. "
                f"Kaynak: {cfg['source']}"
            ),
        }
    )
    return rules


def repair_sqlite() -> tuple[int, int, Path | None]:
    db = PROJECT_ROOT / "data" / "campaigns.db"
    if not db.exists():
        print("[SQLite] campaigns.db bulunamadı; atlandı.")
        return 0, 0, None

    backup_dir = PROJECT_ROOT / "data" / "backups" / "housing_comparison_v2"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"campaigns_before_housing_comparison_v2_{stamp}.db"
    shutil.copy2(db, backup)
    print("[SQLite] Yedek:", backup)

    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    audited = 0
    reclassified = 0
    try:
        rows = con.execute(
            """SELECT product_id,bank_name,product_family_key,product_family,
                      product_name,maximum_maturity_months,maximum_financing_ratio,
                      financing_ratio_rules_text,housing_first_home_rules_text,
                      housing_additional_home_rules_text,housing_finance_rules_json,
                      finance_rules_json
               FROM live_standard_product_details
               WHERE bank_name IN ('Albaraka Türk','Dünya Katılım','Kuveyt Türk','Türkiye Finans')"""
        ).fetchall()

        for row in rows:
            key = (row["bank_name"], normalize_product_name(row["product_name"]))
            pid = int(row["product_id"])

            if key in RECLASSIFIED_PRODUCTS:
                cfg = RECLASSIFIED_PRODUCTS[key]
                rules = _reclassified_rules(row["finance_rules_json"], cfg)
                con.execute(
                    """UPDATE live_standard_product_details SET
                       product_family_key=?, product_family=?,
                       maximum_maturity_months=?, maximum_financing_ratio=?,
                       financing_ratio_rules_text=?,
                       housing_first_home_rules_text=NULL,
                       housing_additional_home_rules_text=NULL,
                       housing_finance_rules_json=NULL,
                       finance_rules_json=?
                       WHERE product_id=?""",
                    (
                        cfg["family_key"],
                        cfg["family_name"],
                        cfg["maximum_maturity_months"],
                        cfg["maximum_financing_ratio"],
                        cfg["financing_ratio_rules_text"],
                        json.dumps(rules, ensure_ascii=False, sort_keys=True),
                        pid,
                    ),
                )
                _sync_sqlite_rules(con, pid, rules)
                reclassified += 1
                print(f"[SQLite][FAMILY] {key[1]} -> {cfg['family_name']}")
                continue

            if key not in VERIFIED_FEES and key not in VERIFIED_OFFERS and key not in {
                ("Albaraka Türk", "Konut Finansmanı"),
                ("Dünya Katılım", "Konut Finansmanı"),
                ("Kuveyt Türk", "Konut Finansmanı"),
                ("Kuveyt Türk", "İlk Evim Konut Finansmanı"),
                ("Kuveyt Türk", "Yeşil Konut Finansmanı"),
                ("Kuveyt Türk", "Gurbetten Sılaya Gayrimenkul Finansmanı"),
                ("Türkiye Finans", "Konut Finansmanı (Konut Kredisi)"),
            }:
                continue

            raw = dict(row)
            raw["product_name"] = normalize_product_name(row["product_name"])
            patched = apply_verified_housing_product_overrides(raw)
            rules = _load_rules(patched.get("finance_rules_json"))
            rules = _clean_verified_rules(rules, key)
            patched["finance_rules_json"] = json.dumps(
                rules, ensure_ascii=False, sort_keys=True
            )

            con.execute(
                """UPDATE live_standard_product_details SET
                   maximum_maturity_months=?, maximum_financing_ratio=?,
                   financing_ratio_rules_text=?, housing_first_home_rules_text=?,
                   housing_additional_home_rules_text=?, housing_finance_rules_json=?,
                   finance_rules_json=?
                   WHERE product_id=?""",
                (
                    patched.get("maximum_maturity_months"),
                    patched.get("maximum_financing_ratio"),
                    patched.get("financing_ratio_rules_text"),
                    patched.get("housing_first_home_rules_text"),
                    patched.get("housing_additional_home_rules_text"),
                    patched.get("housing_finance_rules_json"),
                    patched.get("finance_rules_json"),
                    pid,
                ),
            )
            _sync_sqlite_rules(con, pid, rules)
            audited += 1
            print(f"[SQLite][AUDIT] {key[0]} | {key[1]}")

        con.commit()
    finally:
        con.close()

    return audited, reclassified, backup


def _pg_sync_rules(cur, product_id: int, rules: dict[str, Any]) -> None:
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
               (product_id,category_key,category_label,min_amount,max_amount,
                min_inclusive,max_inclusive,max_installments,max_maturity_months,
                condition_text,source_text,updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
            (
                product_id,row.get("category_key"),row.get("category_label"),
                row.get("min_amount"),row.get("max_amount"),bool(row.get("min_inclusive")),
                bool(row.get("max_inclusive",True)),row.get("max_installments"),
                row.get("max_maturity_months"),row.get("condition_text"),row.get("source_text"),
            ),
        )

    for row in rules.get("amount_maturity_rules", []):
        if row.get("max_maturity_months") is None:
            continue
        cur.execute(
            """INSERT INTO product_amount_maturity_rules
               (product_id,min_amount,max_amount,min_inclusive,max_inclusive,
                max_maturity_months,source_text,updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())""",
            (
                product_id,row.get("min_amount"),row.get("max_amount"),
                bool(row.get("min_inclusive")),bool(row.get("max_inclusive",True)),
                row.get("max_maturity_months"),row.get("source_text"),
            ),
        )

    for row in rules.get("pricing_tiers", []):
        if row.get("maturity_months") is None:
            continue
        cur.execute(
            """INSERT INTO product_pricing_tiers
               (product_id,pricing_variant,financing_amount,maturity_months,
                profit_share_rate,allocation_fee_rate,monthly_total_cost_rate,
                annual_total_cost_rate,source_text,updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
            (
                product_id,row.get("pricing_variant") or "Standart",row.get("financing_amount"),
                row.get("maturity_months"),row.get("profit_share_rate"),
                row.get("allocation_fee_rate"),row.get("monthly_total_cost_rate"),
                row.get("annual_total_cost_rate"),row.get("source_text"),
            ),
        )

    for row in rules.get("fee_rules", []):
        cur.execute(
            """INSERT INTO product_fee_rules
               (product_id,fee_type,fee_label,waived,amount,rate,note,updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())""",
            (
                product_id,row.get("fee_type"),row.get("fee_label"),bool(row.get("waived")),
                row.get("amount"),row.get("rate"),row.get("note"),
            ),
        )

    for row in rules.get("offer_rules", []):
        cur.execute(
            """INSERT INTO product_offer_rules
               (product_id,rule_type,rule_label,min_amount,max_amount,min_inclusive,
                max_inclusive,max_installments,max_maturity_months,interest_free,
                condition_text,source_text,updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())""",
            (
                product_id,row.get("rule_type") or "product_offer",
                row.get("rule_label") or "Ürüne Özel Finansman Koşulu",row.get("min_amount"),
                row.get("max_amount"),bool(row.get("min_inclusive")),
                bool(row.get("max_inclusive",True)),row.get("max_installments"),
                row.get("max_maturity_months"),bool(row.get("interest_free")),
                row.get("condition_text"),row.get("source_text"),
            ),
        )


def repair_postgres() -> tuple[int, int]:
    dsn = os.getenv("POSTGRES_DSN", "").strip()
    if not dsn:
        print("[PostgreSQL] POSTGRES_DSN tanımlı değil; atlandı.")
        return 0, 0

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            'psycopg kurulu değil: python -m pip install "psycopg[binary]"'
        ) from exc

    audited = 0
    reclassified = 0
    with psycopg.connect(dsn) as con:
        with con.cursor() as cur:
            cur.execute("SET search_path TO bansa, public")
            cur.execute(
                "ALTER TABLE bansa.product_pricing_tiers "
                "ADD COLUMN IF NOT EXISTS financing_amount NUMERIC(18,2)"
            )

            # Make sure destination families exist.
            for cfg in RECLASSIFIED_PRODUCTS.values():
                cur.execute(
                    """INSERT INTO product_families (family_key,family_name)
                       VALUES (%s,%s)
                       ON CONFLICT(family_key) DO UPDATE SET family_name=EXCLUDED.family_name""",
                    (cfg["family_key"], cfg["family_name"]),
                )

            cur.execute(
                """SELECT p.id,b.name,p.product_name,f.family_key,f.family_name,
                          p.maximum_maturity_months,p.maximum_financing_ratio,
                          p.financing_ratio_rules_text,p.housing_first_home_rules_text,
                          p.housing_additional_home_rules_text,p.housing_finance_rules,
                          p.finance_rules
                   FROM standard_products p
                   JOIN banks b ON b.id=p.bank_id
                   JOIN product_families f ON f.id=p.family_id
                   WHERE p.is_current=TRUE
                     AND b.name IN ('Albaraka Türk','Dünya Katılım','Kuveyt Türk','Türkiye Finans')"""
            )
            rows = cur.fetchall()

            for row in rows:
                (
                    pid,bank,product_name,family_key,family_name,max_maturity,max_ratio,
                    ratio_text,first_text,additional_text,housing_json,finance_rules,
                ) = row
                key = (bank, normalize_product_name(product_name))

                if key in RECLASSIFIED_PRODUCTS:
                    cfg = RECLASSIFIED_PRODUCTS[key]
                    rules = _reclassified_rules(finance_rules, cfg)
                    cur.execute(
                        "SELECT id FROM product_families WHERE family_key=%s",
                        (cfg["family_key"],),
                    )
                    family_id = cur.fetchone()[0]
                    cur.execute(
                        """UPDATE standard_products SET
                           family_id=%s, maximum_maturity_months=%s,
                           maximum_financing_ratio=%s, financing_ratio_rules_text=%s,
                           housing_first_home_rules_text=NULL,
                           housing_additional_home_rules_text=NULL,
                           housing_finance_rules=NULL,
                           finance_rules=%s::jsonb, updated_at=NOW()
                           WHERE id=%s""",
                        (
                            family_id,cfg["maximum_maturity_months"],
                            cfg["maximum_financing_ratio"],cfg["financing_ratio_rules_text"],
                            json.dumps(rules,ensure_ascii=False),pid,
                        ),
                    )
                    _pg_sync_rules(cur, int(pid), rules)
                    reclassified += 1
                    print(f"[PostgreSQL][FAMILY] {key[1]} -> {cfg['family_name']}")
                    continue

                actual_keys = {
                    ("Albaraka Türk", "Konut Finansmanı"),
                    ("Dünya Katılım", "Konut Finansmanı"),
                    ("Kuveyt Türk", "Konut Finansmanı"),
                    ("Kuveyt Türk", "İlk Evim Konut Finansmanı"),
                    ("Kuveyt Türk", "Yeşil Konut Finansmanı"),
                    ("Kuveyt Türk", "Gurbetten Sılaya Gayrimenkul Finansmanı"),
                    ("Türkiye Finans", "Konut Finansmanı (Konut Kredisi)"),
                }
                if key not in actual_keys:
                    continue

                raw = {
                    "bank_name": bank,
                    "product_name": normalize_product_name(product_name),
                    "maximum_maturity_months": max_maturity,
                    "maximum_financing_ratio": max_ratio,
                    "financing_ratio_rules_text": ratio_text,
                    "housing_first_home_rules_text": first_text,
                    "housing_additional_home_rules_text": additional_text,
                    "housing_finance_rules_json": (
                        json.dumps(housing_json,ensure_ascii=False)
                        if isinstance(housing_json,(dict,list))
                        else housing_json
                    ),
                    "finance_rules_json": (
                        json.dumps(finance_rules,ensure_ascii=False)
                        if isinstance(finance_rules,(dict,list))
                        else finance_rules
                    ),
                }
                patched = apply_verified_housing_product_overrides(raw)
                rules = _load_rules(patched.get("finance_rules_json"))
                rules = _clean_verified_rules(rules, key)

                housing_value = patched.get("housing_finance_rules_json")
                cur.execute(
                    """UPDATE standard_products SET
                       maximum_maturity_months=%s, maximum_financing_ratio=%s,
                       financing_ratio_rules_text=%s, housing_first_home_rules_text=%s,
                       housing_additional_home_rules_text=%s,
                       housing_finance_rules=%s::jsonb, finance_rules=%s::jsonb,
                       updated_at=NOW()
                       WHERE id=%s""",
                    (
                        patched.get("maximum_maturity_months"),
                        patched.get("maximum_financing_ratio"),
                        patched.get("financing_ratio_rules_text"),
                        patched.get("housing_first_home_rules_text"),
                        patched.get("housing_additional_home_rules_text"),
                        housing_value,
                        json.dumps(rules,ensure_ascii=False),
                        pid,
                    ),
                )
                _pg_sync_rules(cur, int(pid), rules)
                audited += 1
                print(f"[PostgreSQL][AUDIT] {bank} | {key[1]}")

        con.commit()

    return audited, reclassified


def main() -> int:
    print("=" * 96)
    print("BANSA — KONUT FİNANSMANI KARŞILAŞTIRMA / VERİ KALİTESİ REPAIR V2")
    print("=" * 96)

    _patch_config()
    sqlite_audited, sqlite_reclassified, sqlite_backup = repair_sqlite()
    pg_audited, pg_reclassified = repair_postgres()

    print("\nSONUÇ")
    print("SQLite audited housing ürün:", sqlite_audited)
    print("SQLite yeniden sınıflandırılan:", sqlite_reclassified)
    print("PostgreSQL audited housing ürün:", pg_audited)
    print("PostgreSQL yeniden sınıflandırılan:", pg_reclassified)
    if sqlite_backup:
        print("SQLite yedek:", sqlite_backup)

    if sqlite_audited == 0:
        return 2
    if os.getenv("POSTGRES_DSN", "").strip() and pg_audited == 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
