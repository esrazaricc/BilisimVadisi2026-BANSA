from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("data") / "campaigns.db"
DEFAULT_CONFIG = (
    Path("config") / "campaign_classification_overrides.json"
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


def load_overrides(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("Override dosyası liste olmalıdır.")
    return value


def table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    return {
        row[1]
        for row in connection.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }


def make_backup(db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = (
        backup_dir
        / f"{db_path.stem}_before_classification_overrides_{stamp}.db"
    )
    shutil.copy2(db_path, backup_path)
    return backup_path


def ensure_log_table(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS
        campaign_classification_override_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            applied_at TEXT NOT NULL,
            bank_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            reason TEXT NOT NULL
        )
        """
    )


def fetch_row(
    connection: sqlite3.Connection,
    *,
    bank_name: str,
    source_url: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM live_campaigns
        WHERE bank_name = ?
          AND source_url = ?
        LIMIT 1
        """,
        (bank_name, source_url),
    ).fetchone()


def apply_overrides(
    connection: sqlite3.Connection,
    overrides: list[dict[str, Any]],
) -> tuple[int, list[str]]:
    columns = table_columns(
        connection,
        "live_campaigns",
    )
    required = {
        "bank_name",
        "source_url",
        "title",
        "record_kind",
        "campaign_category",
        "classification_confidence",
        "classification_reason",
    }
    missing = required - columns
    if missing:
        raise RuntimeError(
            "Eksik live_campaigns sütunları: "
            + ", ".join(sorted(missing))
        )

    ensure_log_table(connection)

    applied = 0
    warnings: list[str] = []

    for override in overrides:
        bank_name = str(override["bank_name"])
        source_url = str(override["source_url"])

        before = fetch_row(
            connection,
            bank_name=bank_name,
            source_url=source_url,
        )
        if before is None:
            warnings.append(
                f"Kayıt bulunamadı: {source_url}"
            )
            continue

        updates: dict[str, Any] = {}

        for field in (
            "title",
            "record_kind",
            "campaign_category",
            "classification_confidence",
            "is_current",
        ):
            if field in override and field in columns:
                updates[field] = override[field]

        reason = str(override.get("reason", "")).strip()
        updates["classification_reason"] = (
            f"MANUEL DOĞRULAMA: {reason}"
        )

        duplicate_source = override.get(
            "duplicate_of_source_url"
        )
        if duplicate_source:
            canonical = fetch_row(
                connection,
                bank_name=bank_name,
                source_url=str(duplicate_source),
            )
            if canonical is None:
                raise RuntimeError(
                    "Ana mükerrer kayıt bulunamadı: "
                    f"{duplicate_source}"
                )

            if "duplicate_of_id" in columns:
                updates["duplicate_of_id"] = canonical["id"]

            updates["classification_reason"] += (
                f" Ana kayıt ID: {canonical['id']}."
            )

        assignments = ", ".join(
            f"{field} = ?"
            for field in updates
        )
        parameters = list(updates.values()) + [
            bank_name,
            source_url,
        ]

        connection.execute(
            f"""
            UPDATE live_campaigns
            SET {assignments}
            WHERE bank_name = ?
              AND source_url = ?
            """,
            parameters,
        )

        after = fetch_row(
            connection,
            bank_name=bank_name,
            source_url=source_url,
        )

        before_dict = dict(before)
        after_dict = dict(after)

        changed = any(
            before_dict.get(field) != after_dict.get(field)
            for field in updates
        )
        if not changed:
            continue

        connection.execute(
            """
            INSERT INTO campaign_classification_override_log (
                applied_at,
                bank_name,
                source_url,
                before_json,
                after_json,
                reason
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now_iso(),
                bank_name,
                source_url,
                json.dumps(
                    before_dict,
                    ensure_ascii=False,
                    default=str,
                ),
                json.dumps(
                    after_dict,
                    ensure_ascii=False,
                    default=str,
                ),
                reason,
            ),
        )
        applied += 1

    return applied, warnings


def print_summary(
    connection: sqlite3.Connection,
    bank_name: str,
) -> None:
    rows = connection.execute(
        """
        SELECT
            record_kind,
            campaign_category,
            is_current
        FROM live_campaigns
        WHERE bank_name = ?
        """,
        (bank_name,),
    ).fetchall()

    kind_counts = Counter(
        row["record_kind"] for row in rows
    )
    category_counts = Counter(
        row["campaign_category"] for row in rows
    )
    current_count = sum(
        int(row["is_current"] or 0)
        for row in rows
    )

    print("\nKayıt türleri:")
    for key, value in sorted(kind_counts.items()):
        print(f"  - {key}: {value}")

    print("\nKategoriler:")
    for key, value in sorted(category_counts.items()):
        print(f"  - {key}: {value}")

    print("\nGüncel kayıt:", current_count)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Doğrulanmış kampanya sınıflandırma düzeltmelerini "
            "yedek alarak ve işlem günlüğü oluşturarak uygular."
        )
    )
    parser.add_argument(
        "--bank",
        default="Kuveyt Türk",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(
            f"Veritabanı bulunamadı: {args.db}"
        )
    if not args.config.exists():
        raise SystemExit(
            f"Override dosyası bulunamadı: {args.config}"
        )

    all_overrides = load_overrides(args.config)
    overrides = [
        item
        for item in all_overrides
        if item.get("bank_name") == args.bank
    ]

    backup_path = make_backup(args.db)

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("BEGIN")
        applied, warnings = apply_overrides(
            connection,
            overrides,
        )
        connection.commit()

        print("Sınıflandırma düzeltmeleri uygulandı.")
        print("Banka:", args.bank)
        print("Override kaydı:", len(overrides))
        print("Değiştirilen kayıt:", applied)
        print("Yedek:", backup_path)

        if warnings:
            print("\nUyarılar:")
            for warning in warnings:
                print("  -", warning)

        print_summary(connection, args.bank)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
