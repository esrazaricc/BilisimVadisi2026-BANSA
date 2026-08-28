# FINANCE_LIVE_CONTRACT_V1

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable


class LiveCalculationStatus(
    str,
    Enum,
):
    """
    Strict tri-state status used by the comparison engine.

    VERIFIED:
        Official calculator/source produced a verified
        result for the exact requested amount + maturity.

    INELIGIBLE:
        Official product/calculator evidence proves that
        the requested scenario is not supported.

    UNVERIFIED:
        There is not enough authoritative evidence to
        produce a numeric comparison.
    """

    VERIFIED = "VERIFIED"
    INELIGIBLE = "INELIGIBLE"
    UNVERIFIED = "UNVERIFIED"



# ============================================================
# FINANCE_RESOLUTION_REASON_CODES_V1
# ============================================================

class FinanceResolutionReasonCode(
    str,
    Enum,
):
    """
    Machine-readable explanation for non-rankable finance results.

    Status answers WHAT happened.
    reason_code answers WHY numeric resolution was not allowed.

    Human-readable details remain in LiveCalculationResult.reason.
    """

    REQUEST_INELIGIBLE = (
        "REQUEST_INELIGIBLE"
    )

    VARIANT_REQUIRED = (
        "VARIANT_REQUIRED"
    )

    CALCULATOR_MAPPING_MISSING = (
        "CALCULATOR_MAPPING_MISSING"
    )

    PRICING_NOT_PROVEN = (
        "PRICING_NOT_PROVEN"
    )

    NUMERIC_SOURCE_UNAVAILABLE = (
        "NUMERIC_SOURCE_UNAVAILABLE"
    )


@dataclass(
    frozen=True,
)
class LiveCalculationRequest:
    """
    One exact user comparison request.

    amount and maturity_months are never benchmark
    defaults here. They represent the user's actual
    requested common comparison dimensions.
    """

    product_id: int
    bank_name: str
    product_name: str
    family_key: str

    amount: Decimal
    maturity_months: int

    variant: str | None = None

    metadata: Mapping[
        str,
        Any,
    ] = field(
        default_factory=dict
    )


    def __post_init__(
        self,
    ) -> None:

        if int(
            self.product_id
        ) <= 0:
            raise ValueError(
                "product_id must be positive."
            )

        if Decimal(
            str(
                self.amount
            )
        ) <= 0:
            raise ValueError(
                "amount must be positive."
            )

        if int(
            self.maturity_months
        ) <= 0:
            raise ValueError(
                "maturity_months must be positive."
            )

        if not str(
            self.bank_name
        ).strip():
            raise ValueError(
                "bank_name is required."
            )

        if not str(
            self.product_name
        ).strip():
            raise ValueError(
                "product_name is required."
            )

        if not str(
            self.family_key
        ).strip():
            raise ValueError(
                "family_key is required."
            )


@dataclass
class LiveCalculationResult:
    """
    Normalized output returned by every bank adapter.

    IMPORTANT:
    A VERIFIED result must match the exact amount and
    maturity from LiveCalculationRequest.

    A result for another amount or another maturity is
    never accepted as fallback.
    """

    request: LiveCalculationRequest

    status: LiveCalculationStatus

    calculated_amount: Decimal | None = None

    calculated_maturity_months: int | None = None

    profit_share_rate: Decimal | None = None

    monthly_installment: Decimal | None = None

    total_repayment: Decimal | None = None

    allocation_fee: Decimal | None = None

    mortgage_fee: Decimal | None = None

    appraisal_fee: Decimal | None = None

    total_fees: Decimal | None = None

    source_kind: str | None = None

    source_url: str | None = None

    source_note: str | None = None

    checked_at: datetime | None = None

    reason: str | None = None

    reason_code: (
        FinanceResolutionReasonCode
        | None
    ) = None

    # ========================================================
    # FINANCE_CONDITIONAL_VERIFIED_VARIANTS_V1
    #
    # A generic request may have more than one independently
    # VERIFIED exact pricing condition.
    #
    # Example:
    # - insured
    # - uninsured
    #
    # The parent remains UNVERIFIED/non-rankable because no
    # single condition was selected by the user. Each child,
    # however, must independently satisfy the full VERIFIED
    # finance contract.
    # ========================================================

    conditional_verified_variants: tuple[
        "LiveCalculationResult",
        ...,
    ] = field(
        default_factory=tuple
    )

    raw_output: dict[
        str,
        Any,
    ] = field(
        default_factory=dict
    )


    @property
    def is_exact_match(
        self,
    ) -> bool:

        if (
            self.calculated_amount
            is None
            or
            self.calculated_maturity_months
            is None
        ):
            return False

        return (
            Decimal(
                str(
                    self.calculated_amount
                )
            )
            ==
            Decimal(
                str(
                    self.request.amount
                )
            )
            and
            int(
                self.calculated_maturity_months
            )
            ==
            int(
                self.request.maturity_months
            )
        )


    @property
    def is_rankable(
        self,
    ) -> bool:

        return (
            self.status
            == LiveCalculationStatus.VERIFIED
            and
            self.is_exact_match
            and
            self.profit_share_rate
            is not None
            and
            self.monthly_installment
            is not None
            and
            self.total_repayment
            is not None
        )


    def validate(
        self,
    ) -> None:
        """
        Fail closed.

        VERIFIED results must have exact dimensions and
        positive core financial values.

        INELIGIBLE / UNVERIFIED results cannot carry
        ranking values.
        """

        if (
            self.reason_code is not None
            and
            not isinstance(
                self.reason_code,
                FinanceResolutionReasonCode,
            )
        ):
            raise ValueError(
                "Invalid finance resolution reason_code."
            )


        if (
            self.status
            == LiveCalculationStatus.VERIFIED
            and
            self.reason_code is not None
        ):
            raise ValueError(
                "VERIFIED finance result cannot carry "
                "a failure reason_code."
            )


        conditional = tuple(
            self.conditional_verified_variants
            or ()
        )


        if conditional:

            if (
                self.status
                !=
                LiveCalculationStatus.UNVERIFIED
            ):
                raise ValueError(
                    "Conditional verified variants "
                    "require an UNVERIFIED parent."
                )

            if self.request.variant is not None:
                raise ValueError(
                    "Conditional verified variants "
                    "require a generic parent request."
                )

            seen_variants = set()

            for child in conditional:

                if not isinstance(
                    child,
                    LiveCalculationResult,
                ):
                    raise ValueError(
                        "Invalid conditional finance "
                        "variant result."
                    )

                child.validate()

                if (
                    child.status
                    !=
                    LiveCalculationStatus.VERIFIED
                    or
                    not child.is_exact_match
                    or
                    not child.is_rankable
                ):
                    raise ValueError(
                        "Conditional finance variant "
                        "must be VERIFIED, exact and "
                        "rankable."
                    )

                if (
                    int(
                        child.request.product_id
                    )
                    !=
                    int(
                        self.request.product_id
                    )
                ):
                    raise ValueError(
                        "Conditional finance variant "
                        "product mismatch."
                    )

                if (
                    Decimal(
                        str(
                            child.request.amount
                        )
                    )
                    !=
                    Decimal(
                        str(
                            self.request.amount
                        )
                    )
                    or
                    int(
                        child.request
                        .maturity_months
                    )
                    !=
                    int(
                        self.request
                        .maturity_months
                    )
                ):
                    raise ValueError(
                        "Conditional finance variant "
                        "scenario mismatch."
                    )

                variant = str(
                    child.request.variant
                    or ""
                ).strip()

                if not variant:
                    raise ValueError(
                        "Conditional finance variant "
                        "requires a variant key."
                    )

                normalized_variant = (
                    variant.casefold()
                )

                if (
                    normalized_variant
                    in seen_variants
                ):
                    raise ValueError(
                        "Duplicate conditional finance "
                        "variant."
                    )

                seen_variants.add(
                    normalized_variant
                )


        if (
            self.status
            == LiveCalculationStatus.VERIFIED
        ):

            if not self.is_exact_match:

                raise ValueError(
                    "Verified live calculation does not "
                    "match requested amount/maturity."
                )


            required_positive = {
                "profit_share_rate":
                    self.profit_share_rate,

                "monthly_installment":
                    self.monthly_installment,

                "total_repayment":
                    self.total_repayment,
            }


            for (
                field_name,
                value,
            ) in required_positive.items():

                if value is None:

                    raise ValueError(
                        "Verified live calculation "
                        f"missing {field_name}."
                    )

                if Decimal(
                    str(
                        value
                    )
                ) <= 0:

                    raise ValueError(
                        "Verified live calculation has "
                        f"invalid {field_name}."
                    )


            if not str(
                self.source_url
                or ""
            ).strip():

                raise ValueError(
                    "Verified live calculation "
                    "requires source_url."
                )


            if self.checked_at is None:

                raise ValueError(
                    "Verified live calculation "
                    "requires checked_at."
                )


            return


        forbidden_numeric = {
            "profit_share_rate":
                self.profit_share_rate,

            "monthly_installment":
                self.monthly_installment,

            "total_repayment":
                self.total_repayment,
        }


        leaked = [
            field_name
            for (
                field_name,
                value,
            ) in forbidden_numeric.items()
            if value is not None
        ]


        if leaked:

            raise ValueError(
                "Non-verified result contains "
                "rankable numeric fields: "
                + ", ".join(
                    leaked
                )
            )


        if not str(
            self.reason
            or ""
        ).strip():

            raise ValueError(
                "INELIGIBLE/UNVERIFIED result "
                "requires a reason."
            )


@runtime_checkable
class FinanceLiveAdapter(
    Protocol,
):
    """
    Common contract implemented by every bank adapter.
    """

    bank_name: str


    def can_handle(
        self,
        request: LiveCalculationRequest,
    ) -> bool:
        ...


    def calculate(
        self,
        request: LiveCalculationRequest,
    ) -> LiveCalculationResult:
        ...


def validate_live_result(
    result: LiveCalculationResult,
) -> LiveCalculationResult:
    """
    Central validation gate used before a result reaches
    compare_financing() or the chatbot.
    """

    result.validate()

    return result
