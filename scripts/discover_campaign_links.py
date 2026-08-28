from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
from collections import Counter

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
        "--report",
        type=Path,
        default=Path("data") / "campaign_discovery_report.json",
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Chrome penceresini görünür açar.",
    )
    parser.add_argument(
        "--max-clicks",
        type=int,
        default=None,
        help="Daha fazla göster düğmesi için üst tıklama sınırı.",
    )
    args = parser.parse_args()

    pages, errors, diagnostics = discover_all_pages(
        config_path=args.config,
        bank_name=args.bank,
        timeout=args.timeout,
        delay_seconds=args.delay,
        headless=not args.headed,
        maximum_load_more_clicks=args.max_clicks,
    )
    write_discovery_results(
        pages,
        errors,
        diagnostics,
        output_path=args.output,
        error_path=args.errors,
        report_path=args.report,
    )

    counts = Counter(page.bank_name for page in pages)

    print("Kampanya bağlantısı keşfi tamamlandı.")
    print(f"Bulunan kaynak sayısı: {len(pages)}")
    for bank_name in sorted(counts):
        print(f"  - {bank_name}: {counts[bank_name]}")

    for item in diagnostics:
        reference = (
            str(item.reference_visible_count)
            if item.reference_visible_count is not None
            else "tanımsız"
        )
        print(
            f"  [{item.bank_name}] yöntem={item.render_mode}, "
            f"tıklama={item.load_more_clicks}, "
            f"bulunan={item.discovered_count}, "
            f"referans={reference}, "
            f"durum={item.completeness_status}"
        )

    print(f"Hata sayısı: {len(errors)}")
    print(f"Çıktı: {args.output}")
    print(f"Hata kaydı: {args.errors}")
    print(f"Keşif raporu: {args.report}")

    incomplete = any(
        item.completeness_status in {
            "BELOW_REFERENCE_COUNT",
            "CLICK_LIMIT_REACHED",
        }
        for item in diagnostics
    )
    return 1 if errors or incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())