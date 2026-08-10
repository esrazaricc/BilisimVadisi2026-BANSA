from __future__ import annotations

import re
import sqlite3
from pathlib import Path


DB_PATH = Path("data") / "campaigns.db"

TARGET_TITLES = (
    "Dijital Müşterilere Özel Pratik Finansman Kart",
    "Vade Farksız 140.000 TL’ye Varan Destek!",
    "Payını Sen Seç Finansmanı",
)

KEYWORDS = (
    "vade",
    " ay",
    "peşinat",
    "pesinat",
    "kâr",
    "kar ",
    "finansman",
    "tahsis",
    "oran",
    "kampanya fırsat",
)


def normalize(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def split_sentences(text: str) -> list[str]:
    normalized = normalize(text)
    parts = re.split(
        r"(?<=[.!?;])\s+|\s*[•●▪]\s*|\n+",
        normalized,
    )
    return [
        part.strip(" -–—")
        for part in parts
        if part.strip(" -–—")
    ]


def contains_keyword(sentence: str) -> bool:
    folded = sentence.casefold()
    return any(keyword.casefold() in folded for keyword in KEYWORDS)


def main() -> int:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        placeholders = ",".join("?" for _ in TARGET_TITLES)

        rows = connection.execute(
            f"""
            SELECT
                campaign.id,
                campaign.title,
                campaign.clean_text,
                finance.finance_type,
                finance.profit_share_rate_text,
                finance.financing_amount_text,
                finance.maturity_text,
                finance.campaign_advantage,
                finance.evidence_text
            FROM live_campaigns AS campaign
            LEFT JOIN live_campaign_finance_details AS finance
                ON finance.campaign_id = campaign.id
            WHERE campaign.bank_name = ?
              AND campaign.title IN ({placeholders})
            ORDER BY campaign.title
            """,
            ("Albaraka Türk", *TARGET_TITLES),
        ).fetchall()

        print("Kontrol edilen kayıt:", len(rows))

        for row in rows:
            print("\n" + "=" * 86)
            print("Başlık:", row["title"])
            print("Finansman türü:", row["finance_type"])
            print("Kâr payı:", row["profit_share_rate_text"])
            print("Finansman tutarı:", row["financing_amount_text"])
            print("Vade:", row["maturity_text"])
            print("Seçilen avantaj:", row["campaign_advantage"])
            print("Seçilen kanıt:", row["evidence_text"])

            print("\nİlgili metin cümleleri:")
            matched = 0

            for index, sentence in enumerate(
                split_sentences(row["clean_text"] or ""),
                start=1,
            ):
                if contains_keyword(sentence):
                    matched += 1
                    print(f"[{index}] {sentence}")

            if matched == 0:
                print("İlgili cümle bulunamadı.")

        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
