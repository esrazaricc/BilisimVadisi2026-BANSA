CREATE SCHEMA IF NOT EXISTS bansa;
SET search_path TO bansa, public;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS banks (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    slug TEXT UNIQUE,
    legal_name TEXT,
    official_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS source_pages (
    id BIGSERIAL PRIMARY KEY,
    bank_id BIGINT NOT NULL REFERENCES banks(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    page_title TEXT,
    source_group TEXT,
    clean_text TEXT,
    content_hash TEXT,
    fetch_status TEXT,
    listing_status TEXT,
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(bank_id, url)
);

CREATE TABLE IF NOT EXISTS source_page_snapshots (
    id BIGSERIAL PRIMARY KEY,
    source_page_id BIGINT NOT NULL REFERENCES source_pages(id) ON DELETE CASCADE,
    content_hash TEXT,
    clean_text TEXT,
    fetch_status TEXT,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source_page_id, content_hash)
);

CREATE TABLE IF NOT EXISTS product_families (
    id BIGSERIAL PRIMARY KEY,
    family_key TEXT NOT NULL UNIQUE,
    family_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS campaigns (
    id BIGSERIAL PRIMARY KEY,
    legacy_live_id BIGINT UNIQUE,
    bank_id BIGINT NOT NULL REFERENCES banks(id) ON DELETE CASCADE,
    source_page_id BIGINT REFERENCES source_pages(id) ON DELETE SET NULL,
    campaign_name TEXT,
    source_group TEXT,
    campaign_category TEXT,
    start_date DATE,
    end_date DATE,
    current_status TEXT NOT NULL DEFAULT 'unknown',
    listing_status TEXT NOT NULL DEFAULT 'unknown',
    fetch_status TEXT NOT NULL DEFAULT 'unknown',
    comparison_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    classification_confidence NUMERIC(8,5),
    classification_reason TEXT,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    removed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS campaign_finance_details (
    campaign_id BIGINT PRIMARY KEY REFERENCES campaigns(id) ON DELETE CASCADE,
    finance_type TEXT NOT NULL,
    profit_share_rate_min NUMERIC(12,6),
    profit_share_rate_max NUMERIC(12,6),
    profit_share_rate_text TEXT,
    financing_amount_min NUMERIC(18,2),
    financing_amount_max NUMERIC(18,2),
    financing_amount_text TEXT,
    maturity_min_months INTEGER,
    maturity_max_months INTEGER,
    maturity_text TEXT,
    installment_count INTEGER,
    allocation_fee_amount NUMERIC(18,2),
    allocation_fee_rate NUMERIC(12,6),
    allocation_fee_status TEXT,
    expense_status TEXT,
    expense_details TEXT,
    campaign_advantage TEXT,
    evidence_text TEXT,
    extraction_confidence NUMERIC(8,5),
    grace_period_months INTEGER,
    extracted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS campaign_benefits (
    id BIGSERIAL PRIMARY KEY,
    legacy_id BIGINT,
    campaign_id BIGINT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    benefit_type TEXT NOT NULL,
    amount NUMERIC(18,2),
    rate NUMERIC(12,6),
    points NUMERIC(18,2),
    minimum_spending NUMERIC(18,2),
    maximum_benefit NUMERIC(18,2),
    description TEXT NOT NULL,
    evidence TEXT,
    extracted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS campaign_audiences (
    id BIGSERIAL PRIMARY KEY,
    legacy_id BIGINT,
    campaign_id BIGINT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    audience_type TEXT NOT NULL,
    audience_label TEXT NOT NULL,
    details TEXT,
    extracted_at TIMESTAMPTZ,
    UNIQUE(campaign_id, audience_type, audience_label)
);

CREATE TABLE IF NOT EXISTS campaign_installment_terms (
    id BIGSERIAL PRIMARY KEY,
    campaign_id BIGINT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    minimum_transaction_amount NUMERIC(18,2),
    maximum_transaction_amount NUMERIC(18,2),
    installment_count INTEGER,
    installment_cost_rate NUMERIC(12,6),
    installment_cost_text TEXT,
    evidence_text TEXT,
    extracted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS campaign_change_events (
    id BIGSERIAL PRIMARY KEY,
    legacy_id BIGINT,
    campaign_id BIGINT REFERENCES campaigns(id) ON DELETE SET NULL,
    bank_id BIGINT NOT NULL REFERENCES banks(id) ON DELETE CASCADE,
    source_url TEXT NOT NULL,
    change_type TEXT NOT NULL,
    old_content_hash TEXT,
    new_content_hash TEXT,
    old_status TEXT,
    new_status TEXT,
    details JSONB,
    changed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS standard_products (
    id BIGSERIAL PRIMARY KEY,
    legacy_live_id BIGINT UNIQUE,
    bank_id BIGINT NOT NULL REFERENCES banks(id) ON DELETE CASCADE,
    source_page_id BIGINT REFERENCES source_pages(id) ON DELETE SET NULL,
    family_id BIGINT NOT NULL REFERENCES product_families(id) ON DELETE RESTRICT,
    product_name TEXT NOT NULL,
    scope TEXT,
    minimum_financing_amount NUMERIC(18,2),
    maximum_financing_amount NUMERIC(18,2),
    minimum_maturity_months INTEGER,
    maximum_maturity_months INTEGER,
    profit_share_rate NUMERIC(12,6),
    profit_share_rate_text TEXT,
    interest_free BOOLEAN,
    interest_free_text TEXT,
    maturity_rules_text TEXT,
    maturity_reference_upper_amount NUMERIC(18,2),
    financing_ratio_rules_text TEXT,
    maximum_financing_ratio NUMERIC(12,6),
    housing_first_home_rules_text TEXT,
    housing_additional_home_rules_text TEXT,
    housing_finance_rules JSONB,
    vehicle_finance_rules_text TEXT,
    vehicle_age_rules_text TEXT,
    shopping_general_limit_amount NUMERIC(18,2),
    shopping_general_max_maturity_months INTEGER,
    shopping_finance_rules_text TEXT,
    fee_waiver_text TEXT,
    insurance_fee_waived BOOLEAN,
    allocation_fee_waived BOOLEAN,
    commission_fee_waived BOOLEAN,
    shopping_phone_rule_text TEXT,
    shopping_tablet_max_maturity_months INTEGER,
    shopping_computer_max_maturity_months INTEGER,
    finance_rules JSONB,
    current_status TEXT NOT NULL DEFAULT 'unknown',
    fetch_status TEXT NOT NULL DEFAULT 'unknown',
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    content_hash TEXT,
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ,
    checked_at TIMESTAMPTZ,
    extracted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    UNIQUE(bank_id, family_id, product_name, source_page_id)
);

CREATE TABLE IF NOT EXISTS product_amount_maturity_rules (
    id BIGSERIAL PRIMARY KEY,
    legacy_id BIGINT,
    product_id BIGINT NOT NULL REFERENCES standard_products(id) ON DELETE CASCADE,
    min_amount NUMERIC(18,2),
    max_amount NUMERIC(18,2),
    min_inclusive BOOLEAN NOT NULL DEFAULT FALSE,
    max_inclusive BOOLEAN NOT NULL DEFAULT TRUE,
    max_maturity_months INTEGER NOT NULL,
    source_text TEXT,
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS product_category_rules (
    id BIGSERIAL PRIMARY KEY,
    legacy_id BIGINT,
    product_id BIGINT NOT NULL REFERENCES standard_products(id) ON DELETE CASCADE,
    category_key TEXT NOT NULL,
    category_label TEXT NOT NULL,
    min_amount NUMERIC(18,2),
    max_amount NUMERIC(18,2),
    min_inclusive BOOLEAN NOT NULL DEFAULT FALSE,
    max_inclusive BOOLEAN NOT NULL DEFAULT TRUE,
    max_installments INTEGER,
    max_maturity_months INTEGER,
    condition_text TEXT,
    source_text TEXT,
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS product_pricing_tiers (
    id BIGSERIAL PRIMARY KEY,
    legacy_id BIGINT,
    product_id BIGINT NOT NULL REFERENCES standard_products(id) ON DELETE CASCADE,
    maturity_months INTEGER NOT NULL,
    profit_share_rate NUMERIC(12,6),
    allocation_fee_rate NUMERIC(12,6),
    monthly_total_cost_rate NUMERIC(12,6),
    annual_total_cost_rate NUMERIC(12,6),
    pricing_variant TEXT,
    financing_amount NUMERIC(18,2),
    value_type TEXT NOT NULL DEFAULT 'exact',
    source_type TEXT NOT NULL DEFAULT 'official_pricing_table',
    conditions TEXT,
    source_url TEXT,
    source_text TEXT,
    updated_at TIMESTAMPTZ
);

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

CREATE TABLE IF NOT EXISTS product_fee_rules (
    id BIGSERIAL PRIMARY KEY,
    legacy_id BIGINT,
    product_id BIGINT NOT NULL REFERENCES standard_products(id) ON DELETE CASCADE,
    fee_type TEXT NOT NULL,
    fee_label TEXT NOT NULL,
    waived BOOLEAN NOT NULL DEFAULT FALSE,
    amount NUMERIC(18,2),
    rate NUMERIC(12,6),
    note TEXT,
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS product_offer_rules (
    id BIGSERIAL PRIMARY KEY,
    legacy_id BIGINT,
    product_id BIGINT NOT NULL REFERENCES standard_products(id) ON DELETE CASCADE,
    rule_type TEXT NOT NULL,
    rule_label TEXT NOT NULL,
    min_amount NUMERIC(18,2),
    max_amount NUMERIC(18,2),
    min_inclusive BOOLEAN NOT NULL DEFAULT FALSE,
    max_inclusive BOOLEAN NOT NULL DEFAULT TRUE,
    max_installments INTEGER,
    max_maturity_months INTEGER,
    interest_free BOOLEAN NOT NULL DEFAULT FALSE,
    condition_text TEXT,
    source_text TEXT,
    updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS product_features (
    id BIGSERIAL PRIMARY KEY,
    legacy_id BIGINT,
    product_id BIGINT NOT NULL REFERENCES standard_products(id) ON DELETE CASCADE,
    feature_key TEXT NOT NULL,
    feature_label TEXT NOT NULL,
    feature_value TEXT NOT NULL,
    source_text TEXT,
    extraction_method TEXT NOT NULL,
    updated_at TIMESTAMPTZ,
    UNIQUE(product_id, feature_key)
);

CREATE TABLE IF NOT EXISTS product_change_events (
    id BIGSERIAL PRIMARY KEY,
    legacy_id BIGINT,
    product_id BIGINT REFERENCES standard_products(id) ON DELETE SET NULL,
    bank_id BIGINT NOT NULL REFERENCES banks(id) ON DELETE CASCADE,
    product_family TEXT,
    product_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    change_type TEXT NOT NULL,
    changed_fields JSONB,
    before_data JSONB,
    after_data JSONB,
    detected_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS product_scan_state (
    product_id BIGINT PRIMARY KEY REFERENCES standard_products(id) ON DELETE CASCADE,
    consecutive_missing_count INTEGER NOT NULL DEFAULT 0,
    last_seen_scan_at TIMESTAMPTZ,
    last_missing_scan_at TIMESTAMPTZ,
    possible_removed BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id BIGSERIAL PRIMARY KEY,
    legacy_id BIGINT,
    bank_id BIGINT NOT NULL REFERENCES banks(id) ON DELETE CASCADE,
    pipeline_kind TEXT NOT NULL DEFAULT 'campaign',
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    discovered_count INTEGER NOT NULL DEFAULT 0,
    processed_count INTEGER NOT NULL DEFAULT 0,
    created_count INTEGER NOT NULL DEFAULT 0,
    content_changed_count INTEGER NOT NULL DEFAULT 0,
    status_changed_count INTEGER NOT NULL DEFAULT 0,
    reactivated_count INTEGER NOT NULL DEFAULT 0,
    removed_count INTEGER NOT NULL DEFAULT 0,
    unchanged_count INTEGER NOT NULL DEFAULT 0,
    unavailable_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    removal_skipped BOOLEAN NOT NULL DEFAULT FALSE,
    details JSONB
);

CREATE TABLE IF NOT EXISTS classification_override_log (
    id BIGSERIAL PRIMARY KEY,
    legacy_id BIGINT,
    bank_id BIGINT NOT NULL REFERENCES banks(id) ON DELETE CASCADE,
    source_url TEXT NOT NULL,
    before_data JSONB NOT NULL,
    after_data JSONB NOT NULL,
    reason TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS migration_runs (
    id BIGSERIAL PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_path TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running',
    details JSONB
);

CREATE INDEX IF NOT EXISTS idx_source_pages_bank ON source_pages(bank_id);
CREATE INDEX IF NOT EXISTS idx_source_pages_url ON source_pages(url);
CREATE INDEX IF NOT EXISTS idx_campaigns_bank ON campaigns(bank_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(current_status, is_current);
CREATE INDEX IF NOT EXISTS idx_campaigns_category ON campaigns(campaign_category);
CREATE INDEX IF NOT EXISTS idx_campaign_benefits_campaign ON campaign_benefits(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_audiences_campaign ON campaign_audiences(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_changes_campaign ON campaign_change_events(campaign_id);
CREATE INDEX IF NOT EXISTS idx_products_bank ON standard_products(bank_id);
CREATE INDEX IF NOT EXISTS idx_products_family ON standard_products(family_id);
CREATE INDEX IF NOT EXISTS idx_products_current ON standard_products(is_current);
CREATE INDEX IF NOT EXISTS idx_amount_maturity_product ON product_amount_maturity_rules(product_id);
CREATE INDEX IF NOT EXISTS idx_category_rules_product ON product_category_rules(product_id);
CREATE INDEX IF NOT EXISTS idx_pricing_product ON product_pricing_tiers(product_id);
CREATE INDEX IF NOT EXISTS idx_finance_evidence_product ON finance_fact_evidence(product_id);
CREATE INDEX IF NOT EXISTS idx_finance_evidence_key ON finance_fact_evidence(fact_key);
CREATE INDEX IF NOT EXISTS idx_features_product ON product_features(product_id);
CREATE INDEX IF NOT EXISTS idx_product_changes_product ON product_change_events(product_id);

CREATE OR REPLACE VIEW v_current_campaigns AS
SELECT
    c.id,
    b.name AS bank_name,
    c.campaign_name,
    c.campaign_category,
    c.start_date,
    c.end_date,
    c.current_status,
    c.comparison_eligible,
    sp.url AS source_url
FROM campaigns c
JOIN banks b ON b.id = c.bank_id
LEFT JOIN source_pages sp ON sp.id = c.source_page_id
WHERE c.is_current = TRUE;

CREATE OR REPLACE VIEW v_current_standard_products AS
SELECT
    p.id,
    b.name AS bank_name,
    f.family_name AS product_family,
    p.product_name,
    p.scope,
    p.minimum_financing_amount,
    p.maximum_financing_amount,
    p.minimum_maturity_months,
    p.maximum_maturity_months,
    p.profit_share_rate,
    p.profit_share_rate_text,
    p.interest_free,
    sp.url AS source_url
FROM standard_products p
JOIN banks b ON b.id = p.bank_id
JOIN product_families f ON f.id = p.family_id
LEFT JOIN source_pages sp ON sp.id = p.source_page_id
WHERE p.is_current = TRUE;

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


INSERT INTO schema_meta(key, value)
VALUES ('schema_version', '2')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
