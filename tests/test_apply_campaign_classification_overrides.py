import json
import sqlite3

from scripts.apply_campaign_classification_overrides import (
    apply_overrides,
)


def create_db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE live_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            title TEXT NOT NULL,
            record_kind TEXT NOT NULL,
            campaign_category TEXT NOT NULL,
            classification_confidence REAL,
            classification_reason TEXT,
            is_current INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    connection.execute(
        """
        INSERT INTO live_campaigns (
            bank_name,
            source_url,
            title,
            record_kind,
            campaign_category,
            classification_confidence,
            classification_reason,
            is_current
        ) VALUES
        (
            'Kuveyt Türk',
            'https://example.com/canonical',
            'Tarım Kampanyası',
            'campaign',
            'other_campaign',
            0.84,
            'Eski',
            1
        ),
        (
            'Kuveyt Türk',
            'https://example.com/duplicate',
            'Tarım Kampanyası',
            'campaign',
            'other_campaign',
            0.84,
            'Eski',
            1
        ),
        (
            'Kuveyt Türk',
            'https://example.com/togg',
            'Kampanya Koşulları',
            'campaign',
            'finance_campaign',
            0.97,
            'Eski',
            1
        )
        """
    )
    return connection


def test_overrides_update_title_category_and_duplicate():
    connection = create_db()
    overrides = [
        {
            "bank_name": "Kuveyt Türk",
            "source_url": "https://example.com/canonical",
            "record_kind": "campaign",
            "campaign_category": "finance_campaign",
            "classification_confidence": 1.0,
            "reason": "Finansman kampanyası.",
        },
        {
            "bank_name": "Kuveyt Türk",
            "source_url": "https://example.com/duplicate",
            "record_kind": "duplicate",
            "campaign_category": "duplicate",
            "classification_confidence": 1.0,
            "is_current": 0,
            "duplicate_of_source_url": (
                "https://example.com/canonical"
            ),
            "reason": "Mükerrer.",
        },
        {
            "bank_name": "Kuveyt Türk",
            "source_url": "https://example.com/togg",
            "title": "TOGG Finansman Kampanyası",
            "record_kind": "campaign",
            "campaign_category": "finance_campaign",
            "classification_confidence": 1.0,
            "reason": "Başlık düzeltildi.",
        },
    ]

    applied, warnings = apply_overrides(
        connection,
        overrides,
    )

    assert applied == 3
    assert warnings == []

    duplicate = connection.execute(
        """
        SELECT *
        FROM live_campaigns
        WHERE source_url = 'https://example.com/duplicate'
        """
    ).fetchone()
    assert duplicate["record_kind"] == "duplicate"
    assert duplicate["campaign_category"] == "duplicate"
    assert duplicate["is_current"] == 0

    togg = connection.execute(
        """
        SELECT *
        FROM live_campaigns
        WHERE source_url = 'https://example.com/togg'
        """
    ).fetchone()
    assert togg["title"] == "TOGG Finansman Kampanyası"

    log_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM campaign_classification_override_log
        """
    ).fetchone()[0]
    assert log_count == 3
