from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scraping.campaign_page_fetcher import (
    build_request_url,
    resolve_campaign_url_alias,
)


CONFIG_PATH = Path("config") / "banks.json"
ERROR_PATH = (
    Path("data") / "campaign_page_fetch_errors.json"
)


def main() -> int:
    banks = json.loads(
        CONFIG_PATH.read_text(encoding="utf-8")
    )
    kuveyt_config = next(
        bank
        for bank in banks
        if bank.get("name") == "Kuveyt Türk"
    )

    errors = []
    if ERROR_PATH.exists():
        value = json.loads(
            ERROR_PATH.read_text(encoding="utf-8")
        )
        if isinstance(value, list):
            errors = value

    konfor_errors = [
        row
        for row in errors
        if (
            row.get("bank_name") == "Kuveyt Türk"
            and "konfor" in str(
                row.get("url", "")
            ).casefold()
        )
    ]

    if not konfor_errors:
        print("Konfor hata kaydı bulunamadı.")
        return 1

    for row in konfor_errors:
        source_url = row["url"]
        alias_url = resolve_campaign_url_alias(
            source_url
        )
        request_url = build_request_url(
            source_url,
            kuveyt_config,
        )

        print("Eski URL:")
        print(" ", source_url)
        print("Eşlenen resmî URL:")
        print(" ", alias_url)
        print("Gerçek istek URL:")
        print(" ", request_url)
        print()

        if not request_url.startswith(
            "https://milesandsmiles.kuveytturk.com.tr/"
        ):
            raise AssertionError(
                "Konfor URL eşlemesi uygulanmadı."
            )

    print("Konfor kampanya URL eşlemesi doğru.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
