from __future__ import annotations

import json
import os
import re
import unicodedata

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

import psycopg

from psycopg.types.json import Jsonb


# ============================================================
# BANSA FINANCE SCENARIO COMMON INFRASTRUCTURE
# ============================================================
#
# Responsibilities:
# - PostgreSQL connection
# - bansa schema search_path
# - canonical product identity verification
# - scenario backups
# - scenario inserts
# - latest scenario reads
# - canonical immutability verification
#
# Bank-specific HTTP/API semantics do NOT belong here.
# ============================================================


SEARCH_PATH_SQL = (
    "SET search_path TO bansa, public"
)


def get_postgres_dsn() -> str:
    """
    Read PostgreSQL DSN from environment.

    Credentials must never be committed to GitHub.
    """

    dsn = (
        os.environ.get("POSTGRES_DSN")
        or ""
    ).strip()

    if not dsn:
        raise RuntimeError(
            "POSTGRES_DSN tanimli degil."
        )

    return dsn


def connect_postgres():
    """
    Open PostgreSQL connection and select BANSA schema.
    """

    conn = psycopg.connect(
        get_postgres_dsn()
    )

    conn.execute(
        SEARCH_PATH_SQL
    )

    return conn


def utc_now():
    return datetime.now(
        timezone.utc
    )


def normalize_text(
    value: Any,
) -> str:
    """
    Turkish-safe comparison normalization.
    """

    value = str(
        value or ""
    )

    replacements = {
        "\u0131": "i",
        "\u0130": "i",
        "\u015f": "s",
        "\u015e": "s",
        "\u011f": "g",
        "\u011e": "g",
        "\u00fc": "u",
        "\u00dc": "u",
        "\u00f6": "o",
        "\u00d6": "o",
        "\u00e7": "c",
        "\u00c7": "c",
    }

    for old, new in replacements.items():
        value = value.replace(
            old,
            new,
        )

    value = unicodedata.normalize(
        "NFKD",
        value,
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(
            char
        )
    )

    value = value.lower()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return " ".join(
        value.split()
    )


def to_decimal(
    value: Any,
) -> Decimal | None:
    """
    Convert common Turkish/JSON numeric forms to Decimal.
    """

    if value is None:
        return None

    if isinstance(
        value,
        Decimal,
    ):
        return value

    if isinstance(
        value,
        (int, float),
    ):
        return Decimal(
            str(value)
        )

    text = (
        str(value)
        .replace("\u00a0", "")
        .replace("TL", "")
        .replace("\u20ba", "")
        .replace("%", "")
        .replace(" ", "")
        .strip()
    )

    if not text:
        return None

    if (
        "." in text
        and "," in text
    ):
        text = (
            text
            .replace(".", "")
            .replace(",", ".")
        )

    elif "," in text:
        text = text.replace(
            ",",
            ".",
        )

    try:
        return Decimal(
            text
        )

    except InvalidOperation:
        return None


def canonical_snapshot(
    conn,
    product_ids: Iterable[int],
) -> dict[int, Any]:
    """
    Snapshot canonical standard_products rows.

    Used before/after scenario writes to prove that
    live calculator snapshots never overwrite
    canonical product data.
    """

    ids = sorted(
        {
            int(value)
            for value in product_ids
        }
    )

    if not ids:
        return {}

    rows = conn.execute(
        """
        SELECT
            p.id,
            to_jsonb(p)
        FROM standard_products p
        WHERE p.id = ANY(%s)
        ORDER BY p.id
        """,
        (
            ids,
        ),
    ).fetchall()

    return {
        int(row[0]): row[1]
        for row in rows
    }


def assert_canonical_unchanged(
    before: dict[int, Any],
    after: dict[int, Any],
) -> None:
    """
    Fail if canonical standard_products changed.
    """

    if before != after:
        raise RuntimeError(
            "CANONICAL STANDARD_PRODUCTS CHANGED"
        )


def assert_product_identity(
    conn,
    *,
    product_id: int,
    bank_name: str,
    product_name: str,
    family_key: str,
    scope: str,
) -> dict[str, Any]:
    """
    Verify exact BANSA product identity before attaching
    a calculator scenario to a canonical product.
    """

    row = conn.execute(
        """
        SELECT
            p.id,
            b.name,
            f.family_key,
            p.scope,
            p.product_name,
            p.source_page_id,
            s.url
        FROM standard_products p
        JOIN banks b
          ON b.id = p.bank_id
        JOIN product_families f
          ON f.id = p.family_id
        LEFT JOIN source_pages s
          ON s.id = p.source_page_id
        WHERE p.id = %s
          AND p.is_current = TRUE
        LIMIT 1
        """,
        (
            int(product_id),
        ),
    ).fetchone()

    if row is None:
        raise RuntimeError(
            f"PRODUCT NOT FOUND: {product_id}"
        )

    actual = {
        "product_id":
            int(row[0]),

        "bank_name":
            row[1],

        "family_key":
            row[2],

        "scope":
            row[3],

        "product_name":
            row[4],

        "source_page_id":
            row[5],

        "source_url":
            row[6],
    }

    checks = {
        "BANK":
            normalize_text(
                actual["bank_name"]
            )
            == normalize_text(
                bank_name
            ),

        "NAME":
            normalize_text(
                actual["product_name"]
            )
            == normalize_text(
                product_name
            ),

        "FAMILY":
            actual["family_key"]
            == family_key,

        "SCOPE":
            actual["scope"]
            == scope,

        "SOURCE":
            bool(
                actual["source_url"]
            ),
    }

    if not all(
        checks.values()
    ):
        raise RuntimeError(
            "PRODUCT IDENTITY FAIL | "
            f"ID={product_id} | "
            f"{checks}"
        )

    actual[
        "identity_checks"
    ] = checks

    return actual


def backup_scenarios(
    conn,
    *,
    bank_slug: str,
    product_ids: Iterable[int],
) -> Path:
    """
    Save current scenario rows + canonical snapshots
    before a live calculator database write.
    """

    ids = sorted(
        {
            int(value)
            for value in product_ids
        }
    )

    canonical = canonical_snapshot(
        conn,
        ids,
    )

    if ids:

        existing = conn.execute(
            """
            SELECT
                to_jsonb(s)
            FROM product_finance_scenarios s
            WHERE s.product_id = ANY(%s)
            ORDER BY
                s.product_id,
                s.id
            """,
            (
                ids,
            ),
        ).fetchall()

        existing = [
            row[0]
            for row in existing
        ]

    else:
        existing = []

    backup_dir = (
        Path("data")
        / "backups"
    )

    backup_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    path = (
        backup_dir
        / (
            f"{bank_slug}_scenarios_before_"
            f"{stamp}.json"
        )
    )

    payload = {
        "created_at":
            utc_now().isoformat(),

        "product_ids":
            ids,

        "canonical_products":
            list(
                canonical.values()
            ),

        "existing_scenarios":
            existing,
    }

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    return path


def insert_scenario(
    conn,
    *,
    product_id: int,
    scenario_key: str,
    scenario_type: str,

    input_amount,
    input_maturity_months: int,
    input_variant: str | None,
    input_metadata: dict[str, Any],

    profit_share_rate,
    monthly_installment,
    total_repayment,

    allocation_fee=None,
    mortgage_fee=None,
    appraisal_fee=None,
    total_fees=None,

    monthly_cost_rate=None,
    annual_cost_rate=None,
    effective_annual_profit_rate=None,

    scenario_status: str,
    source_kind: str,
    source_url: str,
    source_note: str,

    raw_output: dict[str, Any],
    checked_at=None,
) -> int:
    """
    Insert one verified calculator snapshot.

    Important:
    - This writes only product_finance_scenarios.
    - It never updates standard_products.
    """

    checked_at = (
        checked_at
        or utc_now()
    )

    row = conn.execute(
        """
        INSERT INTO product_finance_scenarios (
            product_id,
            scenario_key,
            scenario_type,

            input_amount,
            input_maturity_months,
            input_variant,
            input_metadata,

            profit_share_rate,
            monthly_installment,
            total_repayment,

            monthly_cost_rate,
            annual_cost_rate,
            effective_annual_profit_rate,

            allocation_fee,
            mortgage_fee,
            appraisal_fee,
            total_fees,

            scenario_status,
            source_kind,
            source_url,
            source_note,

            raw_output,
            checked_at
        )
        VALUES (
            %s, %s, %s,

            %s, %s, %s, %s,

            %s, %s, %s,

            %s, %s, %s,

            %s, %s, %s, %s,

            %s, %s, %s, %s,

            %s, %s
        )
        RETURNING id
        """,
        (
            int(product_id),
            scenario_key,
            scenario_type,

            input_amount,
            int(
                input_maturity_months
            ),
            input_variant,
            Jsonb(
                input_metadata
            ),

            profit_share_rate,
            monthly_installment,
            total_repayment,

            monthly_cost_rate,
            annual_cost_rate,
            effective_annual_profit_rate,

            allocation_fee,
            mortgage_fee,
            appraisal_fee,
            total_fees,

            scenario_status,
            source_kind,
            source_url,
            source_note,

            Jsonb(
                raw_output
            ),
            checked_at,
        ),
    ).fetchone()

    if row is None:
        raise RuntimeError(
            "SCENARIO INSERT RETURNING ID FAILED"
        )

    return int(
        row[0]
    )


def get_latest_scenario(
    conn,
    *,
    product_id: int,
    scenario_key: str,
    input_variant: str | None,
) -> dict[str, Any] | None:
    """
    Read latest scenario through BANSA latest-view semantics.
    """

    row = conn.execute(
        """
        SELECT
            id,
            product_id,
            scenario_key,
            scenario_type,

            input_amount,
            input_maturity_months,
            input_variant,

            profit_share_rate,
            monthly_installment,
            total_repayment,

            monthly_cost_rate,
            annual_cost_rate,
            effective_annual_profit_rate,

            allocation_fee,
            mortgage_fee,
            appraisal_fee,
            total_fees,

            scenario_status,
            source_kind,
            source_url,
            source_note,

            input_metadata,
            raw_output,
            checked_at
        FROM v_latest_finance_scenarios
        WHERE product_id = %s
          AND scenario_key = %s
          AND COALESCE(
                input_variant,
                ''
              ) = COALESCE(
                %s,
                ''
              )
        LIMIT 1
        """,
        (
            int(product_id),
            scenario_key,
            input_variant,
        ),
    ).fetchone()

    if row is None:
        return None

    columns = [
        "id",
        "product_id",
        "scenario_key",
        "scenario_type",

        "input_amount",
        "input_maturity_months",
        "input_variant",

        "profit_share_rate",
        "monthly_installment",
        "total_repayment",

        "monthly_cost_rate",
        "annual_cost_rate",
        "effective_annual_profit_rate",

        "allocation_fee",
        "mortgage_fee",
        "appraisal_fee",
        "total_fees",

        "scenario_status",
        "source_kind",
        "source_url",
        "source_note",

        "input_metadata",
        "raw_output",
        "checked_at",
    ]

    return dict(
        zip(
            columns,
            row,
        )
    )


def assert_latest_scenario(
    conn,
    *,
    product_id: int,
    scenario_key: str,
    input_variant: str | None,
    expected: dict[str, Any],
) -> dict[str, Any]:
    """
    Verify selected normalized fields from latest scenario.
    """

    row = get_latest_scenario(
        conn,
        product_id=product_id,
        scenario_key=scenario_key,
        input_variant=input_variant,
    )

    if row is None:
        raise RuntimeError(
            "LATEST SCENARIO MISSING | "
            f"ID={product_id} | "
            f"KEY={scenario_key} | "
            f"VARIANT={input_variant}"
        )

    failures = {}

    for field, expected_value in expected.items():

        actual_value = row.get(
            field
        )

        if isinstance(
            expected_value,
            Decimal,
        ):

            actual_decimal = (
                to_decimal(
                    actual_value
                )
            )

            passed = (
                actual_decimal
                == expected_value
            )

        else:

            passed = (
                actual_value
                == expected_value
            )

        if not passed:

            failures[field] = {
                "expected":
                    expected_value,

                "actual":
                    actual_value,
            }

    if failures:
        raise RuntimeError(
            "LATEST SCENARIO VERIFY FAIL | "
            f"ID={product_id} | "
            f"VARIANT={input_variant} | "
            f"{failures}"
        )

    return row
