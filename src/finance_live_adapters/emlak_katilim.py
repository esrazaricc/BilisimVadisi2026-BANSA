# FINANCE_LIVE_ADAPTER_EMLAK_V1

from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)

from decimal import Decimal
from typing import Any

import requests


from src.finance_live_contract import (
    FinanceLiveAdapter,
    LiveCalculationRequest,
    LiveCalculationResult,
    LiveCalculationStatus,
    validate_live_result,
)


# Reuse the already verified official calculator contract
# and product mappings without changing the legacy sync script.
from scripts.finance_scenarios import (
    sync_emlak_katilim as legacy,
)


PLAN_TOLERANCE = Decimal("0.50")
BALANCE_TOLERANCE = Decimal("0.01")
FEE_TOLERANCE = Decimal("0.01")


def _decimal(
    value: Any,
) -> Decimal | None:

    if value is None:
        return None

    try:
        return Decimal(
            str(value)
        )

    except Exception:
        return None


def _normalized(
    value: Any,
) -> str:

    return (
        str(
            value
            or ""
        )
        .strip()
        .casefold()
    )


class EmlakKatilimLiveAdapter(
    FinanceLiveAdapter,
):

    bank_name = legacy.BANK_NAME


    def _matching_mappings(
        self,
        request: LiveCalculationRequest,
    ) -> list[dict[str, Any]]:

        matches = []

        for mapping in legacy.MAPPINGS:

            if (
                int(
                    mapping[
                        "product_id"
                    ]
                )
                != int(
                    request.product_id
                )
            ):
                continue


            if (
                _normalized(
                    mapping[
                        "family_key"
                    ]
                )
                !=
                _normalized(
                    request.family_key
                )
            ):
                continue


            if (
                request.variant
                is not None
                and
                _normalized(
                    mapping[
                        "variant"
                    ]
                )
                !=
                _normalized(
                    request.variant
                )
            ):
                continue


            matches.append(
                mapping
            )


        return matches


    def can_handle(
        self,
        request: LiveCalculationRequest,
    ) -> bool:

        if (
            _normalized(
                request.bank_name
            )
            !=
            _normalized(
                self.bank_name
            )
        ):
            return False


        return bool(
            self._matching_mappings(
                request
            )
        )


    def _unverified(
        self,
        request: LiveCalculationRequest,
        reason: str,
    ) -> LiveCalculationResult:

        result = LiveCalculationResult(
            request=request,
            status=(
                LiveCalculationStatus.UNVERIFIED
            ),
            reason=reason,
        )

        return validate_live_result(
            result
        )


    def _ineligible(
        self,
        request: LiveCalculationRequest,
        reason: str,
    ) -> LiveCalculationResult:

        result = LiveCalculationResult(
            request=request,
            status=(
                LiveCalculationStatus.INELIGIBLE
            ),
            reason=reason,
        )

        return validate_live_result(
            result
        )


    def _fetch_property(
        self,
        session: requests.Session,
        mapping: dict[str, Any],
        request: LiveCalculationRequest,
    ) -> (
        dict[str, Any]
        |
        LiveCalculationResult
    ):

        response = session.get(
            legacy.PROPERTY_ENDPOINT,
            params={
                "ProductTypeId":
                    mapping[
                        "calculator_code"
                    ],
            },
            headers=legacy.AJAX_HEADERS,
            timeout=30,
        )

        response.raise_for_status()

        payload = response.json()


        if (
            not isinstance(
                payload,
                dict,
            )
            or
            not payload.get(
                "Success"
            )
            or
            not isinstance(
                payload.get(
                    "Data"
                ),
                dict,
            )
        ):

            return self._unverified(
                request,
                (
                    "Official maturity property "
                    "endpoint did not return a "
                    "verifiable result."
                ),
            )


        data = (
            payload.get(
                "Data"
            )
            or {}
        )


        try:

            maturity_min = int(
                data.get(
                    "MaturityMin"
                )
            )

        except Exception:

            maturity_min = None


        try:

            maturity_max = int(
                data.get(
                    "MaturityMax"
                )
            )

        except Exception:

            maturity_max = None


        requested_months = int(
            request.maturity_months
        )


        if (
            maturity_max is not None
            and
            requested_months
            > maturity_max
        ):

            return self._ineligible(
                request,
                (
                    "Requested maturity exceeds "
                    "the official calculator "
                    f"maximum ({maturity_max} months)."
                ),
            )


        # Existing verified Emlak integration interprets
        # MaturityMin as the lower boundary immediately
        # preceding the first selectable maturity.
        if (
            maturity_min is not None
            and
            requested_months
            < maturity_min + 1
        ):

            return self._ineligible(
                request,
                (
                    "Requested maturity is below "
                    "the official calculator "
                    "selectable maturity range."
                ),
            )


        return {
            "payload":
                payload,

            "data":
                data,

            "maturity_min":
                maturity_min,

            "maturity_max":
                maturity_max,
        }


    def _calculate_mapping(
        self,
        request: LiveCalculationRequest,
        mapping: dict[str, Any],
    ) -> LiveCalculationResult:

        session = legacy.create_session()


        # Fail closed if the official calculator
        # catalog or bank-rate semantics changed.
        legacy.discover_official_catalog(
            session
        )


        property_result = (
            self._fetch_property(
                session,
                mapping,
                request,
            )
        )


        if isinstance(
            property_result,
            LiveCalculationResult,
        ):

            return property_result


        requested_amount = Decimal(
            str(
                request.amount
            )
        )

        requested_months = int(
            request.maturity_months
        )


        amount_text = format(
            requested_amount,
            "f",
        )

        if (
            requested_amount
            ==
            requested_amount.to_integral_value()
        ):

            amount_text = str(
                int(
                    requested_amount
                )
            )


        params = {
            "CalculationTypeId":
                "1",

            "ProductTypeId":
                mapping[
                    "calculator_code"
                ],

            "LoanAmount":
                amount_text,

            "LoanMaturity":
                str(
                    requested_months
                ),

            "LoanSegmentId":
                mapping[
                    "segment_id"
                ],
        }


        response = session.get(
            legacy.CALCULATOR_ENDPOINT,
            params=params,
            headers=legacy.AJAX_HEADERS,
            timeout=30,
        )

        response.raise_for_status()


        payload = response.json()


        if (
            not isinstance(
                payload,
                dict,
            )
            or
            not payload.get(
                "Success"
            )
            or
            not isinstance(
                payload.get(
                    "Data"
                ),
                dict,
            )
            or
            not payload.get(
                "Data"
            )
        ):

            # Calculator rejection by itself is not
            # automatically interpreted as ineligible.
            # Without an explicit rule it remains
            # UNVERIFIED.
            return self._unverified(
                request,
                (
                    "Official live calculator did "
                    "not return a verifiable result "
                    "for the exact requested "
                    "amount and maturity."
                ),
            )


        data = payload[
            "Data"
        ]


        rate = _decimal(
            data.get(
                "ProfitRate"
            )
        )

        funding = _decimal(
            data.get(
                "FundingAmount"
            )
        )

        total = _decimal(
            data.get(
                "TotalInstallmentAmount"
            )
        )

        commission = _decimal(
            data.get(
                "CommissionAmount"
            )
        )

        mortgage = _decimal(
            data.get(
                "HypothecAmount"
            )
        )

        appraisal = _decimal(
            data.get(
                "ExpertiseAmount"
            )
        )

        total_fees = _decimal(
            data.get(
                "TotalExpense"
            )
        )


        plan = (
            data.get(
                "InstallmentContractList"
            )
            or []
        )


        if (
            funding is None
            or
            funding
            != requested_amount
        ):

            return self._unverified(
                request,
                (
                    "Official calculator returned "
                    "a funding amount different "
                    "from the requested amount."
                ),
            )


        try:

            installment_count = int(
                data.get(
                    "InstallmentCount"
                )
            )

        except Exception:

            installment_count = None


        if (
            installment_count
            != requested_months
        ):

            return self._unverified(
                request,
                (
                    "Official calculator returned "
                    "a maturity different from "
                    "the requested maturity."
                ),
            )


        if (
            len(
                plan
            )
            != requested_months
        ):

            return self._unverified(
                request,
                (
                    "Official payment-plan row "
                    "count does not match the "
                    "requested maturity."
                ),
            )


        plan_values = [
            _decimal(
                row.get(
                    "Amount"
                )
            )
            for row in plan
        ]


        if (
            not plan_values
            or
            any(
                value is None
                for value
                in plan_values
            )
        ):

            return self._unverified(
                request,
                (
                    "Official payment plan contains "
                    "an unverifiable installment."
                ),
            )


        monthly = plan_values[
            0
        ]


        plan_sum = sum(
            plan_values,
            Decimal("0"),
        )


        if (
            total is None
            or
            total <= 0
        ):

            return self._unverified(
                request,
                (
                    "Official total repayment "
                    "could not be verified."
                ),
            )


        plan_delta = abs(
            plan_sum
            - total
        )


        if (
            plan_delta
            > PLAN_TOLERANCE
        ):

            return self._unverified(
                request,
                (
                    "Official payment-plan sum "
                    "does not match the official "
                    "total repayment."
                ),
            )


        final_balance = _decimal(
            plan[
                -1
            ].get(
                "RemainingPrincipalAmount"
            )
        )


        if (
            final_balance is None
            or
            abs(
                final_balance
            )
            > BALANCE_TOLERANCE
        ):

            return self._unverified(
                request,
                (
                    "Official payment plan does "
                    "not close with a verified "
                    "zero remaining principal."
                ),
            )


        if (
            rate is None
            or
            rate <= 0
            or
            monthly is None
            or
            monthly <= 0
        ):

            return self._unverified(
                request,
                (
                    "Official calculator returned "
                    "missing or invalid core "
                    "financial values."
                ),
            )


        fee_component_sum = (
            (
                commission
                or Decimal("0")
            )
            +
            (
                mortgage
                or Decimal("0")
            )
            +
            (
                appraisal
                or Decimal("0")
            )
        )


        fee_delta = (
            abs(
                fee_component_sum
                - total_fees
            )
            if total_fees
            is not None
            else None
        )


        fee_warning = (
            fee_delta is not None
            and
            fee_delta
            > FEE_TOLERANCE
        )


        # Preserve the legacy verified semantic guard.
        # Housing calculator may expose an official
        # TotalExpense/component delta; other mappings
        # must remain exact.
        if (
            mapping[
                "calculator_code"
            ]
            != "GMENKULKONUTYENI"
            and
            fee_warning
        ):

            return self._unverified(
                request,
                (
                    "Official calculator fee "
                    "components no longer match "
                    "the official total expense."
                ),
            )


        result = LiveCalculationResult(
            request=request,

            status=(
                LiveCalculationStatus.VERIFIED
            ),

            calculated_amount=
                funding,

            calculated_maturity_months=
                installment_count,

            profit_share_rate=
                rate,

            monthly_installment=
                monthly,

            total_repayment=
                total,

            allocation_fee=
                commission,

            mortgage_fee=
                mortgage,

            appraisal_fee=
                appraisal,

            total_fees=
                total_fees,

            source_kind=(
                "official_live_calculator_endpoint"
            ),

            source_url=
                legacy.CALCULATOR_PAGE,

            source_note=(
                "T?rkiye Emlak Kat?l?m official "
                "bank-rate calculator result for "
                "the exact requested amount and "
                "maturity. CustomRate is omitted."
            ),

            checked_at=datetime.now(
                timezone.utc
            ),

            raw_output={
                "calculator_code":
                    mapping[
                        "calculator_code"
                    ],

                "calculator_title":
                    mapping[
                        "calculator_title"
                    ],

                "segment_id":
                    mapping[
                        "segment_id"
                    ],

                "variant":
                    mapping[
                        "variant"
                    ],

                "request_params":
                    params,

                "property_response":
                    property_result[
                        "payload"
                    ],

                "calculator_response":
                    payload,

                "validation": {
                    "payment_plan_sum":
                        str(
                            plan_sum
                        ),

                    "official_total":
                        str(
                            total
                        ),

                    "plan_delta":
                        str(
                            plan_delta
                        ),

                    "final_balance":
                        str(
                            final_balance
                        ),

                    "fee_component_sum":
                        str(
                            fee_component_sum
                        ),

                    "fee_delta":
                        (
                            str(
                                fee_delta
                            )
                            if fee_delta
                            is not None
                            else None
                        ),

                    "fee_warning":
                        fee_warning,
                },
            },
        )


        return validate_live_result(
            result
        )


    def calculate(
        self,
        request: LiveCalculationRequest,
    ) -> LiveCalculationResult:

        if (
            _normalized(
                request.bank_name
            )
            !=
            _normalized(
                self.bank_name
            )
        ):

            return self._unverified(
                request,
                (
                    "Request bank does not match "
                    "T?rkiye Emlak Kat?l?m adapter."
                ),
            )


        mappings = self._matching_mappings(
            request
        )


        if not mappings:

            return self._unverified(
                request,
                (
                    "No verified calculator mapping "
                    "exists for this product."
                ),
            )


        if len(
            mappings
        ) > 1:

            return self._unverified(
                request,
                (
                    "This product has multiple "
                    "calculator variants. A variant "
                    "must be selected explicitly."
                ),
            )


        try:

            return self._calculate_mapping(
                request,
                mappings[
                    0
                ],
            )


        except requests.RequestException as exc:

            return self._unverified(
                request,
                (
                    "Official calculator could not "
                    "be reached: "
                    f"{type(exc).__name__}"
                ),
            )


        except Exception as exc:

            # Fail closed. Unexpected parsing/semantic
            # changes never become guessed financial data.
            return self._unverified(
                request,
                (
                    "Official calculator result "
                    "could not be verified: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
