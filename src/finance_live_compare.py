# FINANCE_LIVE_ADAPTER_ALBARAKA_REGISTRY_V1
# FINANCE_COMPARISON_PURPOSE_FILTER_V1
# FINANCE_LIVE_COMPARE_V1

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

import pandas as pd


from src.finance_runtime_repository import (
    get_standard_products,
)

from src.finance_common_scenario import (
    evaluate_product_eligibility,
)

from src.finance_capability_registry import (
    FinanceCapabilityKind,
    select_finance_capability,
)

from src.finance_live_contract import (
    LiveCalculationRequest,
    LiveCalculationResult,
    LiveCalculationStatus,
    validate_live_result,
)

from src.finance_live_adapters.emlak_katilim import (
    EmlakKatilimLiveAdapter,
)

from src.finance_live_adapters.vakif_katilim import (
    VakifKatilimLiveAdapter,
)

from src.finance_live_adapters.albaraka import (
    AlbarakaLiveAdapter,
)

from src.finance_live_adapters.albaraka_konut import (
    AlbarakaKonutLiveAdapter,
)

from src.finance_live_adapters.dunya_katilim import (
    DunyaKatilimLiveAdapter,
)

from src.finance_comparison_purpose import (
    resolve_comparison_purpose,
    default_comparison_universe_key,
    resolve_default_comparison_universe,
)


def _int_or_none(value) -> int | None:

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    try:
        return int(value)
    except Exception:
        return None


def _normalized(value) -> str:
    return (
        str(value or "")
        .strip()
        .casefold()
    )


def _json_dict(value) -> dict:

    if isinstance(value, dict):
        return value

    if value is None:
        return {}

    try:
        if pd.isna(value):
            return {}
    except Exception:
        pass

    try:
        parsed = __import__("json").loads(
            str(value)
        )
    except Exception:
        return {}

    return (
        parsed
        if isinstance(parsed, dict)
        else {}
    )


# FINANCE_LIVE_AMOUNT_RULE_FRAME_V2
def _amount_maturity_rules(
    product,
) -> pd.DataFrame:
    """
    Convert product-local JSON amount/maturity rules into
    the DataFrame contract expected by
    evaluate_product_eligibility().

    No financial value is inferred here.
    Existing rule fields are preserved as published in
    finance_rules_json; product_id is added only as the
    relational identity required by the eligibility engine.
    """

    columns = [
        "product_id",
        "min_amount",
        "max_amount",
        "min_inclusive",
        "max_inclusive",
        "max_maturity_months",
    ]

    rules_root = _json_dict(
        product.get(
            "finance_rules_json"
        )
    )

    rules = rules_root.get(
        "amount_maturity_rules"
    )

    if not isinstance(
        rules,
        list,
    ):
        return pd.DataFrame(
            columns=columns
        )

    product_id = _int_or_none(
        product.get(
            "id"
        )
    )

    if product_id is None:
        return pd.DataFrame(
            columns=columns
        )

    normalized_rules = []

    for rule in rules:

        if not isinstance(
            rule,
            dict,
        ):
            continue

        normalized = dict(
            rule
        )

        normalized[
            "product_id"
        ] = product_id

        normalized_rules.append(
            normalized
        )

    if not normalized_rules:
        return pd.DataFrame(
            columns=columns
        )

    frame = pd.DataFrame(
        normalized_rules
    )

    for column in columns:

        if column not in frame.columns:
            frame[column] = None

    return frame


def default_live_adapters():
    """
    Central adapter registry.

    New bank adapters will be added here one by one.
    """

    return [
        EmlakKatilimLiveAdapter(),
        VakifKatilimLiveAdapter(),
        AlbarakaLiveAdapter(),
        AlbarakaKonutLiveAdapter(),
        DunyaKatilimLiveAdapter(),
    ]


def _status_result(
    *,
    request: LiveCalculationRequest,
    status: LiveCalculationStatus,
    reason: str,
) -> LiveCalculationResult:

    result = LiveCalculationResult(
        request=request,
        status=status,
        reason=reason,
    )

    return validate_live_result(
        result
    )


def _find_adapter(
    request: LiveCalculationRequest,
    adapters,
):

    matches = [
        adapter
        for adapter in adapters
        if adapter.can_handle(
            request
        )
    ]

    if len(matches) > 1:
        raise RuntimeError(
            "Multiple live adapters matched "
            "the same product request."
        )

    if not matches:
        return None

    return matches[0]


def compare_financing(
    *,
    family: str,
    amount,
    maturity: int,
    purpose: str | None = None,
    scope: str = "bireysel",
    bank_names: Iterable[str] | None = None,
    adapters=None,
) -> list[LiveCalculationResult]:
    """
    Strict common-scenario finance comparison.

    Core rules:
    - Every candidate receives the SAME amount.
    - Every candidate receives the SAME maturity.
    - Explicit product-rule violations become INELIGIBLE.
    - Missing live adapters become UNVERIFIED.
    - Only exact VERIFIED live results are rankable.
    - No mismatched snapshot or canonical-rate fallback.
    - Broad family equality alone is NOT semantic equivalence.
    - ihtiyac_finansmani comparisons require an explicit purpose.
    """

    requested_amount = Decimal(
        str(amount)
    )

    requested_maturity = int(
        maturity
    )

    if requested_amount <= 0:
        raise ValueError(
            "amount must be positive"
        )

    if requested_maturity <= 0:
        raise ValueError(
            "maturity must be positive"
        )


    normalized_family = _normalized(
        family
    )

    normalized_purpose = (
        _normalized(
            purpose
        )
        if purpose is not None
        else None
    )


    if (
        normalized_family
        ==
        "ihtiyac_finansmani"
        and
        not normalized_purpose
    ):
        raise ValueError(
            "purpose is required for "
            "ihtiyac_finansmani comparisons"
        )


    products = (
        get_standard_products()
        .copy()
    )


    products = products[
        products[
            "product_family_key"
        ]
        .fillna("")
        .astype(str)
        .str.casefold()
        .eq(
            _normalized(
                family
            )
        )
    ].copy()


    products = products[
        products[
            "scope"
        ]
        .fillna("")
        .astype(str)
        .str.casefold()
        .eq(
            _normalized(
                scope
            )
        )
    ].copy()


    # --------------------------------------------------------
    # STRICT_SEMANTIC_COMPARISON_UNIVERSE_V1
    #
    # Generic comparisons for selected broad families must not
    # compare special-purpose products merely because they share
    # the same family key.
    #
    # Examples excluded from generic housing:
    # - first-home
    # - green housing
    # - urban transformation
    # - expatriate housing
    #
    # Existing explicit-purpose comparisons remain unchanged.
    # --------------------------------------------------------

    if not normalized_purpose:

        universe_key = (
            default_comparison_universe_key(
                normalized_family
            )
        )


        if universe_key is not None:

            products[
                "_default_comparison_universe"
            ] = products.apply(
                resolve_default_comparison_universe,
                axis=1,
            )


            products = products[
                products[
                    "_default_comparison_universe"
                ]
                .fillna("")
                .astype(str)
                .eq(
                    universe_key
                )
            ].copy()


    if normalized_purpose:

        products[
            "_comparison_purpose"
        ] = products.apply(
            resolve_comparison_purpose,
            axis=1,
        )

        products = products[
            products[
                "_comparison_purpose"
            ]
            .fillna("")
            .astype(str)
            .apply(
                _normalized
            )
            .eq(
                normalized_purpose
            )
        ].copy()


    if bank_names is not None:

        allowed = {
            _normalized(name)
            for name in bank_names
        }

        products = products[
            products[
                "bank_name"
            ]
            .apply(
                _normalized
            )
            .isin(
                allowed
            )
        ].copy()


    if adapters is None:
        adapters = (
            default_live_adapters()
        )


    results: list[
        LiveCalculationResult
    ] = []


    for _, product in products.iterrows():

        product_id = int(
            product["id"]
        )


        request = LiveCalculationRequest(
            product_id=product_id,

            bank_name=str(
                product["bank_name"]
            ),

            product_name=str(
                product["product_name"]
            ),

            family_key=str(
                product[
                    "product_family_key"
                ]
            ),

            amount=requested_amount,

            maturity_months=
                requested_maturity,
        )


        eligibility = (
            evaluate_product_eligibility(
                product,
                amount=float(
                    requested_amount
                ),
                maturity=
                    requested_maturity,
                amount_rules=(
                    _amount_maturity_rules(
                        product
                    )
                ),
            )
        )


        if not eligibility.eligible:

            reason = (
                " | ".join(
                    str(item)
                    for item
                    in eligibility.reasons
                    if str(item).strip()
                )
                or
                "Official product rules reject "
                "the requested scenario."
            )

            results.append(
                _status_result(
                    request=request,

                    status=(
                        LiveCalculationStatus
                        .INELIGIBLE
                    ),

                    reason=reason,
                )
            )

            continue


        # FINANCE_CAPABILITY_REGISTRY_RUNTIME_V3
        #
        # Provider selection is centralized.
        # UI/application layers must not decide between
        # live adapters and portable verified scenarios.
        capability = select_finance_capability(
            request=request,
            adapters=adapters,
            portable_result_lookup=(
                _portable_verified_scenario_result
            ),
        )


        if (
            capability.kind
            ==
            FinanceCapabilityKind
            .NO_NUMERIC_CAPABILITY
        ):

            results.append(
                _status_result(
                    request=request,

                    status=(
                        LiveCalculationStatus
                        .UNVERIFIED
                    ),

                    reason=(
                        capability.reason
                        or
                        "No verified numeric finance "
                        "capability is available."
                    ),
                )
            )

            continue


        if (
            capability.kind
            ==
            FinanceCapabilityKind
            .LIVE_CALCULATOR
        ):

            adapter = capability.provider

            if adapter is None:
                raise RuntimeError(
                    "LIVE_CALCULATOR capability "
                    "has no provider."
                )

            result = adapter.calculate(
                request
            )


        elif (
            capability.kind
            in {
                FinanceCapabilityKind
                .VERIFIED_LOCAL_MODEL,

                FinanceCapabilityKind
                .EXACT_PORTABLE_SNAPSHOT,
            }
        ):

            result = capability.resolved_result

            if result is None:
                raise RuntimeError(
                    "Resolved finance capability "
                    "has no result."
                )


        else:

            raise RuntimeError(
                "Unsupported finance capability: "
                f"{capability.kind}"
            )


        validate_live_result(
            result
        )


        if (
            result.status
            ==
            LiveCalculationStatus.VERIFIED
            and
            not result.is_exact_match
        ):
            raise RuntimeError(
                "Verified adapter result does not "
                "match the common amount/maturity."
            )


        results.append(
            result
        )


    return results


def rank_verified_results(
    results: Iterable[
        LiveCalculationResult
    ],
    *,
    by: str = "profit_share_rate",
) -> list[LiveCalculationResult]:
    """
    Deterministic ranking.

    LLM is never used for financial ordering.
    """

    allowed = {
        "profit_share_rate",
        "monthly_installment",
        "total_repayment",
    }


    if by not in allowed:
        raise ValueError(
            f"Unsupported ranking field: {by}"
        )


    rankable = [
        result
        for result in results
        if result.is_rankable
    ]


    return sorted(
        rankable,
        key=lambda result: getattr(
            result,
            by,
        ),
    )


# ============================================================
# PORTABLE_VERIFIED_SCENARIO_BRIDGE_V1_2
# ============================================================

def _portable_scenario_value(
    value,
):

    if value is None:

        return None


    try:

        import pandas as _pd


        if _pd.isna(
            value
        ):

            return None

    except Exception:

        pass


    text = str(
        value
    ).strip()


    if text.casefold() in (
        "",
        "none",
        "nan",
        "nat",
        "null",
    ):

        return None


    return value


def _portable_scenario_decimal(
    value,
):

    value = _portable_scenario_value(
        value
    )


    if value is None:

        return None


    try:

        return Decimal(
            str(
                value
            )
        )

    except Exception:

        return None


def _portable_scenario_variant(
    value,
):

    value = _portable_scenario_value(
        value
    )


    if value is None:

        return ""


    return (
        str(
            value
        )
        .strip()
        .casefold()
        .replace(
            " ",
            "",
        )
        .replace(
            "_",
            "",
        )
        .replace(
            "-",
            "",
        )
        .replace(
            ".",
            "",
        )
    )


def _portable_scenario_datetime(
    value,
):

    value = _portable_scenario_value(
        value
    )


    if value is None:

        return None


    if hasattr(
        value,
        "to_pydatetime",
    ):

        try:

            return value.to_pydatetime()

        except Exception:

            pass


    from datetime import datetime


    text = str(
        value
    ).strip()


    if text.endswith(
        "Z"
    ):

        text = (
            text[:-1]
            + "+00:00"
        )


    try:

        return datetime.fromisoformat(
            text
        )

    except Exception:

        return None


def _portable_scenario_signature(
    row,
):

    return (
        _portable_scenario_decimal(
            row.get(
                "profit_share_rate"
            )
        ),

        _portable_scenario_decimal(
            row.get(
                "monthly_installment"
            )
        ),

        _portable_scenario_decimal(
            row.get(
                "total_repayment"
            )
        ),

        _portable_scenario_decimal(
            row.get(
                "allocation_fee"
            )
        ),

        _portable_scenario_decimal(
            row.get(
                "mortgage_fee"
            )
        ),

        _portable_scenario_decimal(
            row.get(
                "appraisal_fee"
            )
        ),

        _portable_scenario_decimal(
            row.get(
                "total_fees"
            )
        ),
    )


def _portable_verified_scenario_result(
    request,
):

    # ========================================================
    # ALBARAKA_KONUT_PORTABLE_PROVENANCE_GUARD_V2
    #
    # Historical product_id=97 calculator snapshots remain
    # stored for auditability.
    #
    # They must not be promoted to VERIFIED at runtime because
    # the active Albaraka live adapter cannot reproduce the
    # Konut Finansmani product mapping.
    #
    # Fail closed:
    # - no financial numbers
    # - no source URL presented as verification
    # - no ranking
    # ========================================================

    _provenance_product_id = int(
        getattr(
            request,
            "product_id",
            0,
        )
        or 0
    )

    _provenance_family = str(
        getattr(
            request,
            "family_key",
            "",
        )
        or ""
    ).strip().casefold()

    _provenance_bank = str(
        getattr(
            request,
            "bank_name",
            "",
        )
        or ""
    ).strip().casefold()

    if (
        _provenance_product_id == 97
        and
        _provenance_family
        == "konut_finansmani"
        and
        _provenance_bank
        in {
            "albaraka t\u00fcrk",
            "albaraka turk",
        }
    ):
        return validate_live_result(
            LiveCalculationResult(
                request=request,

                status=(
                    LiveCalculationStatus
                    .UNVERIFIED
                ),

                reason=(
                    "provenance_not_reproducible: "
                    "Historical Albaraka Turk "
                    "Konut Finansmani calculator "
                    "snapshot is retained for audit, "
                    "but its exact official product "
                    "mapping cannot currently be "
                    "reproduced by the active live "
                    "adapter."
                ),
            )
        )
    from src.finance_runtime_repository import (
        get_verified_finance_scenarios,
    )


    rows = (
        get_verified_finance_scenarios(
            product_ids=[
                request.product_id
            ]
        )
    )


    if rows.empty:

        return None


    rows = rows.copy()


    amount_values = (
        rows[
            "input_amount"
        ]
        .apply(
            _portable_scenario_decimal
        )
    )


    rows = rows[
        amount_values.eq(
            request.amount
        )
    ]


    if rows.empty:

        return None


    def maturity_value(
        value,
    ):

        parsed = (
            _portable_scenario_decimal(
                value
            )
        )


        if parsed is None:

            return -1


        return int(
            parsed
        )


    maturity_values = (
        rows[
            "input_maturity_months"
        ]
        .apply(
            maturity_value
        )
    )


    rows = rows[
        maturity_values.eq(
            int(
                request.maturity_months
            )
        )
    ]


    if rows.empty:

        return None


    status = (
        rows[
            "scenario_status"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.casefold()
    )


    rows = rows[
        status.str.startswith(
            "verified_live_calculator_"
        )
    ]


    if rows.empty:

        return None


    source_kind = (
        rows[
            "source_kind"
        ]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.casefold()
    )


    rows = rows[
        source_kind.eq(
            "official_live_calculator_endpoint"
        )
    ]


    if rows.empty:

        return None


    request_variant = (
        _portable_scenario_variant(
            request.variant
        )
    )


    if request_variant:

        variants = (
            rows[
                "input_variant"
            ]
            .apply(
                _portable_scenario_variant
            )
        )


        rows = rows[
            variants.eq(
                request_variant
            )
        ]


        if rows.empty:

            return None


    else:

        signatures = {
            _portable_scenario_signature(
                row
            )

            for _index, row
            in rows.iterrows()
        }


        if len(
            signatures
        ) != 1:

            return None


    row = rows.iloc[
        0
    ]


    rate = (
        _portable_scenario_decimal(
            row.get(
                "profit_share_rate"
            )
        )
    )

    monthly = (
        _portable_scenario_decimal(
            row.get(
                "monthly_installment"
            )
        )
    )

    total = (
        _portable_scenario_decimal(
            row.get(
                "total_repayment"
            )
        )
    )


    if (
        rate is None
        or monthly is None
        or total is None
        or rate <= 0
        or monthly <= 0
        or total <= 0
    ):

        return None


    source_url = str(
        _portable_scenario_value(
            row.get(
                "source_url"
            )
        )
        or ""
    ).strip()


    checked_at = (
        _portable_scenario_datetime(
            row.get(
                "checked_at"
            )
        )
    )


    if (
        not source_url
        or checked_at is None
    ):
        return None

    # V15: exact portable snapshots are a short-lived fallback, never a
    # permanent source of "current" pricing. Live calculator/current official
    # table must win; snapshots older than 72h are retained only for audit.
    from datetime import datetime, timezone, timedelta
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - checked_at.astimezone(timezone.utc) > timedelta(hours=72):
        return None


    stored_variants = tuple(
        sorted(
            {
                str(
                    _portable_scenario_value(
                        value
                    )
                    or ""
                ).strip()

                for value
                in rows[
                    "input_variant"
                ].tolist()

                if str(
                    _portable_scenario_value(
                        value
                    )
                    or ""
                ).strip()
            }
        )
    )


    result = LiveCalculationResult(
        request=request,

        status=(
            LiveCalculationStatus
            .VERIFIED
        ),

        calculated_amount=(
            request.amount
        ),

        calculated_maturity_months=(
            request.maturity_months
        ),

        profit_share_rate=rate,

        monthly_installment=monthly,

        total_repayment=total,

        allocation_fee=(
            _portable_scenario_decimal(
                row.get(
                    "allocation_fee"
                )
            )
        ),

        mortgage_fee=(
            _portable_scenario_decimal(
                row.get(
                    "mortgage_fee"
                )
            )
        ),

        appraisal_fee=(
            _portable_scenario_decimal(
                row.get(
                    "appraisal_fee"
                )
            )
        ),

        total_fees=(
            _portable_scenario_decimal(
                row.get(
                    "total_fees"
                )
            )
        ),

        source_kind=(
            str(
                row.get(
                    "source_kind"
                )
            )
        ),

        source_url=source_url,

        source_note=(
            str(
                _portable_scenario_value(
                    row.get(
                        "source_note"
                    )
                )
                or
                "Portable verified live-calculator snapshot."
            )
        ),

        checked_at=checked_at,

        reason=None,

        raw_output={
            "runtime_fallback":
                "portable_verified_scenario",

            "scenario_status":
                str(
                    row.get(
                        "scenario_status"
                    )
                    or ""
                ),

            "stored_variants":
                stored_variants,

            "variant_collapsed":
                (
                    request.variant is None
                    and
                    len(
                        stored_variants
                    ) > 1
                ),
        },
    )


    validate_live_result(
        result
    )


    return result

