from __future__ import annotations

from src.albaraka_standard_product_overrides import (
    apply_albaraka_standard_product_overrides,
)


def row(name: str, text: str) -> dict:
    return {
        "bank_name": "Albaraka Türk",
        "product_name": name,
        "product_family": "Araç Finansmanı",
        "scope": "bireysel",
        "clean_text": text,
        "maximum_maturity_months": None,
        "maximum_financing_ratio": None,
        "maturity_rules_text": None,
        "financing_ratio_rules_text": None,
        "vehicle_finance_rules_text": None,
        "vehicle_age_rules_text": None,
        "finance_rules_json": None,
    }


VEHICLE_TABLE = (
    "Nihai Fatura / Kasko Değeri Maksimum Oran Azami Vade (Ay) "
    "0 TL – 400.000 TL 70% 48 "
    "400.001 TL – 800.000 TL 50% 36 "
    "800.001 TL – 1.200.000 TL 30% 24 "
    "1.200.001 TL- 2.000.000 TL 20% 12 "
    "2.000.000 ve üzeri 0% 0"
)


def test_albaraka_tasit_vehicle_table_and_age_are_preserved():
    result = apply_albaraka_standard_product_overrides(
        row(
            "Taşıt Finansmanı",
            (
                "İster sıfır (0) araç ister ikinci el (2.el) araç. "
                + VEHICLE_TABLE
                + " İkinci el araçlar için 10 yaşını aşmamış olması şarttır."
            ),
        )
    )

    assert result["maximum_maturity_months"] == 48
    assert result["maximum_financing_ratio"] == 70.0
    assert "Kullandırım yok" in result["vehicle_finance_rules_text"]
    assert result["vehicle_age_rules_text"] == (
        "0 km ve 2. El araçlar; ikinci el araçlarda azami 10 yaş"
    )


def test_albaraka_digital_vehicle_uses_table_max_48_not_intro_36():
    result = apply_albaraka_standard_product_overrides(
        row(
            "Dijital Araç Finansmanı",
            (
                "İkinci el araçlar için Dijital Araç Finansmanı başvurusu yapabilirsiniz. "
                "Kullanım durumuna bağlı olarak 36 aya kadar vade seçenekleri. "
                + VEHICLE_TABLE
                + " İkinci el araç finansmanlarında 10 yaşa kadar finansman desteği."
            ),
        )
    )

    assert result["maximum_maturity_months"] == 48
    assert result["maximum_financing_ratio"] == 70.0
    assert "%70 / 48 ay" in result["vehicle_finance_rules_text"]
    assert "Kullandırım yok" in result["vehicle_finance_rules_text"]
    assert result["vehicle_age_rules_text"] == (
        "Yalnız 2. El araçlar; ikinci el araçlarda azami 10 yaş"
    )


def test_albaraka_togg_marks_zero_km_and_ratio():
    result = apply_albaraka_standard_product_overrides(
        row(
            "Togg Finansmanı",
            (
                "Sadece sıfır kilometre T10X ve T10F modeli Togg araçlar için geçerlidir. "
                "Maksimum 48 aya varan vade imkanı sunar. "
                "Proforma fatura tutarına göre %70’e varan finansman oranı uygulanır."
            ),
        )
    )

    assert result["maximum_maturity_months"] == 48
    assert result["maximum_financing_ratio"] == 70.0
    assert result["vehicle_age_rules_text"] == "Yalnız 0 km Togg"
