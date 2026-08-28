from __future__ import annotations

import pandas as pd

from src.competition_response_service import ask_bansa
from src.ui_campaign_dashboard import public_campaign_columns
from src.ui_finance_comparison import build_finance_comparison_table
from src.ui_finance_dashboard import build_finance_catalog_table, public_catalog_columns
from src.ui_table_density import clean_cell, fill_ratio, sanitize_frame


def _has_ui_noise(frame: pd.DataFrame) -> bool:
    bad = {"nan", "none", "belirtilmedi", "doğrulanmadı"}
    for column in frame.columns:
        for value in frame[column].tolist():
            if str(value).strip().casefold() in bad:
                return True
    return False


def test_finance_catalog_has_no_nan_none_or_belirtilmedi_cells():
    for family in ("konut_finansmani", "arac_finansmani", "ihtiyac_finansmani", "ticari_finansman", "tarim_finansmani"):
        frame = build_finance_catalog_table(family)
        cols = public_catalog_columns(frame, family)
        view = sanitize_frame(frame[cols])
        assert not _has_ui_noise(view)
        assert "Banka" in cols and "Ürün" in cols and "Ürün Kaynağı" in cols


def test_finance_columns_are_family_specific_and_dense():
    housing = build_finance_catalog_table("konut_finansmani")
    housing_cols = public_catalog_columns(housing, "konut_finansmani")
    assert "Ekspertiz Ücreti" in housing_cols
    assert "İpotek / Rehin" in housing_cols

    vehicle = build_finance_catalog_table("arac_finansmani")
    vehicle_cols = public_catalog_columns(vehicle, "arac_finansmani")
    assert "Vade / Ödeme" in vehicle_cols
    assert "Özel Koşullar" in vehicle_cols

    noncash = build_finance_catalog_table("gayri_nakdi_finansman")
    noncash_cols = public_catalog_columns(noncash, "gayri_nakdi_finansman")
    assert "Finansman Yapısı" in noncash_cols
    assert "Para Birimi" in noncash_cols
    assert "Kâr Payı / Fiyatlama" not in noncash_cols


def test_sparse_finance_families_do_not_force_wall_of_empty_columns():
    agriculture = build_finance_catalog_table("tarim_finansmani")
    cols = public_catalog_columns(agriculture, "tarim_finansmani")
    optional = [c for c in cols if c not in {"Banka", "Ürün", "Ürün Kaynağı"}]
    assert len(optional) <= 4
    assert "Özel Koşullar" in optional


def test_scenario_table_uses_one_status_column_instead_of_repeated_missing_labels():
    answer = str(ask_bansa("100000 TL 36 ay taşıt finansmanı seçeneklerini karşılaştır").text)
    table = build_finance_comparison_table(answer, product_label="Taşıt Finansmanı", amount=100000)
    assert "Durum" in table.columns
    assert not _has_ui_noise(table)
    dunya = table[table["Banka"].eq("Dünya Katılım")].iloc[0]
    assert dunya["Aylık Taksit"] == ""
    assert dunya["Durum"] == "Güncel sayısal sonuç yok"


def test_campaign_profile_switches_columns_by_campaign_type():
    sample = sanitize_frame(pd.DataFrame([
        {
            "Banka": "A", "Kampanya": "Taksit", "Tür": "Kart / Taksit Kampanyası",
            "Ana Fayda": "6 taksit", "Taksit": "6", "Hedef Kitle": "Bireysel",
            "Bitiş": "2026-08-31", "Koşullar": "POS işlemi", "Resmî Kaynak": "https://example.com/a",
            "İndirim / İade": "", "Puan": "", "Ödül": "",
        },
        {
            "Banka": "B", "Kampanya": "Taksit 2", "Tür": "Kart / Taksit Kampanyası",
            "Ana Fayda": "3 taksit", "Taksit": "3", "Hedef Kitle": "Bireysel",
            "Bitiş": "2026-09-01", "Koşullar": "Kart işlemi", "Resmî Kaynak": "https://example.com/b",
            "İndirim / İade": "", "Puan": "", "Ödül": "",
        },
    ]))
    cols = public_campaign_columns(sample, "Kart / Taksit Kampanyası")
    assert "Taksit" in cols
    assert "Ana Fayda" in cols
    assert "İndirim / İade" not in cols
    assert "Puan" not in cols


def test_clean_cell_hides_only_missing_markers_not_real_dynamic_pricing():
    assert clean_cell(float("nan")) == ""
    assert clean_cell("Belirtilmedi") == ""
    assert clean_cell("Sayısal fiyatlama yayımlanmamış") == ""
    assert clean_cell("Hesaplama aracında dinamik") == "Hesaplama aracında dinamik"
