from src.extraction.comparison_field_extractor import (
    extract_audiences,
    extract_benefits,
)
from scripts.audit_kuveyt_nonfinance_extraction import (
    detect_signals,
)


def benefit_types(items):
    return {item.benefit_type for item in items}


def audience_types(items):
    return {item.audience_type for item in items}


def test_installment_aya_varan():
    items = extract_benefits(
        "Mobilya Kampanyası",
        "Alışverişlerinizde vade farksız 9 aya varan taksit imkanı.",
    )
    assert "installment" in benefit_types(items)
    assert next(
        item for item in items if item.benefit_type == "installment"
    ).description == "9 taksit"


def test_installment_apostrophe_form():
    items = extract_benefits(
        "Saat Kampanyası",
        "Alışverişlerinizde 5'e varan taksit imkanı.",
    )
    assert next(
        item for item in items if item.benefit_type == "installment"
    ).description == "5 taksit"


def test_explicit_miles_but_not_brand_name():
    brand_only = detect_signals(
        "Miles&Smiles Kuveyt Türk Kredi Kartı ile 9 taksit."
    )
    explicit = detect_signals(
        "2.000 TL üzeri harcamaya 2.000 Mil kazanma fırsatı."
    )
    assert "miles" not in brand_only
    assert "miles" in explicit

    benefits = extract_benefits(
        "Akaryakıt Kampanyası",
        (
            "Miles&Smiles Business kart ile 2.000 TL ve üzeri "
            "harcamalarda ekstra %5, aylık maksimum 2.000 Mil."
        ),
    )
    miles = next(
        item for item in benefits if item.benefit_type == "miles"
    )
    assert miles.points == 2000
    assert miles.rate == 5


def test_altin_puan():
    items = extract_benefits(
        "Altın Puan Kampanyası",
        (
            "2.000 TL ve üzeri harcamalarınızda toplamda "
            "600 TL Altın Puan kazandırıyor."
        ),
    )
    points = next(
        item
        for item in items
        if item.benefit_type == "shopping_points"
    )
    assert points.points == 600


def test_special_rate_and_pos():
    rate_items = extract_benefits(
        "Özel Kur Kampanyası",
        "Yeni müşterilere özel avantajlı kur fırsatı sunulur.",
    )
    assert "special_rate" in benefit_types(rate_items)

    pos_items = extract_benefits(
        "Sanal POS Kampanyası",
        "30 gün bloke ile %0 komisyon avantajı sunulur.",
    )
    assert "pos_advantage" in benefit_types(pos_items)


def test_card_business_and_new_customer_audiences():
    items = extract_audiences(
        "Business Kart Kampanyası",
        (
            "KOBİ müşteriler, Kuveyt Türk Mobil’den müşterimiz "
            "olarak Business Kredi Kartları ile faydalanabilir."
        ),
    )
    types = audience_types(items)
    assert "business_customer" in types
    assert "card_holder" in types
    assert "new_customer" in types
    assert "digital_customer" in types
