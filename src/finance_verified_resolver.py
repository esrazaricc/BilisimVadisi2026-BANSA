from __future__ import annotations

from dataclasses import replace

"""
BANSA unified verified finance resolution boundary.

FINANCE_VERIFIED_RESOLVER_V1

All runtime surfaces that need numeric finance results should
ultimately resolve the request through this module.

Important invariants:
- Same user amount for every candidate.
- Same user maturity for every candidate.
- No benchmark scaling.
- No mismatched maturity fallback.
- No guessed numeric result.
- VERIFIED results must be exact and rankable.
- Non-verified results must not leak ranking numbers.

The underlying bank capability engine currently remains
finance_live_compare.compare_financing().
"""

from collections.abc import Iterable
from typing import Any

import pandas as pd

from src.finance_live_compare import (
    compare_financing as _compare_financing_engine,
)
from src.finance_runtime_repository import (
    get_verified_finance_scenarios,
)

from src.finance_live_contract import (
    LiveCalculationResult,
    LiveCalculationStatus,
    FinanceResolutionReasonCode,
    validate_live_result,
)


SCENARIO_COLUMNS = (
    "product_id",
    "scenario_key",
    "scenario_type",
    "input_amount",
    "input_maturity_months",
    "input_variant",
    "profit_share_rate",
    "monthly_installment",
    "total_repayment",
    "allocation_fee",
    "mortgage_fee",
    "appraisal_fee",
    "total_fees",
    "scenario_status",
    "source_kind",
    "source_url",
    "source_note",
    "checked_at",
)



# ============================================================
# FINANCE_RESOLUTION_REASON_ENRICHMENT_V1
# ============================================================

def _reason_decimal(
    value,
):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    try:
        from decimal import Decimal

        return Decimal(
            str(value)
        )
    except Exception:
        return None


def _reason_maturity(
    value,
):
    parsed = _reason_decimal(
        value
    )

    if parsed is None:
        return None

    try:
        return int(parsed)
    except Exception:
        return None


def _reason_variant(
    value,
) -> str:

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return str(
        value
    ).strip().casefold()


def _reason_signature(
    row,
):

    return (
        _reason_decimal(
            row.get(
                "profit_share_rate"
            )
        ),
        _reason_decimal(
            row.get(
                "monthly_installment"
            )
        ),
        _reason_decimal(
            row.get(
                "total_repayment"
            )
        ),
    )


def _classify_resolution_reason_code(
    result: LiveCalculationResult,
):
    """
    Runtime-safe reason classification.

    Uses only the local portable finance snapshot.
    No PostgreSQL and no network request is required.
    """

    if (
        result.status
        ==
        LiveCalculationStatus.VERIFIED
    ):
        return None

    if (
        result.reason_code
        is not None
    ):
        return result.reason_code

    if (
        result.status
        ==
        LiveCalculationStatus.INELIGIBLE
    ):
        return (
            FinanceResolutionReasonCode
            .REQUEST_INELIGIBLE
        )

    reason_text = str(
        result.reason
        or ""
    ).strip().casefold()

    if (
        "provenance_not_reproducible"
        in reason_text
    ):
        return (
            FinanceResolutionReasonCode
            .CALCULATOR_MAPPING_MISSING
        )

    request = result.request

    rows = get_verified_finance_scenarios(
        product_ids=[
            int(
                request.product_id
            )
        ]
    )

    if (
        rows is None
        or rows.empty
    ):
        return (
            FinanceResolutionReasonCode
            .NUMERIC_SOURCE_UNAVAILABLE
        )

    working = rows.copy()

    if (
        "input_amount"
        not in working.columns
        or
        "input_maturity_months"
        not in working.columns
    ):
        return (
            FinanceResolutionReasonCode
            .CALCULATOR_MAPPING_MISSING
        )

    amounts = working[
        "input_amount"
    ].apply(
        _reason_decimal
    )

    maturities = working[
        "input_maturity_months"
    ].apply(
        _reason_maturity
    )

    exact = working[
        amounts.eq(
            _reason_decimal(
                request.amount
            )
        )
        &
        maturities.eq(
            int(
                request.maturity_months
            )
        )
    ].copy()

    # Product has verified calculator history, but not for the
    # exact amount/maturity requested by the user.
    if exact.empty:
        return (
            FinanceResolutionReasonCode
            .CALCULATOR_MAPPING_MISSING
        )

    request_variant = (
        _reason_variant(
            request.variant
        )
    )

    if request_variant:

        if (
            "input_variant"
            not in exact.columns
        ):
            return (
                FinanceResolutionReasonCode
                .VARIANT_REQUIRED
            )

        variant_values = exact[
            "input_variant"
        ].apply(
            _reason_variant
        )

        exact = exact[
            variant_values.eq(
                request_variant
            )
        ].copy()

        if exact.empty:
            return (
                FinanceResolutionReasonCode
                .VARIANT_REQUIRED
            )

    else:

        signatures = {
            _reason_signature(
                row
            )
            for _, row
            in exact.iterrows()
        }

        variants = set()

        if (
            "input_variant"
            in exact.columns
        ):
            variants = {
                value
                for value
                in exact[
                    "input_variant"
                ].apply(
                    _reason_variant
                )
                .tolist()
                if value
            }

        if (
            len(variants) > 1
            and
            len(signatures) > 1
        ):
            return (
                FinanceResolutionReasonCode
                .VARIANT_REQUIRED
            )

    # Exact verified local history exists but runtime could not
    # safely promote it. This includes provenance guards and
    # unresolved calculator mapping cases.
    return (
        FinanceResolutionReasonCode
        .CALCULATOR_MAPPING_MISSING
    )


def _with_resolution_reason_code(
    result: LiveCalculationResult,
) -> LiveCalculationResult:

    code = (
        _classify_resolution_reason_code(
            result
        )
    )

    if (
        code
        ==
        result.reason_code
    ):
        return result

    return replace(
        result,
        reason_code=code,
    )


def resolve_finance_results(
    *,
    family: str,
    amount: Any,
    maturity: int,
    purpose: str | None = None,
    scope: str = "bireysel",
    bank_names: Iterable[str] | None = None,
    adapters=None,
) -> list[LiveCalculationResult]:
    """
    Canonical BANSA finance-result resolver.

    Returns VERIFIED, INELIGIBLE and UNVERIFIED results so the
    presentation layer can explain unavailable candidates without
    inventing financial numbers.

    Every VERIFIED result is required to be an exact user-scenario
    result and fully rankable.
    """

    results = _compare_financing_engine(
        family=family,
        amount=amount,
        maturity=int(maturity),
        purpose=purpose,
        scope=scope,
        bank_names=bank_names,
        adapters=adapters,
    )

    validated: list[
        LiveCalculationResult
    ] = []

    for result in results:

        # Validate the underlying provider result first.
        # Reason enrichment must never hide an invalid result.
        validate_live_result(
            result
        )

        result = (
            _with_resolution_reason_code(
                result
            )
        )

        validate_live_result(
            result
        )

        if (
            result.status
            ==
            LiveCalculationStatus.VERIFIED
            and
            not result.is_rankable
        ):
            raise RuntimeError(
                "VERIFIED finance result is not rankable."
            )

        validated.append(
            result
        )

    return validated


def verified_results(
    results: Iterable[
        LiveCalculationResult
    ],
) -> list[LiveCalculationResult]:
    """
    Return only exact rankable VERIFIED results.
    """

    accepted: list[
        LiveCalculationResult
    ] = []

    for result in results:

        validate_live_result(
            result
        )

        if (
            result.status
            ==
            LiveCalculationStatus.VERIFIED
        ):

            if not result.is_rankable:
                raise RuntimeError(
                    "VERIFIED finance result is not rankable."
                )

            accepted.append(
                result
            )

    return accepted


def unresolved_results(
    results: Iterable[
        LiveCalculationResult
    ],
) -> list[LiveCalculationResult]:
    """
    Return candidates for which a numeric result must not be shown.
    """

    output: list[
        LiveCalculationResult
    ] = []

    for result in results:

        validate_live_result(
            result
        )

        if (
            result.status
            !=
            LiveCalculationStatus.VERIFIED
        ):
            output.append(
                result
            )

    return output


def verified_results_to_scenario_frame(
    results: Iterable[
        LiveCalculationResult
    ],
) -> pd.DataFrame:
    """
    Compatibility bridge for existing comparison presentation code.

    This does NOT make a new finance calculation.

    It converts already VERIFIED exact LiveCalculationResult values
    into the scenario-shaped rows currently expected by the legacy
    Streamlit comparison presentation.

    This bridge exists so that the presentation can migrate away
    from direct exact-snapshot filtering without a large UI rewrite.
    """

    rows: list[dict[str, Any]] = []

    for result in verified_results(
        results
    ):

        request = result.request

        rows.append(
            {
                "product_id":
                    int(
                        request.product_id
                    ),

                "scenario_key":
                    "resolved_exact_user_scenario",

                "scenario_type":
                    "verified_runtime_resolution",

                "input_amount":
                    request.amount,

                "input_maturity_months":
                    int(
                        request.maturity_months
                    ),

                "input_variant":
                    request.variant,

                "profit_share_rate":
                    result.profit_share_rate,

                "monthly_installment":
                    result.monthly_installment,

                "total_repayment":
                    result.total_repayment,

                "allocation_fee":
                    result.allocation_fee,

                "mortgage_fee":
                    result.mortgage_fee,

                "appraisal_fee":
                    result.appraisal_fee,

                "total_fees":
                    result.total_fees,

                "scenario_status":
                    "verified_runtime_resolution",

                "source_kind":
                    result.source_kind,

                "source_url":
                    result.source_url,

                "source_note":
                    result.source_note,

                "checked_at":
                    result.checked_at,
            }
        )

    return pd.DataFrame(
        rows,
        columns=SCENARIO_COLUMNS,
    )



# ============================================================
# FINANCE_VERIFIED_RESOLVER_PUBLIC_FACADE_V1
# ============================================================
#
# Compatibility facade:
#
# Existing application-layer consumers historically imported
# compare_financing directly from finance_live_compare.
#
# They now import the same public name from this resolver so
# existing dependency-injection/tests can remain stable while
# every application finance request crosses this verification
# boundary.
#
# New application code should prefer resolve_finance_results().
#
compare_financing = resolve_finance_results
