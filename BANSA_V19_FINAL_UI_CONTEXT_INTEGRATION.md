# BANSA V19 — Final UI Context Integration

V19 is the final consolidation layer on top of V18.

## Final fix
The Streamlit chatbot now passes **raw user turns** into `resolve_followup_question()` instead of preferring previously resolved/canonical turns. This aligns the real UI with the V18 resolver contract and fixes clarification chains in production UI, especially:

- `Vakıf Katılım motosiklet finansmanı nasıl?`
- `600 bin için?`
- `Motosikletin değeri 600 bin TL`

The resolver can now recover bank + product + amount semantics from the raw conversation exactly as regression tests do.

## Preserved V18 architecture
- asset value vs requested financing amount semantics
- calculator constraints separate from product/LTV rules
- Dünya Katılım Araç Binek 2.El: verified calculator UI max financing amount 400,000 TL, 12–48 months, vehicle age <=12
- Vakıf Katılım Taşıt Finansmanı 2.El: observed 400,000 TL calculator ceiling is term-scoped to the verified 18-month observation and is not generalized
- calculator-first comparison where a trustworthy adapter exists
- no old snapshot ranking when current calculator pricing is unavailable
- intent-aware product benefits/overview/fees/rate responses
- fast local naturalizer with numeric grounding verification and deterministic fallback
