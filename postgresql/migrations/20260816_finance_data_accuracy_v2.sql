ALTER TABLE product_pricing_tiers ADD COLUMN IF NOT EXISTS financing_amount NUMERIC(18,2);
ALTER TABLE product_pricing_tiers ADD COLUMN IF NOT EXISTS value_type TEXT NOT NULL DEFAULT 'exact';
ALTER TABLE product_pricing_tiers ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'official_pricing_table';
ALTER TABLE product_pricing_tiers ADD COLUMN IF NOT EXISTS conditions TEXT;
ALTER TABLE product_pricing_tiers ADD COLUMN IF NOT EXISTS source_url TEXT;

CREATE TABLE IF NOT EXISTS finance_fact_evidence (
    id BIGSERIAL PRIMARY KEY,
    legacy_id BIGINT,
    product_id BIGINT NOT NULL REFERENCES standard_products(id) ON DELETE CASCADE,
    fact_key TEXT NOT NULL,
    value_text TEXT,
    value_numeric NUMERIC(18,6),
    value_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    conditions TEXT,
    source_url TEXT,
    source_text TEXT,
    verification_status TEXT NOT NULL DEFAULT 'verified',
    updated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_finance_evidence_product ON finance_fact_evidence(product_id);
CREATE INDEX IF NOT EXISTS idx_finance_evidence_key ON finance_fact_evidence(fact_key);
