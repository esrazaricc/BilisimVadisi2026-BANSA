from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_ziraat_katilim_post_sync_pipeline.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "ziraat_pipeline",
        MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_other_banks_digest_ignores_ziraat_changes(
    tmp_path,
):
    module = load_module()
    db_path = tmp_path / "test.db"

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE live_campaigns (
            id INTEGER PRIMARY KEY,
            bank_name TEXT NOT NULL,
            title TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE live_campaign_benefits (
            id INTEGER PRIMARY KEY,
            campaign_id INTEGER NOT NULL,
            description TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE live_campaign_audiences (
            id INTEGER PRIMARY KEY,
            campaign_id INTEGER NOT NULL,
            audience_label TEXT
        )
        """
    )

    conn.executemany(
        """
        INSERT INTO live_campaigns (
            id,
            bank_name,
            title
        )
        VALUES (?, ?, ?)
        """,
        [
            (1, "Ziraat Katılım", "Ziraat kampanyası"),
            (2, "Kuveyt Türk", "Kuveyt kampanyası"),
        ],
    )
    conn.execute(
        """
        INSERT INTO live_campaign_benefits
        VALUES (1, 1, 'Ziraat avantajı')
        """
    )
    conn.execute(
        """
        INSERT INTO live_campaign_benefits
        VALUES (2, 2, 'Kuveyt avantajı')
        """
    )
    conn.commit()

    before = module.other_banks_digest(conn)

    conn.execute(
        """
        UPDATE live_campaigns
        SET title = 'Değişen Ziraat kampanyası'
        WHERE id = 1
        """
    )
    conn.commit()

    after_ziraat_change = module.other_banks_digest(
        conn
    )
    assert before == after_ziraat_change

    conn.execute(
        """
        UPDATE live_campaigns
        SET title = 'Değişen Kuveyt kampanyası'
        WHERE id = 2
        """
    )
    conn.commit()

    after_other_change = module.other_banks_digest(
        conn
    )
    assert before != after_other_change

    conn.close()


def test_required_override_urls_are_unique():
    module = load_module()

    assert len(
        module.REQUIRED_ZIRAAT_OVERRIDE_URLS
    ) == 8


def test_expected_distribution_total_is_72():
    module = load_module()

    assert sum(
        module.EXPECTED_DISTRIBUTION.values()
    ) == module.EXPECTED_CURRENT
