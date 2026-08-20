from src.finance_taxonomy import (
    categories_for_scope,
    category_label,
    category_scope,
    classify_finance_category,
    normalize_scope,
    scope_label,
)


def test_scope_labels():
    assert scope_label("bireysel") == "Bireysel Finansman"
    assert scope_label("ticari") == "İş / Ticari Finansman"


def test_retail_categories_stay_in_retail_scope():
    key = classify_finance_category(
        "Araç Finansmanı",
        "Taksitli Ticari Taşıt Finansmanı",
        "bireysel",
    )
    assert key == "tasit_finansmani"
    assert category_scope(key) == "bireysel"


def test_product_name_ticari_does_not_override_bireysel_scope():
    # Türkiye Finans gibi bankalarda ürün adında "Ticari" geçse bile ürün
    # bankanın bireysel ailesinde yayımlanıyorsa scope korunmalıdır.
    assert classify_finance_category(
        "Araç Finansmanı",
        "Ticari Hat / Ticari Plaka Finansmanı",
        "bireysel",
    ) == "tasit_finansmani"


def test_business_families_have_distinct_categories():
    cases = {
        "Ticari Finansman": "ticari_finansman",
        "Gayri Nakdi Finansman": "gayri_nakdi_finansman",
        "Tarım Finansmanı": "tarim_finansmani",
        "Leasing": "leasing_finansal_kiralama",
        "Sürdürülebilir Finansman": "diger_ticari_finansman",
    }
    for family, expected in cases.items():
        key = classify_finance_category(family, "Örnek Ürün", "ticari")
        assert key == expected
        assert category_scope(key) == "ticari"


def test_business_categories_are_not_exposed_as_retail():
    labels = [item.label for item in categories_for_scope("ticari")]
    assert labels == [
        "Ticari Finansman",
        "Gayri Nakdi Finansman",
        "Tarım Finansmanı",
        "Leasing / Finansal Kiralama",
        "Diğer İş / Ticari Finansman",
    ]
    assert "Konut Finansmanı" not in labels


def test_retail_categories_are_not_exposed_as_business():
    labels = [item.label for item in categories_for_scope("bireysel")]
    assert "Konut Finansmanı" in labels
    assert "Taşıt Finansmanı" in labels
    assert "Ticari Finansman" not in labels


def test_normalize_scope_common_values():
    assert normalize_scope("Bireysel") == "bireysel"
    assert normalize_scope("KOBİ") == "ticari"
    assert normalize_scope("Kurumsal") == "ticari"


def test_category_label_business():
    assert category_label("gayri_nakdi_finansman") == "Gayri Nakdi Finansman"
