# FINANCE_RUNTIME_REPOSITORY_V1

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd


DEFAULT_SNAPSHOT_PATH = Path(
    "data/runtime/finance_snapshot.sqlite"
)

DEFAULT_MANIFEST_PATH = Path(
    "data/runtime/finance_snapshot_manifest.json"
)


EXPECTED_COLUMNS = (
    "id",
    "bank_name",
    "product_family_key",
    "product_family",
    "product_name",
    "scope",
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
    "housing_first_home_rules_text",
    "housing_additional_home_rules_text",
    "housing_finance_rules_json",
    "finance_rules_json",
    "source_url",
    "source_page",
    "clean_text",
    "last_checked_at",
)


BOOLEAN_COLUMNS = {
    "interest_free",
    "insurance_fee_waived",
    "allocation_fee_waived",
    "commission_fee_waived",
}


NUMERIC_COLUMNS = {
    "id",
    "minimum_financing_amount",
    "maximum_financing_amount",
    "minimum_maturity_months",
    "maximum_maturity_months",
    "profit_share_rate",
    "maturity_reference_upper_amount",
    "maximum_financing_ratio",
    "shopping_general_limit_amount",
    "shopping_general_max_maturity_months",
    "shopping_tablet_max_maturity_months",
    "shopping_computer_max_maturity_months",
}


DATETIME_COLUMNS = {
    "last_checked_at",
}


class FinanceSnapshotError(
    RuntimeError
):
    pass


def _snapshot_path() -> Path:

    override = os.getenv(
        "BANSA_FINANCE_SNAPSHOT"
    )

    if override:

        return Path(
            override
        )

    return DEFAULT_SNAPSHOT_PATH


def _manifest_path(
    snapshot_path: Path,
) -> Path:

    override = os.getenv(
        "BANSA_FINANCE_SNAPSHOT_MANIFEST"
    )

    if override:

        return Path(
            override
        )

    if (
        snapshot_path.resolve()
        == DEFAULT_SNAPSHOT_PATH.resolve()
    ):
        return DEFAULT_MANIFEST_PATH

    return snapshot_path.with_name(
        "finance_snapshot_manifest.json"
    )


def _is_missing(
    value,
) -> bool:

    if value is None:
        return True

    try:

        result = pd.isna(
            value
        )

        if isinstance(
            result,
            (
                bool,
                np.bool_,
            ),
        ):
            return bool(
                result
            )

    except Exception:
        pass

    return False


def _canonical_number(
    value,
):

    if _is_missing(
        value
    ):
        return None

    try:

        decimal_value = Decimal(
            str(value)
        )

    except (
        InvalidOperation,
        ValueError,
    ) as exc:

        raise FinanceSnapshotError(
            "Finance snapshot contains "
            "an invalid numeric value."
        ) from exc

    if not decimal_value.is_finite():
        return None

    if decimal_value == 0:
        return "0"

    return format(
        decimal_value.normalize(),
        "f",
    )


def _canonical_boolean(
    value,
):

    if _is_missing(
        value
    ):
        return None

    if isinstance(
        value,
        str,
    ):

        normalized = (
            value.strip().casefold()
        )

        if normalized in {
            "1",
            "true",
            "t",
            "yes",
        }:
            return True

        if normalized in {
            "0",
            "false",
            "f",
            "no",
        }:
            return False

    try:

        return bool(
            int(value)
        )

    except Exception:

        return bool(
            value
        )


def _canonical_datetime(
    value,
):

    if _is_missing(
        value
    ):
        return None

    parsed = pd.to_datetime(
        value,
        errors="raise",
        utc=True,
    )

    return parsed.isoformat()


def _canonical_value(
    column,
    value,
):

    if _is_missing(
        value
    ):
        return None

    if column in NUMERIC_COLUMNS:

        return _canonical_number(
            value
        )

    if column in BOOLEAN_COLUMNS:

        return _canonical_boolean(
            value
        )

    if column in DATETIME_COLUMNS:

        return _canonical_datetime(
            value
        )

    return str(
        value
    )


def canonical_finance_hash(
    frame: pd.DataFrame,
) -> str:

    missing = [
        column
        for column in EXPECTED_COLUMNS
        if column not in frame.columns
    ]

    if missing:

        raise FinanceSnapshotError(
            "Finance snapshot hash cannot "
            "be calculated because columns "
            "are missing: "
            + repr(
                missing
            )
        )

    ordered = (
        frame[
            list(
                EXPECTED_COLUMNS
            )
        ]
        .sort_values(
            by=["id"],
            kind="stable",
        )
    )

    rows = []

    for _, row in ordered.iterrows():

        rows.append(
            {
                column:
                    _canonical_value(
                        column,
                        row[column],
                    )
                for column in (
                    EXPECTED_COLUMNS
                )
            }
        )

    payload = json.dumps(
        rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    )

    return hashlib.sha256(
        payload.encode(
            "utf-8"
        )
    ).hexdigest()


def _restore_runtime_types(
    frame: pd.DataFrame,
) -> pd.DataFrame:

    frame = frame.copy()

    for column in BOOLEAN_COLUMNS:

        frame[column] = (
            frame[column]
            .map(
                lambda value:
                    None
                    if _is_missing(
                        value
                    )
                    else bool(
                        int(value)
                    )
            )
            .astype(object)
        )

    for column in NUMERIC_COLUMNS:

        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

    frame[
        "last_checked_at"
    ] = pd.to_datetime(
        frame[
            "last_checked_at"
        ],
        errors="coerce",
        utc=True,
    )

    return frame


def _read_manifest(
    path: Path,
) -> dict:

    if not path.exists():

        raise FinanceSnapshotError(
            "Finance snapshot manifest "
            f"not found: {path}"
        )

    try:

        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:

        raise FinanceSnapshotError(
            "Finance snapshot manifest "
            "could not be read."
        ) from exc

    return payload


@lru_cache(maxsize=4)
def _load_snapshot_cached(
    snapshot_path_text: str,
    manifest_path_text: str,
) -> pd.DataFrame:

    snapshot_path = Path(
        snapshot_path_text
    )

    manifest_path = Path(
        manifest_path_text
    )

    if not snapshot_path.exists():

        raise FinanceSnapshotError(
            "Portable finance snapshot "
            f"not found: {snapshot_path}"
        )

    manifest = _read_manifest(
        manifest_path
    )

    if manifest.get(
        "schema_version"
    ) != "finance_snapshot_v1":

        raise FinanceSnapshotError(
            "Unsupported finance snapshot "
            "schema version."
        )

    if manifest.get(
        "hash_contract"
    ) != "canonical_finance_v2":

        raise FinanceSnapshotError(
            "Unsupported finance snapshot "
            "hash contract."
        )

    if manifest.get(
        "runtime_postgres_required"
    ) is not False:

        raise FinanceSnapshotError(
            "Finance snapshot manifest "
            "does not declare a portable "
            "PostgreSQL-free runtime."
        )

    connection = sqlite3.connect(
        snapshot_path
    )

    try:

        frame = pd.read_sql_query(
            """
            SELECT *
            FROM standard_products
            ORDER BY id
            """,
            connection,
        )

        snapshot_meta = dict(
            connection.execute(
                """
                SELECT key, value
                FROM snapshot_meta
                """
            ).fetchall()
        )

    except Exception as exc:

        raise FinanceSnapshotError(
            "Finance snapshot could "
            "not be read."
        ) from exc

    finally:

        connection.close()

    actual_columns = list(
        frame.columns
    )

    expected_columns = list(
        EXPECTED_COLUMNS
    )

    if actual_columns != expected_columns:

        raise FinanceSnapshotError(
            "Finance snapshot column "
            "contract mismatch."
        )

    expected_rows = int(
        manifest.get(
            "row_count",
            -1,
        )
    )

    if len(frame) != expected_rows:

        raise FinanceSnapshotError(
            "Finance snapshot row "
            "count mismatch."
        )

    if int(
        manifest.get(
            "column_count",
            -1,
        )
    ) != len(
        EXPECTED_COLUMNS
    ):

        raise FinanceSnapshotError(
            "Finance snapshot manifest "
            "column count mismatch."
        )

    runtime_frame = (
        _restore_runtime_types(
            frame
        )
    )

    actual_hash = (
        canonical_finance_hash(
            runtime_frame
        )
    )

    expected_hash = str(
        manifest.get(
            "content_hash",
            ""
        )
    )

    if (
        not expected_hash
        or actual_hash
        != expected_hash
    ):

        raise FinanceSnapshotError(
            "Finance snapshot integrity "
            "hash mismatch."
        )

    if snapshot_meta.get(
        "content_hash"
    ) != expected_hash:

        raise FinanceSnapshotError(
            "Finance snapshot internal "
            "metadata hash mismatch."
        )

    if snapshot_meta.get(
        "hash_contract"
    ) != "canonical_finance_v2":

        raise FinanceSnapshotError(
            "Finance snapshot internal "
            "hash contract mismatch."
        )

    return runtime_frame


def get_standard_products() -> pd.DataFrame:
    """
    Runtime finance product repository.

    Reads the validated portable SQLite
    snapshot. No PostgreSQL server, DSN,
    password or TCP port is required.
    """

    snapshot = _snapshot_path()
    manifest = _manifest_path(
        snapshot
    )

    frame = _load_snapshot_cached(
        str(
            snapshot.resolve()
        ),
        str(
            manifest.resolve()
        ),
    )

    # Protect cached source from mutation by downstream consumers.
    out = frame.copy(deep=True)

    # BANSA V15 CURRENT OFFICIAL RULE OVERLAY
    # These are product-policy/eligibility facts, not calculator prices.
    # Pricing is still resolved by live calculator/current official pricing
    # tables in the response layer.
    def _rules_with_vehicle_bands(raw):
        try:
            rules = json.loads(raw) if isinstance(raw, str) and raw.strip() else (dict(raw) if isinstance(raw, dict) else {})
        except Exception:
            rules = {}
        bands = [
            {"min_value": None, "max_value": 400000.0, "max_financing_ratio": 70.0, "max_maturity_months": 48},
            {"min_value": 400000.0, "max_value": 800000.0, "max_financing_ratio": 50.0, "max_maturity_months": 36},
            {"min_value": 800000.0, "max_value": 1200000.0, "max_financing_ratio": 30.0, "max_maturity_months": 24},
            {"min_value": 1200000.0, "max_value": 2000000.0, "max_financing_ratio": 20.0, "max_maturity_months": 12},
        ]
        amount_rules = [
            {"min_amount": None, "max_amount": 400000.0, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 48, "source_text": "Araç değeri ≤ 400.000 TL → azami %70 / 48 ay"},
            {"min_amount": 400000.0, "max_amount": 800000.0, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 36, "source_text": "400.000 < araç değeri ≤ 800.000 TL → azami %50 / 36 ay"},
            {"min_amount": 800000.0, "max_amount": 1200000.0, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 24, "source_text": "800.000 < araç değeri ≤ 1.200.000 TL → azami %30 / 24 ay"},
            {"min_amount": 1200000.0, "max_amount": 2000000.0, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 12, "source_text": "1.200.000 < araç değeri ≤ 2.000.000 TL → azami %20 / 12 ay"},
        ]
        meta = rules.setdefault("display_metadata", {})
        meta["vehicle_value_rules"] = bands
        rules["amount_maturity_rules"] = amount_rules
        return json.dumps(rules, ensure_ascii=False)

    emlak_mask = out["id"].eq(230)
    if emlak_mask.any():
        out.loc[emlak_mask, "maximum_maturity_months"] = 48
        out.loc[emlak_mask, "profit_share_rate_text"] = "Hesaplama aracında dinamik"
        out.loc[emlak_mask, "finance_rules_json"] = out.loc[emlak_mask, "finance_rules_json"].apply(_rules_with_vehicle_bands)

    vakif_mask = out["id"].eq(286)
    if vakif_mask.any():
        out.loc[vakif_mask, "maximum_maturity_months"] = 48
        # Mark official pricing-table tiers as current so scenario projection
        # can use the table instead of stale calculator snapshots.
        def _mark_current_vakif(raw):
            try:
                rules = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
            except Exception:
                return raw
            for tier in rules.get("pricing_tiers") or []:
                if isinstance(tier, dict):
                    tier["verified_checked_at"] = "2026-08-26T00:00:00+03:00"
            return json.dumps(rules, ensure_ascii=False)
        out.loc[vakif_mask, "finance_rules_json"] = out.loc[vakif_mask, "finance_rules_json"].apply(_mark_current_vakif)

    tf_mask = out["id"].eq(64)
    if tf_mask.any():
        def _mark_current_tf(raw):
            try:
                rules = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
            except Exception:
                return raw
            for tier in rules.get("pricing_tiers") or []:
                if isinstance(tier, dict):
                    tier["verified_checked_at"] = "2026-08-25T20:55:00+00:00"
            return json.dumps(rules, ensure_ascii=False)
        out.loc[tf_mask, "finance_rules_json"] = out.loc[tf_mask, "finance_rules_json"].apply(_mark_current_tf)

    return out


def clear_finance_snapshot_cache():

    _load_snapshot_cached.cache_clear()

    loader = globals().get(
        "_load_verified_finance_scenarios_cached"
    )

    if loader is not None:

        loader.cache_clear()


def get_finance_runtime_info() -> dict:

    snapshot = _snapshot_path()

    manifest_path = _manifest_path(
        snapshot
    )

    manifest = _read_manifest(
        manifest_path
    )

    return {
        "backend":
            "sqlite_snapshot",

        "snapshot_path":
            str(snapshot),

        "manifest_path":
            str(manifest_path),

        "schema_version":
            manifest.get(
                "schema_version"
            ),

        "hash_contract":
            manifest.get(
                "hash_contract"
            ),

        "row_count":
            manifest.get(
                "row_count"
            ),

        "content_hash":
            manifest.get(
                "content_hash"
            ),

        "runtime_postgres_required":
            False,

        "runtime_password_required":
            False,

        "runtime_port_required":
            False,
    }


# ============================================================
# PORTABLE_VERIFIED_SCENARIO_BRIDGE_V1_2
# ============================================================

from functools import lru_cache as _scenario_lru_cache


@_scenario_lru_cache(
    maxsize=1,
)
def _load_verified_finance_scenarios_cached():

    import sqlite3
    import pandas as pd


    snapshot = _snapshot_path()


    if not snapshot.exists():

        raise RuntimeError(
            "Finance runtime snapshot is missing."
        )


    with sqlite3.connect(
        snapshot
    ) as connection:

        exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE
                type = 'table'
                AND name = 'verified_finance_scenarios'
            LIMIT 1
            """
        ).fetchone()


        if not exists:

            return pd.DataFrame()


        return pd.read_sql_query(
            """
            SELECT *
            FROM verified_finance_scenarios
            """,
            connection,
        )


def get_verified_finance_scenarios(
    product_ids=None,
):

    frame = (
        _load_verified_finance_scenarios_cached()
        .copy()
    )


    if frame.empty:

        return frame


    if product_ids is None:

        return frame


    ids = []


    for value in product_ids:

        try:

            parsed = int(
                value
            )

        except (
            TypeError,
            ValueError,
        ):

            continue


        if parsed > 0:

            ids.append(
                parsed
            )


    ids = sorted(
        set(
            ids
        )
    )


    if not ids:

        return frame.iloc[
            0:0
        ].copy()


    frame_ids = (
        frame[
            "product_id"
        ]
        .astype(int)
    )


    return frame[
        frame_ids.isin(
            ids
        )
    ].copy()

