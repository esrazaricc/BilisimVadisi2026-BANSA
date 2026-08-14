import sqlite3

from src import db as db_module


def test_expected_tables_exist(tmp_path, monkeypatch):
    """Şema testini gerçek proje veritabanına dokunmadan çalıştırır."""
    test_db = tmp_path / "test_campaigns.db"
    monkeypatch.setattr(db_module, "DB_PATH", test_db)

    db_module.init_db(reset=True)

    expected = {
        "banks",
        "source_pages",
        "campaigns",
        "campaign_finance_details",
        "campaign_benefits",
        "campaign_audiences",
        "crawl_logs",
    }

    with sqlite3.connect(test_db) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    table_names = {row[0] for row in rows}
    assert expected.issubset(table_names)
