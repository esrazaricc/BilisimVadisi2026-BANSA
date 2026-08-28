# BANSA V48 — Recommendation Follow-up Fix

## Problem fixed
A two-turn flow such as:

1. `100 bin TL, 36 ay vadeyle bir finansman istiyorum ama aylık ödemem mümkün olduğunca düşük olsun. Bana en mantıklı seçeneği öner.`
2. `konut finansmanı`

correctly preserved amount and maturity, but lost the user's recommendation goal. The second turn therefore listed banks without producing a BANSA recommendation.

## V48 change
The structured conversation state now also carries:

- `recommendation`: whether the user explicitly asked BANSA to recommend/choose.
- `prefer_low_monthly`: whether the user's decision priority is the lowest monthly payment.

These decision goals survive short finance clarification/follow-up turns and are serialized into the resolved question passed to the deterministic answer engine.

The resulting answer now starts with `BANSA önerisi` and separately surfaces:

- En düşük kâr payı
- En düşük aylık taksit
- En düşük toplam geri ödeme
- BANSA'nın first-choice explanation based only on comparable verified results

The underlying V45/V47 live-calculator, verified-pricing, grounding and fail-closed rules are unchanged.

## Presentation cleanup
Nested bold markup in the recommendation sentence was removed so the user-facing Markdown renders cleanly.

## Regression check
Relevant regression bundle: `11 passed`.
Python compile check is included in packaging validation.
