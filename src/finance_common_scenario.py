from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd


# FINANCE_COMMON_SCENARIO_V1
#
# Temel kural:
#   Ayni finansman karsilastirmasinda tutar ve vade ayni olmalidir.
#
# Teknik dogrulama snapshot'lari farkli benchmark'larda tutulabilir;
# ancak kullanici karsilastirmasina sadece birebir ayni tutar +
# ayni vade scenario'su girebilir.


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reasons: tuple[str, ...]
    amount_rule_max_maturity: int | None = None


def _decimal_or_none(
    value: Any,
) -> Decimal | None:

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    text = str(value).strip()

    if not text:
        return None

    try:
        return Decimal(text)
    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return None


def _int_or_none(
    value: Any,
) -> int | None:

    number = _decimal_or_none(
        value
    )

    if number is None:
        return None

    try:
        return int(number)
    except Exception:
        return None


def _bool_value(
    value: Any,
    default: bool,
) -> bool:

    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    key = str(value).strip().casefold()

    if key in {
        "true",
        "1",
        "yes",
        "evet",
    }:
        return True

    if key in {
        "false",
        "0",
        "no",
        "hayir",
    }:
        return False

    return default


def _amount_matches_rule(
    amount: Decimal,
    row: pd.Series,
) -> bool:

    minimum = _decimal_or_none(
        row.get("min_amount")
    )

    maximum = _decimal_or_none(
        row.get("max_amount")
    )

    minimum_inclusive = _bool_value(
        row.get("min_inclusive"),
        True,
    )

    maximum_inclusive = _bool_value(
        row.get("max_inclusive"),
        True,
    )


    if minimum is not None:

        if minimum_inclusive:

            if amount < minimum:
                return False

        else:

            if amount <= minimum:
                return False


    if maximum is not None:

        if maximum_inclusive:

            if amount > maximum:
                return False

        else:

            if amount >= maximum:
                return False


    return True


def evaluate_product_eligibility(
    product: pd.Series,
    *,
    amount: float | int | Decimal,
    maturity: int,
    amount_rules: pd.DataFrame | None = None,
) -> EligibilityResult:

    requested_amount = Decimal(
        str(amount)
    )

    requested_maturity = int(
        maturity
    )

    reasons: list[str] = []


    minimum_amount = _decimal_or_none(
        product.get(
            "minimum_financing_amount"
        )
    )

    maximum_amount = _decimal_or_none(
        product.get(
            "maximum_financing_amount"
        )
    )

    minimum_maturity = _int_or_none(
        product.get(
            "minimum_maturity_months"
        )
    )

    maximum_maturity = _int_or_none(
        product.get(
            "maximum_maturity_months"
        )
    )


    if (
        minimum_amount is not None
        and requested_amount < minimum_amount
    ):

        reasons.append(
            "Talep edilen tutar urunun "
            "asgari finansman tutarinin altinda."
        )


    if (
        maximum_amount is not None
        and requested_amount > maximum_amount
    ):

        reasons.append(
            "Talep edilen tutar urunun "
            "azami finansman tutarini asiyor."
        )


    if (
        minimum_maturity is not None
        and requested_maturity < minimum_maturity
    ):

        reasons.append(
            "Talep edilen vade urunun "
            "asgari vadesinin altinda."
        )


    if (
        maximum_maturity is not None
        and requested_maturity > maximum_maturity
    ):

        reasons.append(
            "Talep edilen vade urunun "
            "azami vadesini asiyor."
        )


    amount_rule_max_maturity = None


    if (
        amount_rules is not None
        and not amount_rules.empty
        and "product_id" in amount_rules.columns
    ):

        product_id = _int_or_none(
            product.get("id")
        )

        if product_id is not None:

            subset = amount_rules[
                amount_rules["product_id"]
                == product_id
            ]

            matching_limits: list[int] = []

            for _, row in subset.iterrows():

                if not _amount_matches_rule(
                    requested_amount,
                    row,
                ):
                    continue

                limit = _int_or_none(
                    row.get(
                        "max_maturity_months"
                    )
                )

                if limit is not None:
                    matching_limits.append(
                        limit
                    )


            if matching_limits:

                # Birden fazla ayni anda uygulanabilir resmi kural
                # varsa en koruyucu vade siniri kullanilir.
                amount_rule_max_maturity = min(
                    matching_limits
                )

                if (
                    requested_maturity
                    > amount_rule_max_maturity
                ):

                    reasons.append(
                        "Talep edilen tutarda "
                        "izin verilen azami vade "
                        f"{amount_rule_max_maturity} ay."
                    )


    return EligibilityResult(
        eligible=not reasons,
        reasons=tuple(reasons),
        amount_rule_max_maturity=(
            amount_rule_max_maturity
        ),
    )


def filter_exact_verified_scenarios(
    scenarios: pd.DataFrame,
    *,
    amount: float | int | Decimal,
    maturity: int,
    tolerance: Decimal = Decimal("0.01"),
) -> pd.DataFrame:
    """
    Kullanici karsilastirmasinda yalnizca birebir ayni
    tutar + ayni vade scenario'larini dondurur.

    Farkli benchmark'a fallback YOKTUR.
    """

    if scenarios is None or scenarios.empty:
        return pd.DataFrame(
            columns=(
                scenarios.columns
                if scenarios is not None
                else None
            )
        )


    required = {
        "input_amount",
        "input_maturity_months",
    }

    missing = required.difference(
        scenarios.columns
    )

    if missing:

        raise RuntimeError(
            "Scenario frame missing columns: "
            + ", ".join(
                sorted(missing)
            )
        )


    frame = scenarios.copy()


    if (
        "scenario_status"
        in frame.columns
    ):

        # FINANCE_SCENARIO_VERIFIED_STATUS_V2
        #
        # Dogrulanmis scenario durumlari projede:
        #   verified
        #   verified_live_calculator_mapped
        #   verified_live_calculator_direct_mapping
        #   verified_published_example
        # gibi ayrintili alt durumlar kullanabilir.
        #
        # Ortak senaryo motoru yalnizca "verified" esitligini
        # degil, verified ile baslayan tum dogrulanmis
        # durumlari kabul eder.
        _verified_status = (
            frame["scenario_status"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.casefold()
        )

        frame = frame[
            _verified_status.str.startswith(
                "verified"
            )
        ].copy()


    requested_amount = Decimal(
        str(amount)
    )

    requested_maturity = int(
        maturity
    )


    def amount_is_exact(
        value: Any,
    ) -> bool:

        parsed = _decimal_or_none(
            value
        )

        if parsed is None:
            return False

        return (
            abs(
                parsed
                - requested_amount
            )
            <= tolerance
        )


    amount_mask = frame[
        "input_amount"
    ].apply(
        amount_is_exact
    )


    maturity_mask = (
        pd.to_numeric(
            frame[
                "input_maturity_months"
            ],
            errors="coerce",
        )
        .eq(
            requested_maturity
        )
    )


    return frame[
        amount_mask
        & maturity_mask
    ].copy()


def exact_scenarios_by_product(
    scenarios: pd.DataFrame,
    *,
    amount: float | int | Decimal,
    maturity: int,
) -> dict[int, pd.DataFrame]:

    exact = filter_exact_verified_scenarios(
        scenarios,
        amount=amount,
        maturity=maturity,
    )

    if exact.empty:
        return {}


    result: dict[
        int,
        pd.DataFrame,
    ] = {}


    for product_id, group in exact.groupby(
        "product_id",
        sort=False,
    ):

        result[
            int(product_id)
        ] = group.copy()


    return result


def assert_single_common_scenario(
    scenarios: pd.DataFrame,
    *,
    amount: float | int | Decimal,
    maturity: int,
) -> None:
    """
    UI'ya girecek scenario setinin baska tutar/vade
    icermedigini dogrular.
    """

    if scenarios is None or scenarios.empty:
        return


    exact = filter_exact_verified_scenarios(
        scenarios,
        amount=amount,
        maturity=maturity,
    )


    if len(exact) != len(scenarios):

        raise RuntimeError(
            "Mixed financing scenarios detected. "
            "Comparison requires one common "
            "amount and one common maturity."
        )
