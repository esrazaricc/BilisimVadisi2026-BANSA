from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scraping.campaign_page_fetcher import (
    normalize_text,
    title_compare_key,
)


INDEX_PATH = Path("data") / "campaign_page_index.json"


def main() -> int:
    rows = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    kuveyt_rows = [
        row
        for row in rows
        if row.get("bank_name") == "Kuveyt Türk"
    ]

    suffix_rows = [
        row
        for row in kuveyt_rows
        if (
            "kuveyt turk katilim bankasi"
            in title_compare_key(row.get("title"))
        )
    ]

    print("Kuveyt Türk indeks kaydı:", len(kuveyt_rows))
    print("Banka/site eki kalan başlık:", len(suffix_rows))

    print("\nBaşlık ön izlemesi:")
    for row in kuveyt_rows[:10]:
        print("  -", normalize_text(row.get("title")))

    if suffix_rows:
        print("\nSite eki kalan kayıtlar:")
        for row in suffix_rows[:20]:
            print("  -", row.get("title"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
