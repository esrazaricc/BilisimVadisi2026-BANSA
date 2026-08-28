"""Deterministic scenario projection from verified BANSA finance evidence.

Purpose
-------
The strict verified resolver only returns a numeric result when the *exact*
amount/maturity was previously verified.  For jury-facing Q&A this can be too
rigid even when BANSA already owns trustworthy evidence for the same product:

* an official published pricing table for the requested maturity, or
* a verified official-calculator result for the same maturity at another
  principal amount.

This module provides a deliberately conservative second tier.  It never
changes the observed profit-share rate and never interpolates between
maturities.  It can only:

1. return an exact verified scenario;
2. reuse an official table rate for the exact requested maturity and calculate
   the standard annuity payment; or
3. scale a verified calculator payment from the *same maturity* to a different
   principal amount (payment is linear in principal when the rate/maturity are
   unchanged).

Projected results are explicitly labelled and are never represented as a live
bank quote.  Product fee rules remain authoritative; scenario-only fees are
not blindly scaled.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, getcontext
import json
from typing import Iterable

import pandas as pd

from src.finance_runtime_repository import get_verified_finance_scenarios

getcontext().prec = 34


@dataclass(frozen=True)
class ScenarioProjection:
    bank_name: str
    product_name: str
    variant: str
    amount: Decimal
    maturity_months: int
    profit_share_rate: Decimal
    monthly_installment: Decimal
    installment_total: Decimal
    mode: str
    source_kind: str
    source_url: str
    checked_at: str
    base_amount: Decimal | None = None
    base_monthly_installment: Decimal | None = None
    allocation_fee: Decimal | None = None
    allocation_fee_rate: Decimal | None = None
    appraisal_fee: Decimal | None = None
    mortgage_fee: Decimal | None = None
    fee_note: str = ""

    @property
    def exact(self) -> bool:
        return self.mode == "exact_verified"

    @property
    def projected(self) -> bool:
        return not self.exact


def _d(value) -> Decimal | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except Exception:
        pass
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none"}:
        return None
    try:
        return Decimal(text)
    except Exception:
        return None


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rules(row) -> dict:
    raw = row.get("finance_rules_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _fee_policy(row, amount: Decimal) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None, str]:
    """Return authoritative product fee information for this amount.

    The allocation fee is calculable when the official rule is percentage
    based.  Third-party appraisal/mortgage amounts are kept as published
    reference/minimum amounts, not scaled with the financing principal.
    """
    allocation = None
    allocation_rate = None
    appraisal = None
    mortgage = None
    notes: list[str] = []

    for fee in _rules(row).get("fee_rules", []) or []:
        if not isinstance(fee, dict):
            continue
        fee_type = str(fee.get("fee_type") or "").strip().casefold()
        waived = bool(fee.get("waived"))
        rate = _d(fee.get("rate"))
        fixed = _d(fee.get("amount"))
        note = str(fee.get("note") or "").strip()

        if fee_type == "allocation":
            if waived:
                allocation = Decimal("0.00")
            elif rate is not None:
                allocation_rate = rate
                allocation = _money(amount * rate / Decimal("100"))
            elif fixed is not None:
                allocation = _money(fixed)
            if note:
                notes.append("Tahsis: " + note)
        elif fee_type == "appraisal" and fixed is not None:
            appraisal = _money(fixed)
            if note:
                notes.append("Ekspertiz: " + note)
        elif fee_type in {"mortgage_establishment", "mortgage", "pledge"} and fixed is not None:
            mortgage = _money(fixed)
            if note:
                notes.append("İpotek: " + note)

    return allocation, allocation_rate, appraisal, mortgage, " | ".join(notes)


def _published_tiers(row, maturity: int) -> list[dict]:
    tiers = []
    for tier in _rules(row).get("pricing_tiers", []) or []:
        if not isinstance(tier, dict):
            continue
        try:
            tier_maturity = int(tier.get("maturity_months"))
        except Exception:
            continue
        if tier_maturity != int(maturity):
            continue
        rate = _d(tier.get("profit_share_rate"))
        if rate is None or rate <= 0:
            continue
        tiers.append(tier)
    return tiers


def _annuity(amount: Decimal, monthly_rate_percent: Decimal, maturity: int) -> Decimal:
    r = monthly_rate_percent / Decimal("100")
    n = int(maturity)
    if r == 0:
        return _money(amount / Decimal(n))
    factor = (Decimal("1") + r) ** n
    monthly = amount * (r * factor) / (factor - Decimal("1"))
    return _money(monthly)


def _safe_variant(value) -> str:
    text = str(value or "standard").strip()
    return text if text and text.casefold() not in {"nan", "none"} else "standard"


def _ts(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return pd.to_datetime(value, utc=True, errors="coerce")
    except Exception:
        return None


def _tiers_are_fresher_than_exact(tiers: list[dict], exact: pd.DataFrame) -> bool:
    """Prefer a newer official pricing table over an older calculator snapshot.

    Competition overlays carry verified_checked_at on every published pricing
    tier.  Historical exact scenarios stay useful, but must not silently
    override a newer official table after a bank changes its rates.
    """
    if not tiers or exact is None or exact.empty:
        return False
    tier_times = [_ts(t.get("verified_checked_at") or t.get("checked_at")) for t in tiers]
    tier_times = [t for t in tier_times if t is not None and not pd.isna(t)]
    exact_times = [_ts(v) for v in exact.get("checked_at", pd.Series(dtype=object)).tolist()]
    exact_times = [t for t in exact_times if t is not None and not pd.isna(t)]
    if not tier_times:
        return False
    if not exact_times:
        return True
    return max(tier_times) > max(exact_times)


def _tier_projections(row, amount_d: Decimal, maturity: int, tiers: list[dict],
                      allocation, allocation_rate, appraisal, mortgage, fee_note) -> tuple[ScenarioProjection, ...]:
    out = []
    for tier in tiers:
        rate = _d(tier.get("profit_share_rate"))
        if rate is None:
            continue
        monthly = _annuity(amount_d, rate, int(maturity))
        out.append(ScenarioProjection(
            bank_name=str(row.get("bank_name")),
            product_name=str(row.get("product_name")),
            variant=_safe_variant(tier.get("pricing_variant")),
            amount=amount_d,
            maturity_months=int(maturity),
            profit_share_rate=rate,
            monthly_installment=monthly,
            installment_total=_money(monthly * Decimal(int(maturity))),
            mode="official_pricing_table_model",
            source_kind=str(tier.get("source_type") or "official_pricing_table"),
            source_url=str(tier.get("source_url") or row.get("source_url") or row.get("url") or ""),
            checked_at=str(tier.get("verified_checked_at") or row.get("last_checked_at") or row.get("checked_at") or ""),
            allocation_fee=allocation,
            allocation_fee_rate=allocation_rate,
            appraisal_fee=appraisal,
            mortgage_fee=mortgage,
            fee_note=fee_note,
        ))
    return tuple(out)


def _managed_catalog_projections(row, amount_d: Decimal, maturity: int) -> tuple[ScenarioProjection, ...] | None:
    """V40 user-approved managed calculation layer.

    Returns None for non-target finance families.  Returns an empty tuple when
    the target row must stay outside numeric comparison (for example personal
    offer banks or invalid amount/vade).
    """
    try:
        from src.bansa_v40_finance_catalog import (
            TARGET_FAMILIES,
            managed_rate_options,
            is_personal_offer,
            is_calculated_bank,
        )
    except Exception:
        return None

    family_key = str(row.get("product_family_key") or "").strip().casefold()
    if family_key not in TARGET_FAMILIES:
        return None
    if is_personal_offer(row) or not is_calculated_bank(row):
        return tuple()

    options = managed_rate_options(row, amount_d, int(maturity))
    if not options:
        return tuple()

    allocation, allocation_rate, appraisal, mortgage, fee_note = _fee_policy(row, amount_d)
    out: list[ScenarioProjection] = []
    for opt in options:
        rate = _d(opt.get("rate"))
        if rate is None or rate <= 0:
            continue
        opt_allocation_rate = _d(opt.get("allocation_fee_rate"))
        use_allocation_rate = opt_allocation_rate if opt_allocation_rate is not None else allocation_rate
        use_allocation = allocation
        if use_allocation_rate is not None:
            use_allocation = _money(amount_d * use_allocation_rate / Decimal("100"))
        # V43: for an official calculator screenshot/snapshot, exact same-vade
        # scenarios are calibrated against the bank screen amount/taksit.  This
        # avoids treating a bank calculator result as a plain annuity when the
        # bank screen includes product-specific cost/tax/fee rounding.  For
        # other maturities BANSA still uses the declared kâr payı oranı and
        # labels the result as a snapshot-based projection, not a live offer.
        base_amount = _d(opt.get("base_amount"))
        base_maturity = opt.get("base_maturity")
        base_monthly = _d(opt.get("base_monthly_installment"))
        base_total = _d(opt.get("base_total_payment"))
        try:
            base_maturity_int = int(base_maturity) if base_maturity is not None else None
        except Exception:
            base_maturity_int = None

        monthly = _annuity(amount_d, rate, int(maturity))
        installment_total = _money(monthly * Decimal(int(maturity)))
        if (
            str(opt.get("source_kind") or "") == "official_calculator_snapshot"
            and base_amount is not None
            and base_amount > 0
            and base_maturity_int == int(maturity)
            and base_monthly is not None
        ):
            scale = amount_d / base_amount
            monthly = _money(base_monthly * scale)
            if base_total is not None:
                installment_total = _money(base_total * scale)
            else:
                installment_total = _money(monthly * Decimal(int(maturity)))

        opt_appraisal = _d(opt.get("appraisal_fee"))
        opt_mortgage = _d(opt.get("mortgage_fee"))
        opt_fees_total = _d(opt.get("fees_total"))
        use_appraisal = opt_appraisal if opt_appraisal is not None else appraisal
        use_mortgage = opt_mortgage if opt_mortgage is not None else mortgage
        note_parts = [part for part in [fee_note, str(opt.get("note") or "").strip()] if part]
        if opt_fees_total is not None:
            note_parts.append(f"Snapshot masraf toplamı: {opt_fees_total} TL")

        out.append(ScenarioProjection(
            bank_name=str(row.get("bank_name")),
            product_name=str(row.get("product_name")),
            variant=_safe_variant(opt.get("variant")),
            amount=amount_d,
            maturity_months=int(maturity),
            profit_share_rate=rate,
            monthly_installment=monthly,
            installment_total=installment_total,
            mode=str(opt.get("mode") or "bansa_managed_calculator_model"),
            source_kind=str(opt.get("source_kind") or "official_calculator_reference"),
            source_url=str(opt.get("source_url") or row.get("source_url") or row.get("url") or ""),
            checked_at=str(opt.get("checked_at") or row.get("last_checked_at") or row.get("checked_at") or ""),
            base_amount=base_amount,
            base_monthly_installment=base_monthly,
            allocation_fee=use_allocation,
            allocation_fee_rate=use_allocation_rate,
            appraisal_fee=use_appraisal,
            mortgage_fee=use_mortgage,
            fee_note=" | ".join(note_parts),
        ))
    return tuple(out)


def _row_allows_current_rate_claim(row) -> bool:
    """Bir ürünün ``current_rate_claim_allowed=False`` olarak işaretlenip
    işaretlenmediğini kontrol eder (örn. Vakıf Katılım taşıt/motosiklet
    finansmanı, hesaplama aracındaki oran alanı kullanıcı tarafından
    girildiği için). Bu bayrak varsa, bu ürün için doğrulanmış bir senaryo
    dahi olsa, o oranı bankanın güncel fiyatlaması gibi ölçekleyip taksit
    üretmek yasaktır.
    """
    raw = row.get("finance_rules_json")
    rules: dict = {}
    if isinstance(raw, dict):
        rules = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            import json
            rules = json.loads(raw)
        except Exception:
            rules = {}
    if not isinstance(rules, dict):
        return True
    metadata = rules.get("display_metadata")
    if not isinstance(metadata, dict):
        return True
    return metadata.get("current_rate_claim_allowed", True) is not False


def project_row(row, amount, maturity: int) -> tuple[ScenarioProjection, ...]:
    amount_d = _d(amount)
    if amount_d is None or amount_d <= 0 or int(maturity) <= 0:
        return tuple()

    family_key = str(row.get("product_family_key") or "").strip().casefold()

    managed = _managed_catalog_projections(row, amount_d, int(maturity))
    if managed is not None:
        return managed

    # Vehicle queries can safely use an *official published pricing table* for
    # the requested finance principal, but must never scale an old calculator
    # snapshot because a number in a vehicle conversation may instead be the
    # asset/kasko value.  Housing keeps the full exact/table/same-term cascade.
    if family_key not in {"konut_finansmani", "arac_finansmani"}:
        return tuple()

    if family_key == "arac_finansmani":
        # V15 (retained): a generic annuity projection from a *published
        # pricing tier* can disagree with the bank's official calculator, so
        # tiers alone are still not treated as proof of the exact payment
        # formula for a brand-new amount/maturity pair.
        #
        # V23: when BANSA already holds a bank's own verified calculator
        # result at the SAME maturity, scaling the payment linearly for a
        # different principal is safe arithmetic (rate and term are
        # unchanged). This is BLOCKED when the product is flagged
        # current_rate_claim_allowed=False (e.g. Vakıf Katılım vehicle
        # products, where the calculator's rate field is filled in by the
        # user, not published by the bank) — scaling a user-typed number is
        # exactly the "invented monthly payment" this flag exists to prevent.
        if not _row_allows_current_rate_claim(row):
            return tuple()
        product_id = int(row.get("id"))
        scenarios = get_verified_finance_scenarios()
        work = scenarios[scenarios["product_id"].eq(product_id)].copy()
        if work.empty:
            return tuple()
        status = work["scenario_status"].astype(str).str.casefold()
        work = work[status.str.contains("verified", na=False)].copy()
        same_maturity = work[
            pd.to_numeric(work["input_maturity_months"], errors="coerce").eq(int(maturity))
        ].copy()
        if same_maturity.empty:
            return tuple()
        allocation, allocation_rate, appraisal, mortgage, fee_note = _fee_policy(row, amount_d)
        out = []
        for _, s in same_maturity.iterrows():
            base_amount = _d(s.get("input_amount"))
            base_monthly = _d(s.get("monthly_installment"))
            rate = _d(s.get("profit_share_rate"))
            if base_amount is None or base_amount <= 0 or base_monthly is None or rate is None:
                continue
            ratio = amount_d / base_amount
            monthly = _money(base_monthly * ratio)
            total = _money(monthly * Decimal(int(maturity)))
            out.append(ScenarioProjection(
                bank_name=str(row.get("bank_name")),
                product_name=str(row.get("product_name")),
                variant=_safe_variant(s.get("input_variant")),
                amount=amount_d,
                maturity_months=int(maturity),
                profit_share_rate=rate,
                monthly_installment=monthly,
                installment_total=total,
                mode="verified_same_maturity_projection",
                source_kind=str(s.get("source_kind") or "verified_calculator_snapshot"),
                source_url=str(s.get("source_url") or row.get("source_url") or row.get("url") or ""),
                checked_at=str(s.get("checked_at") or ""),
                base_amount=base_amount,
                base_monthly_installment=base_monthly,
                allocation_fee=allocation,
                allocation_fee_rate=allocation_rate,
                appraisal_fee=appraisal,
                mortgage_fee=mortgage,
                fee_note=fee_note,
            ))
        return tuple(out)

    product_id = int(row.get("id"))
    scenarios = get_verified_finance_scenarios()
    work = scenarios[scenarios["product_id"].eq(product_id)].copy()
    if not work.empty:
        status = work["scenario_status"].astype(str).str.casefold()
        work = work[status.str.contains("verified", na=False)].copy()

        # V16 FRESH-DYNAMIC-SNAPSHOT GATE
        #
        # A calculator snapshot is not a published price list.  When a bank
        # exposes only a dynamic calculator (Albaraka housing is the important
        # case), old same-maturity rows must not be scaled indefinitely and
        # presented as current pricing.  Keep calculator snapshots for at most
        # 72 hours unless a current official pricing tier independently owns
        # the requested term later in this function.
        if not work.empty and "checked_at" in work.columns:
            source_kind = (
                work.get("source_kind", pd.Series("", index=work.index))
                .fillna("")
                .astype(str)
                .str.casefold()
            )
            scenario_status = (
                work.get("scenario_status", pd.Series("", index=work.index))
                .fillna("")
                .astype(str)
                .str.casefold()
            )
            dynamic = (
                source_kind.eq("official_live_calculator_endpoint")
                | scenario_status.str.contains("live_calculator", na=False)
            )
            checked = pd.to_datetime(work["checked_at"], utc=True, errors="coerce")
            now = pd.Timestamp.now(tz="UTC")
            fresh = checked.notna() & ((now - checked) <= pd.Timedelta(hours=72))
            work = work[(~dynamic) | fresh].copy()

    allocation, allocation_rate, appraisal, mortgage, fee_note = _fee_policy(row, amount_d)
    tiers = _published_tiers(row, int(maturity))

    # Exact snapshots remain strongest only while they are at least as fresh as
    # the currently published official pricing table.  If the bank has changed
    # its rate table since that snapshot, the newer official table owns the
    # scenario instead of serving stale numbers to the jury.
    exact = pd.DataFrame()
    if not work.empty:
        exact = work[
            pd.to_numeric(work["input_maturity_months"], errors="coerce").eq(int(maturity))
            & pd.to_numeric(work["input_amount"], errors="coerce").eq(float(amount_d))
        ].copy()

    if _tiers_are_fresher_than_exact(tiers, exact):
        fresh = _tier_projections(
            row, amount_d, int(maturity), tiers,
            allocation, allocation_rate, appraisal, mortgage, fee_note,
        )
        if fresh:
            return fresh

    # Tier 1: exact amount + maturity, preserving original verified numbers.
    if not exact.empty:
        out = []
        for _, s in exact.iterrows():
            rate = _d(s.get("profit_share_rate"))
            monthly = _d(s.get("monthly_installment"))
            total = _d(s.get("total_repayment"))
            if rate is None or monthly is None or total is None:
                continue
            out.append(ScenarioProjection(
                bank_name=str(row.get("bank_name")),
                product_name=str(row.get("product_name")),
                variant=_safe_variant(s.get("input_variant")),
                amount=amount_d,
                maturity_months=int(maturity),
                profit_share_rate=rate,
                monthly_installment=_money(monthly),
                installment_total=_money(total),
                mode="exact_verified",
                source_kind=str(s.get("source_kind") or "verified_calculator_snapshot"),
                source_url=str(s.get("source_url") or row.get("source_url") or row.get("url") or ""),
                checked_at=str(s.get("checked_at") or ""),
                allocation_fee=_d(s.get("allocation_fee")) or allocation,
                allocation_fee_rate=allocation_rate,
                appraisal_fee=_d(s.get("appraisal_fee")) or appraisal,
                mortgage_fee=_d(s.get("mortgage_fee")) or mortgage,
                fee_note=fee_note,
            ))
        if out:
            return tuple(out)

    # Tier 2: official pricing table for this exact maturity. No maturity/rate
    # interpolation is allowed. Each published variant remains separate.
    if tiers:
        published = _tier_projections(
            row, amount_d, int(maturity), tiers,
            allocation, allocation_rate, appraisal, mortgage, fee_note,
        )
        if published:
            return published

    # Tier 3: verified official-calculator result at the SAME maturity.
    # We do not reuse a rate across maturities.  Scaling principal/payment is
    # mathematically linear for an unchanged rate and term; the answer is
    # clearly labelled as a BANSA scenario projection, not a live quote.
    if not work.empty:
        same_maturity = work[
            pd.to_numeric(work["input_maturity_months"], errors="coerce").eq(int(maturity))
        ].copy()
        if not same_maturity.empty:
            out = []
            for _, s in same_maturity.iterrows():
                base_amount = _d(s.get("input_amount"))
                base_monthly = _d(s.get("monthly_installment"))
                rate = _d(s.get("profit_share_rate"))
                if base_amount is None or base_amount <= 0 or base_monthly is None or rate is None:
                    continue
                ratio = amount_d / base_amount
                monthly = _money(base_monthly * ratio)
                total = _money(monthly * Decimal(int(maturity)))
                out.append(ScenarioProjection(
                    bank_name=str(row.get("bank_name")),
                    product_name=str(row.get("product_name")),
                    variant=_safe_variant(s.get("input_variant")),
                    amount=amount_d,
                    maturity_months=int(maturity),
                    profit_share_rate=rate,
                    monthly_installment=monthly,
                    installment_total=total,
                    mode="verified_same_maturity_projection",
                    source_kind=str(s.get("source_kind") or "verified_calculator_snapshot"),
                    source_url=str(s.get("source_url") or row.get("source_url") or row.get("url") or ""),
                    checked_at=str(s.get("checked_at") or ""),
                    base_amount=base_amount,
                    base_monthly_installment=base_monthly,
                    allocation_fee=allocation,
                    allocation_fee_rate=allocation_rate,
                    appraisal_fee=appraisal,
                    mortgage_fee=mortgage,
                    fee_note=fee_note,
                ))
            if out:
                return tuple(out)

    return tuple()


def project_rows(rows: Iterable, amount, maturity: int) -> dict[str, tuple[ScenarioProjection, ...]]:
    out: dict[str, tuple[ScenarioProjection, ...]] = {}
    for row in rows:
        records = project_row(row, amount, maturity)
        if records:
            out[str(row.get("bank_name"))] = records
    return out
