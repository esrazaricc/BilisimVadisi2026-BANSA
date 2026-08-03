from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scraping.campaign_discovery import (
    discover_all_pages,
    write_discovery_results,
)
from src.scraping.campaign_page_fetcher import (
    fetch_campaign_pages,
    write_fetch_results,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Kampanya bağlantılarını ve metinlerini tek akışta "
            "yeniler; aktif/yaklaşan/sona ermiş durumunu hesaplar."
        )
    )
    parser.add_argument("--bank")
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    pages, discovery_errors, diagnostics = discover_all_pages(
        bank_name=args.bank,
        timeout=args.timeout,
        delay_seconds=args.delay,
        headless=not args.headed,
    )
    write_discovery_results(
        pages,
        discovery_errors,
        diagnostics,
    )

    snapshots, fetch_errors = fetch_campaign_pages(
        bank_name=args.bank,
        limit=args.limit,
        timeout=args.timeout,
        delay_seconds=args.delay,
        headless=not args.headed,
    )
    write_fetch_results(snapshots, fetch_errors)

    print("\nCanlı kampanya yenilemesi tamamlandı.")
    print(f"Bulunan bağlantı: {len(pages)}")
    print(f"İşlenen kampanya: {len(snapshots)}")
    print(
        "Toplam hata: "
        f"{len(discovery_errors) + len(fetch_errors)}"
    )

    return 1 if discovery_errors or fetch_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
