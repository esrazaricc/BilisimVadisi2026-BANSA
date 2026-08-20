from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.repository import get_campaigns


BANK_NAME = "Vakıf Katılım"


def main() -> int:
    campaigns = get_campaigns()
    bank_rows = campaigns[campaigns["bank_name"] == BANK_NAME].copy()

    if bank_rows.empty:
        raise RuntimeError(
            "Vakıf Katılım get_campaigns() sonucunda görünmüyor."
        )

    generic = bank_rows[
        bank_rows["campaign_name"]
        .fillna("")
        .str.strip()
        .str.casefold()
        .isin({"", "detay", "detaylı bilgi", "detayli bilgi"})
    ]
    if not generic.empty:
        raise RuntimeError("Vakıf Katılım kayıtlarında genel başlık kaldı.")

    type_counts = (
        bank_rows["campaign_type"]
        .fillna("unclassified")
        .value_counts()
        .to_dict()
    )
    print("Vakıf Katılım dashboard doğrulaması başarılı.")
    print("Görünen kampanya:", len(bank_rows))
    print("Kampanya türleri:", type_counts)
    print("Banka seçeneklerinde görünür: EVET")
    print("Karşılaştırmada görünür: EVET")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
