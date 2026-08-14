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
                updated_at
            )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            d.product_name,
            d.product_family,
            d.scope,
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

            totals["products"] += 1
            for key, value in counts.items():
                totals[key] += value
            totals["feature"] += feature_count

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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
