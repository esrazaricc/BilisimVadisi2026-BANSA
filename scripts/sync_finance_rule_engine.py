from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.qualitative_feature_extractor import (
    FEATURE_LABELS,
    ProductFeature,
    extract_qualitative_features,
)
from src.albaraka_standard_product_overrides import (
    ALBARAKA_REBUILD_FEATURE_KEYS,
    albaraka_feature_overrides,
)
from src.finance_evidence import annotate_pricing_rows, fact_evidence_record


DEFAULT_DB = Path("data") / "campaigns.db"


def now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS
        live_product_category_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            category_key TEXT NOT NULL,
            category_label TEXT NOT NULL,
            min_amount REAL,
            max_amount REAL,
            min_inclusive INTEGER NOT NULL DEFAULT 0,
            max_inclusive INTEGER NOT NULL DEFAULT 1,
            max_installments INTEGER,
            max_maturity_months INTEGER,
            condition_text TEXT,
            source_text TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(product_id)
                REFERENCES live_campaigns(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS
        live_product_amount_maturity_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            min_amount REAL,
            max_amount REAL,
            min_inclusive INTEGER NOT NULL DEFAULT 0,
            max_inclusive INTEGER NOT NULL DEFAULT 1,
            max_maturity_months INTEGER NOT NULL,
            source_text TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(product_id)
                REFERENCES live_campaigns(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS
        live_product_pricing_tiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            pricing_variant TEXT,
            financing_amount REAL,
            maturity_months INTEGER NOT NULL,
            profit_share_rate REAL,
            allocation_fee_rate REAL,
            monthly_total_cost_rate REAL,
            annual_total_cost_rate REAL,
            source_text TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(product_id)
                REFERENCES live_campaigns(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS
        live_product_fee_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            fee_type TEXT NOT NULL,
            fee_label TEXT NOT NULL,
            waived INTEGER NOT NULL DEFAULT 0,
            amount REAL,
            rate REAL,
            note TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(product_id)
                REFERENCES live_campaigns(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS
        live_product_offer_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            rule_type TEXT NOT NULL,
            rule_label TEXT NOT NULL,
            min_amount REAL,
            max_amount REAL,
            min_inclusive INTEGER NOT NULL DEFAULT 0,
            max_inclusive INTEGER NOT NULL DEFAULT 1,
            max_installments INTEGER,
            max_maturity_months INTEGER,
            interest_free INTEGER NOT NULL DEFAULT 0,
            condition_text TEXT,
            source_text TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(product_id)
                REFERENCES live_campaigns(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS
        live_finance_fact_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            fact_key TEXT NOT NULL,
            value_text TEXT,
            value_numeric REAL,
            value_type TEXT NOT NULL,
            source_type TEXT NOT NULL,
            conditions TEXT,
            source_url TEXT,
            source_text TEXT,
            verification_status TEXT NOT NULL DEFAULT 'verified',
            updated_at TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES live_campaigns(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_finance_fact_evidence_product
        ON live_finance_fact_evidence(product_id);

        CREATE INDEX IF NOT EXISTS idx_finance_fact_evidence_key
        ON live_finance_fact_evidence(fact_key);

        CREATE TABLE IF NOT EXISTS
        live_product_features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            feature_key TEXT NOT NULL,
            feature_label TEXT NOT NULL,
            feature_value TEXT NOT NULL,
            source_text TEXT,
            extraction_method TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(product_id)
                REFERENCES live_campaigns(id)
                ON DELETE CASCADE,
            UNIQUE(product_id, feature_key)
        );

        CREATE INDEX IF NOT EXISTS
        idx_product_features_product
        ON live_product_features(product_id);

        CREATE INDEX IF NOT EXISTS
        idx_product_features_key
        ON live_product_features(feature_key);

        CREATE INDEX IF NOT EXISTS
        idx_product_category_rules_product
        ON live_product_category_rules(product_id);

        CREATE INDEX IF NOT EXISTS
        idx_product_category_rules_key
        ON live_product_category_rules(category_key);

        CREATE INDEX IF NOT EXISTS
        idx_product_amount_maturity_product
        ON live_product_amount_maturity_rules(product_id);

        CREATE INDEX IF NOT EXISTS
        idx_product_pricing_tiers_product
        ON live_product_pricing_tiers(product_id);

        CREATE INDEX IF NOT EXISTS
        idx_product_fee_rules_product
        ON live_product_fee_rules(product_id);


        CREATE INDEX IF NOT EXISTS
        idx_product_offer_rules_product
        ON live_product_offer_rules(product_id);
        """
    )

    pricing_columns = {
        row[1]
        for row in con.execute(
            "PRAGMA table_info(live_product_pricing_tiers)"
        ).fetchall()
    }

    if "pricing_variant" not in pricing_columns:
        con.execute(
            "ALTER TABLE live_product_pricing_tiers "
            "ADD COLUMN pricing_variant TEXT"
        )

    if "financing_amount" not in pricing_columns:
        con.execute(
            "ALTER TABLE live_product_pricing_tiers "
            "ADD COLUMN financing_amount REAL"
        )

    for column_name, column_type in (
        ("value_type", "TEXT"),
        ("source_type", "TEXT"),
        ("conditions", "TEXT"),
        ("source_url", "TEXT"),
    ):
        if column_name not in pricing_columns:
            con.execute(
                f"ALTER TABLE live_product_pricing_tiers ADD COLUMN {column_name} {column_type}"
            )


def sync_product_rules(
    con: sqlite3.Connection,
    product_id: int,
    rules: dict,
    timestamp: str,
) -> dict[str, int]:
    counts = {
        "category": 0,
        "amount_maturity": 0,
        "pricing": 0,
        "fee": 0,
        "offer": 0,
        "feature": 0,
    }

    con.execute(
        "DELETE FROM live_product_category_rules "
        "WHERE product_id=?",
        (product_id,),
    )
    con.execute(
        "DELETE FROM live_product_amount_maturity_rules "
        "WHERE product_id=?",
        (product_id,),
    )
    con.execute(
        "DELETE FROM live_product_pricing_tiers "
        "WHERE product_id=?",
        (product_id,),
    )
    con.execute(
        "DELETE FROM live_product_fee_rules "
        "WHERE product_id=?",
        (product_id,),
    )
    con.execute(
        "DELETE FROM live_product_offer_rules "
        "WHERE product_id=?",
        (product_id,),
    )

    for row in rules.get("category_rules", []):
        con.execute(
            """
            INSERT INTO live_product_category_rules (
                product_id,
                category_key,
                category_label,
                min_amount,
                max_amount,
                min_inclusive,
                max_inclusive,
                max_installments,
                max_maturity_months,
                condition_text,
                source_text,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                row.get("category_key"),
                row.get("category_label"),
                row.get("min_amount"),
                row.get("max_amount"),
                1 if row.get("min_inclusive") else 0,
                1 if row.get("max_inclusive", True) else 0,
                row.get("max_installments"),
                row.get("max_maturity_months"),
                row.get("condition_text"),
                row.get("source_text"),
                timestamp,
            ),
        )
        counts["category"] += 1

    for row in rules.get("amount_maturity_rules", []):
        con.execute(
            """
            INSERT INTO live_product_amount_maturity_rules (
                product_id,
                min_amount,
                max_amount,
                min_inclusive,
                max_inclusive,
                max_maturity_months,
                source_text,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                row.get("min_amount"),
                row.get("max_amount"),
                1 if row.get("min_inclusive") else 0,
                1 if row.get("max_inclusive", True) else 0,
                row.get("max_maturity_months"),
                row.get("source_text"),
                timestamp,
            ),
        )
        counts["amount_maturity"] += 1

    for row in rules.get("pricing_tiers", []):
        con.execute(
            """
            INSERT INTO live_product_pricing_tiers (
                product_id,
                pricing_variant,
                financing_amount,
                maturity_months,
                profit_share_rate,
                allocation_fee_rate,
                monthly_total_cost_rate,
                annual_total_cost_rate,
                source_text,
                value_type,
                source_type,
                conditions,
                source_url,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                row.get("pricing_variant", "Standart"),
                row.get("financing_amount"),
                row.get("maturity_months"),
                row.get("profit_share_rate"),
                row.get("allocation_fee_rate"),
                row.get("monthly_total_cost_rate"),
                row.get("annual_total_cost_rate"),
                row.get("source_text"),
                row.get("value_type", "exact"),
                row.get("source_type", "official_pricing_table"),
                row.get("conditions"),
                row.get("source_url"),
                timestamp,
            ),
        )
        counts["pricing"] += 1

    for row in rules.get("fee_rules", []):
        con.execute(
            """
            INSERT INTO live_product_fee_rules (
                product_id,
                fee_type,
                fee_label,
                waived,
                amount,
                rate,
                note,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                row.get("fee_type"),
                row.get("fee_label"),
                1 if row.get("waived") else 0,
                row.get("amount"),
                row.get("rate"),
                row.get("note"),
                timestamp,
            ),
        )
        counts["fee"] += 1

    for row in rules.get("offer_rules", []):
        con.execute(
            """
            INSERT INTO live_product_offer_rules (
                product_id,
                rule_type,
                rule_label,
                min_amount,
                max_amount,
                min_inclusive,
                max_inclusive,
                max_installments,
                max_maturity_months,
                interest_free,
                condition_text,
                source_text,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                row.get("rule_type", "product_offer"),
                row.get(
                    "rule_label",
                    "Ürüne Özel Finansman Koşulu",
                ),
                row.get("min_amount"),
                row.get("max_amount"),
                1 if row.get("min_inclusive") else 0,
                1 if row.get("max_inclusive", True) else 0,
                row.get("max_installments"),
                row.get("max_maturity_months"),
                1 if row.get("interest_free") else 0,
                row.get("condition_text"),
                row.get("source_text"),
                timestamp,
            ),
        )
        counts["offer"] += 1

    return counts




def sync_product_evidence(
    con: sqlite3.Connection,
    *,
    product_id: int,
    bank_name: str,
    product_name: str,
    source_url: str,
    detail_row: sqlite3.Row | dict,
    rules: dict,
    timestamp: str,
) -> int:
    """Finansal karar alanlarının kanıt metadata'sını normalize eder.

    NULL değer için 0 üretmez; yalnız kaynakta bulunan gerçek değerleri yazar.
    """
    con.execute("DELETE FROM live_finance_fact_evidence WHERE product_id=?", (product_id,))
    records: list[dict] = []

    def add(**kwargs):
        try:
            records.append(fact_evidence_record(**kwargs))
        except ValueError:
            return

    top_numeric = (
        ("minimum_financing_amount", "minimum", "Asgari finansman tutarı"),
        ("maximum_financing_amount", "maximum", "Azami finansman tutarı"),
        ("maximum_maturity_months", "maximum", "Azami vade (ay)"),
        ("profit_share_rate", "exact", "Ürün seviyesi kâr payı"),
        ("maximum_financing_ratio", "maximum", "Azami finansman oranı"),
        ("shopping_general_limit_amount", "maximum", "Alışveriş genel limit"),
        ("shopping_general_max_maturity_months", "maximum", "Alışveriş azami vade (ay)"),
    )
    for field, value_type, label in top_numeric:
        value = detail_row[field] if field in detail_row.keys() else None
        if value is None:
            continue
        add(
            fact_key=field,
            value_text=label,
            value_numeric=value,
            value_type=value_type,
            source_type="product_page",
            source_url=source_url,
        )

    for idx, row in enumerate(rules.get("amount_maturity_rules", []), start=1):
        add(
            fact_key=f"amount_maturity_rule:{idx}",
            value_text=f"Azami vade {row.get('max_maturity_months')} ay",
            value_numeric=row.get("max_maturity_months"),
            value_type="maximum",
            source_type="product_page",
            conditions=(
                f"min={row.get('min_amount')}; max={row.get('max_amount')}; "
                f"min_inclusive={bool(row.get('min_inclusive'))}; max_inclusive={bool(row.get('max_inclusive', True))}"
            ),
            source_url=source_url,
            source_text=row.get("source_text"),
        )

    for idx, row in enumerate(rules.get("category_rules", []), start=1):
        if row.get("max_installments") is not None:
            add(
                fact_key=f"category_installment_rule:{idx}",
                value_text=f"{row.get('category_label')} · azami {row.get('max_installments')} taksit",
                value_numeric=row.get("max_installments"),
                value_type="maximum", source_type="product_page",
                conditions=row.get("condition_text"), source_url=source_url, source_text=row.get("source_text"),
            )
        if row.get("max_maturity_months") is not None:
            add(
                fact_key=f"category_maturity_rule:{idx}",
                value_text=f"{row.get('category_label')} · azami {row.get('max_maturity_months')} ay",
                value_numeric=row.get("max_maturity_months"),
                value_type="maximum", source_type="product_page",
                conditions=row.get("condition_text"), source_url=source_url, source_text=row.get("source_text"),
            )

    for idx, row in enumerate(rules.get("offer_rules", []), start=1):
        numeric = row.get("max_amount")
        if numeric is None:
            numeric = row.get("max_maturity_months")
        if numeric is None:
            numeric = row.get("max_installments")
        add(
            fact_key=f"offer_rule:{idx}",
            value_text=row.get("condition_text") or row.get("rule_label"),
            value_numeric=numeric,
            value_type="conditional_pricing" if row.get("interest_free") else "maximum",
            source_type="product_page",
            conditions=row.get("condition_text"), source_url=source_url, source_text=row.get("source_text"),
        )

    display_metadata = rules.get("display_metadata") if isinstance(rules.get("display_metadata"), dict) else {}
    for idx, vehicle in enumerate(display_metadata.get("vehicle_value_rules", []) or [], start=1):
        if vehicle.get("max_financing_ratio") is not None:
            add(
                fact_key=f"vehicle_financing_ratio_rule:{idx}",
                value_text=f"Azami finansman oranı %{vehicle.get('max_financing_ratio')}",
                value_numeric=vehicle.get("max_financing_ratio"),
                value_type="maximum", source_type="product_page",
                conditions=f"min_value={vehicle.get('min_value')}; max_value={vehicle.get('max_value')}; max_maturity_months={vehicle.get('max_maturity_months')}",
                source_url=source_url,
            )

    pricing = annotate_pricing_rows(
        rules.get("pricing_tiers", []),
        bank_name=bank_name,
        product_name=product_name,
        source_url=source_url,
    )
    for idx, row in enumerate(pricing, start=1):
        add(
            fact_key=f"pricing_tier:{idx}",
            value_text=(
                f"{row.get('pricing_variant') or 'Standart'} · {row.get('maturity_months')} ay"
            ),
            value_numeric=row.get("profit_share_rate"),
            value_type=row.get("value_type", "exact"),
            source_type=row.get("source_type", "official_pricing_table"),
            conditions=row.get("conditions"),
            source_url=row.get("source_url") or source_url,
            source_text=row.get("source_text"),
        )

    for idx, row in enumerate(rules.get("fee_rules", []), start=1):
        note = str(row.get("note") or "")
        note_key = note.casefold()
        fee_key = str(row.get("fee_type") or idx)
        source_type = (
            "official_fee_tariff"
            if any(token in note_key for token in ("ücret tablos", "ücret tarif", "ürün ve hizmet ücret"))
            else "product_page"
        )
        verification_status = "source_conflict" if "farklı değer" in note_key or "birbiriyle farklı" in note_key else "verified"

        if row.get("waived"):
            add(
                fact_key=f"fee_rule:{fee_key}:waived",
                value_text="Alınmıyor", value_numeric=None, value_type="exact",
                source_type=source_type, conditions=note or None, source_url=source_url,
                source_text=note or None, verification_status=verification_status,
            )

        if row.get("amount") is not None:
            if "örnek ödeme tablos" in note_key or "örnek" in note_key:
                amount_value_type = "example"
                amount_source_type = "example_payment_table"
            elif "asgari" in note_key:
                amount_value_type = "minimum"
                amount_source_type = source_type
            elif "azami" in note_key or "maksimum" in note_key:
                amount_value_type = "maximum"
                amount_source_type = source_type
            else:
                amount_value_type = "exact"
                amount_source_type = source_type
            add(
                fact_key=f"fee_rule:{fee_key}:amount",
                value_text=row.get("fee_label"), value_numeric=row.get("amount"),
                value_type=amount_value_type, source_type=amount_source_type,
                conditions=note or None, source_url=source_url, source_text=note or None,
                verification_status=verification_status,
            )

        if row.get("rate") is not None:
            rate_value_type = "maximum" if "azami" in note_key or "maksimum" in note_key else "exact"
            add(
                fact_key=f"fee_rule:{fee_key}:rate",
                value_text=row.get("fee_label"), value_numeric=row.get("rate"),
                value_type=rate_value_type, source_type=source_type,
                conditions=note or None, source_url=source_url, source_text=note or None,
                verification_status=verification_status,
            )

    for record in records:
        con.execute(
            """
            INSERT INTO live_finance_fact_evidence (
                product_id,fact_key,value_text,value_numeric,value_type,source_type,
                conditions,source_url,source_text,verification_status,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                product_id, record["fact_key"], record["value_text"], record["value_numeric"],
                record["value_type"], record["source_type"], record["conditions"],
                record["source_url"], record["source_text"], record["verification_status"], timestamp,
            ),
        )
    return len(records)

def sync_product_features(
    con: sqlite3.Connection,
    *,
    product_id: int,
    product_name: str,
    product_family: str,
    scope: str,
    clean_text: str,
    bank_name: str,
    timestamp: str,
) -> int:
    con.execute(
        "DELETE FROM live_product_features "
        "WHERE product_id=?",
        (product_id,),
    )

    # Güncel qualitative extractor imzası bank_name almaz.
    # Bankaya özel source-safe düzeltmeleri generic extraction sonrasında
    # uyguluyoruz; böylece mevcut global extractor lineage'ını bozmuyoruz.
    features = extract_qualitative_features(
        product_name=product_name,
        product_family=product_family,
        scope=scope,
        clean_text=clean_text,
    )

    if bank_name == "Albaraka Türk":
        overrides = albaraka_feature_overrides(
            product_name=product_name,
            product_family=product_family,
            scope=scope,
            clean_text=clean_text,
        )

        replace_keys = set(ALBARAKA_REBUILD_FEATURE_KEYS) | set(overrides)
        features = [
            feature for feature in features
            if feature.feature_key not in replace_keys
        ]

        extra_labels = {
            "transaction_limit": "İşlem / Limit",
            "cost_advantage": "Maliyet / Avantaj",
        }
        for feature_key, (feature_value, source_text) in overrides.items():
            features.append(
                ProductFeature(
                    feature_key=feature_key,
                    feature_label=FEATURE_LABELS.get(
                        feature_key,
                        extra_labels.get(feature_key, feature_key),
                    ),
                    feature_value=feature_value,
                    source_text=source_text,
                    extraction_method="albaraka_source_guardrail_v1",
                )
            )

    if bank_name == "Türkiye Finans" and product_name == "eXtra Limit":
        source_key = " ".join(str(clean_text or "").split()).casefold()
        required = (
            "standart taksit sayısına otomatik bölünür",
            "limit yeniden kullanıma açılır",
            "minimum taksitlendirme tutarı 100 tl",
        )
        if all(item in source_key for item in required):
            features = [
                feature for feature in features
                if feature.feature_key != "repayment_structure"
            ]
            features.append(
                ProductFeature(
                    feature_key="repayment_structure",
                    feature_label=FEATURE_LABELS["repayment_structure"],
                    feature_value=(
                        "Döner limit · Harcamalar standart taksit sayısına otomatik bölünür · "
                        "Taksit ödendikçe limit yeniden kullanıma açılır"
                    ),
                    source_text=(
                        "Harcamalar standart taksit sayısına otomatik bölünür; "
                        "eXtra Limit taksitleri ödendikçe limit yeniden kullanıma açılır."
                    ),
                    extraction_method="turkiye_finans_extra_limit_guardrail_v1",
                )
            )

    if bank_name == "Kuveyt Türk" and product_name == "Çatı GES Finansmanı" and str(scope).casefold() == "bireysel":
        features = [f for f in features if f.feature_key != "comparison_subtype"]
        features.append(
            ProductFeature(
                feature_key="comparison_subtype",
                feature_label="Alt Tür",
                feature_value="Sürdürülebilir / Enerji",
                source_text="Bireysel sürdürülebilir finansman ürünü: Çatı GES Finansmanı",
                extraction_method="finance_data_accuracy_v2",
            )
        )

    for feature in features:
        con.execute(
            """
            INSERT INTO live_product_features (
                product_id,
                feature_key,
                feature_label,
                feature_value,
                source_text,
                extraction_method,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_id,
                feature.feature_key,
                feature.feature_label,
                feature.feature_value,
                feature.source_text,
                feature.extraction_method,
                timestamp,
            ),
        )

    return len(features)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
    )
    parser.add_argument(
        "--bank",
        default=None,
    )
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")

    ensure_schema(con)

    columns = {
        row[1]
        for row in con.execute(
            "PRAGMA table_info(live_standard_product_details)"
        ).fetchall()
    }

    if "finance_rules_json" not in columns:
        raise RuntimeError(
            "finance_rules_json kolonu bulunamadı. "
            "Önce güncel sync_standard_products_to_db.py ile "
            "ürünleri yeniden senkronize edin."
        )

    sql = """
        SELECT
            c.id AS product_id,
            c.bank_name,
            c.source_url,
            d.product_name,
            d.product_family,
            d.scope,
            d.minimum_financing_amount,
            d.maximum_financing_amount,
            d.maximum_maturity_months,
            d.profit_share_rate,
            d.maximum_financing_ratio,
            d.shopping_general_limit_amount,
            d.shopping_general_max_maturity_months,
            c.clean_text,
            d.finance_rules_json
        FROM live_campaigns AS c
        JOIN live_standard_product_details AS d
            ON d.product_id = c.id
        WHERE c.record_kind='standard_product'
          AND c.is_current=1
    """
    params = []

    if args.bank:
        sql += " AND c.bank_name=?"
        params.append(args.bank)

    rows = con.execute(
        sql,
        params,
    ).fetchall()

    totals = {
        "products": 0,
        "category": 0,
        "amount_maturity": 0,
        "pricing": 0,
        "fee": 0,
        "offer": 0,
        "feature": 0,
        "evidence": 0,
    }
    timestamp = now_iso()

    with con:
        for row in rows:
            raw = row["finance_rules_json"]
            rules = (
                json.loads(raw)
                if raw
                else {}
            )

            rules["pricing_tiers"] = annotate_pricing_rows(
                rules.get("pricing_tiers", []),
                bank_name=row["bank_name"],
                product_name=row["product_name"],
                source_url=row["source_url"],
            )
            counts = sync_product_rules(
                con,
                int(row["product_id"]),
                rules,
                timestamp,
            )
            feature_count = sync_product_features(
                con,
                product_id=int(row["product_id"]),
                product_name=str(
                    row["product_name"] or ""
                ),
                product_family=str(
                    row["product_family"] or ""
                ),
                scope=str(
                    row["scope"] or ""
                ),
                clean_text=str(
                    row["clean_text"] or ""
                ),
                bank_name=str(
                    row["bank_name"] or ""
                ),
                timestamp=timestamp,
            )

            evidence_count = sync_product_evidence(
                con,
                product_id=int(row["product_id"]),
                bank_name=str(row["bank_name"] or ""),
                product_name=str(row["product_name"] or ""),
                source_url=str(row["source_url"] or ""),
                detail_row=row,
                rules=rules,
                timestamp=timestamp,
            )

            totals["products"] += 1
            for key, value in counts.items():
                totals[key] += value
            totals["feature"] += feature_count
            totals["evidence"] += evidence_count

    con.close()

    print("=" * 80)
    print("FİNANSMAN KURAL MOTORU SENKRONİZASYONU")
    print("=" * 80)
    if args.bank:
        print("Banka:", args.bank)
    print("Ürün:", totals["products"])
    print("Kategori kuralı:", totals["category"])
    print("Tutar-vade kuralı:", totals["amount_maturity"])
    print("Fiyatlama kademesi:", totals["pricing"])
    print("Masraf kuralı:", totals["fee"])
    print("Ürüne özel koşul:", totals["offer"])
    print("Nitel ürün özelliği:", totals["feature"])
    print("Finansal kanıt kaydı:", totals["evidence"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
