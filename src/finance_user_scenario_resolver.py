from __future__ import annotations

"""One authoritative scenario resolver shared by BANSA dashboard + chatbot.

V45 policy
----------
1. If BANSA has an explicit official live-calculator mapping for a product,
   that calculator owns exact amount/maturity pricing.
2. A live-mapped bank that cannot be verified *right now* does NOT silently
   fall back to an older calculator snapshot/rate model.  Returning no number
   is safer than presenting a stale rate as current.
3. Products without an authoritative live mapping may continue to use BANSA's
   existing verified deterministic projection layer (current official pricing
   tables / verified models).

This module exists so the Streamlit dashboard and chatbot cannot drift into
separate finance-resolution policies again.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from src.finance_official_calculator_service import (
    is_live_capable_row,
    live_records_for_row,
    live_records_for_rows,
)
from src.finance_scenario_projection import ScenarioProjection, project_row


@dataclass(frozen=True)
class ScenarioResolution:
    mode: str  # live | model | live_unavailable | none
    live_capable: bool
    live_records: tuple[dict[str, Any], ...] = ()
    projections: tuple[ScenarioProjection, ...] = ()
    reason: str = ""

    @property
    def has_numeric(self) -> bool:
        return bool(self.live_records or self.projections)


def resolve_user_scenario(
    row,
    amount: int | float | Decimal,
    maturity: int,
    *,
    adapters: Iterable[Any] | None = None,
) -> ScenarioResolution:
    """Resolve one exact user-entered amount/maturity scenario.

    Live-mapped banks are fail-closed: if the official calculator does not
    return an exact VERIFIED result, no stale numeric fallback is exposed.
    """
    live_capable = is_live_capable_row(row, adapters=adapters)
    records = live_records_for_row(row, amount, maturity, adapters=adapters)
    if records:
        return ScenarioResolution(
            mode="live",
            live_capable=True,
            live_records=tuple(records),
            reason="official_live_exact",
        )

    if live_capable:
        return ScenarioResolution(
            mode="live_unavailable",
            live_capable=True,
            reason="official_live_not_verified_for_exact_scenario",
        )

    projections = tuple(project_row(row, amount, int(maturity)) or ())
    if projections:
        return ScenarioResolution(
            mode="model",
            live_capable=False,
            projections=projections,
            reason="verified_non_live_model",
        )

    return ScenarioResolution(
        mode="none",
        live_capable=False,
        reason="no_verified_numeric_source",
    )


def resolve_user_scenarios(
    products,
    amount: int | float | Decimal,
    maturity: int,
    *,
    adapters: Iterable[Any] | None = None,
    max_workers: int = 6,
) -> dict[int, ScenarioResolution]:
    """Bulk version used by the dashboard; official calculators run in parallel."""
    items = [row.copy() for _, row in products.iterrows()]
    if not items:
        return {}

    live_map = live_records_for_rows(
        products,
        amount,
        int(maturity),
        adapters=adapters,
        max_workers=max_workers,
    )

    out: dict[int, ScenarioResolution] = {}
    for row in items:
        pid = int(row.get("id"))
        records = tuple(live_map.get(pid, ()) or ())
        live_capable = is_live_capable_row(row, adapters=adapters)

        if records:
            out[pid] = ScenarioResolution(
                mode="live",
                live_capable=True,
                live_records=records,
                reason="official_live_exact",
            )
            continue

        if live_capable:
            out[pid] = ScenarioResolution(
                mode="live_unavailable",
                live_capable=True,
                reason="official_live_not_verified_for_exact_scenario",
            )
            continue

        projections = tuple(project_row(row, amount, int(maturity)) or ())
        if projections:
            out[pid] = ScenarioResolution(
                mode="model",
                live_capable=False,
                projections=projections,
                reason="verified_non_live_model",
            )
        else:
            out[pid] = ScenarioResolution(
                mode="none",
                live_capable=False,
                reason="no_verified_numeric_source",
            )

    return out
