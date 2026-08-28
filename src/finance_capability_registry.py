from __future__ import annotations

"""
BANSA finance numeric capability registry.

FINANCE_CAPABILITY_REGISTRY_V3

Selects WHICH verified numeric capability may answer one exact
finance request.

This module does not calculate finance values itself.

Priority:
1. Explicit official live calculator adapter
2. Explicit verified local deterministic model
3. Exact portable verified calculator snapshot
4. No numeric capability

Safety:
- multiple live adapter matches are rejected
- no amount/maturity approximation
- no implicit pricing extrapolation
- unsupported requests fail closed
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterable

from src.finance_live_contract import (
    LiveCalculationRequest,
    LiveCalculationResult,
)


class FinanceCapabilityKind(str, Enum):

    LIVE_CALCULATOR = "LIVE_CALCULATOR"

    VERIFIED_LOCAL_MODEL = (
        "VERIFIED_LOCAL_MODEL"
    )

    EXACT_PORTABLE_SNAPSHOT = (
        "EXACT_PORTABLE_SNAPSHOT"
    )

    NO_NUMERIC_CAPABILITY = (
        "NO_NUMERIC_CAPABILITY"
    )


@dataclass(frozen=True)
class FinanceCapabilitySelection:

    kind: FinanceCapabilityKind

    provider: Any = None

    resolved_result: (
        LiveCalculationResult
        | None
    ) = None

    reason: str | None = None


def matching_live_adapters(
    request: LiveCalculationRequest,
    adapters: Iterable[Any],
) -> list[Any]:

    matches = [
        adapter
        for adapter in adapters
        if adapter.can_handle(request)
    ]

    if len(matches) > 1:

        raise RuntimeError(
            "Multiple live finance capabilities matched "
            "the same exact product request."
        )

    return matches


def select_finance_capability(
    *,
    request: LiveCalculationRequest,
    adapters: Iterable[Any],
    portable_result_lookup: Callable[
        [LiveCalculationRequest],
        LiveCalculationResult | None,
    ],
    verified_local_model_lookup: (
        Callable[
            [LiveCalculationRequest],
            LiveCalculationResult | None,
        ]
        | None
    ) = None,
) -> FinanceCapabilitySelection:

    live_matches = matching_live_adapters(
        request,
        adapters,
    )

    if live_matches:

        return FinanceCapabilitySelection(
            kind=(
                FinanceCapabilityKind
                .LIVE_CALCULATOR
            ),
            provider=live_matches[0],
            reason=(
                "Explicit verified live calculator "
                "mapping is available."
            ),
        )

    if verified_local_model_lookup is not None:

        local_result = (
            verified_local_model_lookup(
                request
            )
        )

        if local_result is not None:

            return FinanceCapabilitySelection(
                kind=(
                    FinanceCapabilityKind
                    .VERIFIED_LOCAL_MODEL
                ),
                resolved_result=local_result,
                reason=(
                    "Verified local deterministic "
                    "pricing capability is available."
                ),
            )

    portable_result = portable_result_lookup(
        request
    )

    if portable_result is not None:

        return FinanceCapabilitySelection(
            kind=(
                FinanceCapabilityKind
                .EXACT_PORTABLE_SNAPSHOT
            ),
            resolved_result=portable_result,
            reason=(
                "Exact portable verified calculator "
                "scenario is available."
            ),
        )

    return FinanceCapabilitySelection(
        kind=(
            FinanceCapabilityKind
            .NO_NUMERIC_CAPABILITY
        ),
        reason=(
            "No verified dynamic official calculator "
            "adapter or exact portable verified live "
            "scenario is available for this product "
            "and request."
        ),
    )
