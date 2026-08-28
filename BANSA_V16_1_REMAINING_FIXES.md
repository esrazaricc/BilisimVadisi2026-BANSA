# BANSA V16.1 — Remaining Context & Routing Fixes

## Fixed after V16 verification

- Vakıf motorcycle follow-up keeps the previous asset value for `En fazla ne kadar finansman kullanabilirim?`.
  - 600,000 TL motorcycle value => max 50%, about 300,000 TL financing, max 36 months.
- Comparison follow-ups always rebase to the original comparison scenario.
  - `ikinci en düşük` no longer contaminates `ilk üçü sırala` or bank-to-bank difference questions.
- Top-3 follow-up reports only currently verified numeric banks and explicitly refuses to fill the list with stale snapshots.
- Pairwise difference follow-up returns a concise safe-abstention when one selected bank lacks a fresh numeric result instead of dumping the entire catalog.
- Explicit `... finansmanı` product questions no longer get hijacked by similarly named active campaigns.
  - `Albaraka Türk eğitim finansmanının avantajları?` routes to the Education Financing product, not the education installment campaign.

## Regression verification

39 targeted regression tests passed, covering:
- V15 live-pricing integrity
- V16 mixed housing live/static comparison
- campaign follow-up context
- campaign installment consistency
- housing live adapters
- V16.1 remaining context/routing regressions

`python -m compileall -q src` passes.
