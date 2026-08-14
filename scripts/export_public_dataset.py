from __future__ import annotations
import csv, json, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "campaigns.db"
OUT = ROOT / "dataset"
OUT.mkdir(exist_ok=True)

QUERIES = {
    "campaigns.csv": """
        SELECT c.id AS campaign_id, c.bank_name, c.title AS campaign_name,
               c.campaign_category, c.source_group, c.source_url,
               c.start_date, c.end_date, c.current_status, c.listing_status,
               c.fetch_status, c.comparison_eligible, c.classification_confidence,
               c.classification_reason, c.first_seen_at, c.last_seen_at, c.last_checked_at,
               f.finance_type, f.profit_share_rate_min, f.profit_share_rate_max,
               f.financing_amount_min, f.financing_amount_max,
               f.maturity_min_months, f.maturity_max_months, f.installment_count,
               f.allocation_fee_amount, f.allocation_fee_rate, f.allocation_fee_status,
               f.expense_status, f.expense_details, f.campaign_advantage,
               f.grace_period_months
        FROM live_campaigns c
        LEFT JOIN live_campaign_finance_details f ON f.campaign_id=c.id
        WHERE c.record_kind='campaign' AND c.is_current=1
        ORDER BY c.bank_name, c.title
    """,
    "campaign_texts.csv": """
        SELECT id AS record_id, bank_name, record_kind, title, source_url,
               clean_text, content_hash, last_checked_at
        FROM live_campaigns
        WHERE is_current=1
        ORDER BY bank_name, record_kind, title
    """,
    "campaign_benefits.csv": "SELECT * FROM live_campaign_benefits ORDER BY campaign_id,id",
    "campaign_audiences.csv": "SELECT * FROM live_campaign_audiences ORDER BY campaign_id,id",
    "campaign_installment_terms.csv": "SELECT * FROM live_campaign_installment_terms ORDER BY campaign_id",
    "standard_products.csv": """
        SELECT p.*, c.source_url
        FROM live_standard_product_details p
        LEFT JOIN live_campaigns c ON c.id=p.product_id
        ORDER BY p.bank_name,p.product_family,p.product_name
    """,
    "product_amount_maturity_rules.csv": "SELECT * FROM live_product_amount_maturity_rules ORDER BY product_id,id",
    "product_category_rules.csv": "SELECT * FROM live_product_category_rules ORDER BY product_id,id",
    "product_pricing_tiers.csv": "SELECT * FROM live_product_pricing_tiers ORDER BY product_id,id",
    "product_fee_rules.csv": "SELECT * FROM live_product_fee_rules ORDER BY product_id,id",
    "product_offer_rules.csv": "SELECT * FROM live_product_offer_rules ORDER BY product_id,id",
    "product_features.csv": "SELECT * FROM live_product_features ORDER BY product_id,id",
}

con=sqlite3.connect(DB)
con.row_factory=sqlite3.Row
manifest={}
for filename, query in QUERIES.items():
    rows=con.execute(query).fetchall()
    path=OUT/filename
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        if rows:
            w=csv.DictWriter(f,fieldnames=rows[0].keys())
            w.writeheader(); w.writerows(dict(r) for r in rows)
        else:
            f.write('')
    manifest[filename]={"rows":len(rows)}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
