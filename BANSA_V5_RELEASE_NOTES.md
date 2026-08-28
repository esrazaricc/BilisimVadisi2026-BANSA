# BANSA Competition Final V5

## V5 finance scenario engine

V5 keeps the strict verified finance engine as the highest-priority source, but
adds a conservative numeric second tier for jury-facing questions.

Priority:

1. Exact verified user scenario (same amount + same maturity)
2. Official published pricing table at the exact requested maturity
3. Verified official-calculator result at the same maturity, projected to the
   requested principal amount
4. Product/rule catalog and natural-language explanation
5. RAG / local Qwen / smart fallback

No maturity interpolation is used. Vehicle/motorcycle finance is excluded from
principal scaling because the numeric amount may represent vehicle value rather
than requested finance principal.

Projected answers are explicitly labelled as BANSA scenario calculations and
not as live bank offers. Fee rules from official product/fee sources take
precedence over fee amounts observed in calculator examples.

## Example

Question:

`Konut finansmanında Vakıf mı Türkiye Finans mı daha avantajlı?`

Follow-up:

`500.000 TL 36 ay`

BANSA now applies Türkiye Finans's official 36-month pricing table and Vakıf
Katılım's verified 36-month official calculator evidence to the requested
500,000 TL amount, instead of merely displaying unrelated 100,000 TL example
rows.

## Start

- Normal competition mode: `RUN_BANSA_COMPETITION.bat`
- Emergency offline mode: `RUN_BANSA_OFFLINE_DEMO.bat`
