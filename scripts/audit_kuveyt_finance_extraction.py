from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("data") / "campaigns.db"
DEFAULT_REPORT = (
    Path("data") / "kuveyt_finance_extraction_audit.json"
)


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize(
        "NFKC",
        str(value or ""),
    )
    return re.sub(r"\s+", " ", text).strip()


def search_key(value: Any) -> str:
    text = unicodedata.normalize(
        "NFKD",
        normalize_text(value),
    )
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    return (
        text.replace("ı", "i")
        .replace("İ", "i")
        .casefold()
    )


def split_sentences(text: str) -> list[str]:
    parts = re.split(
        r"(?<=[.!?;])\s+|\s*[•●▪]\s*|\n+",
        normalize_text(text),
    )
    return [
        item.strip(" -–—")
        for item in parts
        if item.strip(" -–—")
    ]


EVIDENCE_TERMS = (
    "kâr payı",
    "kar payı",
    "oran",
    "finansman",
    "tl",
    "vade",
    "taksit",
    "ödemesiz",
    "erteleme",
    "tahsis",
    "masraf",
    "komisyon",
    "ücret",
)


DISCLAIMER_TERMS = (
    "değişiklik yapma hakkına sahiptir",
    "değiştirme hakkına sahiptir",
    "kredi değerlendirme sonucuna göre değişebilir",
    "başvuru sahibinin kredi değerlendirme",
    "koşulları değiştirebilir",
)


def evidence_sentences(
    text: str,
    *,
    limit: int = 14,
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for sentence in split_sentences(text):
        key = search_key(sentence)
        if not any(
            search_key(term) in key
            for term in EVIDENCE_TERMS
        ):
            continue

        if key in seen:
            continue

        seen.add(key)
        result.append(sentence[:700])

        if len(result) >= limit:
            break

    return result


def detect_review_flags(row: sqlite3.Row) -> list[str]:
    title = normalize_text(row["title"])
    text = normalize_text(row["clean_text"])
    folded = search_key(f"{title} {text}")
    flags: list[str] = []

    rate_text = normalize_text(
        row["profit_share_rate_text"]
    )
    amount_text = normalize_text(
        row["financing_amount_text"]
    )
    maturity_text = normalize_text(
        row["maturity_text"]
    )
    grace = row["grace_period_months"]
    installment = row["installment_count"]
    advantage = search_key(
        row["campaign_advantage"]
    )

    if (
        (
            "vade farksiz" in folded
            or "%0 kar payi" in folded
            or "% 0 kar payi" in folded
        )
        and not rate_text
    ):
        flags.append(
            "Vade farksız/%0 kanıtı var; kâr payı %0 kaçmış olabilir."
        )

    has_money_and_finance = (
        bool(
            re.search(
                r"\b\d[\d\.\,]*\s*(?:tl|₺)",
                folded,
            )
        )
        and "finansman" in folded
    )
    if has_money_and_finance and not amount_text:
        flags.append(
            "TL tutarı ve finansman kanıtı var; finansman tutarı kaçmış olabilir."
        )

    if (
        (
            "odemesiz donem" in folded
            or "ay erteleme" in folded
            or "aya kadar odemesiz" in folded
        )
        and grace is None
    ):
        flags.append(
            "Ödemesiz dönem/erteleme kanıtı var; ay bilgisi çıkarılamamış."
        )

    if "taksit" in folded and installment is None:
        flags.append(
            "Taksit kanıtı var; taksit sayısı çıkarılamamış."
        )

    if advantage and any(
        search_key(term) in advantage
        for term in DISCLAIMER_TERMS
    ):
        flags.append(
            "Seçilen avantaj kampanya faydası yerine hukuki açıklama görünüyor."
        )

    if (
        "hgs kampanyasi" in search_key(title)
        and not any(
            (
                rate_text,
                amount_text,
                maturity_text,
                grace,
                installment,
            )
        )
    ):
        flags.append(
            "HGS hediyesi finansman şartı değil; other_campaign olması gerekebilir."
        )

    if (
        "taksitlio" in search_key(title)
        and "6 taksit" in folded
        and installment != 6
    ):
        flags.append(
            "Taksitlio metninde 6 taksit kanıtı var; çıkarılan taksit sayısı farklı."
        )

    return flags


def audit_rows(
    rows: list[sqlite3.Row],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    for row in rows:
        flags = detect_review_flags(row)
        item = {
            "campaign_id": int(row["id"]),
            "title": normalize_text(row["title"]),
            "source_url": normalize_text(
                row["source_url"]
            ),
            "finance_type": normalize_text(
                row["finance_type"]
            ),
            "profit_share_rate_text": normalize_text(
                row["profit_share_rate_text"]
            )
            or None,
            "financing_amount_text": normalize_text(
                row["financing_amount_text"]
            )
            or None,
            "maturity_text": normalize_text(
                row["maturity_text"]
            )
            or None,
            "grace_period_months": (
                row["grace_period_months"]
            ),
            "installment_count": row["installment_count"],
            "allocation_fee_status": normalize_text(
                row["allocation_fee_status"]
            )
            or None,
            "expense_status": normalize_text(
                row["expense_status"]
            )
            or None,
            "campaign_advantage": normalize_text(
                row["campaign_advantage"]
            )
            or None,
            "extraction_confidence": (
                row["extraction_confidence"]
            ),
            "review_flags": flags,
            "evidence_sentences": evidence_sentences(
                row["clean_text"] or ""
            ),
        }
        items.append(item)

    return {
        "finance_campaign_count": len(rows),
        "review_campaign_count": sum(
            bool(item["review_flags"])
            for item in items
        ),
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Kuveyt Türk finansman alanlarını değiştirmeden "
            "kaynak metin kanıtlarıyla denetler."
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
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(
            f"Veritabanı bulunamadı: {args.db}"
        )

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute(
            """
            SELECT
                campaign.id,
                campaign.title,
                campaign.source_url,
                campaign.clean_text,
                finance.finance_type,
                finance.profit_share_rate_text,
                finance.financing_amount_text,
                finance.maturity_text,
                finance.grace_period_months,
                finance.installment_count,
                finance.allocation_fee_status,
                finance.expense_status,
                finance.campaign_advantage,
                finance.extraction_confidence
            FROM live_campaigns AS campaign
            LEFT JOIN live_campaign_finance_details AS finance
                ON finance.campaign_id = campaign.id
            WHERE campaign.bank_name = ?
              AND campaign.record_kind = 'campaign'
              AND campaign.campaign_category = 'finance_campaign'
              AND campaign.is_current = 1
            ORDER BY campaign.title
            """,
            (args.bank,),
        ).fetchall()
    finally:
        connection.close()

    result = audit_rows(rows)

    args.report.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.report.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Finansman çıkarım denetimi tamamlandı.")
    print("Banka:", args.bank)
    print(
        "Finansman kampanyası:",
        result["finance_campaign_count"],
    )
    print(
        "Kontrol gereken kampanya:",
        result["review_campaign_count"],
    )

    for item in result["items"]:
        print("\n" + "=" * 90)
        print("ID:", item["campaign_id"])
        print("Kampanya:", item["title"])
        print("Finansman türü:", item["finance_type"])
        print(
            "Kâr payı:",
            item["profit_share_rate_text"]
            or "Belirtilmemiş",
        )
        print(
            "Finansman tutarı:",
            item["financing_amount_text"]
            or "Belirtilmemiş",
        )
        print(
            "Vade:",
            item["maturity_text"]
            or "Belirtilmemiş",
        )
        print(
            "Ödemesiz dönem:",
            item["grace_period_months"]
            if item["grace_period_months"] is not None
            else "Belirtilmemiş",
        )
        print(
            "Taksit sayısı:",
            item["installment_count"]
            if item["installment_count"] is not None
            else "Belirtilmemiş",
        )
        print(
            "Seçilen avantaj:",
            item["campaign_advantage"]
            or "Belirtilmemiş",
        )

        print("\nKontrol işaretleri:")
        if item["review_flags"]:
            for flag in item["review_flags"]:
                print("  -", flag)
        else:
            print("  - Otomatik işaret bulunmadı.")

        print("\nKaynak metindeki ilgili cümleler:")
        if item["evidence_sentences"]:
            for index, sentence in enumerate(
                item["evidence_sentences"],
                start=1,
            ):
                print(f"  [{index}] {sentence}")
        else:
            print("  İlgili cümle bulunamadı.")

    print("\nRapor:", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())