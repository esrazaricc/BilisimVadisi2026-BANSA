from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scraping.campaign_page_fetcher import build_request_url


CONFIG_PATH = Path("config") / "banks.json"
DISCOVERY_PATH = (
    Path("data") / "discovered_campaign_pages.json"
)


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Dosya bulunamadı: {path}")

    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    banks = load_json(CONFIG_PATH)
    rows = load_json(DISCOVERY_PATH)

    kuveyt_config = next(
        (
            bank
            for bank in banks
            if bank.get("name") == "Kuveyt Türk"
        ),
        None,
    )
    if kuveyt_config is None:
        print("Kuveyt Türk yapılandırması bulunamadı.")
        return 1

    kuveyt_rows = [
        row
        for row in rows
        if row.get("bank_name") == "Kuveyt Türk"
    ][:3]

    if not kuveyt_rows:
        print("Kuveyt Türk keşif kaydı bulunamadı.")
        return 1

    print(
        "Kuveyt Türk base_url:",
        kuveyt_config.get("base_url"),
    )
    print()

    all_valid = True

    for index, row in enumerate(kuveyt_rows, start=1):
        discovered_url = str(row.get("url", "")).strip()
        request_url = build_request_url(
            discovered_url,
            kuveyt_config,
        )

        print(f"[{index}] Keşif URL:")
        print("   ", discovered_url)
        print("    İstek URL:")
        print("   ", request_url)

        valid = request_url.startswith(
            "https://www.kuveytturk.com.tr/"
        )

        if valid:
            print("    Durum: DOĞRU")
        else:
            print("    Durum: HATALI")
            all_valid = False

        print()

    if not all_valid:
        print(
            "Bazı istek URL'lerinde www alan adı kullanılmıyor."
        )
        return 1

    print("İlk üç Kuveyt Türk istek URL'si doğru.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())