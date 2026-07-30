from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from src.scraping.campaign_discovery import (
    discover_all_pages,
    write_discovery_results,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Katılım bankalarının resmî kampanya sayfalarından "
            "kampanya detay bağlantılarını bulur."
        )
    )
    parser.add_argument(
        "--bank",
        help='Yalnızca belirtilen bankayı tara. Örnek: "Albaraka Türk"',
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config") / "banks.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "discovered_campaign_pages.json",
    )
    parser.add_argument(
        "--errors",
        type=Path,
        default=Path("data") / "campaign_discovery_errors.json",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
    )
    args = parser.parse_args()

    pages, errors = discover_all_pages(
        config_path=args.config,
        bank_name=args.bank,
        timeout=args.timeout,
        delay_seconds=args.delay,
    )
    write_discovery_results(
        pages,
        errors,
        output_path=args.output,
        error_path=args.errors,
    )

    counts = Counter(page.bank_name for page in pages)

    print("Kampanya bağlantısı keşfi tamamlandı.")
    print(f"Bulunan kaynak sayısı: {len(pages)}")
    for bank_name in sorted(counts):
        print(f"  - {bank_name}: {counts[bank_name]}")

    print(f"Hata sayısı: {len(errors)}")
    print(f"Çıktı: {args.output}")
    print(f"Hata kaydı: {args.errors}")

    return 0 if pages or not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
