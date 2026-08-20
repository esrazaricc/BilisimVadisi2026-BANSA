import json

from src.finance_data_quality import apply_finance_data_quality_overrides


def test_tom_mojibake_veresiye_uses_final_url_for_identity_and_minimum_pricing():
    out = apply_finance_data_quality_overrides({
        "bank_name": "T.O.M. Katılım",
        "product_name": "Veresiye AlÄ±Å\x9fveriÅ\x9f Kredisi | TOM Bank",
        "url": "https://tombank.com.tr/veresiye.html",
        "source_page": "https://tombank.com.tr/urunlerimiz.html",
        "profit_share_rate": 3.99,
        "finance_rules_json": json.dumps({"pricing_tiers": [{"profit_share_rate": 3.99}]}),
    })
    assert out["product_name"] == "Veresiye Alışveriş Kredisi"
    assert out["source_page"].endswith("/veresiye.html")
    assert out["profit_share_rate"] is None
    assert "başlayan" in out["profit_share_rate_text"].casefold()
    assert json.loads(out["finance_rules_json"])["pricing_tiers"] == []


def test_tom_mojibake_store_credit_uses_final_url_and_verified_product_limits():
    out = apply_finance_data_quality_overrides({
        "bank_name": "T.O.M. Katılım",
        "product_name": "MaÄ\x9fazadan AlÄ±Å\x9fveriÅ\x9f Kredisi | TOM Bank",
        "url": "https://www.tombank.com.tr/magazadan-alisveris-kredisi.html",
        "source_page": "https://tombank.com.tr/urunlerimiz.html",
        "minimum_financing_amount": None,
        "maximum_financing_amount": None,
        "maximum_maturity_months": None,
        "finance_rules_json": "{}",
    })
    assert out["product_name"] == "Mağazadan Alışveriş Kredisi"
    assert out["source_page"].endswith("/magazadan-alisveris-kredisi.html")
    assert out["minimum_financing_amount"] == 1000.0
    assert out["maximum_financing_amount"] == 200000.0
    assert out["maximum_maturity_months"] == 36


def test_tom_taksitli_title_is_canonicalized_from_final_url():
    out = apply_finance_data_quality_overrides({
        "bank_name": "T.O.M. Katılım",
        "product_name": "HADi Taksitli AlÄ±Å\x9fveriÅ\x9f Kredisi | TOM Bank",
        "url": "https://tombank.com.tr/taksitle.html",
        "source_page": "https://tombank.com.tr/urunlerimiz.html",
        "finance_rules_json": "{}",
    })
    assert out["product_name"] == "Taksitli Alışveriş Kredisi"
    assert out["source_page"].endswith("/taksitle.html")
