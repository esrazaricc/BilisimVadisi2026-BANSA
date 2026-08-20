from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "scan_standard_products.py"
spec = importlib.util.spec_from_file_location("scan_standard_products_v21", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def test_failed_ziraat_detail_is_nonfatal_when_official_embedded_catalog_has_same_product():
    rows = [
        {
            "bank_name": "Ziraat Katılım",
            "product_name": "Tarımsal Mekanizasyon Finansmanı",
            "product_family_key": "tarim_finansmani",
            "embedded_product": True,
        }
    ]
    errors = [
        {
            "url": "https://www.ziraatkatilim.com.tr/tarim/tarimsal-finansman-urunleri/tarimsal-mekanizasyon-finansmani",
            "error_type": "HTTPError",
            "message": "404 Client Error",
        }
    ]
    fatal, covered = mod.filter_ziraat_errors_covered_by_embedded_catalog(errors, rows)
    assert fatal == []
    assert len(covered) == 1
    assert covered[0]["canonical_product_name"] == "Tarımsal Mekanizasyon Finansmanı"


def test_embedded_page_failure_stays_fatal():
    rows = []
    errors = [
        {
            "url": "https://www.ziraatkatilim.com.tr/tarim/tarimsal-finansman-%C3%BCr%C3%BCnleri",
            "error_type": "ValueError",
            "message": "Alt ürün bölümü bulunamadı",
            "embedded_page": True,
        }
    ]
    fatal, covered = mod.filter_ziraat_errors_covered_by_embedded_catalog(errors, rows)
    assert len(fatal) == 1
    assert covered == []


def test_unknown_detail_failure_stays_fatal():
    rows = [
        {
            "bank_name": "Ziraat Katılım",
            "product_name": "Bitkisel Üretim Finansmanı",
            "product_family_key": "tarim_finansmani",
            "embedded_product": True,
        }
    ]
    errors = [
        {
            "url": "https://www.ziraatkatilim.com.tr/tarim/bilinmeyen-urun",
            "error_type": "HTTPError",
            "message": "404 Client Error",
        }
    ]
    fatal, covered = mod.filter_ziraat_errors_covered_by_embedded_catalog(errors, rows)
    assert len(fatal) == 1
    assert covered == []
