BEGIN;

ALTER TABLE bansa.product_pricing_tiers
    ADD COLUMN IF NOT EXISTS financing_amount NUMERIC(18,2);

COMMIT;
