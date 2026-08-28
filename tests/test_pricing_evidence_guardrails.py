from __future__ import annotations

import pandas as pd

from src.pricing_guardrails import (
    authoritative_pricing_rows,
    filter_authoritative_pricing_frame,
    is_example_only_pricing_row,
    sanitize_product_rate_fields,
    text_marks_example_only,
)


def test_turkish_softened_ornegi_marker_is_detected():
    assert text_marks_example_only("Resmî maliyet örneği · 100.000 TL")
    assert text_marks_example_only("Örnek ödeme tablosu")
    assert text_marks_example_only("Temsili senaryo")


def test_real_pricing_variant_is_not_blocked():
    assert not is_example_only_pricing_row(
        {
            "pricing_variant": "İlk Konut · Sigortalı",
            "source_text": "120 | 2,95% | 0,50%",
        }
    )


def test_example_pricing_row_is_removed_before_customer_use():
    rows = [
        {
            "pricing_variant": "Resmî maliyet örneği · 100.000 TL",
            "source_text": "100.000 TL örneği",
            "profit_share_rate": 2.95,
        },
        {
            "pricing_variant": "Sigortalı",
            "source_text": "120 | 3,41%",
            "profit_share_rate": 3.41,
        },
    ]
    cleaned = authoritative_pricing_rows(rows)
    assert len(cleaned) == 1
    assert cleaned[0]["profit_share_rate"] == 3.41


def test_dataframe_read_guard_blocks_stale_example_rows():
    frame = pd.DataFrame(
        [
            {
                "product_id": 1,
                "pricing_variant": "Resmî maliyet örneği · 100.000 TL",
                "source_text": "Albaraka resmî maliyet örneği",
                "profit_share_rate": 2.95,
            },
            {
                "product_id": 2,
                "pricing_variant": "Standart",
                "source_text": "Güncel fiyat tablosu",
                "profit_share_rate": 3.10,
            },
        ]
    )
    cleaned = filter_authoritative_pricing_frame(frame)
    assert cleaned["product_id"].tolist() == [2]


def test_product_level_example_rate_cannot_remain_numeric():
    cleaned = sanitize_product_rate_fields(
        {
            "profit_share_rate": 2.95,
            "profit_share_rate_text": "100.000 TL örnek ödeme tablosu oranı",
        }
    )
    assert cleaned["profit_share_rate"] is None
    assert "örnek" in cleaned["profit_share_rate_text"]
