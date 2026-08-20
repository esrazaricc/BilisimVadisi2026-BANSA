from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("data") / "campaigns.db"
DEFAULT_REPORT = (
    Path("data") / "kuveyt_classification_audit.json"
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
    text = text.translate(
        str.maketrans(
            {
                "ı": "i",
                "İ": "i",
            }
        )
    )
    return text.casefold()


def preview(value: Any, limit: int = 650) -> str:
    text = normalize_text(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}…"


def table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    return {
        row[1]
        for row in connection.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }


def is_generic_title(title: str) -> bool:
    key = search_key(title)
    exact_titles = {
        "kampanya kosullari",
        "kampanya detaylari",
        "kampanya detayi",
        "avantajlar",
        "firsatlar",
    }
    return (
        key in exact_titles
        or len(key) < 12
    )


def looks_like_standard_product(
    title: str,
    clean_text: str,
) -> bool:
    title_key = search_key(title)
    combined = search_key(
        f"{title} {clean_text[:2500]}"
    )

    product_title_terms = (
        "finansmani avantajlari",
        "finansman avantajlari",
        "urun ozellikleri",
        "genel ozellikler",
        "kart ozellikleri",
    )
    product_body_terms = (
        "nasil basvurabilirim",
        "kimler basvurabilir",
        "urun ozellikleri",
        "genel ozellikler",
    )
    campaign_evidence = (
        "tarihine kadar",
        "tarihleri arasinda",
        "kampanya kapsaminda",
        "kampanya doneminde",
        "son katilim",
        "indirim",
        "hediye",
        "puan",
        "mil kazan",
        "vade farksiz",
        "ozel oran",
    )

    title_product = any(
        term in title_key
        for term in product_title_terms
    )
    body_product = any(
        term in combined
        for term in product_body_terms
    )
    has_campaign_evidence = any(
        term in combined
        for term in campaign_evidence
    )

    return (
        title_product
        and body_product
        and not has_campaign_evidence
    )


def audit_rows(
    rows: list[sqlite3.Row],
) -> dict[str, Any]:
    kind_counts = Counter(
        normalize_text(row["record_kind"])
        for row in rows
    )
    category_counts = Counter(
        normalize_text(row["campaign_category"])
        for row in rows
    )

    title_groups: dict[str, list[sqlite3.Row]] = defaultdict(list)
    hash_groups: dict[str, list[sqlite3.Row]] = defaultdict(list)

    for row in rows:
        title_groups[search_key(row["title"])].append(row)

        content_hash = normalize_text(row["content_hash"])
        if content_hash:
            hash_groups[content_hash].append(row)

    duplicate_titles = [
        group
        for key, group in title_groups.items()
        if key and len(group) > 1
    ]
    duplicate_hashes = [
        group
        for group in hash_groups.values()
        if len(group) > 1
    ]

    review_by_id: dict[int, dict[str, Any]] = {}

    def add_review(
        row: sqlite3.Row,
        reason: str,
    ) -> None:
        item = review_by_id.setdefault(
            int(row["id"]),
            {
                "id": int(row["id"]),
                "title": normalize_text(row["title"]),
                "source_url": normalize_text(
                    row["source_url"]
                ),
                "source_group": normalize_text(
                    row["source_group"]
                ),
                "record_kind": normalize_text(
                    row["record_kind"]
                ),
                "campaign_category": normalize_text(
                    row["campaign_category"]
                ),
                "classification_confidence": (
                    row["classification_confidence"]
                ),
                "classification_reason": normalize_text(
                    row["classification_reason"]
                ),
                "current_status": normalize_text(
                    row["current_status"]
                ),
                "clean_text_preview": preview(
                    row["clean_text"]
                ),
                "review_reasons": [],
            },
        )
        if reason not in item["review_reasons"]:
            item["review_reasons"].append(reason)

    for row in rows:
        title = normalize_text(row["title"])
        clean_text = normalize_text(row["clean_text"])
        confidence = row["classification_confidence"]

        if is_generic_title(title):
            add_review(
                row,
                "Başlık genel veya içerik başlığı gibi görünüyor.",
            )

        if search_key(title) == "kampanya kosullari":
            add_review(
                row,
                "Gerçek kampanya adı yerine bölüm başlığı çekilmiş olabilir.",
            )

        if "konut finansmani avantajlari" in search_key(title):
            add_review(
                row,
                "Standart finansman ürünü olma ihtimali yüksek.",
            )

        if looks_like_standard_product(title, clean_text):
            add_review(
                row,
                "Metin dönemsel kampanyadan çok standart ürün anlatımına benziyor.",
            )

        if confidence is not None and float(confidence) <= 0.85:
            add_review(
                row,
                "Sınıflandırma güveni düşük veya orta seviyede.",
            )

    for group in duplicate_titles:
        for row in group:
            add_review(
                row,
                "Aynı normalize edilmiş başlık birden fazla kayıtta bulunuyor.",
            )

    for group in duplicate_hashes:
        for row in group:
            add_review(
                row,
                "Aynı içerik özeti başka bir kayıtta da bulunuyor.",
            )

    finance_rows = [
        {
            "id": int(row["id"]),
            "title": normalize_text(row["title"]),
            "source_url": normalize_text(row["source_url"]),
            "source_group": normalize_text(row["source_group"]),
            "confidence": row["classification_confidence"],
            "reason": normalize_text(
                row["classification_reason"]
            ),
        }
        for row in rows
        if normalize_text(row["campaign_category"])
        == "finance_campaign"
    ]

    duplicate_title_report = [
        [
            {
                "id": int(row["id"]),
                "title": normalize_text(row["title"]),
                "source_url": normalize_text(
                    row["source_url"]
                ),
                "source_group": normalize_text(
                    row["source_group"]
                ),
                "content_hash": normalize_text(
                    row["content_hash"]
                ),
            }
            for row in group
        ]
        for group in duplicate_titles
    ]

    duplicate_hash_report = [
        [
            {
                "id": int(row["id"]),
                "title": normalize_text(row["title"]),
                "source_url": normalize_text(
                    row["source_url"]
                ),
                "source_group": normalize_text(
                    row["source_group"]
                ),
                "content_hash": normalize_text(
                    row["content_hash"]
                ),
            }
            for row in group
        ]
        for group in duplicate_hashes
    ]

    review_rows = sorted(
        review_by_id.values(),
        key=lambda item: (
            item["title"].casefold(),
            item["id"],
        ),
    )

    return {
        "total": len(rows),
        "record_kind_counts": dict(sorted(kind_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "review_count": len(review_rows),
        "review_rows": review_rows,
        "duplicate_title_groups": duplicate_title_report,
        "duplicate_content_groups": duplicate_hash_report,
        "finance_campaigns": finance_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Kuveyt Türk sınıflandırmasını değiştirmeden "
            "şüpheli, mükerrer ve ürün benzeri kayıtları denetler."
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
        columns = table_columns(
            connection,
            "live_campaigns",
        )
        required = {
            "id",
            "bank_name",
            "source_url",
            "source_group",
            "title",
            "clean_text",
            "content_hash",
            "current_status",
            "record_kind",
            "campaign_category",
            "classification_confidence",
            "classification_reason",
        }
        missing = sorted(required - columns)
        if missing:
            raise SystemExit(
                "Eksik live_campaigns sütunları: "
                + ", ".join(missing)
            )

        rows = connection.execute(
            """
            SELECT
                id,
                bank_name,
                source_url,
                source_group,
                title,
                clean_text,
                content_hash,
                current_status,
                record_kind,
                campaign_category,
                classification_confidence,
                classification_reason
            FROM live_campaigns
            WHERE bank_name = ?
            ORDER BY id
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

    print("Sınıflandırma denetimi tamamlandı.")
    print("Banka:", args.bank)
    print("Toplam kayıt:", result["total"])
    print(
        "Manuel kalite kontrol adayı:",
        result["review_count"],
    )
    print(
        "Mükerrer başlık grubu:",
        len(result["duplicate_title_groups"]),
    )
    print(
        "Aynı içerik grubu:",
        len(result["duplicate_content_groups"]),
    )
    print(
        "Finansman kampanyası adayı:",
        len(result["finance_campaigns"]),
    )

    if result["review_rows"]:
        print("\nÖncelikli kontrol kayıtları:")
        for item in result["review_rows"]:
            print("\nID:", item["id"])
            print("Başlık:", item["title"])
            print("URL:", item["source_url"])
            print("Kaynak grubu:", item["source_group"])
            print("Tür:", item["record_kind"])
            print("Kategori:", item["campaign_category"])
            print(
                "Güven:",
                item["classification_confidence"],
            )
            print(
                "Neden:",
                " | ".join(item["review_reasons"]),
            )
            print(
                "Sınıflandırma gerekçesi:",
                item["classification_reason"],
            )
            print(
                "Metin ön izlemesi:",
                item["clean_text_preview"],
            )

    print("\nRapor:", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
