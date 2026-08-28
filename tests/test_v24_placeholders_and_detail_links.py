from __future__ import annotations

from urllib.parse import urlparse

from src.repository import get_campaigns
from src.source_link_resolver import resolve_campaign_detail_url, resolve_product_detail_url
from src.ui_finance_dashboard import build_finance_catalog_table, public_catalog_columns
from src.ui_table_density import display_frame_with_missing_label, sanitize_frame


def test_visible_finance_cells_use_belirtilmedi_instead_of_blank_nan_none():
    frame = build_finance_catalog_table("ihtiyac_finansmani")
    cols = public_catalog_columns(frame, "ihtiyac_finansmani")
    raw = sanitize_frame(frame[cols])
    view = display_frame_with_missing_label(raw, preserve_columns=("Ürün Kaynağı",))
    for column in [c for c in view.columns if c != "Ürün Kaynağı"]:
        values = view[column].astype(str).str.strip()
        assert not values.eq("").any()
        assert not values.str.casefold().isin({"nan", "none"}).any()


def test_campaign_listing_url_is_promoted_to_ziraat_campaign_detail():
    resolved = resolve_campaign_detail_url(
        "Ziraat Katılım",
        "A101'de 6 Taksit",
        "https://ziraatkatilim.com.tr/kart-kampanyalari",
    )
    assert resolved.endswith("/kart-kampanyalari/a101de-6-taksit")


def test_campaign_listing_url_is_promoted_to_dunya_campaign_detail():
    resolved = resolve_campaign_detail_url(
        "Dünya Katılım",
        "Enerya yeni doğal gaz abonelerine Dünya Katılım’dan finansman fırsatı!",
        "https://dunyakatilim.com.tr/kampanyalar",
    )
    assert resolved.endswith("/kampanyalar/enerya-finansmani")


def test_product_category_url_is_promoted_to_specific_product_page():
    resolved = resolve_product_detail_url(
        "Dünya Katılım",
        "Enerya Karz-ı Hasen",
        "https://dunyakatilim.com.tr/kendim-icin/finansmanlar",
    )
    assert resolved.endswith("/ihtiyac-finansmanlari/enerya-karz-i-hasen")


def test_repository_campaign_sources_are_not_empty_for_current_campaigns():
    frame = get_campaigns()
    current = frame[frame["is_active"].eq(1)].copy()
    assert not current.empty
    assert current["source_url"].fillna("").astype(str).str.strip().ne("").all()


def test_dunya_vehicle_source_correction_is_preserved():
    frame = build_finance_catalog_table("arac_finansmani", ["Dünya Katılım"])
    row = frame[frame["Ürün"].eq("Araç Finansmanı")].iloc[0]
    assert row["Finansman Oranı / Kuralı"] == ""
    assert "%50" not in str(row["Vade / Ödeme"])
    assert "36 ay" in str(row["Vade / Ödeme"])
    assert "400.000" in str(row["Hesaplama Aracı"])
