# BANSA V20 Final UI

V20 keeps the V19 finance/campaign/chat core and replaces the jury-facing shell with a focused three-panel interface.

## Visible panels

1. BANSA Asistanı
2. Finansman Karşılaştırması
3. Kampanya Karşılaştırması

Legacy development/audit pages remain in the repository but are hidden from Streamlit's automatic sidebar navigation.

## UX changes

- New shared BANSA competition theme and branded sidebar.
- Fast home page: RAG/model prewarm is opt-in, not blocking by default.
- Finance comparison is scenario-first: requested financing amount, maturity, product family and optional banks.
- Finance panel delegates the calculation to the existing verified `ask_bansa` service, preserving calculator-first/freshness/verified-subset rules.
- Campaign comparison shows active campaigns only, with compact filtering, comparison table, source links and deterministic criterion highlights.
- Chatbot keeps persistent conversation history and V19 raw-user-turn context handling, but uses the same shared navigation and visual language.
- Automatic Streamlit pages navigation is hidden; only jury-facing panels are shown.

## Verification

- `compileall` passed for all new/modified UI entrypoints.
- Current conversation/finance/campaign critical regression set: 51 passed.
