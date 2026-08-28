from src.finance_live_adapters.dunya_katilim import _discover_housing_variant_codes


def test_dunya_current_product_codes_are_discovered_from_labels_not_hardcoded():
    options = {
        "NEW-HOUSING-2026": "Konut Finansmanı",
        "USED-HOUSING-2026": "2. El Konut Finansmanı",
        "IHT-1": "İhtiyaç Finansmanı",
    }
    found = _discover_housing_variant_codes(options)
    assert found["yeni_konut"] == "NEW-HOUSING-2026"
    assert found["2el_konut"] == "USED-HOUSING-2026"


def test_dunya_single_generic_housing_option_stays_live_capable():
    options = {
        "HOME-CURRENT": "Konut Finansmanı",
        "NEED-CURRENT": "İhtiyaç Finansmanı",
    }
    found = _discover_housing_variant_codes(options)
    assert found["yeni_konut"] == "HOME-CURRENT"
    assert found["standard"] == "HOME-CURRENT"


def test_dunya_historical_codes_are_only_compatibility_fallback():
    options = {
        "KONUTTUKETICI": "Başka Başlık",
        "2ELKONUTTUKETICI": "Başka Başlık 2",
    }
    found = _discover_housing_variant_codes(options)
    assert found["yeni_konut"] == "KONUTTUKETICI"
    assert found["2el_konut"] == "2ELKONUTTUKETICI"
