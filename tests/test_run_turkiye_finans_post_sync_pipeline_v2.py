from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.run_turkiye_finans_post_sync_pipeline import (
    build_steps,
    other_banks_fingerprint,
    sqlite_backup,
    sqlite_restore,
)


def create_basic_db(path: Path) -> None:
    connection = sqlite3.connect(path)

    try:
        connection.executescript(
            """
            CREATE TABLE live_campaigns (
                id INTEGER PRIMARY KEY,
                bank_name TEXT NOT NULL,
                title TEXT,
                source_url TEXT,
                record_kind TEXT,
                campaign_category TEXT
            );

            CREATE TABLE live_campaign_finance_details (
                campaign_id INTEGER NOT NULL,
                finance_type TEXT
            );

            CREATE TABLE live_campaign_benefits (
                id INTEGER PRIMARY KEY,
                campaign_id INTEGER NOT NULL,
                benefit_type TEXT
            );

            CREATE TABLE live_campaign_audiences (
                campaign_id INTEGER NOT NULL,
                audience_type TEXT,
                audience_label TEXT
            );
            """
        )

        connection.executemany(
            """
            INSERT INTO live_campaigns (
                id,
                bank_name,
                title,
                source_url,
                record_kind,
                campaign_category
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    1,
                    "Türkiye Finans",
                    "TF Kampanya",
                    "https://example.com/tf",
                    "campaign",
                    "card_campaign",
                ),
                (
                    2,
                    "Albaraka Türk",
                    "Albaraka Kampanya",
                    "https://example.com/albaraka",
                    "campaign",
                    "discount_campaign",
                ),
            ),
        )

        connection.execute(
            """
            INSERT INTO live_campaign_finance_details (
                campaign_id,
                finance_type
            )
            VALUES (2, 'İhtiyaç Finansmanı')
            """
        )
        connection.execute(
            """
            INSERT INTO live_campaign_benefits (
                id,
                campaign_id,
                benefit_type
            )
            VALUES (1, 2, 'discount')
            """
        )
        connection.execute(
            """
            INSERT INTO live_campaign_audiences (
                campaign_id,
                audience_type,
                audience_label
            )
            VALUES (2, 'individual_customer', 'Bireysel Müşteriler')
            """
        )
        connection.commit()

    finally:
        connection.close()


def test_pipeline_step_order(tmp_path):
    report = tmp_path / "report.json"
    steps = build_steps(
        bank="Türkiye Finans",
        report_path=report,
    )

    assert [step.script for step in steps] == [
        "classify_campaign_records.py",
        "apply_campaign_classification_overrides.py",
        "extract_comparison_fields.py",
    ]


def test_every_step_is_limited_to_turkiye_finans(tmp_path):
    steps = build_steps(
        bank="Türkiye Finans",
        report_path=tmp_path / "report.json",
    )

    for step in steps:
        assert "--bank" in step.args
        bank_index = step.args.index("--bank") + 1
        assert step.args[bank_index] == "Türkiye Finans"


def test_sqlite_backup_and_restore(tmp_path):
    source = tmp_path / "campaigns.db"
    backup = tmp_path / "backup.db"
    create_basic_db(source)

    sqlite_backup(source, backup)

    connection = sqlite3.connect(source)
    try:
        connection.execute(
            """
            UPDATE live_campaigns
            SET title = 'Bozulmuş'
            WHERE id = 1
            """
        )
        connection.commit()
    finally:
        connection.close()

    sqlite_restore(backup, source)

    connection = sqlite3.connect(source)
    try:
        title = connection.execute(
            """
            SELECT title
            FROM live_campaigns
            WHERE id = 1
            """
        ).fetchone()[0]
    finally:
        connection.close()

    assert title == "TF Kampanya"


def test_fingerprint_supports_tables_without_id(tmp_path):
    db_path = tmp_path / "campaigns.db"
    create_basic_db(db_path)

    fingerprints = other_banks_fingerprint(
        db_path,
        "Türkiye Finans",
    )

    assert fingerprints["live_campaign_finance_details"]
    assert fingerprints["live_campaign_benefits"]
    assert fingerprints["live_campaign_audiences"]


def test_other_bank_fingerprint_ignores_target_changes(
    tmp_path,
):
    db_path = tmp_path / "campaigns.db"
    create_basic_db(db_path)

    before = other_banks_fingerprint(
        db_path,
        "Türkiye Finans",
    )

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            UPDATE live_campaigns
            SET title = 'TF Değişti'
            WHERE bank_name = 'Türkiye Finans'
            """
        )
        connection.commit()
    finally:
        connection.close()

    after = other_banks_fingerprint(
        db_path,
        "Türkiye Finans",
    )

    assert before == after


def test_other_bank_fingerprint_detects_foreign_change(
    tmp_path,
):
    db_path = tmp_path / "campaigns.db"
    create_basic_db(db_path)

    before = other_banks_fingerprint(
        db_path,
        "Türkiye Finans",
    )

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            UPDATE live_campaigns
            SET title = 'Albaraka Değişti'
            WHERE bank_name = 'Albaraka Türk'
            """
        )
        connection.commit()
    finally:
        connection.close()

    after = other_banks_fingerprint(
        db_path,
        "Türkiye Finans",
    )

    assert before != after
