from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


LABELS = {
    "new_product": "Yeni Ürün",
    "terms_changed": "Koşullar Güncellendi",
    "content_changed": "İçerik Güncellendi",
    "reactivated": "Yeniden Göründü",
    "possible_removed": "Kaynakta Görünmüyor",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data") / "campaigns.db",
    )
    args = parser.parse_args()

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row

    rows = connection.execute(
        """
        SELECT
            bank_name,
            product_family,
            product_name,
            change_type,
            changed_fields_json,
            detected_at
        FROM live_standard_product_changes
        ORDER BY detected_at DESC, id DESC
        LIMIT 50
        """
    ).fetchall()

    print("=" * 80)
    print("STANDART ÜRÜN DEĞİŞİKLİK DENETİMİ")
    print("=" * 80)
    print("Son değişiklik:", len(rows))
    print()

    for row in rows:
        print(
            row["detected_at"],
            "|",
            LABELS.get(
                row["change_type"],
                row["change_type"],
            ),
        )
        print(
            " ",
            row["bank_name"],
            "|",
            row["product_family"],
            "|",
            row["product_name"],
        )
        if row["changed_fields_json"]:
            print(
                "  Değişen alanlar:",
                row["changed_fields_json"],
            )

    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
