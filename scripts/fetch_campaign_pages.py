from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse

from src.scraping.campaign_page_fetcher import (
    fetch_campaign_pages,
    write_fetch_results,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Keşfedilen kampanya bağlantılarından başlık ve "
            "kampanya metnini toplar."
        )
    )
    parser.add_argument(
        "--bank",
        help='Yalnızca belirtilen bankayı işler.',
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data") / "discovered_campaign_pages.json",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config") / "banks.json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Deneme amacıyla işlenecek en fazla sayfa sayısı.",
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument(
        "--no-browser-fallback",
        action="store_true",
        help="Kısa/boş sayfalarda Selenium yedeğini kapatır.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Selenium yedeği gerekirse Chrome penceresini gösterir.",
    )
    args = parser.parse_args()

    snapshots, errors = fetch_campaign_pages(
        discovered_path=args.input,
        config_path=args.config,
        bank_name=args.bank,
        limit=args.limit,
        timeout=args.timeout,
        delay_seconds=args.delay,
        browser_fallback=not args.no_browser_fallback,
        headless=not args.headed,
    )
    write_fetch_results(snapshots, errors)

    ok_count = sum(
        snapshot.fetch_status == "ok"
        for snapshot in snapshots
    )
    short_count = sum(
        snapshot.fetch_status != "ok"
        for snapshot in snapshots
    )

    print("\nKampanya metni toplama tamamlandı.")
    print(f"Başarılı/uygun metin: {ok_count}")
    print(f"Kontrol gerektiren metin: {short_count}")
    print(f"Hata: {len(errors)}")
    print("İndeks: data\\campaign_page_index.json")
    print("Metinler: data\\campaign_pages")
    print("Rapor: data\\campaign_page_fetch_report.json")
    print("Hatalar: data\\campaign_page_fetch_errors.json")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
