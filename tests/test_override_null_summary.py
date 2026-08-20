import sqlite3

from scripts.apply_campaign_classification_overrides import print_summary


def test_print_summary_handles_null_category_and_kind(capsys):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row

    connection.execute(
        """
        CREATE TABLE live_campaigns (
            id INTEGER PRIMARY KEY,
            bank_name TEXT NOT NULL,
            record_kind TEXT,
            campaign_category TEXT,
            is_current INTEGER
        )
        """
    )

    connection.executemany(
        """
        INSERT INTO live_campaigns (
            id,
            bank_name,
            record_kind,
            campaign_category,
            is_current
        ) VALUES (?, 'Kuveyt Türk', ?, ?, ?)
        """,
        [
            (1, "campaign", "finance_campaign", 1),
            (2, "campaign", None, 1),
            (3, None, None, 0),
            (4, "duplicate", "duplicate", 0),
        ],
    )

    print_summary(connection, "Kuveyt Türk")
    output = capsys.readouterr().out

    assert "campaign: 2" in output
    assert "duplicate: 1" in output
    assert "unclassified: 1" in output
    assert "finance_campaign: 1" in output
    assert "duplicate: 1" in output
    assert "unclassified: 2" in output
    assert "Güncel kayıt: 2" in output
