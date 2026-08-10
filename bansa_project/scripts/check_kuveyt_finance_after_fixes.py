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

    rows = connection.execute(
        """
        SELECT campaign.title, finance.*
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

    hgs = connection.execute(
        """
        SELECT
            campaign.campaign_category,
            finance.campaign_id AS finance_row,
            benefit.benefit_type,
            benefit.description
        FROM live_campaigns AS campaign
        LEFT JOIN live_campaign_finance_details AS finance
          ON finance.campaign_id = campaign.id
        LEFT JOIN live_campaign_benefits AS benefit
          ON benefit.campaign_id = campaign.id
         AND benefit.benefit_type = 'free_service'
        WHERE campaign.bank_name = ?
          AND campaign.title LIKE '%HGS Kampanyası%'
        LIMIT 1
        """,
        (args.bank,),
    ).fetchone()

    connection.close()

    print("Finansman kampanyası:", len(rows))
    for row in rows:
        print("\nKampanya:", row["title"])
        print("Tür:", row["finance_type"])
        print(
            "Kâr payı:",
            row["profit_share_rate_text"] or "Belirtilmemiş",
        )
        print(
            "Finansman tutarı:",
            row["financing_amount_text"] or "Belirtilmemiş",
        )
        print(
            "Vade:",
            row["maturity_text"] or "Belirtilmemiş",
        )
        print(
            "Ödemesiz dönem:",
            row["grace_period_months"]
            if row["grace_period_months"] is not None
            else "Belirtilmemiş",
        )
        print(
            "Taksit:",
            row["installment_count"]
            if row["installment_count"] is not None
            else "Belirtilmemiş",
        )
        print("Avantaj:", row["campaign_advantage"])

    errors = []
    if len(rows) != 7:
        errors.append("Finansman kampanyası sayısı 7 değil.")

    def find(part):
        return next(
            (row for row in rows if part in row["title"]),
            None,
        )

    diyanet = find("Diyanet Umre")
    if not diyanet or (
        diyanet["profit_share_rate_text"] != "%0"
        or diyanet["installment_count"] != 3
    ):
        errors.append("Diyanet Umre alanları yanlış.")

    investment = find("Yatırım Finansmanı")
    if not investment or (
        investment["grace_period_months"] != 6
        or investment["maturity_max_months"] != 60
    ):
        errors.append("KFK yatırım alanları yanlış.")

    tourism = find("Turizm Sektörüne")
    if not tourism or (
        tourism["grace_period_months"] != 6
        or tourism["maturity_max_months"] != 12
    ):
        errors.append("KFK turizm alanları yanlış.")

    business = find("Sağlam Business")
    if not business or (
        business["grace_period_months"] != 3
        or business["installment_count"] != 9
    ):
        errors.append("Sağlam Business alanları yanlış.")

    togg = find("TOGG")
    if not togg or (
        togg["financing_amount_min"] != 600000
        or togg["financing_amount_max"] != 1700000
        or togg["grace_period_months"] != 3
    ):
        errors.append("TOGG alanları yanlış.")

    taksitlio = find("Taksitlio")
    if not taksitlio or (
        taksitlio["financing_amount_max"] != 100000
        or taksitlio["maturity_max_months"] != 6
        or taksitlio["installment_count"] != 6
    ):
        errors.append("Taksitlio alanları yanlış.")

    tarim = find("Tarımda Kuveyt Türk")
    if not tarim or (
        tarim["finance_type"] != "Tarım Leasing Finansmanı"
    ):
        errors.append("Tarım leasing türü yanlış.")

    print("\nHGS kontrolü:")
    if hgs:
        print("Kategori:", hgs["campaign_category"])
        print("Finansman satırı:", hgs["finance_row"])
        print("Avantaj türü:", hgs["benefit_type"])
        print("Avantaj:", hgs["description"])
        if hgs["campaign_category"] != "other_campaign":
            errors.append("HGS kategorisi yanlış.")
        if hgs["finance_row"] is not None:
            errors.append("HGS finansman satırı silinmemiş.")
        if hgs["benefit_type"] != "free_service":
            errors.append("HGS avantajı çıkarılmamış.")
    else:
        errors.append("HGS kaydı bulunamadı.")

    print()
    if errors:
        print("Kontrol hataları:")
        for error in errors:
            print("  -", error)
        return 1

    print("Kuveyt Türk finansman alanları doğru.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
