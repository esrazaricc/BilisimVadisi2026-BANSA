from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("data") / "campaigns.db"


REQUIRED_LIVE_COLUMNS = {
    "id",
    "bank_name",
    "source_url",
    "source_group",
    "title",
    "clean_text",
    "content_hash",
    "current_status",
    "listing_status",
    "fetch_status",
    "first_seen_at",
    "last_seen_at",
    "last_checked_at",
    "is_current",
    "removed_at",
    "created_at",
    "updated_at",
    "record_kind",
    "campaign_category",
    "comparison_eligible",
    "classification_confidence",
    "classification_reason",
}


TRACKED_FIELDS = (
    "product_family_key",
    "product_family",
    "product_name",
    "minimum_financing_amount",
    "maximum_financing_amount",
    "minimum_maturity_months",
    "maximum_maturity_months",
    "profit_share_rate",
    "profit_share_rate_text",
    "interest_free",
    "interest_free_text",
    "maturity_rules_text",
    "maturity_reference_upper_amount",
    "financing_ratio_rules_text",
    "maximum_financing_ratio",
    "housing_first_home_rules_text",
    "housing_additional_home_rules_text",
    "housing_finance_rules_json",
    "vehicle_finance_rules_text",
    "vehicle_age_rules_text",
    "shopping_general_limit_amount",
    "shopping_general_max_maturity_months",
    "shopping_finance_rules_text",
    "shopping_phone_rule_text",
    "shopping_tablet_max_maturity_months",
    "shopping_computer_max_maturity_months",
    "fee_waiver_text",
    "insurance_fee_waived",
    "allocation_fee_waived",
    "commission_fee_waived",
    "finance_rules_json",
)


def now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


def text_hash(value: str | None) -> str:
    return hashlib.sha256(
        str(value or "").encode("utf-8")
    ).hexdigest()


def table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }


def ensure_schema(
    connection: sqlite3.Connection,
) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS
        live_standard_product_details (
            product_id INTEGER PRIMARY KEY,
            bank_name TEXT NOT NULL,
            product_family_key TEXT NOT NULL,
            product_family TEXT NOT NULL,
            product_name TEXT NOT NULL,
            scope TEXT,
            source_page TEXT,
            minimum_financing_amount REAL,
            maximum_financing_amount REAL,
            minimum_maturity_months INTEGER,
            maximum_maturity_months INTEGER,
            profit_share_rate REAL,
            profit_share_rate_text TEXT,
            interest_free INTEGER,
            interest_free_text TEXT,
            maturity_rules_text TEXT,
            maturity_reference_upper_amount REAL,
            financing_ratio_rules_text TEXT,
            maximum_financing_ratio REAL,
            housing_first_home_rules_text TEXT,
            housing_additional_home_rules_text TEXT,
            housing_finance_rules_json TEXT,
            vehicle_finance_rules_text TEXT,
            vehicle_age_rules_text TEXT,
            shopping_general_limit_amount REAL,
            shopping_general_max_maturity_months INTEGER,
            shopping_finance_rules_text TEXT,
            shopping_phone_rule_text TEXT,
            shopping_tablet_max_maturity_months INTEGER,
            shopping_computer_max_maturity_months INTEGER,
            fee_waiver_text TEXT,
            insurance_fee_waived INTEGER,
            allocation_fee_waived INTEGER,
            commission_fee_waived INTEGER,
            finance_rules_json TEXT,
            checked_at TEXT,
            extracted_at TEXT NOT NULL,
            FOREIGN KEY(product_id)
                REFERENCES live_campaigns(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS
        live_standard_product_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            bank_name TEXT NOT NULL,
            product_family TEXT,
            product_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            change_type TEXT NOT NULL,
            changed_fields_json TEXT,
            before_json TEXT,
            after_json TEXT,
            detected_at TEXT NOT NULL,
            FOREIGN KEY(product_id)
                REFERENCES live_campaigns(id)
                ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS
        live_standard_product_scan_state (
            product_id INTEGER PRIMARY KEY,
            consecutive_missing_count INTEGER NOT NULL DEFAULT 0,
            last_seen_scan_at TEXT,
            last_missing_scan_at TEXT,
            possible_removed INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(product_id)
                REFERENCES live_campaigns(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS
        idx_standard_product_family
        ON live_standard_product_details(
            product_family_key,
            bank_name
        );

        CREATE INDEX IF NOT EXISTS
        idx_standard_product_bank
        ON live_standard_product_details(bank_name);

        CREATE INDEX IF NOT EXISTS
        idx_standard_product_changes_detected
        ON live_standard_product_changes(detected_at);

        CREATE INDEX IF NOT EXISTS
        idx_standard_product_changes_product
        ON live_standard_product_changes(product_id);
        """
    )

    detail_columns = table_columns(
        connection,
        "live_standard_product_details",
    )
    if "maturity_rules_text" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN maturity_rules_text TEXT"
        )
    if "maturity_reference_upper_amount" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN maturity_reference_upper_amount REAL"
        )
    if "financing_ratio_rules_text" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN financing_ratio_rules_text TEXT"
        )
    if "maximum_financing_ratio" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN maximum_financing_ratio REAL"
        )
    if "housing_first_home_rules_text" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN housing_first_home_rules_text TEXT"
        )
    if "housing_additional_home_rules_text" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN housing_additional_home_rules_text TEXT"
        )
    if "housing_finance_rules_json" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN housing_finance_rules_json TEXT"
        )
    if "vehicle_finance_rules_text" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN vehicle_finance_rules_text TEXT"
        )
    if "vehicle_age_rules_text" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN vehicle_age_rules_text TEXT"
        )
    if "shopping_general_limit_amount" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN shopping_general_limit_amount REAL"
        )
    if "shopping_general_max_maturity_months" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN shopping_general_max_maturity_months INTEGER"
        )
    if "shopping_finance_rules_text" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN shopping_finance_rules_text TEXT"
        )
    if "shopping_phone_rule_text" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN shopping_phone_rule_text TEXT"
        )
    if "shopping_tablet_max_maturity_months" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN shopping_tablet_max_maturity_months INTEGER"
        )
    if "shopping_computer_max_maturity_months" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN shopping_computer_max_maturity_months INTEGER"
        )
    if "fee_waiver_text" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN fee_waiver_text TEXT"
        )
    if "insurance_fee_waived" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN insurance_fee_waived INTEGER"
        )
    if "allocation_fee_waived" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN allocation_fee_waived INTEGER"
        )
    if "commission_fee_waived" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN commission_fee_waived INTEGER"
        )
    if "finance_rules_json" not in detail_columns:
        connection.execute(
            "ALTER TABLE live_standard_product_details "
            "ADD COLUMN finance_rules_json TEXT"
        )


def load_scan(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Tarama raporu bulunamadı: {path}"
        )

    data = json.loads(
        path.read_text(encoding="utf-8")
    )
    if not isinstance(data, dict):
        raise ValueError(
            "Tarama raporu JSON nesnesi olmalı."
        )
    return data


def validate_scan(
    data: dict[str, Any],
    *,
    allow_errors: bool,
) -> list[dict[str, Any]]:
    products = data.get("products", [])
    if not isinstance(products, list):
        raise ValueError(
            "Tarama raporundaki products alanı liste değil."
        )

    reported_count = int(
        data.get("product_count", len(products))
    )
    error_count = int(data.get("error_count", 0))

    if reported_count != len(products):
        raise ValueError(
            "product_count ile products uzunluğu eşleşmiyor."
        )

    if not products:
        raise RuntimeError(
            "Tarama sonucu 0 ürün. DB senkronizasyonu iptal edildi."
        )

    if error_count > 0 and not allow_errors:
        raise RuntimeError(
            f"Tarama {error_count} hata içeriyor. "
            "Eksik katalog DB'ye yazılmadı. "
            "Gerekirse --allow-errors kullanın."
        )

    bank_name = str(data.get("bank_name") or "").strip()
    if not bank_name:
        raise ValueError(
            "Tarama raporunda bank_name yok."
        )

    for product in products:
        if str(product.get("bank_name") or "").strip() != bank_name:
            raise ValueError(
                "Tarama raporunda farklı bankaya ait ürün bulundu."
            )
        if not str(product.get("url") or "").strip():
            raise ValueError(
                "source URL'si olmayan standart ürün bulundu."
            )
        if not str(product.get("product_name") or "").strip():
            raise ValueError(
                "Ürün adı olmayan standart ürün bulundu."
            )
        if not str(product.get("product_family") or "").strip():
            raise ValueError(
                "Finansman ailesi olmayan ürün bulundu."
            )

    return products


def backup_db(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = (
        db_path.parent
        / "backups"
        / f"campaigns_before_standard_product_sync_{stamp}.db"
    )
    backup.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(db_path, backup)
    return backup


def detail_snapshot(
    row: sqlite3.Row | None,
) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        field: row[field]
        for field in TRACKED_FIELDS
    }


def product_snapshot(
    product: dict[str, Any],
) -> dict[str, Any]:
    return {
        "product_family_key": str(
            product.get("product_family_key") or ""
        ),
        "product_family": str(
            product.get("product_family") or ""
        ),
        "product_name": str(
            product.get("product_name") or ""
        ),
        "minimum_financing_amount":
            product.get("minimum_financing_amount"),
        "maximum_financing_amount":
            product.get("maximum_financing_amount"),
        "minimum_maturity_months":
            product.get("minimum_maturity_months"),
        "maximum_maturity_months":
            product.get("maximum_maturity_months"),
        "profit_share_rate":
            product.get("profit_share_rate"),
        "profit_share_rate_text":
            product.get("profit_share_rate_text"),
        "interest_free":
            1 if product.get("interest_free") is True else 0,
        "interest_free_text":
            product.get("interest_free_text"),
        "maturity_rules_text":
            product.get("maturity_rules_text"),
        "maturity_reference_upper_amount":
            product.get("maturity_reference_upper_amount"),
        "financing_ratio_rules_text":
            product.get("financing_ratio_rules_text"),
        "maximum_financing_ratio":
            product.get("maximum_financing_ratio"),
        "housing_first_home_rules_text":
            product.get("housing_first_home_rules_text"),
        "housing_additional_home_rules_text":
            product.get("housing_additional_home_rules_text"),
        "housing_finance_rules_json":
            product.get("housing_finance_rules_json"),
        "vehicle_finance_rules_text":
            product.get("vehicle_finance_rules_text"),
        "vehicle_age_rules_text":
            product.get("vehicle_age_rules_text"),
        "shopping_general_limit_amount":
            product.get("shopping_general_limit_amount"),
        "shopping_general_max_maturity_months":
            product.get("shopping_general_max_maturity_months"),
        "shopping_finance_rules_text":
            product.get("shopping_finance_rules_text"),
        "shopping_phone_rule_text":
            product.get("shopping_phone_rule_text"),
        "shopping_tablet_max_maturity_months":
            product.get("shopping_tablet_max_maturity_months"),
        "shopping_computer_max_maturity_months":
            product.get("shopping_computer_max_maturity_months"),
        "fee_waiver_text":
            product.get("fee_waiver_text"),
        "insurance_fee_waived":
            1 if product.get("insurance_fee_waived") is True else 0,
        "allocation_fee_waived":
            1 if product.get("allocation_fee_waived") is True else 0,
        "commission_fee_waived":
            1 if product.get("commission_fee_waived") is True else 0,
        "finance_rules_json":
            product.get("finance_rules_json"),
    }


def changed_fields(
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> list[str]:
    if before is None:
        return list(TRACKED_FIELDS)

    return [
        field
        for field in TRACKED_FIELDS
        if before.get(field) != after.get(field)
    ]


def log_change(
    connection: sqlite3.Connection,
    *,
    product_id: int | None,
    bank_name: str,
    product_family: str | None,
    product_name: str,
    source_url: str,
    change_type: str,
    timestamp: str,
    fields: list[str] | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO live_standard_product_changes (
            product_id,
            bank_name,
            product_family,
            product_name,
            source_url,
            change_type,
            changed_fields_json,
            before_json,
            after_json,
            detected_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            product_id,
            bank_name,
            product_family,
            product_name,
            source_url,
            change_type,
            (
                json.dumps(fields, ensure_ascii=False)
                if fields
                else None
            ),
            (
                json.dumps(before, ensure_ascii=False)
                if before is not None
                else None
            ),
            (
                json.dumps(after, ensure_ascii=False)
                if after is not None
                else None
            ),
            timestamp,
        ),
    )


def upsert_product(
    connection: sqlite3.Connection,
    product: dict[str, Any],
    timestamp: str,
) -> tuple[str, int, list[str]]:
    source_url = str(product["url"]).strip()
    bank_name = str(product["bank_name"]).strip()
    product_name = str(product["product_name"]).strip()
    family = str(product["product_family"]).strip()
    clean_text = str(product.get("clean_text") or "").strip()
    content_hash = text_hash(clean_text)
    after = product_snapshot(product)

    existing = connection.execute(
        """
        SELECT id, record_kind, content_hash, is_current
        FROM live_campaigns
        WHERE source_url = ?
        LIMIT 1
        """,
        (source_url,),
    ).fetchone()

    before_detail = None
    if existing is not None:
        before_detail = connection.execute(
            """
            SELECT *
            FROM live_standard_product_details
            WHERE product_id = ?
            """,
            (int(existing["id"]),),
        ).fetchone()

    before = detail_snapshot(before_detail)
    fields = changed_fields(before, after)

    if existing is None:
        cursor = connection.execute(
            """
            INSERT INTO live_campaigns (
                bank_name,
                source_url,
                source_group,
                title,
                clean_text,
                content_hash,
                start_date,
                end_date,
                current_status,
                listing_status,
                fetch_status,
                first_seen_at,
                last_seen_at,
                last_checked_at,
                is_current,
                removed_at,
                created_at,
                updated_at,
                record_kind,
                campaign_category,
                comparison_eligible,
                classification_confidence,
                classification_reason
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, NULL, NULL,
                'active', 'active', 'success',
                ?, ?, ?, 1, NULL, ?, ?,
                'standard_product',
                'standard_product',
                1,
                1.0,
                ?
            )
            """,
            (
                bank_name,
                source_url,
                family,
                product_name,
                clean_text,
                content_hash,
                timestamp,
                timestamp,
                timestamp,
                timestamp,
                timestamp,
                (
                    "Resmî standart ürün kataloğundan "
                    "ürün olarak keşfedildi."
                ),
            ),
        )
        product_id = int(cursor.lastrowid)
        action = "created"
    else:
        product_id = int(existing["id"])
        existing_kind = str(
            existing["record_kind"] or ""
        )

        if existing_kind not in {
            "standard_product",
            "unclassified",
            "",
        }:
            raise RuntimeError(
                "URL çakışması: mevcut kayıt kampanya/başka tür. "
                f"ID={product_id}, record_kind={existing_kind}, "
                f"URL={source_url}"
            )

        was_current = int(existing["is_current"] or 0) == 1
        hash_changed = (
            str(existing["content_hash"] or "")
            != content_hash
        )

        if fields:
            action = "terms_changed"
        elif hash_changed:
            action = "content_changed"
        else:
            action = "unchanged"

        connection.execute(
            """
            UPDATE live_campaigns
            SET
                bank_name = ?,
                source_group = ?,
                title = ?,
                clean_text = ?,
                content_hash = ?,
                current_status = 'active',
                listing_status = 'active',
                fetch_status = 'success',
                last_seen_at = ?,
                last_checked_at = ?,
                is_current = 1,
                removed_at = NULL,
                updated_at = ?,
                record_kind = 'standard_product',
                campaign_category = 'standard_product',
                comparison_eligible = 1,
                classification_confidence = 1.0,
                classification_reason = ?
            WHERE id = ?
            """,
            (
                bank_name,
                family,
                product_name,
                clean_text,
                content_hash,
                timestamp,
                timestamp,
                timestamp,
                (
                    "Resmî standart ürün kataloğundan "
                    "ürün olarak keşfedildi."
                ),
                product_id,
            ),
        )

        if not was_current:
            action = "reactivated"

    connection.execute(
        """
        INSERT INTO live_standard_product_details (
            product_id,
            bank_name,
            product_family_key,
            product_family,
            product_name,
            scope,
            source_page,
            minimum_financing_amount,
            maximum_financing_amount,
            minimum_maturity_months,
            maximum_maturity_months,
            profit_share_rate,
            profit_share_rate_text,
            interest_free,
            interest_free_text,
            maturity_rules_text,
            maturity_reference_upper_amount,
            financing_ratio_rules_text,
            maximum_financing_ratio,
            housing_first_home_rules_text,
            housing_additional_home_rules_text,
            housing_finance_rules_json,
            vehicle_finance_rules_text,
            vehicle_age_rules_text,
            shopping_general_limit_amount,
            shopping_general_max_maturity_months,
            shopping_finance_rules_text,
            shopping_phone_rule_text,
            shopping_tablet_max_maturity_months,
            shopping_computer_max_maturity_months,
            fee_waiver_text,
            insurance_fee_waived,
            allocation_fee_waived,
            commission_fee_waived,
            finance_rules_json,
            checked_at,
            extracted_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT(product_id) DO UPDATE SET
            bank_name = excluded.bank_name,
            product_family_key =
                excluded.product_family_key,
            product_family =
                excluded.product_family,
            product_name =
                excluded.product_name,
            scope = excluded.scope,
            source_page =
                excluded.source_page,
            minimum_financing_amount =
                excluded.minimum_financing_amount,
            maximum_financing_amount =
                excluded.maximum_financing_amount,
            minimum_maturity_months =
                excluded.minimum_maturity_months,
            maximum_maturity_months =
                excluded.maximum_maturity_months,
            profit_share_rate =
                excluded.profit_share_rate,
            profit_share_rate_text =
                excluded.profit_share_rate_text,
            interest_free =
                excluded.interest_free,
            interest_free_text =
                excluded.interest_free_text,
            maturity_rules_text =
                excluded.maturity_rules_text,
            maturity_reference_upper_amount =
                excluded.maturity_reference_upper_amount,
            financing_ratio_rules_text =
                excluded.financing_ratio_rules_text,
            maximum_financing_ratio =
                excluded.maximum_financing_ratio,
            housing_first_home_rules_text =
                excluded.housing_first_home_rules_text,
            housing_additional_home_rules_text =
                excluded.housing_additional_home_rules_text,
            housing_finance_rules_json =
                excluded.housing_finance_rules_json,
            vehicle_finance_rules_text =
                excluded.vehicle_finance_rules_text,
            vehicle_age_rules_text =
                excluded.vehicle_age_rules_text,
            shopping_general_limit_amount =
                excluded.shopping_general_limit_amount,
            shopping_general_max_maturity_months =
                excluded.shopping_general_max_maturity_months,
            shopping_finance_rules_text =
                excluded.shopping_finance_rules_text,
            shopping_phone_rule_text =
                excluded.shopping_phone_rule_text,
            shopping_tablet_max_maturity_months =
                excluded.shopping_tablet_max_maturity_months,
            shopping_computer_max_maturity_months =
                excluded.shopping_computer_max_maturity_months,
            fee_waiver_text =
                excluded.fee_waiver_text,
            insurance_fee_waived =
                excluded.insurance_fee_waived,
            allocation_fee_waived =
                excluded.allocation_fee_waived,
            commission_fee_waived =
                excluded.commission_fee_waived,
            finance_rules_json =
                excluded.finance_rules_json,
            checked_at =
                excluded.checked_at,
            extracted_at =
                excluded.extracted_at
        """,
        (
            product_id,
            bank_name,
            after["product_family_key"],
            family,
            product_name,
            product.get("scope"),
            product.get("source_page"),
            after["minimum_financing_amount"],
            after["maximum_financing_amount"],
            after["minimum_maturity_months"],
            after["maximum_maturity_months"],
            after["profit_share_rate"],
            after["profit_share_rate_text"],
            after["interest_free"],
            after["interest_free_text"],
            after["maturity_rules_text"],
            after["maturity_reference_upper_amount"],
            after["financing_ratio_rules_text"],
            after["maximum_financing_ratio"],
            after["housing_first_home_rules_text"],
            after["housing_additional_home_rules_text"],
            after["housing_finance_rules_json"],
            after["vehicle_finance_rules_text"],
            after["vehicle_age_rules_text"],
            after["shopping_general_limit_amount"],
            after["shopping_general_max_maturity_months"],
            after["shopping_finance_rules_text"],
            after["shopping_phone_rule_text"],
            after["shopping_tablet_max_maturity_months"],
            after["shopping_computer_max_maturity_months"],
            after["fee_waiver_text"],
            after["insurance_fee_waived"],
            after["allocation_fee_waived"],
            after["commission_fee_waived"],
            after["finance_rules_json"],
            product.get("checked_at"),
            timestamp,
        ),
    )

    connection.execute(
        """
        INSERT INTO live_standard_product_scan_state (
            product_id,
            consecutive_missing_count,
            last_seen_scan_at,
            last_missing_scan_at,
            possible_removed
        )
        VALUES (?, 0, ?, NULL, 0)
        ON CONFLICT(product_id) DO UPDATE SET
            consecutive_missing_count = 0,
            last_seen_scan_at = excluded.last_seen_scan_at,
            last_missing_scan_at = NULL,
            possible_removed = 0
        """,
        (product_id, timestamp),
    )

    if action == "created":
        log_change(
            connection,
            product_id=product_id,
            bank_name=bank_name,
            product_family=family,
            product_name=product_name,
            source_url=source_url,
            change_type="new_product",
            timestamp=timestamp,
            fields=fields,
            before=None,
            after=after,
        )
    elif action == "terms_changed":
        log_change(
            connection,
            product_id=product_id,
            bank_name=bank_name,
            product_family=family,
            product_name=product_name,
            source_url=source_url,
            change_type="terms_changed",
            timestamp=timestamp,
            fields=fields,
            before=before,
            after=after,
        )
    elif action == "content_changed":
        log_change(
            connection,
            product_id=product_id,
            bank_name=bank_name,
            product_family=family,
            product_name=product_name,
            source_url=source_url,
            change_type="content_changed",
            timestamp=timestamp,
            fields=None,
            before=before,
            after=after,
        )
    elif action == "reactivated":
        log_change(
            connection,
            product_id=product_id,
            bank_name=bank_name,
            product_family=family,
            product_name=product_name,
            source_url=source_url,
            change_type="reactivated",
            timestamp=timestamp,
            fields=fields or None,
            before=before,
            after=after,
        )

    return action, product_id, fields


def update_missing_state(
    connection: sqlite3.Connection,
    *,
    bank_name: str,
    scanned_urls: set[str],
    timestamp: str,
    threshold: int,
) -> int:
    rows = connection.execute(
        """
        SELECT
            c.id,
            c.source_url,
            d.product_family,
            d.product_name,
            COALESCE(s.consecutive_missing_count, 0)
                AS missing_count,
            COALESCE(s.possible_removed, 0)
                AS possible_removed
        FROM live_campaigns AS c
        JOIN live_standard_product_details AS d
            ON d.product_id = c.id
        LEFT JOIN live_standard_product_scan_state AS s
            ON s.product_id = c.id
        WHERE c.record_kind = 'standard_product'
          AND c.bank_name = ?
        """,
        (bank_name,),
    ).fetchall()

    warned = 0

    for row in rows:
        if row["source_url"] in scanned_urls:
            continue

        new_count = int(row["missing_count"]) + 1
        possible_removed = 1 if new_count >= threshold else 0

        connection.execute(
            """
            INSERT INTO live_standard_product_scan_state (
                product_id,
                consecutive_missing_count,
                last_seen_scan_at,
                last_missing_scan_at,
                possible_removed
            )
            VALUES (?, ?, NULL, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                consecutive_missing_count =
                    excluded.consecutive_missing_count,
                last_missing_scan_at =
                    excluded.last_missing_scan_at,
                possible_removed =
                    excluded.possible_removed
            """,
            (
                int(row["id"]),
                new_count,
                timestamp,
                possible_removed,
            ),
        )

        if possible_removed and not int(row["possible_removed"]):
            warned += 1
            log_change(
                connection,
                product_id=int(row["id"]),
                bank_name=bank_name,
                product_family=row["product_family"],
                product_name=row["product_name"],
                source_url=row["source_url"],
                change_type="possible_removed",
                timestamp=timestamp,
            )

    return warned


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            Path("data")
            / "standard_products"
            / "dunya_katilim.json"
        ),
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
    )
    parser.add_argument(
        "--allow-errors",
        action="store_true",
    )
    parser.add_argument(
        "--missing-threshold",
        type=int,
        default=2,
    )
    args = parser.parse_args()

    data = load_scan(args.input)
    products = validate_scan(
        data,
        allow_errors=args.allow_errors,
    )

    if not args.db.exists():
        raise FileNotFoundError(
            f"Veritabanı bulunamadı: {args.db}"
        )

    backup = backup_db(args.db)

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")

    columns = table_columns(
        connection,
        "live_campaigns",
    )
    missing = REQUIRED_LIVE_COLUMNS - columns
    if missing:
        connection.close()
        raise RuntimeError(
            "live_campaigns şeması beklenen sürümde değil. "
            "Eksik kolonlar: "
            + ", ".join(sorted(missing))
        )

    ensure_schema(connection)

    timestamp = now_iso()
    counts = {
        "created": 0,
        "terms_changed": 0,
        "content_changed": 0,
        "reactivated": 0,
        "unchanged": 0,
    }

    scanned_urls = {
        str(product["url"]).strip()
        for product in products
    }

    with connection:
        for product in products:
            action, _, _ = upsert_product(
                connection,
                product,
                timestamp,
            )
            counts[action] += 1

        possible_removed = 0
        # Eksik katalog sonucunda yanlış alarm üretmemek için
        # yalnızca hatasız tam taramada missing kontrolü yapılır.
        if int(data.get("error_count", 0)) == 0:
            possible_removed = update_missing_state(
                connection,
                bank_name=str(data["bank_name"]),
                scanned_urls=scanned_urls,
                timestamp=timestamp,
                threshold=max(2, args.missing_threshold),
            )

    bank_name = str(data["bank_name"])

    total_current = connection.execute(
        """
        SELECT COUNT(*)
        FROM live_campaigns
        WHERE record_kind = 'standard_product'
          AND is_current = 1
        """
    ).fetchone()[0]

    bank_total = connection.execute(
        """
        SELECT COUNT(*)
        FROM live_campaigns
        WHERE record_kind = 'standard_product'
          AND is_current = 1
          AND bank_name = ?
        """,
        (bank_name,),
    ).fetchone()[0]

    connection.close()

    print("=" * 80)
    print("CANLI STANDART ÜRÜN DB SENKRONİZASYONU")
    print("=" * 80)
    print("Banka:", bank_name)
    print("DB yedeği:", backup)
    print("Yeni ürün:", counts["created"])
    print("Koşulu değişen:", counts["terms_changed"])
    print("Metni değişen:", counts["content_changed"])
    print("Yeniden görünen:", counts["reactivated"])
    print("Değişmeyen:", counts["unchanged"])
    print("Olası kaldırılmış uyarısı:", possible_removed)
    print("Bu bankada güncel ürün:", bank_total)
    print("DB toplam güncel ürün:", total_current)
    print()
    print(
        "Not: Ürün tek taramada bulunamazsa silinmez. "
        "Ardışık eksik taramalarda yalnızca "
        "'olası kaldırılmış' uyarısı oluşturulur."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
