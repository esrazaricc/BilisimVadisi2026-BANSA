from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.processing.campaign_classifier import (
    classify_campaign_record,
)


def ensure_columns(connection: sqlite3.Connection) -> None:
    existing = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(live_campaigns)"
        ).fetchall()
    }

    columns = {
        "record_kind": "TEXT DEFAULT 'unclassified'",
        "campaign_category": "TEXT",
        "comparison_eligible": "INTEGER DEFAULT 0",
        "classification_confidence": "REAL",
        "classification_reason": "TEXT",
    }

    for name, definition in columns.items():
        if name not in existing:
            connection.execute(
                f"ALTER TABLE live_campaigns "
                f"ADD COLUMN {name} {definition}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", default="Albaraka Türk")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data") / "campaigns.db",
    )
    parser.add_argument(
        "--only-unclassified-current",
        action="store_true",
        help=(
            "Yalnızca güncel olup record_kind/campaign_category alanı "
            "boş veya unclassified olan kayıtları sınıflandırır. "
            "Eski doğrulanmış kayıtları değiştirmez."
        ),
    )
    args = parser.parse_args()

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row

    try:
        ensure_columns(connection)

        if args.only_unclassified_current:
            rows = connection.execute(
                """
                SELECT *
                FROM live_campaigns
                WHERE bank_name = ?
                  AND is_current = 1
                  AND (
                        record_kind IS NULL
                        OR record_kind = ''
                        OR record_kind = 'unclassified'
                        OR campaign_category IS NULL
                        OR campaign_category = ''
                        OR campaign_category = 'unclassified'
                  )
                ORDER BY id
                """,
                (args.bank,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT *
                FROM live_campaigns
                WHERE bank_name = ?
                ORDER BY id
                """,
                (args.bank,),
            ).fetchall()

        kind_counts = Counter()
        category_counts = Counter()

        with connection:
            for row in rows:
                result = classify_campaign_record(
                    title=row["title"] or "",
                    clean_text=row["clean_text"] or "",
                    source_group=row["source_group"] or "",
                )

                current_status = row["current_status"] or "unknown"
                new_status = current_status

                if (
                    result.record_kind == "campaign"
                    and current_status == "unknown"
                    and int(row["is_current"]) == 1
                ):
                    new_status = "active"

                connection.execute(
                    """
                    UPDATE live_campaigns
                    SET
                        record_kind = ?,
                        campaign_category = ?,
                        comparison_eligible = ?,
                        classification_confidence = ?,
                        classification_reason = ?,
                        current_status = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        result.record_kind,
                        result.campaign_category,
                        int(result.comparison_eligible),
                        result.confidence,
                        result.reason,
                        new_status,
                        row["id"],
                    ),
                )

                kind_counts[result.record_kind] += 1
                category_counts[result.campaign_category] += 1

        print("Kampanya sınıflandırması tamamlandı.")
        print(f"Banka: {args.bank}")
        if args.only_unclassified_current:
            print("Mod: yalnızca güncel unclassified kayıtlar")
        else:
            print("Mod: tüm banka kayıtları")
        print(f"İşlenen kayıt: {len(rows)}")

        print("\nKayıt türleri:")
        for key, value in sorted(kind_counts.items()):
            print(f"  - {key}: {value}")

        print("\nKampanya kategorileri:")
        for key, value in sorted(category_counts.items()):
            print(f"  - {key}: {value}")

        review_rows = connection.execute(
            """
            SELECT
                title,
                source_url,
                record_kind,
                campaign_category,
                classification_confidence,
                classification_reason,
                current_status
            FROM live_campaigns
            WHERE bank_name = ?
              AND record_kind != 'campaign'
            ORDER BY title
            """,
            (args.bank,),
        ).fetchall()

        print("\nKampanya dışı / kontrol gereken kayıt:", len(review_rows))
        for row in review_rows:
            print("\nBaşlık:", row["title"])
            print("URL:", row["source_url"])
            print("Tür:", row["record_kind"])
            print("Kategori:", row["campaign_category"])
            print("Güven:", row["classification_confidence"])
            print("Durum:", row["current_status"])
            print("Neden:", row["classification_reason"])

        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())