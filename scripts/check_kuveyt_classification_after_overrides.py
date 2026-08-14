from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from pathlib import Path


def label(value) -> str:
    return str(value or "unclassified")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", default="Kuveyt Türk")
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
            id,
            title,
            source_url,
            record_kind,
            campaign_category,
            is_current
        FROM live_campaigns
        WHERE bank_name = ?
        ORDER BY id
        """,
        (args.bank,),
    ).fetchall()

    connection.close()

    kinds = Counter(label(row["record_kind"]) for row in rows)
    categories = Counter(
        label(row["campaign_category"]) for row in rows
    )

    current_rows = [
        row for row in rows
        if int(row["is_current"] or 0) == 1
    ]
    current_campaigns = [
        row for row in current_rows
        if label(row["record_kind"]) == "campaign"
    ]
    current_unclassified = [
        row for row in current_rows
        if (
            label(row["record_kind"]) == "unclassified"
            or label(row["campaign_category"]) == "unclassified"
        )
    ]
    current_noncampaign = [
        row for row in current_rows
        if label(row["record_kind"]) != "campaign"
    ]

    duplicate_rows = [
        row for row in rows
        if label(row["record_kind"]) == "duplicate"
    ]
    current_duplicates = [
        row for row in duplicate_rows
        if int(row["is_current"] or 0) == 1
    ]

    print("Toplam kayıt:", len(rows))
    print("Kayıt türleri:", dict(sorted(kinds.items())))
    print("Kategoriler:", dict(sorted(categories.items())))
    print("Güncel kayıt:", len(current_rows))
    print("Güncel campaign:", len(current_campaigns))
    print("Güncel unclassified:", len(current_unclassified))
    print("Güncel campaign-dışı:", len(current_noncampaign))
    print("Duplicate kayıt:", len(duplicate_rows))
    print("Güncel duplicate:", len(current_duplicates))

    if current_unclassified:
        print("\nGÜNCEL UNCLASSIFIED KAYITLAR:")
        for row in current_unclassified:
            print("-", row["title"])
            print(" ", row["source_url"])

    errors: list[str] = []

    if not rows:
        errors.append("Kuveyt Türk için DB kaydı yok.")

    if current_unclassified:
        errors.append(
            f"Güncel unclassified kayıt kaldı: {len(current_unclassified)}"
        )

    if current_noncampaign:
        errors.append(
            f"Güncel campaign-dışı kayıt var: {len(current_noncampaign)}"
        )

    # Kuveyt Türk'te doğrulanmış tek tarihsel duplicate kaydı korunur.
    # Yeni duplicate oluşursa manuel inceleme gerektirir.
    if len(duplicate_rows) != 1:
        errors.append(
            f"Beklenen 1 duplicate yerine {len(duplicate_rows)} bulundu."
        )

    if current_duplicates:
        errors.append("Duplicate kayıt güncel olarak işaretlenmiş.")

    if len(current_rows) != len(current_campaigns):
        errors.append(
            "Güncel kayıt sayısı ile güncel campaign sayısı eşleşmiyor."
        )

    print()
    if errors:
        print("Kuveyt Türk sınıflandırması kontrol edilmeli.")
        for error in errors:
            print("  -", error)
        return 1

    print("Kuveyt Türk dinamik sınıflandırma kontrolü doğru.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
