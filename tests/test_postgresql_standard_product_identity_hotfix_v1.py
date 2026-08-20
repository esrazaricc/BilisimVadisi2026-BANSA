from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sync_finance_data_accuracy_v2_to_postgresql.py"


def test_sync_reconciles_natural_product_identity_before_insert():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "WHERE bank_id=%s AND family_id=%s AND product_name=%s AND source_page_id=%s" in text
    assert "[PG KIMLIK UZLASTIRMA]" in text
    assert "UPDATE standard_products SET" in text
    # Legacy-only ON CONFLICT tek başına doğal unique constraint'i çözemez;
    # doğal kimlik kontrolü INSERT'ten önce bulunmalı.
    natural_pos = text.index("WHERE bank_id=%s AND family_id=%s AND product_name=%s AND source_page_id=%s")
    insert_pos = text.index("INSERT INTO standard_products(legacy_live_id", natural_pos)
    assert natural_pos < insert_pos


def test_sync_keeps_natural_unique_key_intact():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "legacy_live_id=%s" in text
    assert "existing_legacy_id" in text
