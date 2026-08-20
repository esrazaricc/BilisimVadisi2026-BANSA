from __future__ import annotations

import json
from pathlib import Path

from src.finance_data_quality import (
    apply_finance_data_quality_overrides,
    canonicalize_ziraat_product_identity,
    is_generic_ziraat_product_name,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "standard_product_sources.json"


def ziraat_config():
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    return next(item for item in data["banks"] if item["name"] == "Ziraat Katılım")


def embedded_by_url():
    return {p["url"]: p for p in ziraat_config().get("embedded_product_pages", [])}


def names(page):
    return [p["product_name"] for p in page["products"]]


def test_ziraat_official_catalog_counts_are_explicit():
    pages = embedded_by_url()
    assert len(names(pages["https://www.ziraatkatilim.com.tr/tarim/tarimsal-finansman-%C3%BCr%C3%BCnleri"])) == 14
    assert len(names(pages["https://www.ziraatkatilim.com.tr/bireysel/finansman-urunleri/ihtiyac-finansmani"])) == 8
    assert len(names(pages["https://www.ziraatkatilim.com.tr/bireysel/finansman-urunleri/konut-gayrimenkul-finansmani"])) == 4
    assert len(names(pages["https://www.ziraatkatilim.com.tr/bireysel/finansman-urunleri/tasit-finansmani"])) == 2
    assert len(names(pages["https://www.ziraatkatilim.com.tr/ticari/finansal-kiralama-leasing"])) == 2


def test_ziraat_tarim_catalog_has_14_distinct_real_product_names():
    page = embedded_by_url()["https://www.ziraatkatilim.com.tr/tarim/tarimsal-finansman-%C3%BCr%C3%BCnleri"]
    product_names = names(page)
    assert len(product_names) == len(set(product_names)) == 14
    assert "Tarımsal Mekanizasyon Finansmanı" in product_names
    assert "Küçük Ekipman Finansmanı" in product_names
    assert all(not is_generic_ziraat_product_name(name) for name in product_names)


def test_generic_ziraat_title_is_canonicalized_by_official_detail_url():
    row = canonicalize_ziraat_product_identity(
        {
            "bank_name": "Ziraat Katılım",
            "product_name": "Ziraat Katılım Bankası",
            "url": "https://www.ziraatkatilim.com.tr/tarim/tarimsal-finansman-urunleri/tarimsal-mekanizasyon-finansmani",
            "product_family_key": "tarim_finansmani",
            "product_family": "Tarım Finansmanı",
        }
    )
    assert row["product_name"] == "Tarımsal Mekanizasyon Finansmanı"
    assert row["product_family_key"] == "tarim_finansmani"


def test_green_products_route_to_comparison_categories_not_generic_sustainable():
    green_home = canonicalize_ziraat_product_identity(
        {
            "bank_name": "Ziraat Katılım",
            "product_name": "Ziraat Katılım Bankası",
            "url": "https://www.ziraatkatilim.com.tr/bireysel/finansman-urunleri/surdurulebilirlik-temali-bireysel-urunler/yesil-ev-konut-finansmani",
        }
    )
    green_vehicle = canonicalize_ziraat_product_identity(
        {
            "bank_name": "Ziraat Katılım",
            "product_name": "Ziraat Katılım Bankası",
            "url": "https://www.ziraatkatilim.com.tr/bireysel/finansman-urunleri/surdurulebilirlik-temali-bireysel-urunler/yesil-tasit-finansmani",
        }
    )
    assert green_home["product_name"] == "Yeşil Ev Konut Finansmanı"
    assert green_home["product_family_key"] == "konut_finansmani"
    assert green_vehicle["product_name"] == "Yeşil Taşıt Finansmanı"
    assert green_vehicle["product_family_key"] == "arac_finansmani"


def test_tarim_state_support_percentage_never_becomes_profit_share_rate():
    out = apply_finance_data_quality_overrides(
        {
            "bank_name": "Ziraat Katılım",
            "product_name": "Bitkisel Üretim Finansmanı",
            "product_family_key": "tarim_finansmani",
            "product_family": "Tarım Finansmanı",
            "url": "https://www.ziraatkatilim.com.tr/tarim/tarimsal-finansman-urunleri/bitkiseluretim",
            "clean_text": "Bitkisel üretim faaliyetleriniz için %100'e varan devlet destekli (sübvansiyonlu) finansman imkânları.",
            "profit_share_rate": 100.0,
            "profit_share_rate_text": "%100",
            "finance_rules_json": json.dumps({"pricing_tiers": [{"profit_share_rate": 100.0, "source_text": "%100 devlet destekli"}]}, ensure_ascii=False),
        }
    )
    assert out["profit_share_rate"] is None
    assert "kâr payı değildir" in out["profit_share_rate_text"]
    rules = json.loads(out["finance_rules_json"])
    assert rules["pricing_tiers"] == []
    assert "state_support_note" in rules["display_metadata"]


def test_leasing_generic_title_maps_to_real_product():
    row = canonicalize_ziraat_product_identity(
        {
            "bank_name": "Ziraat Katılım",
            "product_name": "Ziraat Katılım Bankası",
            "url": "https://www.ziraatkatilim.com.tr/ticari/finansal-kiralama-leasing/finansal-kiralama-leasing",
        }
    )
    assert row["product_name"] == "Finansal Kiralama (Leasing)"
    assert row["product_family_key"] == "leasing"


def test_generic_title_detection_is_strict():
    assert is_generic_ziraat_product_name("Ziraat Katılım Bankası")
    assert is_generic_ziraat_product_name("Ziraat Katılım")
    assert not is_generic_ziraat_product_name("Tarım Finansmanı")
