from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "campaigns.db"
CONFIG_PATH = (
    ROOT / "config" / "campaign_classification_overrides.json"
)
BACKUP_DIR = ROOT / "data" / "backups"

BANK = "Ziraat Katılım"
EXPECTED_OVERRIDE_COUNT = 8

EXPECTED_DISTRIBUTION = {
    "card_campaign": 56,
    "discount_campaign": 10,
    "points_campaign": 5,
    "new_customer_campaign": 1,
}


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def get_columns(
    conn: sqlite3.Connection,
    table: str,
) -> set[str]:
    return {
        row[1]
        for row in conn.execute(
            f"PRAGMA table_info({quote(table)})"
        )
    }


def pick(
    columns: set[str],
    *candidates: str,
) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate

    return None


def other_banks_digest(
    conn: sqlite3.Connection,
    bank_col: str,
) -> str:
    rows = conn.execute(
        f"""
        SELECT *
        FROM live_campaigns
        WHERE {quote(bank_col)} <> ?
        ORDER BY rowid
        """,
        (BANK,),
    ).fetchall()

    payload = json.dumps(
        [tuple(row) for row in rows],
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def main() -> int:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Veritabanı bulunamadı: {DB_PATH}"
        )

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Override dosyası bulunamadı: {CONFIG_PATH}"
        )

    config = json.loads(
        CONFIG_PATH.read_text(encoding="utf-8")
    )

    if not isinstance(config, list):
        raise RuntimeError(
            "Override dosyasının ana yapısı liste olmalıdır."
        )

    overrides = [
        item
        for item in config
        if isinstance(item, dict)
        and item.get("bank_name") == BANK
    ]

    if len(overrides) != EXPECTED_OVERRIDE_COUNT:
        raise RuntimeError(
            "Ziraat Katılım override sayısı beklenenden farklı: "
            f"{len(overrides)}"
        )

    urls = [
        item.get("source_url")
        for item in overrides
    ]

    if any(not isinstance(url, str) or not url for url in urls):
        raise RuntimeError(
            "Override kayıtlarından en az birinde source_url eksik."
        )

    if len(set(urls)) != len(urls):
        raise RuntimeError(
            "Ziraat Katılım override kayıtlarında tekrarlı URL var."
        )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        columns = get_columns(
            conn,
            "live_campaigns",
        )

        bank_col = pick(
            columns,
            "bank_name",
            "bank",
        )
        url_col = pick(
            columns,
            "source_url",
            "url",
            "page_url",
        )
        category_col = pick(
            columns,
            "campaign_category",
            "category",
            "classification",
        )
        kind_col = pick(
            columns,
            "record_kind",
            "record_type",
            "content_type",
        )
        confidence_col = pick(
            columns,
            "classification_confidence",
            "confidence",
        )
        current_col = pick(
            columns,
            "is_current",
        )
        title_col = pick(
            columns,
            "title",
            "campaign_title",
            "name",
        )

        required = {
            "banka": bank_col,
            "URL": url_col,
            "kategori": category_col,
        }

        missing = [
            label
            for label, column in required.items()
            if column is None
        ]

        if missing:
            raise RuntimeError(
                "Gerekli sütunlar bulunamadı: "
                + ", ".join(missing)
            )

        before_other_digest = other_banks_digest(
            conn,
            bank_col,
        )

        placeholders = ",".join(
            "?"
            for _ in urls
        )

        current_condition = (
            f"AND {quote(current_col)} = 1"
            if current_col
            else ""
        )

        found_rows = conn.execute(
            f"""
            SELECT
                {quote(url_col)} AS source_url,
                {quote(title_col)} AS title,
                {quote(category_col)} AS campaign_category
            FROM live_campaigns
            WHERE {quote(bank_col)} = ?
              AND {quote(url_col)} IN ({placeholders})
              {current_condition}
            """,
            [BANK, *urls],
        ).fetchall()

        found_urls = {
            row["source_url"]
            for row in found_rows
        }

        missing_urls = set(urls) - found_urls

        if missing_urls:
            raise RuntimeError(
                "Veritabanında bulunamayan override URL'leri:\n- "
                + "\n- ".join(sorted(missing_urls))
            )

        BACKUP_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )
        stamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        backup_path = (
            BACKUP_DIR
            / f"campaigns_before_ziraat_classification_overrides_{stamp}.db"
        )
        shutil.copy2(
            DB_PATH,
            backup_path,
        )

        conn.execute("BEGIN IMMEDIATE")

        changed = 0

        for override in overrides:
            assignments = [
                f"{quote(category_col)} = ?",
            ]
            values = [
                override["campaign_category"],
            ]

            if kind_col:
                assignments.append(
                    f"{quote(kind_col)} = ?"
                )
                values.append(
                    override.get(
                        "record_kind",
                        "campaign",
                    )
                )

            if confidence_col:
                assignments.append(
                    f"{quote(confidence_col)} = ?"
                )
                values.append(
                    float(
                        override.get(
                            "classification_confidence",
                            1.0,
                        )
                    )
                )

            values.extend(
                [
                    BANK,
                    override["source_url"],
                ]
            )

            cursor = conn.execute(
                f"""
                UPDATE live_campaigns
                SET {", ".join(assignments)}
                WHERE {quote(bank_col)} = ?
                  AND {quote(url_col)} = ?
                  {current_condition}
                """,
                values,
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Beklenmeyen güncelleme sayısı "
                    f"({cursor.rowcount}) için: "
                    f"{override['source_url']}"
                )

            changed += cursor.rowcount

        rows = conn.execute(
            f"""
            SELECT
                {quote(category_col)} AS category,
                COUNT(*) AS count
            FROM live_campaigns
            WHERE {quote(bank_col)} = ?
              {current_condition}
            GROUP BY {quote(category_col)}
            """,
            (BANK,),
        ).fetchall()

        distribution = {
            row["category"]: row["count"]
            for row in rows
        }

        for category, expected in EXPECTED_DISTRIBUTION.items():
            actual = distribution.get(
                category,
                0,
            )

            if actual != expected:
                raise RuntimeError(
                    f"Kategori doğrulaması başarısız: "
                    f"{category} beklenen={expected}, "
                    f"gerçek={actual}"
                )

        if distribution.get("other_campaign", 0) != 0:
            raise RuntimeError(
                "other_campaign kayıtları tamamen temizlenmedi."
            )

        after_other_digest = other_banks_digest(
            conn,
            bank_col,
        )

        if before_other_digest != after_other_digest:
            raise RuntimeError(
                "Diğer bankaların kayıtları değişti."
            )

        conn.commit()

        print(
            "Ziraat Katılım sınıflandırma override'ları uygulandı."
        )
        print("Override kaydı:", len(overrides))
        print("Güncellenen kayıt:", changed)
        print("Diğer bankalar: değişmedi")
        print("Yedek:", backup_path)
        print()
        print("Kategori dağılımı:")

        for category, count in sorted(
            distribution.items(),
            key=lambda item: (-item[1], item[0]),
        ):
            print(f"- {category}: {count}")

        return 0

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
