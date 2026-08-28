from __future__ import annotations

"""Shared official finance-calculator resolution for BANSA UI + chatbot.

The service is intentionally conservative:
- official live adapters are attempted first for the exact user amount/maturity;
- only VERIFIED + exact-match results become numeric rows;
- condition-specific variants are expanded explicitly;
- if a live endpoint is unreachable or no verified mapping exists, callers may
  fall back to the existing deterministic V43 projection layer;
- no HTTP failure is converted into guessed finance numbers.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from typing import Any, Iterable

import src.finance_live_compare as finance_live_compare
from src.finance_live_contract import (
    LiveCalculationRequest,
    LiveCalculationResult,
    LiveCalculationStatus,
    validate_live_result,
)


# Calculators that price condition-specific variants and correctly refuse a
# generic request are expanded with these explicit, already-verified mappings.
_VARIANTS_BY_ADAPTER_AND_FAMILY: dict[tuple[str, str], tuple[str, ...]] = {
    ("AlbarakaKonutLiveAdapter", "konut_finansmani"): ("ilk_ev", "mevcut_konut"),
    ("DunyaKatilimLiveAdapter", "konut_finansmani"): ("yeni_konut", "2el_konut"),
    ("EmlakKatilimLiveAdapter", "arac_finansmani"): ("0km", "2el"),
    ("EmlakKatilimLiveAdapter", "konut_finansmani"): ("yeni_konut",),
    ("EmlakKatilimLiveAdapter", "ihtiyac_finansmani"): ("standard",),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _request(row, amount: int | float | Decimal, maturity: int, *, variant: str | None = None) -> LiveCalculationRequest:
    return LiveCalculationRequest(
        product_id=int(row.get("id")),
        bank_name=_text(row.get("bank_name")),
        product_name=_text(row.get("product_name")),
        family_key=_text(row.get("product_family_key")),
        amount=Decimal(str(amount)),
        maturity_months=int(maturity),
        variant=variant,
    )


def _matching_adapter(row, amount: int | float | Decimal, maturity: int, adapters=None):
    adapters = list(finance_live_compare.default_live_adapters() if adapters is None else adapters)
    req = _request(row, amount, maturity)
    matches = [adapter for adapter in adapters if adapter.can_handle(req)]
    if len(matches) != 1:
        return None
    return matches[0]


def is_live_capable_row(row, *, adapters=None) -> bool:
    """Whether BANSA has an explicit official-calculator mapping for this row.

    This is a mapping/capability metric only. It does not claim that the bank
    endpoint is reachable at this exact moment.
    """
    try:
        return _matching_adapter(row, Decimal("100000"), 12, adapters=adapters) is not None
    except Exception:
        return False


def _result_variant(result: LiveCalculationResult) -> str:
    direct = _text(getattr(result.request, "variant", None))
    if direct:
        return direct
    raw = result.raw_output if isinstance(result.raw_output, dict) else {}
    return _text(raw.get("variant")) or _text(raw.get("calculator_title")) or "standard"


def _convert(result: LiveCalculationResult, row) -> dict[str, Any] | None:
    try:
        validate_live_result(result)
    except Exception:
        return None
    if result.status != LiveCalculationStatus.VERIFIED or not result.is_exact_match:
        return None
    if result.profit_share_rate is None or result.monthly_installment is None or result.total_repayment is None:
        return None
    checked = result.checked_at.isoformat() if result.checked_at is not None else ""
    return {
        "bank_name": _text(row.get("bank_name")),
        "product_name": _text(row.get("product_name")),
        "variant": _result_variant(result),
        "rate": result.profit_share_rate,
        "monthly": result.monthly_installment,
        "total": result.total_repayment,
        "fees": result.total_fees,
        "allocation_fee": result.allocation_fee,
        "appraisal_fee": result.appraisal_fee,
        "mortgage_fee": result.mortgage_fee,
        "source_kind": result.source_kind or "official_live_calculator_endpoint",
        "source_url": result.source_url or _text(row.get("source_url")),
        "source_note": result.source_note or "",
        "checked_at": checked,
        "freshness_mode": "live_calculator",
        "result_status": "VERIFIED",
    }


def live_records_for_row(
    row,
    amount: int | float | Decimal,
    maturity: int,
    *,
    adapters: Iterable[Any] | None = None,
) -> list[dict[str, Any]]:
    """Resolve exact verified official-calculator outputs for one product row."""
    try:
        adapter = _matching_adapter(row, amount, maturity, adapters=adapters)
    except Exception:
        return []
    if adapter is None:
        return []

    base_request = _request(row, amount, maturity)
    output: list[dict[str, Any]] = []

    try:
        direct_result = adapter.calculate(base_request)
    except Exception:
        direct_result = None

    if direct_result is not None:
        direct = _convert(direct_result, row)
        if direct is not None:
            output.append(direct)

        # Contract-level conditional variants, when supplied by an adapter.
        for child in getattr(direct_result, "conditional_verified_variants", ()) or ():
            converted = _convert(child, row)
            if converted is not None:
                output.append(converted)

    if output:
        return _dedupe(output)

    family = _text(row.get("product_family_key")).casefold()
    variants = _VARIANTS_BY_ADAPTER_AND_FAMILY.get((type(adapter).__name__, family), ())
    for variant in variants:
        req = _request(row, amount, maturity, variant=variant)
        if not adapter.can_handle(req):
            continue
        try:
            converted = _convert(adapter.calculate(req), row)
        except Exception:
            converted = None
        if converted is not None:
            output.append(converted)

    return _dedupe(output)


def _dedupe(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out: list[dict[str, Any]] = []
    for rec in records:
        key = (
            _text(rec.get("variant")).casefold(),
            str(rec.get("rate")),
            str(rec.get("monthly")),
            str(rec.get("total")),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    return out


def live_capable_bank_count(products, *, adapters=None) -> int:
    banks: set[str] = set()
    for _, row in products.iterrows():
        if is_live_capable_row(row, adapters=adapters):
            banks.add(_text(row.get("bank_name")))
    return len({b for b in banks if b})


def live_records_for_rows(
    products,
    amount: int | float | Decimal,
    maturity: int,
    *,
    adapters: Iterable[Any] | None = None,
    max_workers: int = 6,
) -> dict[int, list[dict[str, Any]]]:
    """Resolve mapped official calculators concurrently for a product frame.

    Concurrency is presentation/runtime isolation only; every individual result
    still has to satisfy the exact VERIFIED finance contract.  A bank timeout
    therefore cannot block all other banks or become a guessed result.
    """
    items = [row.copy() for _, row in products.iterrows()]
    if not items:
        return {}

    adapter_list = list(finance_live_compare.default_live_adapters() if adapters is None else adapters)
    workers = max(1, min(int(max_workers or 1), len(items)))
    out: dict[int, list[dict[str, Any]]] = {}

    def _run(row):
        pid = int(row.get("id"))
        return pid, live_records_for_row(
            row, amount, maturity, adapters=adapter_list
        )

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bansa-live-finance") as pool:
        futures = [pool.submit(_run, row) for row in items]
        for future in as_completed(futures):
            try:
                pid, records = future.result()
            except Exception:
                continue
            out[pid] = records

    return out
