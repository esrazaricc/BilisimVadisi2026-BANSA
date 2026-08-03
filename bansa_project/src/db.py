from __future__ import annotations

import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from src.config import DB_PATH


SCHEMA_VERSION = 2

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_info (
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS banks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    legal_name TEXT,
    slug TEXT NOT NULL UNIQUE,
    official_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    page_title TEXT,
    raw_text TEXT NOT NULL,
    content_hash TEXT,
    page_type TEXT NOT NULL CHECK(
        page_type IN ('campaign', 'standard_product', 'other')
    ),
    is_campaign INTEGER NOT NULL CHECK(is_campaign IN (0, 1)),
    classification_reason TEXT,
    classification_confidence REAL,
    http_status INTEGER,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0, 1)),
    FOREIGN KEY(bank_id) REFERENCES banks(id) ON DELETE CASCADE,
    UNIQUE(bank_id, url)
);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_id INTEGER NOT NULL,
    source_page_id INTEGER NOT NULL UNIQUE,
    campaign_name TEXT NOT NULL,
    campaign_type TEXT NOT NULL,
    product_type TEXT,
    start_date TEXT,
    end_date TEXT,
    campaign_conditions TEXT,
    status TEXT NOT NULL DEFAULT 'unknown' CHECK(
        status IN ('active', 'expired', 'unknown')
    ),
    source_evidence TEXT,
    extraction_confidence REAL,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(bank_id) REFERENCES banks(id) ON DELETE CASCADE,
    FOREIGN KEY(source_page_id) REFERENCES source_pages(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS campaign_finance_details (
    campaign_id INTEGER PRIMARY KEY,
    profit_share_rate REAL,
    financing_amount_min REAL,
    financing_amount_max REAL,
    maturity_min_months INTEGER,
    maturity_max_months INTEGER,
    installment_count INTEGER,
    allocation_fee_amount REAL,
    allocation_fee_rate REAL,
    expense_status TEXT,
    expense_details TEXT,
    currency TEXT NOT NULL DEFAULT 'TRY',
    FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS campaign_benefits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    benefit_type TEXT NOT NULL,
    amount REAL,
    rate REAL,
    points REAL,
    currency TEXT NOT NULL DEFAULT 'TRY',
    maximum_benefit REAL,
    minimum_spending REAL,
    description TEXT,
    evidence TEXT,
    FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS campaign_audiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    audience_type TEXT NOT NULL,
    audience_label TEXT NOT NULL,
    details TEXT,
    FOREIGN KEY(campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
    UNIQUE(campaign_id, audience_type, audience_label)
);

CREATE TABLE IF NOT EXISTS crawl_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_id INTEGER,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    checked_url_count INTEGER NOT NULL DEFAULT 0,
    found_campaign_count INTEGER NOT NULL DEFAULT 0,
    added_campaign_count INTEGER NOT NULL DEFAULT 0,
    updated_campaign_count INTEGER NOT NULL DEFAULT 0,
    skipped_page_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    details TEXT,
    FOREIGN KEY(bank_id) REFERENCES banks(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_source_pages_bank
    ON source_pages(bank_id);
CREATE INDEX IF NOT EXISTS idx_source_pages_type
    ON source_pages(page_type);
CREATE INDEX IF NOT EXISTS idx_campaigns_bank
    ON campaigns(bank_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_type
    ON campaigns(campaign_type);
CREATE INDEX IF NOT EXISTS idx_campaigns_status
    ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaigns_end_date
    ON campaigns(end_date);
CREATE INDEX IF NOT EXISTS idx_benefits_campaign
    ON campaign_benefits(campaign_id);
CREATE INDEX IF NOT EXISTS idx_audiences_campaign
    ON campaign_audiences(campaign_id);
CREATE INDEX IF NOT EXISTS idx_crawl_logs_bank
    ON crawl_logs(bank_id);
"""


def _has_table(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _database_version(
    connection: sqlite3.Connection,
) -> int | None:
    if not _has_table(connection, "schema_info"):
        return None

    row = connection.execute(
        """
        SELECT version
        FROM schema_info
        ORDER BY rowid DESC
        LIMIT 1
        """
    ).fetchone()
    return int(row[0]) if row else None


def _backup_old_database() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.with_name(
        f"{DB_PATH.stem}_backup_{timestamp}{DB_PATH.suffix}"
    )
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def _write_schema_version(
    connection: sqlite3.Connection,
) -> None:
    connection.execute("DELETE FROM schema_info")
    connection.execute(
        "INSERT INTO schema_info (version) VALUES (?)",
        (SCHEMA_VERSION,),
    )


def init_db(reset: bool = False) -> Path | None:
    """
    Veritabanını güvenli biçimde hazırlar.

    Önemli:
    - Normal uygulama açılışında mevcut veritabanı silinmez.
    - ``live_campaigns`` tablosu bulunan yeni/canlı veritabanına
      eski şema uygulanmaz.
    - Silme işlemi yalnızca açıkça ``reset=True`` verilirse yapılır.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None

    if reset and DB_PATH.exists():
        backup_path = _backup_old_database()
        DB_PATH.unlink()

    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH, timeout=30) as connection:
            # Projenin güncel canlı şeması zaten mevcutsa hiçbir
            # tabloyu silme veya eski şemayı ekleme.
            if _has_table(connection, "live_campaigns"):
                return backup_path

            current_version = _database_version(connection)

            if current_version is not None:
                # Şema sürümü farklı olsa bile otomatik silme yok.
                # Mevcut tabloları IF NOT EXISTS ile koruyarak
                # yalnızca eksikleri tamamla.
                connection.executescript(SCHEMA)
                _write_schema_version(connection)
                connection.commit()
                return backup_path

            # İçinde veri tabloları bulunan ama sürüm bilgisi olmayan
            # bir veritabanını da otomatik sıfırlama.
            user_tables = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                      AND name NOT LIKE 'sqlite_%'
                    """
                )
            }
            if user_tables:
                return backup_path

    # Yeni veya açıkça sıfırlanmış veritabanını oluştur.
    with sqlite3.connect(DB_PATH, timeout=30) as connection:
        connection.executescript(SCHEMA)
        _write_schema_version(connection)
        connection.commit()

    return backup_path


@contextmanager
def get_connection():
    """
    Veritabanı bağlantısı açar.

    Mevcut dosya varsa her bağlantıda ``init_db`` çalıştırılmaz;
    böylece açık veritabanını silme girişimi oluşmaz.
    """
    if not DB_PATH.exists():
        init_db(reset=False)

    connection = sqlite3.connect(
        DB_PATH,
        timeout=30,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

