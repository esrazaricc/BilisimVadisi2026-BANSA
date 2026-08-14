from __future__ import annotations

import argparse
import shutil
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path


DEFAULT_DB = Path("data") / "campaigns.db"


def key(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.casefold().replace("ı", "i")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    if not args.db.exists():
        raise FileNotFoundError(args.db)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = (
        args.db.parent
        / "backups"
        / f"campaigns_before_title_category_fix_{stamp}.db"
    )
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.db, backup)

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    rows = con.execute(
        """
        SELECT id, bank_name, title, campaign_category
        FROM live_campaigns
        WHERE record_kind = 'campaign'
          AND is_current = 1
        ORDER BY id
        """
    ).fetchall()

    changes = []
    point_terms = (
        "worldpuan",
        "altin puan",
        "parafpara",
        "paraf para",
        "bankkart lira",
    )
    installment_terms = (
        "taksit",
        "vade farksiz",
    )
    discount_terms = (
        "indirim",
        "nakit iade",
        "harcama iadesi",
    )

    with con:
        for row in rows:
            title_key = key(row["title"])
            old = row["campaign_category"]
            new = None

            # Finansman ve yeni müşteri kategorileri bilinçli olarak
            # korunur; hedefli düzeltme yalnızca diğer yanlış kategorilerde
            # uygulanır.
            if old not in {"finance_campaign", "new_customer_campaign"}:
                if any(term in title_key for term in point_terms):
                    new = "points_campaign"
                elif any(term in title_key for term in discount_terms):
                    new = "discount_campaign"
                elif any(term in title_key for term in installment_terms):
                    new = "card_campaign"

            if new and new != old:
                con.execute(
                    """
                    UPDATE live_campaigns
                    SET campaign_category = ?,
                        comparison_eligible = 1,
                        classification_confidence = MAX(
                            COALESCE(classification_confidence, 0),
                            0.97
                        ),
                        classification_reason = ?
                    WHERE id = ?
                    """,
                    (
                        new,
                        (
                            "Başlıktaki açık kampanya sinyaline göre "
                            "hedefli kategori düzeltmesi."
                        ),
                        row["id"],
                    ),
                )
                changes.append(
                    (
                        row["id"],
                        row["bank_name"],
                        row["title"],
                        old,
                        new,
                    )
                )

    con.close()

    print("Başlık bazlı kategori düzeltmesi tamamlandı.")
    print("Yedek:", backup)
    print("Değişen kayıt:", len(changes))
    for _, bank, title, old, new in changes:
        print(f"- {bank} | {title}")
        print(f"  {old} -> {new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
