from __future__ import annotations

import argparse
import sqlite3
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

    finance_rows = connection.execute(
        """
        SELECT
            campaign.title,
            finance.*
        FROM live_campaigns AS campaign
        JOIN live_campaign_finance_details AS finance
          ON finance.campaign_id = campaign.id
        WHERE campaign.bank_name = ?
          AND campaign.record_kind = 'campaign'
          AND campaign.campaign_category = 'finance_campaign'
          AND campaign.is_current = 1
        ORDER BY campaign.title
        """,
        (args.bank,),
    ).fetchall()

    audience_rows = connection.execute(
        """
        SELECT
            campaign.title,
            GROUP_CONCAT(
                audience.audience_type,
                ','
            ) AS audience_types
        FROM live_campaigns AS campaign
        LEFT JOIN live_campaign_audiences AS audience
          ON audience.campaign_id = campaign.id
        WHERE campaign.bank_name = ?
          AND campaign.title IN (
              'Akademisyenlere Özel Avantaj Paketi',
              'Esnaf, Çiftçi ve Tüzel Şirketlere Özel 16.000 TL Değerinde Finansal Ürün Paketi Hediye!'
          )
        GROUP BY campaign.id, campaign.title
        """,
        (args.bank,),
    ).fetchall()

    connection.close()

    errors: list[str] = []

    print("Finansman kampanyası:", len(finance_rows))
    if len(finance_rows) != 9:
        errors.append(
            f"Finansman kampanyası 9 yerine {len(finance_rows)}."
        )

    def find(part: str):
        return next(
            (
                row
                for row in finance_rows
                if part in row["title"]
            ),
            None,
        )

    hepsi = find("Hepsiburada")
    if not hepsi or (
        hepsi["financing_amount_max"] != 50000
        or hepsi["profit_share_rate_text"] != "%0"
        or hepsi["installment_count"] != 9
    ):
        errors.append("Hepsiburada finansman alanları yanlış.")

    ihtiyac = find("İhtiyaç Kart")
    if not ihtiyac or (
        ihtiyac["financing_amount_max"] != 100000
        or ihtiyac["profit_share_rate_text"] != "%1,99"
        or ihtiyac["grace_period_months"] != 2
        or ihtiyac["installment_count"] != 12
    ):
        errors.append("İhtiyaç Kart finansman alanları yanlış.")

    for row in audience_rows:
        types = set(
            (row["audience_types"] or "").split(",")
        )
        print(
            row["title"],
            "->",
            ", ".join(sorted(types)),
        )
        if "new_customer" not in types:
            errors.append(
                f"Yeni müşteri hedef kitlesi eksik: {row['title']}"
            )

    print()
    if errors:
        print("Kontrol hataları:")
        for error in errors:
            print("  -", error)
        return 1

    print("Kuveyt Türk üçüncü düzeltme kontrolleri doğru.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
