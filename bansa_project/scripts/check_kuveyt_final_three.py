from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


TARGET_TITLES = (
    "Kuveyt Türk ve TESK Esnafın Yanında!",
    (
        "Mobilden Kuveyt Türklü olan Esnaf, Çiftçi ve "
        "Şahıs Firmalarına Özel 1000 TL Hediye!"
    ),
    (
        "Yakınlarını Kuveyt Türk'e Davet Et Toplamda "
        "5.000 TL'ye Varan Hediye Kazan!"
    ),
)


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

    placeholders = ",".join("?" for _ in TARGET_TITLES)

    audience_rows = connection.execute(
        f"""
        SELECT
            campaign.title,
            GROUP_CONCAT(
                DISTINCT audience.audience_type
            ) AS audience_types
        FROM live_campaigns AS campaign
        LEFT JOIN live_campaign_audiences AS audience
          ON audience.campaign_id = campaign.id
        WHERE campaign.bank_name = ?
          AND campaign.title IN ({placeholders})
        GROUP BY campaign.id, campaign.title
        ORDER BY campaign.title
        """,
        (args.bank, *TARGET_TITLES),
    ).fetchall()

    tesk_rewards = connection.execute(
        """
        SELECT
            benefit.amount,
            benefit.description,
            benefit.evidence
        FROM live_campaigns AS campaign
        JOIN live_campaign_benefits AS benefit
          ON benefit.campaign_id = campaign.id
        WHERE campaign.bank_name = ?
          AND campaign.title = ?
          AND benefit.benefit_type = 'reward'
        """,
        (args.bank, TARGET_TITLES[0]),
    ).fetchall()

    connection.close()

    errors: list[str] = []

    for row in audience_rows:
        types = {
            item
            for item in (
                row["audience_types"] or ""
            ).split(",")
            if item
        }
        print(
            row["title"],
            "->",
            ", ".join(sorted(types)),
        )
        if "new_customer" not in types:
            errors.append(
                "new_customer eksik: "
                + row["title"]
            )

    false_atm_reward = [
        row
        for row in tesk_rewards
        if any(
            phrase in (row["evidence"] or "").casefold()
            for phrase in (
                "para çekme",
                "para yatırma",
                "atm’lerinden",
                "atm'lerinden",
            )
        )
    ]

    print("\nTESK reward kaydı:", len(tesk_rewards))
    for row in tesk_rewards:
        print(
            "  -",
            row["amount"],
            "|",
            row["description"],
            "|",
            row["evidence"],
        )

    if false_atm_reward:
        errors.append(
            "TESK ATM limiti hâlâ reward olarak tutuluyor."
        )

    print()
    if errors:
        print("Kontrol hataları:")
        for error in errors:
            print("  -", error)
        return 1

    print("Kuveyt Türk son üç kayıt doğru.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
