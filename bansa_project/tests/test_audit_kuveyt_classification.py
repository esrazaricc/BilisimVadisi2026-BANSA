import sqlite3

from scripts.audit_kuveyt_classification import (
    audit_rows,
)


def make_row(
    connection,
    *,
    title,
    url,
    text,
    content_hash,
    category="other_campaign",
    confidence=0.84,
):
    connection.execute(
        """
        INSERT INTO live_campaigns (
            bank_name,
            source_url,
            source_group,
            title,
            clean_text,
            content_hash,
            current_status,
            record_kind,
            campaign_category,
            classification_confidence,
            classification_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Kuveyt Türk",
            url,
            "Test",
            title,
            text,
            content_hash,
            "active",
            "campaign",
            category,
            confidence,
            "Test sınıflandırması",
        ),
    )


def test_audit_finds_generic_product_and_duplicates():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE live_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_name TEXT,
            source_url TEXT,
            source_group TEXT,
            title TEXT,
            clean_text TEXT,
            content_hash TEXT,
            current_status TEXT,
            record_kind TEXT,
            campaign_category TEXT,
            classification_confidence REAL,
            classification_reason TEXT
        )
        """
    )

    make_row(
        connection,
        title="Kampanya Koşulları",
        url="https://example.com/a",
        text="Kampanya 31 Aralık 2026 tarihine kadar geçerlidir.",
        content_hash="hash-a",
    )
    make_row(
        connection,
        title="Tarımda Büyüme Zamanı!",
        url="https://example.com/b",
        text="Tarım kampanyası özel avantaj sunar.",
        content_hash="same-hash",
    )
    make_row(
        connection,
        title="Tarımda Büyüme Zamanı!",
        url="https://example.com/c",
        text="Tarım kampanyası özel avantaj sunar.",
        content_hash="same-hash",
    )
    make_row(
        connection,
        title="Konut Finansmanı Avantajları",
        url="https://example.com/d",
        text=(
            "Ürün özellikleri ve nasıl başvurabilirim "
            "bilgileri yer alır."
        ),
        content_hash="hash-d",
        category="finance_campaign",
        confidence=0.94,
    )

    rows = connection.execute(
        "SELECT * FROM live_campaigns ORDER BY id"
    ).fetchall()
    result = audit_rows(rows)

    assert result["total"] == 4
    assert result["review_count"] == 4
    assert len(result["duplicate_title_groups"]) == 1
    assert len(result["duplicate_content_groups"]) == 1

    titles = {
        item["title"]
        for item in result["review_rows"]
    }
    assert "Kampanya Koşulları" in titles
    assert "Konut Finansmanı Avantajları" in titles
