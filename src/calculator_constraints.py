"""Verified official calculator UI constraints.

These constraints are deliberately separate from product eligibility rules.

- Product eligibility: asset invoice/kasko value -> financing ratio / term.
- Calculator constraints: requested financing amount / maturity accepted by the
  bank's official calculator UI for a specific product/variant.

Never generalize a term-scoped observation to other maturities.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

from src.competition_fast_router import normalize


@dataclass(frozen=True)
class CalculatorConstraint:
    bank_name: str
    family_key: str
    calculator_product: str
    variant: str | None
    query_markers: tuple[str, ...]
    max_financing_amount: float | None
    min_maturity_months: int | None
    max_maturity_months: int | None
    max_vehicle_age: int | None
    observed_maturity_months: int | None
    amount_limit_mode: str
    source_url: str
    evidence_note: str

    def amount_limit_applies(self, maturity_months: int | None) -> bool:
        if self.max_financing_amount is None:
            return False
        if self.amount_limit_mode == "hard_ui_limit":
            return True
        if self.amount_limit_mode == "term_scoped_observation":
            return (
                maturity_months is not None
                and self.observed_maturity_months is not None
                and int(maturity_months) == int(self.observed_maturity_months)
            )
        return False


@lru_cache(maxsize=1)
def _load() -> tuple[CalculatorConstraint, ...]:
    path = Path(__file__).resolve().parents[1] / "config" / "calculator_constraints.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return tuple()
    out = []
    for item in raw.get("constraints") or []:
        try:
            out.append(CalculatorConstraint(
                bank_name=str(item.get("bank_name") or ""),
                family_key=str(item.get("family_key") or ""),
                calculator_product=str(item.get("calculator_product") or ""),
                variant=(str(item.get("variant")) if item.get("variant") is not None else None),
                query_markers=tuple(str(x) for x in (item.get("query_markers") or [])),
                max_financing_amount=(float(item["max_financing_amount"]) if item.get("max_financing_amount") is not None else None),
                min_maturity_months=(int(item["min_maturity_months"]) if item.get("min_maturity_months") is not None else None),
                max_maturity_months=(int(item["max_maturity_months"]) if item.get("max_maturity_months") is not None else None),
                max_vehicle_age=(int(item["max_vehicle_age"]) if item.get("max_vehicle_age") is not None else None),
                observed_maturity_months=(int(item["observed_maturity_months"]) if item.get("observed_maturity_months") is not None else None),
                amount_limit_mode=str(item.get("amount_limit_mode") or ""),
                source_url=str(item.get("source_url") or ""),
                evidence_note=str(item.get("evidence_note") or ""),
            ))
        except Exception:
            continue
    return tuple(out)


def matching_constraint(
    bank_name: str,
    family_key: str | None,
    query: str,
    *,
    require_variant_evidence: bool = True,
) -> CalculatorConstraint | None:
    q = normalize(query)
    bank_n = normalize(bank_name)
    fam_n = normalize(family_key or "")
    for c in _load():
        if normalize(c.bank_name) != bank_n or normalize(c.family_key) != fam_n:
            continue
        if require_variant_evidence and c.query_markers:
            if not any(normalize(marker) in q for marker in c.query_markers):
                continue
        return c
    return None


def all_constraints() -> tuple[CalculatorConstraint, ...]:
    return _load()
