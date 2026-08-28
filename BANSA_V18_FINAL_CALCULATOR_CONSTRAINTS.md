# BANSA V18 — Final Finance Assistant Contract

V18 consolidates the final jury-facing behavior after the V17 review.

## 1. Amount semantics is explicit
BANSA keeps different amount meanings separate:
- `asset_value`: vehicle/motorcycle invoice or kasko value,
- `requested_financing_amount`: financing principal the user wants,
- ambiguous bare amounts trigger one short clarification.

A bare `600 bin için?` is never silently multiplied by an LTV ratio.

## 2. Raw conversation history recovery
The Streamlit UI stores raw user turns. V18 can recover the most recent bank/product through a bare numeric clarification sequence, so:

`Vakıf motosiklet -> 600 bin için? -> motosikletin değeri 600 bin TL`

keeps `Vakıf + Motosiklet Finansmanı + 600.000 TL` correctly.

If the user then says `Vakıf Katılım'da 600 bin TL finansman kullanmak istiyorum`, the same product can be inherited in that conversation. In a standalone query with no product, BANSA asks which financing product is meant instead of selecting an unrelated catalog row.

## 3. Eligibility rules and calculator constraints are separate
BANSA models two different kinds of limits:

1. **Product/eligibility rule** — asset value -> max financing ratio / max maturity.
2. **Official calculator constraint** — accepted requested financing amount / maturity for a specific calculator product/variant.

Effective financing can only be derived when both scopes are actually verified.

## 4. Verified calculator UI constraints included in V18
The new `config/calculator_constraints.json` stores narrow, evidence-scoped UI constraints.

### Dünya Katılım — Araç Binek 2.El
Official calculator UI observed:
- requested financing slider max: 400.000 TL,
- maturity: 12–48 months,
- second-hand vehicle age: up to 12 years.

This is separate from the vehicle-value LTV bands.

### Vakıf Katılım — Taşıt Finansmanı 2.El
Official calculator UI observed in the verified 18-month scenario:
- `Seçilen vade için 400.000 TL’ye kadar hesaplama yapılabilmektedir.`

Because the bank itself says **selected maturity**, V18 does not generalize the 400.000 TL ceiling to other maturities without live verification.

## 5. Calculator-first comparison
For `100 bin TL 36 ay araç finansmanlarını karşılaştır`:
- 100.000 TL means requested financing principal,
- official live calculator/exact current pricing is attempted first,
- asset-value LTV tables are not dumped as if they were installment results,
- stale snapshots do not fill missing rankings,
- missing banks are summarized briefly.

## 6. Intent-aware natural responses
Different questions use different response contracts:
- overview / `nasıl?`,
- product features,
- product benefits,
- fees,
- rate/pricing,
- maturity,
- financing limit,
- scenario calculation,
- comparison.

Albaraka Education Finance benefits therefore come from the official benefit section, not a generic product summary.

## 7. BANSA-derived examples are labeled
Deterministically derived examples are shown as:

`Örnek senaryo (BANSA hesaplaması)`

so a jury member can distinguish an official published rule from a BANSA calculation based on that rule.

## 8. Fast naturalizer safety
- local/on-prem Qwen only,
- default fast-naturalizer timeout: 0.8 seconds,
- no external LLM API,
- no request-time loading of the 0.6B fallback by default,
- generated answer cannot introduce financial numbers absent from deterministic facts; otherwise deterministic output is used.

## 9. Current V18 regression contract
The V17 + V18 current-contract tests cover:
- amount clarification,
- raw-history recovery,
- same-bank product continuation,
- no random SÖİK fallback,
- Dünya 2.El calculator max amount/maturity scope,
- Vakıf 2.El term-scoped 400k observation,
- product benefit intent,
- compact product overview,
- calculator-first vehicle comparison,
- motorcycle evidence guards,
- explicit product override after housing comparison.

Older tests that require superseded behavior (for example technical Vakıf rate caveats in every overview or long eligibility catalogs in comparison output) are historical contracts and are not part of V18.
