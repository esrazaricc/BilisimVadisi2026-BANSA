from src.finance_taxonomy import (
    category_label,
    classify_finance_category,
    normalize_scope,
)


def test_primary_explicit_families_are_normalized():
    assert classify_finance_category("Konut Finansmanı", "İlk Evim", "bireysel") == "konut_finansmani"
    assert classify_finance_category("Araç Finansmanı", "Dijital Araç", "bireysel") == "tasit_finansmani"
    assert classify_finance_category("Taşıt Finansmanı", "Taşıt", "bireysel") == "tasit_finansmani"
    assert classify_finance_category("İhtiyaç Finansmanı", "Eğitim Finansmanı", "bireysel") == "ihtiyac_finansmani"
    assert classify_finance_category("Alışveriş Finansmanı", "Bana Bunu Al", "bireysel") == "alisveris_finansmani"


def test_real_estate_subfamilies_merge_into_one_comparison_category():
    assert classify_finance_category("Arsa Finansmanı", "Arsa Finansmanı", "bireysel") == "gayrimenkul_finansmani"
    assert classify_finance_category("İş Yeri Finansmanı", "İş Yeri Finansmanı", "bireysel") == "gayrimenkul_finansmani"


def test_sustainable_umbrella_uses_only_explicit_product_meaning():
    assert classify_finance_category("Sürdürülebilir Finansman", "Yeşil Konut Finansmanı", "bireysel") == "konut_finansmani"
    assert classify_finance_category("Sürdürülebilir Finansman", "Sürdürülebilir Araç Finansmanı", "bireysel") == "tasit_finansmani"
    assert classify_finance_category("Sürdürülebilir Finansman", "Çatı GES Finansmanı", "bireysel") == "diger_bireysel_finansman"


def test_bank_family_is_respected_for_ambiguous_product_names():
    # Albaraka'nın Motosiklet/ATV/Bisiklet ürünü banka kaynağında İhtiyaç
    # ailesinde tutuluyorsa BANSA ürün adından zorla Taşıt'a taşımaz.
    assert classify_finance_category(
        "İhtiyaç Finansmanı",
        "Motosiklet ATV Bisiklet Finansmanı",
        "bireysel",
    ) == "ihtiyac_finansmani"


def test_commercial_products_do_not_leak_into_retail_categories():
    assert classify_finance_category("Ticari Finansman", "İşletme Finansmanı", "ticari") == "ticari_finansman"
    assert classify_finance_category("Leasing", "Finansal Kiralama", "ticari") == "leasing_finansal_kiralama"


def test_labels_and_scope_normalization():
    assert category_label("gayrimenkul_finansmani") == "Gayrimenkul Finansmanı"
    assert normalize_scope("Bireysel") == "bireysel"
    assert normalize_scope("Ticari") == "ticari"
