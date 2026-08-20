-- BANSA finance scenario cache / live-calculator evidence
-- Added for reproducible clean-clone setup.
SET search_path TO bansa, public;

CREATE TABLE IF NOT EXISTS product_finance_scenarios (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES standard_products(id) ON DELETE CASCADE,
    scenario_key TEXT NOT NULL,
    scenario_type TEXT NOT NULL,
    input_amount NUMERIC(18,2),
    input_maturity_months INTEGER,
    input_variant TEXT,
    input_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    profit_share_rate NUMERIC(12,6),
    monthly_installment NUMERIC(18,2),
    total_repayment NUMERIC(18,2),
    monthly_cost_rate NUMERIC(12,6),
    annual_cost_rate NUMERIC(12,6),
    effective_annual_profit_rate NUMERIC(12,6),
    allocation_fee NUMERIC(18,2),
    mortgage_fee NUMERIC(18,2),
    appraisal_fee NUMERIC(18,2),
    total_fees NUMERIC(18,2),
    scenario_status TEXT NOT NULL,
    source_kind TEXT,
    source_url TEXT,
    source_note TEXT,
    raw_output JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finance_scenarios_product
    ON product_finance_scenarios(product_id);
CREATE INDEX IF NOT EXISTS idx_finance_scenarios_lookup
    ON product_finance_scenarios(product_id, scenario_key, input_variant, checked_at DESC);

CREATE OR REPLACE VIEW v_latest_finance_scenarios AS
SELECT
    id,
    product_id,
    scenario_key,
    scenario_type,
    input_amount,
    input_maturity_months,
    input_variant,
    input_metadata,
    profit_share_rate,
    monthly_installment,
    total_repayment,
    monthly_cost_rate,
    annual_cost_rate,
    effective_annual_profit_rate,
    allocation_fee,
    mortgage_fee,
    appraisal_fee,
    total_fees,
    scenario_status,
    source_kind,
    source_url,
    source_note,
    raw_output,
    checked_at,
    created_at
FROM (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY
                s.product_id,
                s.scenario_key,
                COALESCE(s.input_variant, '')
            ORDER BY
                s.checked_at DESC,
                s.id DESC
        ) AS _rn
    FROM product_finance_scenarios AS s
) ranked
WHERE _rn = 1;
