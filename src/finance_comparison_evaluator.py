# UNIVERSAL_FINANCE_COMPARISON_EVALUATOR_V2

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True)
class FinanceCriterionResult:

    field: str
    label: str

    winner_product_ids: tuple[int, ...]
    winner_labels: tuple[str, ...]

    best_value: Decimal
    comparable_count: int


@dataclass(frozen=True)
class FinanceComparisonEvaluation:

    ranking_allowed: bool

    winner_product_ids: tuple[int, ...]
    winner_labels: tuple[str, ...]

    overall_metric: str | None
    overall_metric_label: str | None
    overall_best_value: Decimal | None

    criteria: tuple[
        FinanceCriterionResult,
        ...
    ]

    reason: str


CRITERIA = (
    (
        "profit_share_rate",
        "K\u00e2r pay\u0131 oran\u0131",
    ),
    (
        "monthly_installment",
        "Ayl\u0131k taksit",
    ),
    (
        "total_repayment",
        "Toplam geri \u00f6deme",
    ),
    (
        "allocation_fee",
        "Tahsis \u00fccreti",
    ),
    (
        "appraisal_fee",
        "Ekspertiz \u00fccreti",
    ),
    (
        "mortgage_fee",
        "\u0130potek \u00fccreti",
    ),
    (
        "total_fees",
        "Toplam do\u011frulanm\u0131\u015f \u00fccret",
    ),
)


def _decimal(
    value,
) -> Decimal | None:

    if value is None:

        return None

    if isinstance(
        value,
        Decimal,
    ):

        return value

    try:

        return Decimal(
            str(
                value
            )
        )

    except Exception:

        return None


def _product_id(
    item,
) -> int:

    return int(
        getattr(
            item,
            "product_id",
        )
    )


def candidate_label(
    item,
) -> str:

    bank = str(
        getattr(
            item,
            "bank_name",
            "",
        )
        or ""
    ).strip()

    product = str(
        getattr(
            item,
            "product_name",
            "",
        )
        or ""
    ).strip()


    if (
        bank
        and
        product
    ):

        return (
            bank
            + " - "
            + product
        )


    return (
        bank
        or
        product
        or
        "Finansman"
    )


def _is_safe_rank_candidate(
    item,
) -> bool:
    """
    Keep exactly the existing grounding idea:

    - verified
    - exact match
    - rankable

    must all be true.
    """

    return bool(
        getattr(
            item,
            "verified",
            False,
        )
        and
        getattr(
            item,
            "exact_match",
            False,
        )
        and
        getattr(
            item,
            "rankable",
            False,
        )
    )


def _criterion(
    candidates,
    *,
    field: str,
    label: str,
) -> FinanceCriterionResult | None:
    """
    A criterion is compared only when EVERY safe
    candidate has a numeric value for that field.

    This prevents missing fee information from
    making another bank look artificially cheaper.
    """

    if len(
        candidates
    ) < 2:

        return None


    values = []


    for item in candidates:

        value = _decimal(
            getattr(
                item,
                field,
                None,
            )
        )


        if value is None:

            return None


        values.append(
            (
                item,
                value,
            )
        )


    best_value = min(
        value
        for _item, value
        in values
    )


    winners = tuple(
        item
        for item, value
        in values
        if value == best_value
    )


    return FinanceCriterionResult(
        field=field,
        label=label,

        winner_product_ids=tuple(
            _product_id(
                item
            )
            for item
            in winners
        ),

        winner_labels=tuple(
            candidate_label(
                item
            )
            for item
            in winners
        ),

        best_value=best_value,
        comparable_count=len(
            values
        ),
    )


def evaluate_finance_results(
    results: Iterable,
    *,
    allow_ranking: bool,
) -> FinanceComparisonEvaluation:
    """
    Universal deterministic finance comparison.

    No LLM is used.

    Overall decision:
      1. If every safe candidate has both
         total_repayment and total_fees:
           total_repayment + total_fees

      2. Otherwise, if every safe candidate
         has total_repayment:
           total_repayment

      3. Otherwise:
           no overall winner.
    """

    all_results = tuple(
        results
        or ()
    )


    candidates = tuple(
        item
        for item
        in all_results
        if _is_safe_rank_candidate(
            item
        )
    )


    if not allow_ranking:

        return FinanceComparisonEvaluation(
            ranking_allowed=False,
            winner_product_ids=tuple(),
            winner_labels=tuple(),
            overall_metric=None,
            overall_metric_label=None,
            overall_best_value=None,
            criteria=tuple(),
            reason=(
                "grounding_contract_blocks_ranking"
            ),
        )


    if len(
        candidates
    ) < 2:

        return FinanceComparisonEvaluation(
            ranking_allowed=False,
            winner_product_ids=tuple(),
            winner_labels=tuple(),
            overall_metric=None,
            overall_metric_label=None,
            overall_best_value=None,
            criteria=tuple(),
            reason=(
                "fewer_than_two_safe_candidates"
            ),
        )


    criteria = []


    for field, label in CRITERIA:

        criterion = _criterion(
            candidates,
            field=field,
            label=label,
        )


        if criterion is not None:

            criteria.append(
                criterion
            )


    # --------------------------------------------------------
    # COMPLETE COST
    # --------------------------------------------------------

    complete_cost_values = []


    for item in candidates:

        repayment = _decimal(
            getattr(
                item,
                "total_repayment",
                None,
            )
        )

        fees = _decimal(
            getattr(
                item,
                "total_fees",
                None,
            )
        )


        if (
            repayment is None
            or
            fees is None
        ):

            complete_cost_values = []
            break


        complete_cost_values.append(
            (
                item,
                repayment + fees,
            )
        )


    if complete_cost_values:

        overall_metric = (
            "overall_total_cost"
        )

        overall_metric_label = (
            "Toplam geri \u00f6deme "
            "+ toplam do\u011frulanm\u0131\u015f \u00fccret"
        )

        overall_values = (
            complete_cost_values
        )

        reason = (
            "complete_repayment_and_fee_coverage"
        )


    else:

        repayment_values = []


        for item in candidates:

            repayment = _decimal(
                getattr(
                    item,
                    "total_repayment",
                    None,
                )
            )


            if repayment is None:

                repayment_values = []
                break


            repayment_values.append(
                (
                    item,
                    repayment,
                )
            )


        if not repayment_values:

            return FinanceComparisonEvaluation(
                ranking_allowed=False,
                winner_product_ids=tuple(),
                winner_labels=tuple(),
                overall_metric=None,
                overall_metric_label=None,
                overall_best_value=None,
                criteria=tuple(
                    criteria
                ),
                reason=(
                    "no_complete_overall_metric"
                ),
            )


        overall_metric = (
            "total_repayment"
        )

        overall_metric_label = (
            "Toplam geri \u00f6deme"
        )

        overall_values = (
            repayment_values
        )

        reason = (
            "fee_coverage_incomplete_"
            "total_repayment_used"
        )


    overall_best = min(
        value
        for _item, value
        in overall_values
    )


    overall_winners = tuple(
        item
        for item, value
        in overall_values
        if value == overall_best
    )


    return FinanceComparisonEvaluation(
        ranking_allowed=True,

        winner_product_ids=tuple(
            _product_id(
                item
            )
            for item
            in overall_winners
        ),

        winner_labels=tuple(
            candidate_label(
                item
            )
            for item
            in overall_winners
        ),

        overall_metric=(
            overall_metric
        ),

        overall_metric_label=(
            overall_metric_label
        ),

        overall_best_value=(
            overall_best
        ),

        criteria=tuple(
            criteria
        ),

        reason=reason,
    )
