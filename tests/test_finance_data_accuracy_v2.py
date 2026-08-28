from __future__ import annotations

import json

import pandas as pd

from src.finance_data_quality import apply_finance_data_quality_overrides
from src.finance_evidence import annotate_pricing_rows
from src.finance_rule_engine import extract_amount_maturity_rules
from src.pricing_guardrails import filter_authoritative_pricing_frame


def test_amount_parser_keeps_250k_not_zero_and_three_canonical_bands():
    text = (
        "125.000 TL’ye kadar olması durumunda maksimum vade 36 ay. "
        "125.000 - 250.000 TL’ ye kadar olması durumunda maksimum vade 24 ay. "
        "250.000 TL’den fazla olması durumunda maksimum vade 12 ay."
    )
    rules = extract_amount_maturity_rules(text)
    assert len(rules) == 3
    assert rules[0]["max_amount"] == 125000
    assert rules[1]["min_amount"] == 125000
    assert rules[1]["max_amount"] == 250000
    assert rules[2]["min_amount"] == 250000
    assert rules[2]["max_amount"] is None
    assert all(row.get("min_amount") != 0 for row in rules)


def test_kuveyt_example_pricing_is_retained_but_not_headline():
    rows = annotate_pricing_rows(
        [{"pricing_variant": "Standart", "maturity_months": 12, "profit_share_rate": 4.82,
          "source_text": "10.000 TL | 12 Ay | 4,82 %"}],
        bank_name="Kuveyt Türk", product_name="Eğitim Finansmanı",
        source_url="https://example.test",
    )
    assert rows[0]["value_type"] == "example"
    frame = pd.DataFrame(rows)
    assert filter_authoritative_pricing_frame(frame).empty


def test_kuveyt_hac_umre_and_tekne_aliases_are_example():
    for product in ("Hac-Umre Finansmanı", "Tekne Tüketici Finansmanı"):
        row = annotate_pricing_rows(
            [{"maturity_months": 12, "profit_share_rate": 4.82, "source_text": "10.000 TL"}],
            bank_name="Kuveyt Türk", product_name=product,
        )[0]
        assert row["value_type"] == "example"


def test_tf_digital_need_override_has_exact_three_bands_and_conditional_pricing():
    source = {
        "bank_name": "Türkiye Finans",
        "product_name": "Dijital İhtiyaç Finansmanı (Dijital İhtiyaç Kredisi)*",
        "scope": "bireysel",
        "url": "https://example.test",
        "finance_rules_json": json.dumps({
            "amount_maturity_rules": [{"min_amount": 0, "max_amount": None, "max_maturity_months": 12}],
            "pricing_tiers": [{"pricing_variant": "Sigortalı", "maturity_months": 36, "profit_share_rate": 3.8}],
        }),
    }
    out = apply_finance_data_quality_overrides(source)
    rules = json.loads(out["finance_rules_json"])
    assert [(r["min_amount"], r["max_amount"], r["max_maturity_months"]) for r in rules["amount_maturity_rules"]] == [
        (None, 125000.0, 36), (125000.0, 250000.0, 24), (250000.0, None, 12)
    ]
    assert rules["pricing_tiers"][0]["value_type"] == "conditional_pricing"


def test_hayat_bana_bunu_al_product_limits_override_generic_legal_bands():
    source = {
        "bank_name": "Hayat Finans", "product_name": "Bana Bunu Al", "scope": "bireysel",
        "url": "https://example.test", "finance_rules_json": json.dumps({
            "amount_maturity_rules": [{"max_amount": 125000, "max_maturity_months": 36}],
            "pricing_tiers": [{"pricing_variant": "Maliyet Tablosu", "maturity_months": 18, "profit_share_rate": 4.25}],
        })
    }
    out = apply_finance_data_quality_overrides(source)
    assert out["minimum_financing_amount"] == 500
    assert out["maximum_financing_amount"] == 50000
    assert out["maximum_maturity_months"] == 18
    rules = json.loads(out["finance_rules_json"])
    assert rules["amount_maturity_rules"] == []
    assert rules["pricing_tiers"][0]["value_type"] == "conditional_pricing"


def test_dunya_vehicle_override_repairs_all_four_bands_and_age():
    source = {
        "bank_name": "Dünya Katılım", "product_name": "Araç Finansmanı", "scope": "bireysel",
        "url": "https://example.test", "finance_rules_json": "{}"
    }
    out = apply_finance_data_quality_overrides(source)
    rules = json.loads(out["finance_rules_json"])
    assert len(rules["amount_maturity_rules"]) == 4
    assert [r["max_maturity_months"] for r in rules["amount_maturity_rules"]] == [48, 36, 24, 12]
    assert "12 yaşa kadar" in out["vehicle_age_rules_text"]
    assert len(rules["display_metadata"]["vehicle_value_rules"]) == 4


def test_albaraka_togg_rows_keep_model_amount_maturity_conditions():
    source = {
        "bank_name": "Albaraka Türk", "product_name": "Togg Finansmanı", "scope": "bireysel",
        "url": "https://example.test", "finance_rules_json": json.dumps({
            "pricing_tiers": [
                {"pricing_variant": "T10X V2", "financing_amount": 800000, "maturity_months": 12, "profit_share_rate": 0},
                {"pricing_variant": "T10X V2", "financing_amount": 1700000, "maturity_months": 48, "profit_share_rate": 2.99},
            ]
        })
    }
    out = apply_finance_data_quality_overrides(source)
    pricing = json.loads(out["finance_rules_json"])["pricing_tiers"]
    assert len(pricing) == 2
    assert all(row["value_type"] == "conditional_pricing" for row in pricing)
    assert all("Model:" in row["conditions"] and "Finansman tutarı:" in row["conditions"] for row in pricing)


def test_albaraka_2b_text_is_not_a_numeric_rate():
    out = apply_finance_data_quality_overrides({
        "bank_name": "Albaraka Türk", "product_name": "2B Arazi Finansmanı", "scope": "bireysel",
        "profit_share_rate": 2.95, "profit_share_rate_text": "x", "finance_rules_json": "{}"
    })
    assert out["profit_share_rate"] is None
    assert out["profit_share_rate_text"] == "Resmî fiyatlama sayfasından güncel olarak belirlenir"


def test_individual_rooftop_ges_has_sustainable_energy_subtype_metadata():
    out = apply_finance_data_quality_overrides({
        "bank_name": "Kuveyt Türk", "product_name": "Çatı GES Finansmanı", "scope": "bireysel",
        "finance_rules_json": "{}"
    })
    rules = json.loads(out["finance_rules_json"])
    assert rules["display_metadata"]["comparison_subtype"] == "Sürdürülebilir / Enerji"


def test_albaraka_hac_umre_uses_maturity_bands_not_fake_product_limit():
    source = {
        "bank_name": "Albaraka Türk", "product_name": "Hac ve Umre Finansmanı", "scope": "bireysel",
        "minimum_financing_amount": 125001, "maximum_financing_amount": 250000,
        "finance_rules_json": "{}",
    }
    out = apply_finance_data_quality_overrides(source)
    assert out["minimum_financing_amount"] is None
    assert out["maximum_financing_amount"] is None
    assert out["maximum_maturity_months"] == 36
    rules = json.loads(out["finance_rules_json"])["amount_maturity_rules"]
    assert [(r["min_amount"], r["max_amount"], r["max_maturity_months"]) for r in rules] == [
        (None, 125000.0, 36), (125000.0, 250000.0, 24), (250000.0, None, 12)
    ]


def test_albaraka_jet_intersects_general_bands_with_60k_product_limit():
    source = {
        "bank_name": "Albaraka Türk", "product_name": "Jet Finansman", "scope": "bireysel",
        "finance_rules_json": "{}",
    }
    out = apply_finance_data_quality_overrides(source)
    assert out["minimum_financing_amount"] == 1000
    assert out["maximum_financing_amount"] == 60000
    rules = json.loads(out["finance_rules_json"])["amount_maturity_rules"]
    assert [(r["min_amount"], r["max_amount"], r["max_maturity_months"]) for r in rules] == [
        (1000.0, 50000.0, 36), (50000.0, 60000.0, 24)
    ]


def test_tf_normal_need_has_exact_three_nonduplicated_maturity_bands():
    source = {
        "bank_name": "Türkiye Finans", "product_name": "İhtiyaç Finansmanı", "scope": "bireysel",
        "finance_rules_json": json.dumps({"amount_maturity_rules": [
            {"min_amount": 125000, "max_amount": 250000, "max_maturity_months": 24},
            {"min_amount": 125001, "max_amount": 250000, "max_maturity_months": 24},
        ]}),
    }
    out = apply_finance_data_quality_overrides(source)
    rules = json.loads(out["finance_rules_json"])["amount_maturity_rules"]
    assert len(rules) == 3
    assert [(r["min_amount"], r["max_amount"], r["max_maturity_months"]) for r in rules] == [
        (None, 125000.0, 36), (125000.0, 250000.0, 24), (250000.0, None, 12)
    ]


def test_tf_trendyol_uses_product_specific_1k_70k_and_36_months():
    source = {
        "bank_name": "Türkiye Finans", "product_name": "Trendyol Alışveriş Finansmanı", "scope": "bireysel",
        "finance_rules_json": json.dumps({"amount_maturity_rules": [
            {"max_amount": 125000, "max_maturity_months": 36}
        ]}),
    }
    out = apply_finance_data_quality_overrides(source)
    assert out["minimum_financing_amount"] == 1000
    assert out["maximum_financing_amount"] == 70000
    assert out["maximum_maturity_months"] == 36
    assert json.loads(out["finance_rules_json"])["amount_maturity_rules"] == []


def test_lc_waikiki_moves_verified_conditions_into_core_decision_fields():
    source = {
        "bank_name": "Kuveyt Türk", "product_name": "LC Waikiki Alışveriş Finansmanı", "scope": "bireysel",
        "profit_share_rate": 4.52, "profit_share_rate_text": "%4,52", "finance_rules_json": "{}",
    }
    out = apply_finance_data_quality_overrides(source)
    assert out["maximum_financing_amount"] == 5000
    assert out["maximum_maturity_months"] == 3
    assert out["interest_free"] is True
    assert out["interest_free_text"] == "Vade farksız"
    assert out["profit_share_rate"] is None
    rules = json.loads(out["finance_rules_json"])
    assert rules["display_metadata"]["verified_channel"] == "LC Waikiki uygulaması / web sitesi"


def test_standard_vehicle_products_use_full_1_2m_2m_bands_and_70pct_headline_max():
    samples = [
        ("Albaraka Türk", "Taşıt Finansmanı"),
        ("Kuveyt Türk", "Araç Finansmanı"),
        ("Türkiye Finans", "Dijital Taşıt Finansmanı"),
    ]
    for bank, product in samples:
        out = apply_finance_data_quality_overrides({
            "bank_name": bank, "product_name": product, "scope": "bireysel", "finance_rules_json": "{}"
        })
        rules = json.loads(out["finance_rules_json"])["amount_maturity_rules"]
        assert out["maximum_financing_ratio"] == 70
        assert [r["max_amount"] for r in rules] == [400000.0, 800000.0, 1200000.0, 2000000.0]
        assert [r["max_maturity_months"] for r in rules] == [48, 36, 24, 12]
