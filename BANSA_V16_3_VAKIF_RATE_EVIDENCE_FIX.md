# BANSA V16.3 — Vakıf Katılım Rate Evidence Guard

V16.3 adds a conservative evidence rule for Vakıf Katılım's public financing calculator.

The calculator UI contains a `Kâr Oranı Kendin Belirle` control. A profit-rate value used or returned by that calculator is therefore not, by itself, sufficient evidence that the bank publishes that value as its generally applicable current profit-share rate.

Changes:
- Vakıf Katılım vehicle and motorcycle eligibility rules remain available.
- Calculator-entered/returned profit rates are not promoted to a current bank rate.
- Historical Vakıf calculator snapshots are not used to answer current rate questions or rank current comparisons.
- Product answers no longer say that Vakıf's rate is automatically "determined by the scenario" merely because a calculator exists.
- If an exact current payment cannot be independently verified, BANSA does not derive or invent monthly installment / total repayment.

This is additive to the V16.2 context, campaign, eligibility, freshness and comparison fixes.
