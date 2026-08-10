import json
from pathlib import Path


BANKS_FILE = Path("config") / "banks.json"


def test_bank_config_contains_ten_banks():
    banks = json.loads(BANKS_FILE.read_text(encoding="utf-8"))

    assert len(banks) == 10
    assert len({bank["name"] for bank in banks}) == 10
    assert len({bank["slug"] for bank in banks}) == 10


def test_campaign_sources_do_not_use_standard_product_pages():
    banks = json.loads(BANKS_FILE.read_text(encoding="utf-8"))

    forbidden_parts = [
        "/finansmanlar/",
        "/finansman-urunleri/",
        "/urun-ve-hizmetler",
        "/hesaplama-araclari",
    ]

    for bank in banks:
        for page in bank.get("campaign_pages", []):
            assert not any(part in page for part in forbidden_parts)


def test_adil_katilim_is_not_filled_with_a_product_page():
    banks = json.loads(BANKS_FILE.read_text(encoding="utf-8"))
    adil = next(bank for bank in banks if bank["name"] == "Adil Katılım")

    assert adil["campaign_pages"] == []
    assert adil["source_status"] == "public_campaign_page_not_found"

