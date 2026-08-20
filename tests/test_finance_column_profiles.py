from __future__ import annotations

import pandas as pd

from src.finance_column_profiles import (
    get_profile,
    join_verified_values,
    select_main_table_columns,
)


def test_join_verified_values_never_invents_missing_data():
    assert join_verified_values("Belirtilmedi", None, "—") == "—"
    assert join_verified_values("12 aya kadar", "Esnek ödeme") == "12 aya kadar · Esnek ödeme"
    assert join_verified_values("Şube", "Şube") == "Şube"


def test_ticari_finansman_uses_decision_columns_not_generic_noise():
    frame = pd.DataFrame(
        [
            {
                "Banka": "A",
                "Ürün": "Jet Ticari",
                "Kullanım Amacı": "İşletme finansman ihtiyacı",
                "Finansman Yapısı": "—",
                "Finansman Limiti": "≤ 2.000.000 TL",
                "İşlem / Kanal Limiti": "—",
                "Vade / Ödeme": "—",
                "Teminat / Güvence": "—",
                "Para Birimi": "—",
                "Kullanım / Kanal": "Dijital Kanallar · Dijital: Evet",
                "Dış Ticaret": "—",
                "Kâr Payı / Fiyatlama": "—",
                "Tahsis Ücreti": "—",
                "Hedef Kitle": "Ticari",
                "Dijital": "Evet",
                "Ürün Kaynağı": "https://example.com/a",
                "Ücret Kaynağı": None,
            },
            {
                "Banka": "B",
                "Ürün": "Taksitli Ticari",
                "Kullanım Amacı": "Mal ve hizmet finansmanı",
                "Finansman Yapısı": "Taksitli finansman",
                "Finansman Limiti": "—",
                "İşlem / Kanal Limiti": "Bayide şubesiz işlem 60.000 TL'ye kadar",
                "Vade / Ödeme": "Esnek ödeme · Taksitli",
                "Teminat / Güvence": "—",
                "Para Birimi": "TL / Yabancı Para",
                "Kullanım / Kanal": "Şube",
                "Dış Ticaret": "Evet",
                "Kâr Payı / Fiyatlama": "—",
                "Tahsis Ücreti": "—",
                "Hedef Kitle": "Ticari · İşletmeler",
                "Dijital": "—",
                "Ürün Kaynağı": "https://example.com/b",
                "Ücret Kaynağı": None,
            },
        ]
    )
    columns = select_main_table_columns(frame, "ticari", "Ticari Finansman")

    assert columns == [
        "Banka",
        "Ürün",
        "Kullanım Amacı",
        "Finansman Yapısı",
        "Finansman Limiti",
        "İşlem / Kanal Limiti",
        "Vade / Ödeme",
        "Para Birimi",
        "Kullanım / Kanal",
        "Ürün Kaynağı",
    ]
    assert "Hedef Kitle" not in columns
    assert "Dijital" not in columns
    assert "Kâr Payı / Fiyatlama" not in columns
    assert "Tahsis Ücreti" not in columns


def test_ticari_finansman_separates_finance_limit_from_channel_limit():
    frame = pd.DataFrame([
        {
            "Banka": "Albaraka Türk",
            "Ürün": "Bayide Finansman",
            "Kullanım Amacı": "Bayide finansman",
            "Finansman Yapısı": "—",
            "Finansman Limiti": "—",
            "İşlem / Kanal Limiti": "Bayide şubesiz işlem 60.000 TL'ye kadar; üzeri şubede tamamlanır",
            "Vade / Ödeme": "36 aya kadar",
            "Teminat / Güvence": "—",
            "Para Birimi": "—",
            "Kullanım / Kanal": "Bayide / Şube",
            "Dış Ticaret": "—",
            "Kâr Payı / Fiyatlama": "—",
            "Tahsis Ücreti": "—",
            "Ürün Kaynağı": "https://example.com/bayide",
        },
        {
            "Banka": "Albaraka Türk",
            "Ürün": "Jet Ticari Finansman",
            "Kullanım Amacı": "Dijital ticari finansman",
            "Finansman Yapısı": "—",
            "Finansman Limiti": "≤ 2.000.000 TL",
            "İşlem / Kanal Limiti": "—",
            "Vade / Ödeme": "—",
            "Teminat / Güvence": "—",
            "Para Birimi": "—",
            "Kullanım / Kanal": "Dijital",
            "Dış Ticaret": "—",
            "Kâr Payı / Fiyatlama": "—",
            "Tahsis Ücreti": "—",
            "Ürün Kaynağı": "https://example.com/jet",
        },
    ])
    columns = select_main_table_columns(frame, "ticari", "Ticari Finansman")
    assert "Finansman Limiti" in columns
    assert "İşlem / Kanal Limiti" in columns
    assert "Limit / Finansman Tutarı" not in columns


def test_gayri_nakdi_does_not_force_cash_finance_metrics():
    frame = pd.DataFrame(
        [{
            "Banka": "A",
            "Ürün": "Teminat Mektubu",
            "Enstrüman Türü": "Teminat Mektubu",
            "Kullanım Alanı": "Ticari yükümlülüklerin güvence altına alınması",
            "İşlem / Limit": "15.000.000 TL mektup üst limiti",
            "Para Birimi": "TL / Yabancı Para",
            "Dış Ticaret": "Evet",
            "Vade / Ödeme": "—",
            "Teminat / Güvence": "—",
            "Kullanım / Kanal": "İnternet Şubesi · Mobil",
            "Kâr Payı / Fiyatlama": "%4,00",
            "Finansman Tutarı": "1.000.000 TL",
            "Tahsis Ücreti": "%0,50",
            "Ürün Kaynağı": "https://example.com",
        }]
    )
    columns = select_main_table_columns(frame, "ticari", "Gayri Nakdi Finansman")
    assert "Kâr Payı / Fiyatlama" not in columns
    assert "Finansman Tutarı" not in columns
    assert "Tahsis Ücreti" not in columns
    assert "Enstrüman Türü" in columns
    assert "Kullanım Alanı" in columns
    assert "İşlem / Limit" in columns
    assert "Dış Ticaret" not in columns
    assert "Teminat / Güvence" not in columns


def test_housing_keeps_user_required_core_columns_even_when_missing():
    frame = pd.DataFrame(
        [{
            "Banka": "A",
            "Ürün": "Konut",
            "Kâr Payı / Fiyatlama": "—",
            "Azami Vade": "120 ay",
            "Finansman Oranı": "—",
            "Tahsis Ücreti": "—",
            "Ekspertiz Ücreti": "—",
            "İpotek Tesis Ücreti": "—",
            "Ürün Kaynağı": "https://example.com",
            "Ücret Kaynağı": None,
        }]
    )
    columns = select_main_table_columns(frame, "bireysel", "Konut Finansmanı")
    assert columns[:2] == ["Banka", "Ürün"]
    for required in (
        "Kâr Payı / Fiyatlama",
        "Azami Vade",
        "Finansman Oranı",
        "Tahsis Ücreti",
        "Ekspertiz Ücreti",
        "İpotek Tesis Ücreti",
    ):
        assert required in columns


def test_profiles_exist_for_every_taxonomy_leaf():
    expected = [
        ("bireysel", "Konut Finansmanı"),
        ("bireysel", "Taşıt Finansmanı"),
        ("bireysel", "İhtiyaç Finansmanı"),
        ("bireysel", "Gayrimenkul Finansmanı"),
        ("bireysel", "Alışveriş Finansmanı"),
        ("bireysel", "Diğer Bireysel Finansman"),
        ("ticari", "Ticari Finansman"),
        ("ticari", "Gayri Nakdi Finansman"),
        ("ticari", "Tarım Finansmanı"),
        ("ticari", "Leasing / Finansal Kiralama"),
        ("ticari", "Diğer İş / Ticari Finansman"),
    ]
    for scope, label in expected:
        profile = get_profile(scope, label)
        assert profile.scope == scope
        assert profile.category_label == label
        assert profile.preferred_columns


def test_pricing_source_is_never_exposed_as_main_table_column():
    frame = pd.DataFrame([
        {
            "Banka": "A",
            "Ürün": "Ürün A",
            "Kâr Payı / Fiyatlama": "%3,00",
            "Vade / Ödeme": "12 ay",
            "Ürün Kaynağı": "https://example.com/product",
            "Fiyatlama Kaynağı": "https://example.com/pricing",
            "Ücret Kaynağı": "https://example.com/fees",
        }
    ])
    columns = select_main_table_columns(frame, "bireysel", "İhtiyaç Finansmanı")
    assert "Fiyatlama Kaynağı" not in columns
    assert "Ürün Kaynağı" in columns
    assert "Ücret Kaynağı" in columns


def test_tarim_profile_prioritizes_agricultural_decision_fields():
    frame = pd.DataFrame([{
        "Banka": "Kuveyt Türk",
        "Ürün": "Tarım ve Hayvancılık Finansmanı",
        "Kullanım Amacı": "Tarım ve hayvancılık yatırımı",
        "Finansman Limiti": "—",
        "Ödeme / Hasat Yapısı": "Hasat dönemine uygun esnek ödeme",
        "Teminat / Güvence": "—",
        "Para Birimi": "TL / USD / EUR",
        "Kullanım / Kanal": "Şube",
        "Dış Ticaret": "Evet",
        "Ürün Kaynağı": "https://example.com/tarim",
    }])
    columns = select_main_table_columns(frame, "ticari", "Tarım Finansmanı")
    assert columns == [
        "Banka", "Ürün", "Kullanım Amacı", "Ödeme / Hasat Yapısı",
        "Ürün Kaynağı"
    ]
    # Tarım ana tablosu karar alanlarını sade tutar; para birimi, kanal ve
    # dış ticaret gibi ikincil alanlar kategori profilinde özellikle gösterilmez.
    assert "Para Birimi" not in columns
    assert "Kullanım / Kanal" not in columns
    assert "Dış Ticaret" not in columns


def test_leasing_profile_uses_asset_rent_and_kdv_not_foreign_trade():
    frame = pd.DataFrame([{
        "Banka": "Türkiye Finans",
        "Ürün": "Leasing",
        "Varlık / Yatırım Türü": "Yatırım malı",
        "Finansman Oranı": "%100'e kadar",
        "Vade / Kira Planı": "60 aya kadar · esnek ödeme",
        "Para Birimi": "TL",
        "Maliyet / KDV Yapısı": "%1 KDV yalnız uygun varlıklarda",
        "Kullanım / Kanal": "Şube / İnternet sitesi",
        "Dış Ticaret": "Evet",
        "Ürün Kaynağı": "https://example.com/leasing",
    }])
    columns = select_main_table_columns(frame, "ticari", "Leasing / Finansal Kiralama")
    assert columns == [
        "Banka", "Ürün", "Varlık / Yatırım Türü", "Finansman Oranı",
        "Vade / Kira Planı", "Para Birimi", "Maliyet / KDV Yapısı",
        "Kullanım / Kanal", "Ürün Kaynağı"
    ]
    assert "Dış Ticaret" not in columns
