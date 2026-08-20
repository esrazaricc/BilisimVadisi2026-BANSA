from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from src.scraping.campaign_page_fetcher import (
    is_generic_title,
    normalize_text,
    title_compare_key,
)


INDEX_PATH = Path("data") / "campaign_page_index.json"

INVALID_TITLE_KEYS = {
    "blog",
    "kuveyt turk blog",
    "kuveyt turk katilim bankasi",
}


def main() -> int:
    rows = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    kuveyt = [
        row
        for row in rows
        if row.get("bank_name") == "Kuveyt Türk"
    ]

    titles = [
        normalize_text(row.get("title"))
        for row in kuveyt
    ]

    invalid = [
        row
        for row in kuveyt
        if (
            is_generic_title(
                normalize_text(row.get("title")),
                bank_name="Kuveyt Türk",
            )
            or title_compare_key(row.get("title"))
            in INVALID_TITLE_KEYS
        )
    ]

    duplicate_titles = {
        title: count
        for title, count in Counter(titles).items()
        if title and count > 1
    }

    print("Kuveyt Türk indeks kaydı:", len(kuveyt))
    print("Geçersiz genel başlık kalan:", len(invalid))
    print("Tekrar eden başlık grubu:", len(duplicate_titles))

    print("\nBaşlık ön izlemesi:")
    for row in kuveyt[:10]:
        print("  -", row.get("title"))
        print("    ", row.get("requested_url") or row.get("url"))

    if invalid:
        print("\nGeçersiz başlıklı kayıtlar:")
        for row in invalid:
            print(
                "  -",
                row.get("title"),
                "→",
                row.get("requested_url") or row.get("url"),
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
