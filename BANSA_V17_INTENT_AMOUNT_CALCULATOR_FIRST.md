# BANSA V17 — Intent-Aware Finance Assistant

V17 consolidates the final jury-facing behavior requested after V16.4.

## Core changes

- Intent-aware finance responses: overview, benefits, eligibility, fees, pricing, maturity, financing limit and comparison are rendered differently.
- Amount semantics: `asset_value` and `requested_financing_amount` are separate concepts. Bare numeric follow-ups are clarified rather than silently reinterpreted.
- Clarification replies preserve the previous numeric amount when the user answers e.g. `motosikletin değeri`.
- Vehicle-value eligibility bands are never used as payment pricing.
- Calculator-first scenario path: for exact amount + maturity, mapped official live calculators are attempted before snapshots/product rules.
- Historical calculator examples are removed from broad product overviews.
- Missing calculator results are summarized in one concise sentence; long `%70/%50/%30/%20` catalogs are not dumped into a payment comparison.
- Product benefits use the bank's own benefits section when available (e.g. Albaraka Education Finance).
- Generic vehicle rules are not transplanted to motorcycle products.
- Albaraka motorcycle scope preserves the official 125 cc split: 125 cc and above -> vehicle finance; below 125 cc -> need finance.
- Vakıf user-controlled calculator-rate evidence remains excluded from current-bank pricing claims.
- Fast naturalizer timeout defaults to 0.8s; transformer fallback is not synchronously loaded on the user request path unless explicitly enabled.
- Naturalizer output is still numerically grounded; source links remain deterministic.

## New regression contract

`tests/test_competition_v17_intent_amount_calculator_natural.py`

Covers:
- critical-facts-first product overview,
- amount ambiguity clarification,
- clarification-state preservation,
- requested-financing guard,
- education-benefits retrieval,
- compact housing overview,
- concise comparison output,
- comparison amount semantics,
- explicit asset-value rules,
- explicit new-product override,
- Dünya motorcycle scope guard,
- Albaraka 125 cc motorcycle rule.

## Compatibility note

Some older tests intentionally assert behavior superseded by V17 requirements (for example silently treating `600 bin için?` as an asset value, forcing technical Vakıf calculator-rate caveats into every overview, or requiring long eligibility catalogs in comparison output). Those assertions are not part of the V17 contract.
