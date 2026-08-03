from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from pathlib import Path


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
            record_kind,
            campaign_category,
            is_current
        FROM live_campaigns
        WHERE bank_name = ?
        """,
        (args.bank,),
    ).fetchall()
    connection.close()

    kinds = Counter(row["record_kind"] for row in rows)
    categories = Counter(
        row["campaign_category"] for row in rows
    )
    current_count = sum(
        int(row["is_current"] or 0)
        for row in rows
    )

    print("Toplam kayıt:", len(rows))
    print("Kayıt türleri:", dict(sorted(kinds.items())))
    print("Kategoriler:", dict(sorted(categories.items())))
    print("Güncel kayıt:", current_count)

    expected = (
        len(rows) == 111
        and kinds["campaign"] == 110
        and kinds["duplicate"] == 1
        and categories["card_campaign"] == 61
        and categories["discount_campaign"] == 30
        and categories["duplicate"] == 1
        and categories["finance_campaign"] == 9
        and categories["new_customer_campaign"] == 6
        and categories["other_campaign"] == 2
        and categories["points_campaign"] == 2
        and current_count == 110
    )

    print()
    if expected:
        print("Kuveyt Türk sınıflandırması doğru.")
        return 0

    print("Kuveyt Türk sınıflandırması kontrol edilmeli.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())