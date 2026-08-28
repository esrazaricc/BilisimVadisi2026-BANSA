from __future__ import annotations

import json

from src.extraction.standard_product_extractor import extract_standard_product
from src.finance_rule_engine import build_finance_rules
from src.housing_verified_source_overrides import apply_verified_housing_product_overrides
from src.qualitative_feature_extractor import extract_qualitative_features


STANDARD_ROWS = """
<tr><td>5 milyona kadar konutlar</td><td>%90</td><td>%80</td><td>%70</td></tr>
<tr><td>5-7 milyon arasındaki konutlar</td><td>%80</td><td>%70</td><td>%60</td></tr>
<tr><td>7-10 milyon arasındaki konutlar</td><td>%70</td><td>%60</td><td>%50</td></tr>
<tr><td>10-20 milyon arasındaki konutlar</td><td>%50</td><td>%40</td><td>%30</td></tr>
<tr><td>20 milyon üzeri konutlar</td><td>%40</td><td>%30</td><td>%20</td></tr>
"""
ADDITIONAL_ROWS = """
<tr><td>5 milyona kadar konutlar</td><td>%22,5</td><td>%20</td><td>%17,5</td></tr>
<tr><td>5-7 milyon arasındaki konutlar</td><td>%20</td><td>%17,5</td><td>%15</td></tr>
<tr><td>7-10 milyon arasındaki konutlar</td><td>%17,5</td><td>%15</td><td>%12,5</td></tr>
<tr><td>10-20 milyon arasındaki konutlar</td><td>%12,5</td><td>%10</td><td>%7,5</td></tr>
<tr><td>20 milyon üzeri konutlar</td><td>%10</td><td>%7,5</td><td>%5</td></tr>
"""


def table(header: str, rows: str) -> str:
    return f"""<table><tr><th>{header}</th><th>A-B Sınıfı</th><th>C Sınıfı</th><th>Diğer</th></tr>{rows}</table>"""


def test_dunya_two_housing_tables_are_canonical_dict():
    html = f"""
    <html><h1>Konut Finansmanı</h1>
    <h2>İlk Ev / İlk Konut</h2>{table('Konut Değeri', STANDARD_ROWS)}
    <h2>İkinci ve Sonraki Konut</h2>{table('Konut Değeri', ADDITIONAL_ROWS)}
    </html>
    """
    result = extract_standard_product(html)
    rules = json.loads(result.housing_finance_rules_json)
    assert len(rules["standard_home"]) == 5
    assert len(rules["additional_home"]) == 5
    assert rules["standard_home"][0]["ab"] == 90.0
    assert rules["additional_home"][0]["ab"] == 22.5


def test_turkiye_finans_konut_ekspertiz_header_and_ilk_konut_heading():
    html = f"""
    <html><h1>Konut Finansmanı (Konut Kredisi)*</h1>
    <h2>İlk Konutunu Alan</h2>{table('Konut Ekspertiz Değeri', STANDARD_ROWS)}
    </html>
    """
    result = extract_standard_product(html)
    rules = json.loads(result.housing_finance_rules_json)
    assert len(rules["standard_home"]) == 5
    assert not rules["additional_home"]


def test_kuveyt_ilk_evim_unheaded_table_is_standard_by_product_identity():
    html = f"""
    <html><h1>İlk Evim Konut Finansmanı</h1>
    {table('Ekspertiz Değeri/Enerji Sınıfı', STANDARD_ROWS)}
    </html>
    """
    result = extract_standard_product(html)
    rules = json.loads(result.housing_finance_rules_json)
    assert len(rules["standard_home"]) == 5
    assert not rules["additional_home"]


def test_kuveyt_regular_low_ratio_unheaded_table_is_additional_home():
    html = f"""
    <html><h1>Konut Finansmanı</h1>
    {table('Ekspertiz Değeri/Enerji Sınıfı', ADDITIONAL_ROWS)}
    </html>
    """
    result = extract_standard_product(html)
    rules = json.loads(result.housing_finance_rules_json)
    assert not rules["standard_home"]
    assert len(rules["additional_home"]) == 5


def test_is_yeri_fark_vade_phrase_extracts_60_months():
    html = """
    <html><h1>İş Yeri Finansmanı</h1>
    <p>Geri ödeme planınız oluşturulurken 60 aya kadar fark vade seçeneklerini tercih edebilirsiniz.</p>
    </html>
    """
    result = extract_standard_product(html)
    assert result.maximum_maturity_months == 60


def test_2b_explicit_asset_ratio_is_100_percent():
    html = """
    <html><h1>2B Finansmanı</h1>
    <p>Arazi değerinin %100’üne kadar finansman kullanılabilir.</p>
    <p>60 aya varan vade seçeneklerinden yararlanılabilir.</p>
    </html>
    """
    result = extract_standard_product(html)
    assert result.maximum_financing_ratio == 100.0
    assert result.maximum_maturity_months == 60


def test_gurbet_explicit_expert_value_ratio_is_50_percent():
    html = """
    <html><h1>Gurbetten Sılaya Gayrimenkul Finansmanı</h1>
    <p>Ekspertiz değerinin %50’si tutarında finansman kullanılabilir.</p>
    </html>
    """
    result = extract_standard_product(html)
    assert result.maximum_financing_ratio == 50.0


def test_commercial_allocation_fee_maximum_1_10_is_preserved_as_maximum():
    clean = (
        "Finansman tahsis ücreti; ticari nitelikli finansmanlarda "
        "finansman tutarı üzerinden maksimum %1.10 olacak şekilde hesaplanmaktadır."
    )
    rules = build_finance_rules(html=f"<html><body>{clean}</body></html>", clean_text=clean)
    fees = [row for row in rules["fee_rules"] if row.get("fee_type") == "allocation"]
    assert len(fees) == 1
    assert fees[0]["rate"] == 1.10
    assert fees[0]["fee_label"] == "Azami Tahsis Ücreti"
    assert "maksimum" in fees[0]["note"].casefold()


def test_housing_purpose_does_not_become_business_financing():
    features = extract_qualitative_features(
        product_name="Konut Finansmanı",
        product_family="Konut Finansmanı",
        scope="Bireysel",
        clean_text=(
            "Konut finansmanı, ev sahibi olmak isteyen kişilere avantajlı kâr oranları "
            "ve farklı vade seçenekleri sunarak ev sahibi olma sürecini kolaylaştırır."
        ),
    )
    values = {row.feature_key: row.feature_value for row in features}
    assert values.get("usage_purpose") == "Konut ediniminin finansmanı"


def test_verified_overrides_use_audited_housing_fees_and_guard_example_pricing():
    dunya = apply_verified_housing_product_overrides(
        {"bank_name": "Dünya Katılım", "product_name": "Konut Finansmanı", "finance_rules_json": "{}"}
    )
    dunya_rules = json.loads(dunya["finance_rules_json"])
    dunya_fees = {row["fee_type"]: row for row in dunya_rules["fee_rules"]}
    assert dunya_fees["allocation"]["rate"] == 0.50
    assert dunya_fees["appraisal"]["amount"] == 20_778.0
    assert "asgari" in dunya_fees["appraisal"]["note"].casefold()
    assert dunya_fees["mortgage_establishment"]["amount"] == 3_000.0
    assert "asgari" in dunya_fees["mortgage_establishment"]["note"].casefold()

    albaraka = apply_verified_housing_product_overrides(
        {"bank_name": "Albaraka Türk", "product_name": "Konut Finansmanı", "finance_rules_json": "{}"}
    )
    albaraka_rules = json.loads(albaraka["finance_rules_json"])
    assert albaraka_rules["pricing_tiers"] == []
    assert albaraka["profit_share_rate"] is None
    assert albaraka["profit_share_rate_text"] == "Güncel oran hesaplama aracında belirlenir"

    for product_name in (
        "Konut Finansmanı",
        "İlk Evim Konut Finansmanı",
        "Yeşil Konut Finansmanı",
        "Gurbetten Sılaya Gayrimenkul Finansmanı",
    ):
        kuveyt = apply_verified_housing_product_overrides(
            {"bank_name": "Kuveyt Türk", "product_name": product_name, "finance_rules_json": "{}"}
        )
        kuveyt_rules = json.loads(kuveyt["finance_rules_json"])
        fees = {row["fee_type"]: row for row in kuveyt_rules["fee_rules"]}
        assert fees["allocation"]["rate"] == 0.50
        assert fees["appraisal"]["amount"] == 23_645.0
        assert "asgari" in fees["appraisal"]["note"].casefold()
        assert "23.203" in fees["appraisal"]["note"]
        assert "23.645" in fees["appraisal"]["note"]
        assert "resmî kaynaklar birbiriyle farklı" in fees["appraisal"]["note"].casefold()
        assert "29.07.2026" in fees["appraisal"]["note"]
        assert "örnek" not in fees["appraisal"]["note"].casefold()
        assert "hesaplama aracı" not in fees["appraisal"]["note"].casefold()
        assert fees["mortgage_establishment"]["amount"] == 4_500.0
        assert "asgari 4.500" in fees["mortgage_establishment"]["note"].casefold()
        assert "sayısal bir ipotek tesis tutarı yayımlamaz" in fees["mortgage_establishment"]["note"].casefold()
        assert "gerçek masraf" in fees["mortgage_establishment"]["note"].casefold()
        assert "örnek" not in fees["mortgage_establishment"]["note"].casefold()

    green = apply_verified_housing_product_overrides(
        {"bank_name": "Kuveyt Türk", "product_name": "Yeşil Konut Finansmanı", "finance_rules_json": "{}"}
    )
    green_rules = json.loads(green["finance_rules_json"])
    pricing_validity = [row for row in green_rules["offer_rules"] if row["rule_type"] == "pricing_validity"]
    assert pricing_validity[0]["max_amount"] == 3_000_000.0


def test_turkiye_finans_verified_override_replaces_false_no_expense_and_adds_detail():
    stale = {
        "category_rules": [],
        "amount_maturity_rules": [],
        "pricing_tiers": [
            {
                "pricing_variant": "İlk Konut · Sigortalı",
                "maturity_months": 120,
                "profit_share_rate": 2.95,
                "allocation_fee_rate": 0.50,
            }
        ],
        "fee_rules": [
            {
                "fee_type": "allocation",
                "fee_label": "Tahsis Ücreti",
                "waived": False,
                "rate": 0.50,
            },
            {
                "fee_type": "general_expense",
                "fee_label": "Masraf",
                "waived": True,
                "note": "Yanlış stale kayıt",
            },
        ],
        "offer_rules": [],
    }
    tf = apply_verified_housing_product_overrides(
        {
            "bank_name": "Türkiye Finans",
            "product_name": "Konut Finansmanı (Konut Kredisi)*",
            "finance_rules_json": json.dumps(stale, ensure_ascii=False),
        }
    )
    rules = json.loads(tf["finance_rules_json"])
    fee_types = {row["fee_type"] for row in rules["fee_rules"]}
    assert fee_types == {"allocation", "appraisal", "mortgage_establishment"}
    assert not any(row.get("waived") for row in rules["fee_rules"])
    fee_map = {row["fee_type"]: row for row in rules["fee_rules"]}
    assert "100.000 TL örnek" in fee_map["appraisal"]["note"]
    assert "100.000 TL örnek" in fee_map["mortgage_establishment"]["note"]
    assert "faturalandır" in fee_map["mortgage_establishment"]["note"].casefold()
    assert rules["pricing_tiers"][0]["profit_share_rate"] == 2.95
    labels = {row["rule_label"] for row in rules["offer_rules"]}
    assert "Maliyet Tablosu Fiyatlama Koşulu" in labels
    assert "Ekspertiz Ücreti ve Bloke Koşulu" in labels
    assert "Sigorta Primlerinin Değişkenliği" in labels
