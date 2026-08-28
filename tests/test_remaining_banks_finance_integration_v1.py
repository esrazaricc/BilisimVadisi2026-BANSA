from __future__ import annotations

import json
from pathlib import Path

from src.finance_data_quality import apply_finance_data_quality_overrides
from src.finance_taxonomy import classify_finance_category
from scripts.scan_standard_products import embedded_section_html

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "standard_product_sources.json"


def banks():
    return json.loads(CONFIG.read_text(encoding="utf-8"))["banks"]


def bank(name: str):
    return next(row for row in banks() if row["name"] == name)


def test_standard_product_config_contains_all_10_bddk_participation_banks_in_scope_order():
    assert [row["name"] for row in banks()] == [
        "Adil Katılım", "Albaraka Türk", "Dünya Katılım", "Hayat Finans", "Kuveyt Türk",
        "T.O.M. Katılım", "Türkiye Emlak Katılım", "Türkiye Finans", "Vakıf Katılım", "Ziraat Katılım",
    ]


def test_tom_only_integrates_three_verified_public_shopping_credit_products():
    row = bank("T.O.M. Katılım")
    assert {r["family_key"] for r in row["family_rules"]} == {"alisveris_finansmani"}
    assert set(row["family_rules"][0]["exact_paths"]) == {
        "/veresiye.html", "/taksitle.html", "/magazadan-alisveris-kredisi.html"
    }


def test_adil_uses_only_two_public_generic_finance_sections_without_numeric_catalog_guessing():
    row = bank("Adil Katılım")
    assert row["family_rules"] == []
    page = row["embedded_product_pages"][0]
    assert set(page["stop_headings"]) >= {"Katılma Hesapları", "Kurumsal"}
    assert page["products"] == [
        {"product_name": "Bireysel Finansman"},
        {
            "product_name": "Ticari Finansman",
            "scope": "ticari",
            "product_family_key": "ticari_finansman",
            "product_family": "Ticari Finansman",
        },
    ]


def test_emlak_embedded_need_catalog_has_16_products_and_stops_before_example_table():
    row = bank("Türkiye Emlak Katılım")
    page = next(p for p in row["embedded_product_pages"] if p["product_family_key"] == "ihtiyac_finansmani")
    assert len(page["products"]) == 16
    assert "Örnek İhtiyaç Finansmanı Tablosu" in page["stop_headings"]
    devre = next(p for p in page["products"] if p["product_name"] == "Devre Mülk Finansmanı")
    assert devre["product_family_key"] == "gayrimenkul_finansmani"
    assert "/tr/bireysel/finansmanlar/toki-islemleri" in row["exclude_exact_paths"]


def test_emlak_housing_embedded_variants_stop_before_suspicious_detailed_table():
    row = bank("Türkiye Emlak Katılım")
    page = next(p for p in row["embedded_product_pages"] if p["product_family_key"] == "konut_finansmani")
    assert {p["product_name"] for p in page["products"]} == {
        "Birlikte Konut Finansmanı", "Çevreci Konut Finansmanı", "Memlekette Konut Finansmanı"
    }
    assert any("AZAMİ KREDİ TUTARI" in h for h in page["stop_headings"])


def test_vakif_has_eight_verified_retail_exact_products_and_four_business_families():
    row = bank("Vakıf Katılım")
    retail_keys = {"konut_finansmani", "arac_finansmani", "ihtiyac_finansmani", "arsa_finansmani", "isyeri_finansmani"}
    paths = {
        p
        for rule in row["family_rules"] if rule["family_key"] in retail_keys
        for p in rule.get("exact_paths", [])
    }
    assert len(paths) == 8
    assert {"ticari_finansman", "gayri_nakdi_finansman", "tarim_finansmani", "leasing"}.issubset(
        {rule["family_key"] for rule in row["family_rules"]}
    )


def test_ziraat_source_catalog_covers_retail_business_agriculture_and_leasing():
    row = bank("Ziraat Katılım")
    urls = [p["url"] for p in row["listing_pages"]]
    assert any("/bireysel/" in x for x in urls)
    assert any("/ticari/finansman-urunleri/" in x for x in urls)
    assert any("/tarim/" in x for x in urls)
    assert any("/ticari/finansal-kiralama-leasing" in x for x in urls)
    assert {"ticari_finansman", "gayri_nakdi_finansman", "tarim_finansmani", "leasing"}.issubset(
        {rule["family_key"] for rule in row["family_rules"]}
    )


def test_adil_guardrail_strips_all_synthetic_numeric_finance_metrics():
    out = apply_finance_data_quality_overrides({
        "bank_name": "Adil Katılım", "product_name": "Bireysel Finansman", "scope": "bireysel",
        "minimum_financing_amount": 1, "maximum_financing_amount": 999999,
        "minimum_maturity_months": 1, "maximum_maturity_months": 99,
        "profit_share_rate": 9.98, "maximum_financing_ratio": 99.8,
        "finance_rules_json": json.dumps({
            "amount_maturity_rules": [{"max_amount": 123, "max_maturity_months": 12}],
            "pricing_tiers": [{"profit_share_rate": 9.98}], "fee_rules": [{"amount": 100}],
        }),
    })
    for key in (
        "minimum_financing_amount", "maximum_financing_amount", "minimum_maturity_months",
        "maximum_maturity_months", "profit_share_rate", "maximum_financing_ratio",
    ):
        assert out[key] is None
    rules = json.loads(out["finance_rules_json"])
    assert rules["amount_maturity_rules"] == []
    assert rules["pricing_tiers"] == []
    assert rules["fee_rules"] == []


def test_tom_veresiye_399_is_minimum_starting_rate_not_fixed_headline():
    out = apply_finance_data_quality_overrides({
        "bank_name": "T.O.M. Katılım", "product_name": "Veresiye Alışveriş Kredisi",
        "url": "https://tombank.com.tr/veresiye.html", "profit_share_rate": 3.99,
        "finance_rules_json": json.dumps({"pricing_tiers": [{"profit_share_rate": 3.99}]}),
    })
    assert out["profit_share_rate"] is None
    assert "%3,99'dan başlayan" in out["profit_share_rate_text"]
    rules = json.loads(out["finance_rules_json"])
    assert rules["pricing_tiers"] == []
    assert rules["display_metadata"]["pricing_value_type"] == "minimum"


def test_tom_store_credit_has_verified_product_specific_limit_and_maturity():
    out = apply_finance_data_quality_overrides({
        "bank_name": "T.O.M. Katılım", "product_name": "Mağazadan Alışveriş Kredisi",
        "url": "https://tombank.com.tr/magazadan-alisveris-kredisi.html", "finance_rules_json": "{}",
    })
    assert out["minimum_financing_amount"] == 1000
    assert out["maximum_financing_amount"] == 200000
    assert out["maximum_maturity_months"] == 36


def test_ziraat_calculator_default_099_is_suppressed_from_product_pricing():
    out = apply_finance_data_quality_overrides({
        "bank_name": "Ziraat Katılım", "product_name": "Konut Finansmanı",
        "profit_share_rate": 0.99,
        "finance_rules_json": json.dumps({
            "pricing_tiers": [{"maturity_months": 12, "profit_share_rate": 0.99}]
        }),
    })
    assert out["profit_share_rate"] is None
    assert "bilgi amaçlı" in out["profit_share_rate_text"]
    assert json.loads(out["finance_rules_json"])["pricing_tiers"] == []


def test_vakif_housing_guardrail_never_uses_source_anomaly_150_as_financing_ratio():
    out = apply_finance_data_quality_overrides({
        "bank_name": "Vakıf Katılım", "product_name": "Konut Finansmanı",
        "maximum_financing_ratio": 150,
        "housing_finance_rules_json": json.dumps({"bad": 150}),
        "finance_rules_json": "{}",
    })
    assert out["maximum_financing_ratio"] == 90
    assert out["maximum_maturity_months"] == 120
    assert out["housing_finance_rules_json"] is None
    rules = json.loads(out["finance_rules_json"])
    assert "%150" in rules["display_metadata"]["source_anomaly_warning"]


def test_emlak_generic_housing_uses_only_verified_main_80pct_headline():
    out = apply_finance_data_quality_overrides({
        "bank_name": "Türkiye Emlak Katılım", "product_name": "Konut Finansmanı",
        "maximum_financing_ratio": 0, "housing_finance_rules_json": json.dumps({"broken": True}),
        "finance_rules_json": "{}",
    })
    assert out["maximum_financing_ratio"] == 80
    assert out["housing_finance_rules_json"] is None
    assert "%80" in out["financing_ratio_rules_text"]


def test_emlak_need_embedded_product_does_not_inherit_shared_169_example_rate():
    out = apply_finance_data_quality_overrides({
        "bank_name": "Türkiye Emlak Katılım", "product_name": "Eğitim Tüketici Finansmanı",
        "source_page": "https://www.emlakkatilim.com.tr/tr/bireysel/finansmanlar/ihtiyac-finansmani",
        "profit_share_rate": 1.69,
        "finance_rules_json": json.dumps({"pricing_tiers": [{"profit_share_rate": 1.69}]}),
    })
    assert out["profit_share_rate"] is None
    assert "sabit güncel oran yayımlanmamış" in out["profit_share_rate_text"]
    assert json.loads(out["finance_rules_json"])["pricing_tiers"] == []


def test_embedded_section_respects_non_product_stop_heading():
    html = """
    <html><body>
      <h3>Ürün A</h3><p>Ürüne özel gerçek açıklama.</p>
      <h3>Örnek İhtiyaç Finansmanı Tablosu</h3><p>30.000 TL 12 Ay %1,69</p>
    </body></html>
    """
    result = embedded_section_html(
        html,
        product_name="Ürün A",
        aliases=["Ürün A"],
        all_product_aliases=["Ürün A", "Örnek İhtiyaç Finansmanı Tablosu"],
    )
    assert result is not None
    section, _ = result
    assert "Ürüne özel gerçek açıklama" in section
    assert "30.000 TL" not in section
    assert "%1,69" not in section


def test_new_bank_products_map_to_correct_bansa_categories_without_name_hallucination():
    assert classify_finance_category("İhtiyaç Finansmanı", "Bireysel Finansman", "bireysel") == "ihtiyac_finansmani"
    assert classify_finance_category("Ticari Finansman", "Ticari Finansman", "ticari") == "ticari_finansman"
    assert classify_finance_category("Alışveriş Finansmanı", "Veresiye Alışveriş Kredisi", "bireysel") == "alisveris_finansmani"
    assert classify_finance_category("Gayrimenkul Finansmanı", "Devre Mülk Finansmanı", "bireysel") == "gayrimenkul_finansmani"
