# BANSA V16 — Mixed Housing Pricing Comparison Fix

## Problem fixed

A named housing comparison such as:

- `Albaraka Türk ve Türkiye Finans konut finansmanlarını karşılaştır`
- follow-up: `500.000 TL 36 ay`

could show Türkiye Finans numeric pricing while dropping Albaraka Türk with a
`numeric model unavailable` message, even though BANSA already has an explicit
Albaraka housing live-calculator adapter.

## Root causes

1. **Condition-specific Albaraka housing pricing**
   - `AlbarakaKonutLiveAdapter` intentionally refuses to collapse the generic
     housing request when `ilk_ev` and `mevcut_konut` return different values.
   - The natural comparison layer interpreted that safe `UNVERIFIED` generic
     result as if Albaraka had no calculator capability.

2. **Mixed evidence renderer dropped exact/live results**
   - Housing can legitimately combine a current official static pricing table
     for one bank with an exact live calculator for another bank.
   - When `projection_by_bank` was non-empty, the old projection renderer did
     not receive `exact_by_bank`, so an available live bank could disappear.

3. **Old dynamic housing snapshots could be scaled for too long**
   - A historical calculator result for the same maturity could be scaled to a
     new principal even when the snapshot was several days old.
   - This conflicts with V15's live-pricing-first policy.

## V16 behavior

### Albaraka housing live fallback

If generic Albaraka housing live calculation is condition-specific, BANSA now
queries these official calculator variants independently:

- `ilk_ev`
- `mevcut_konut`

Verified results are preserved as separate comparison rows.

The same condition-expansion mechanism is enabled for the existing Dünya
housing adapter (`yeni_konut`, `2el_konut`).

### Mixed live + current official table

The housing comparison renderer now accepts both:

- exact/live calculator records, and
- current official pricing-table projections.

Neither evidence mode can erase the other.

### Fresh dynamic snapshot gate

Dynamic official-calculator snapshots are usable for projection for at most
**72 hours**. Older rows remain in the audit store but cannot be scaled or used
to declare a current winner.

## Safety contract

- No old Albaraka snapshot is silently scaled when the live calculator fails.
- No bank is declared cheaper unless at least two current numeric candidates
  are available.
- First-home / existing-home and insurance variants stay visible when they
  materially change pricing.
- Current official pricing tables and live calculator results are labelled
  separately.

## Regression tests

`tests/test_competition_v16_housing_mixed_live_compare.py`

Covers:

1. condition-specific Albaraka live results + Türkiye Finans official table in
   the same answer;
2. stale Albaraka dynamic snapshots are not projected as current pricing.
