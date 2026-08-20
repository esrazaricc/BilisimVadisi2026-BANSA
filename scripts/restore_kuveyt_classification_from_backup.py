from __future__ import annotations

import argparse
import shutil
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path


EXPECTED_CATEGORIES = {
    "card_campaign": 62,
    "discount_campaign": 30,
    "duplicate": 1,
    "finance_campaign": 8,
    "new_customer_campaign": 7,
    "other_campaign": 1,
    "points_campaign": 2,
}

EXPECTED_KINDS = {
    "campaign": 110,
    "duplicate": 1,
}


def table_columns(
    connection: sqlite3.Connection,
    schema: str,
    table: str,
) -> set[str]:
    return {
        row[1]
        for row in connection.execute(
            f"PRAGMA {schema}.table_info({table})"
        ).fetchall()
    }


def counts_for_database(
    database: Path,
    bank: str,
) -> tuple[Counter, Counter, int]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT
                record_kind,
                campaign_category,
                is_current
            FROM live_campaigns
            WHERE bank_name = ?
            """,
            (bank,),
        ).fetchall()
    finally:
        connection.close()

    kinds = Counter(row["record_kind"] for row in rows)
    categories = Counter(
        row["campaign_category"]
        for row in rows
    )
    current_count = sum(
        int(row["is_current"] or 0)
        for row in rows
    )
    return kinds, categories, current_count


def is_known_good_snapshot(
    database: Path,
    bank: str,
) -> bool:
    try:
        kinds, categories, current_count = (
            counts_for_database(database, bank)
        )
    except sqlite3.Error:
        return False

    return (
        dict(kinds) == EXPECTED_KINDS
        and all(
            categories[key] == value
            for key, value in EXPECTED_CATEGORIES.items()
        )
        and sum(categories.values()) == 111
        and current_count == 110
    )


def find_backup(
    backup_dir: Path,
    bank: str,
) -> Path | None:
    preferred = (
        backup_dir
        / "campaigns_before_classification_overrides_20260731_144220.db"
    )
    if preferred.exists() and is_known_good_snapshot(
        preferred,
        bank,
    ):
        return preferred

    candidates = sorted(
        backup_dir.glob("*.db"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        if is_known_good_snapshot(candidate, bank):
            return candidate

    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Kuveyt Türk sınıflandırma alanlarını bilinen doğru "
            "veritabanı yedeğinden geri yükler."
        )
    )
    parser.add_argument(
        "--bank",
        default="Kuveyt Türk",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data") / "campaigns.db",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=Path("data") / "backups",
    )
    parser.add_argument(
        "--source-backup",
        type=Path,
        default=None,
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(
            f"Ana veritabanı bulunamadı: {args.db}"
        )

    source = args.source_backup
    if source is None:
        source = find_backup(
            args.backup_dir,
            args.bank,
        )

    if source is None or not source.exists():
        raise SystemExit(
            "Beklenen dağılıma sahip doğru sınıflandırma "
            "yedeği bulunamadı."
        )

    if not is_known_good_snapshot(source, args.bank):
        raise SystemExit(
            f"Seçilen yedek doğrulanamadı: {source}"
        )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    safety_backup = (
        args.backup_dir
        / f"campaigns_before_classification_recovery_{timestamp}.db"
    )
    args.backup_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(args.db, safety_backup)

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row

    try:
        connection.execute(
            "ATTACH DATABASE ? AS recovery_db",
            (str(source),),
        )

        main_columns = table_columns(
            connection,
            "main",
            "live_campaigns",
        )
        backup_columns = table_columns(
            connection,
            "recovery_db",
            "live_campaigns",
        )

        candidate_fields = (
            "record_kind",
            "campaign_category",
            "comparison_eligible",
            "classification_confidence",
            "classification_reason",
            "is_current",
        )
        fields = [
            field
            for field in candidate_fields
            if field in main_columns
            and field in backup_columns
        ]

        if not fields:
            raise RuntimeError(
                "Geri yüklenecek ortak sınıflandırma alanı yok."
            )

        assignments = ",\n".join(
            (
                f"{field} = ("
                f"SELECT source.{field} "
                f"FROM recovery_db.live_campaigns AS source "
                f"WHERE source.bank_name = live_campaigns.bank_name "
                f"AND source.source_url = live_campaigns.source_url"
                f")"
            )
            for field in fields
        )

        with connection:
            cursor = connection.execute(
                f"""
                UPDATE live_campaigns
                SET
                    {assignments},
                    updated_at = CURRENT_TIMESTAMP
                WHERE bank_name = ?
                  AND EXISTS (
                      SELECT 1
                      FROM recovery_db.live_campaigns AS source
                      WHERE
                          source.bank_name = live_campaigns.bank_name
                          AND source.source_url = live_campaigns.source_url
                  )
                """,
                (args.bank,),
            )

        connection.execute(
            "DETACH DATABASE recovery_db"
        )
    finally:
        connection.close()

    kinds, categories, current_count = (
        counts_for_database(args.db, args.bank)
    )

    print("Sınıflandırma geri yüklendi.")
    print("Banka:", args.bank)
    print("Kaynak yedek:", source)
    print("Güvenlik yedeği:", safety_backup)
    print("Güncellenen kayıt:", cursor.rowcount)

    print("\nKayıt türleri:")
    for key, value in sorted(kinds.items()):
        print(f"  - {key}: {value}")

    print("\nKategoriler:")
    for key, value in sorted(categories.items()):
        print(f"  - {key}: {value}")

    print("\nGüncel kayıt:", current_count)

    if (
        dict(kinds) != EXPECTED_KINDS
        or any(
            categories[key] != value
            for key, value in EXPECTED_CATEGORIES.items()
        )
        or current_count != 110
    ):
        print(
            "\nGeri yükleme tamamlandı ancak dağılım "
            "beklenen değerlerle eşleşmedi."
        )
        return 1

    print(
        "\nBilinen doğru sınıflandırma tabanı geri yüklendi."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
