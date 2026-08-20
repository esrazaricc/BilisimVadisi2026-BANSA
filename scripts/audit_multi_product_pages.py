from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup


CONFIG = (
    Path("config")
    / "standard_product_sources.json"
)


GENERIC_HEADINGS = {
    "sayfa içeriği",
    "avantajları nelerdir",
    "özellikleri nelerdir",
    "nasıl başvurulur",
    "kimler yararlanabilir",
    "sıkça sorulan sorular",
    "başvuru",
    "iletişim",
    "ürünler",
    "finansman",
    "kampanyalar",
}


def norm(value: str) -> str:
    value = re.sub(
        r"\s+",
        " ",
        str(value or "").strip(),
    ).casefold()

    return value


def candidate_headings(html: str) -> list[str]:
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    result = []

    for tag in soup.find_all(
        ["h2", "h3", "h4", "h5", "strong"]
    ):
        text = re.sub(
            r"\s+",
            " ",
            tag.get_text(
                " ",
                strip=True,
            ),
        ).strip()

        key = norm(text)

        if not (3 <= len(text) <= 80):
            continue

        if key in GENERIC_HEADINGS:
            continue

        if any(
            token in key
            for token in (
                "facebook",
                "twitter",
                "linkedin",
                "sayfayı yazdır",
                "müşteri memnuniyet",
            )
        ):
            continue

        if text not in result:
            result.append(text)

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bank",
        default=None,
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
    )
    args = parser.parse_args()

    data = json.loads(
        CONFIG.read_text(encoding="utf-8")
    )

    banks = data.get("banks", [])

    if args.bank:
        banks = [
            bank
            for bank in banks
            if norm(bank.get("name"))
            == norm(args.bank)
        ]

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 "
                "AppleWebKit/537.36 "
                "Chrome/150 Safari/537.36"
            )
        }
    )

    print("=" * 100)
    print("TÜM BANKALAR — ÇOK ÜRÜNLÜ SAYFA ADAY DENETİMİ")
    print("=" * 100)

    total_candidates = 0

    for bank in banks:
        urls = []

        for source in bank.get(
            "listing_pages",
            [],
        ):
            url = str(
                source.get("url") or ""
            ).strip()

            if url and url not in urls:
                urls.append(url)

        for page in bank.get(
            "embedded_product_pages",
            [],
        ):
            url = str(
                page.get("url") or ""
            ).strip()

            if url and url not in urls:
                urls.append(url)

        for url in urls:
            try:
                response = session.get(
                    url,
                    timeout=args.timeout,
                )
                response.raise_for_status()

                html = response.text
                text_key = norm(
                    BeautifulSoup(
                        html,
                        "html.parser",
                    ).get_text(
                        " ",
                        strip=True,
                    )
                )

                headings = candidate_headings(
                    html
                )

                # Audit-only heuristic:
                # otomatik ürün oluşturmuyoruz.
                looks_multi = (
                    (
                        "ürünleri nelerdir"
                        in text_key
                        or "urunleri nelerdir"
                        in text_key
                        or "ürünlerimiz"
                        in text_key
                        or "urunlerimiz"
                        in text_key
                    )
                    and len(headings) >= 3
                )

                if not looks_multi:
                    continue

                total_candidates += 1

                print()
                print(
                    f"[ADAY] {bank['name']}"
                )
                print("URL:", response.url)
                print("Başlık adayları:")

                for heading in headings[:20]:
                    print("  -", heading)

            except Exception as error:
                print()
                print(
                    f"[HATA] {bank['name']} | "
                    f"{url} | {error}"
                )

    print()
    print("=" * 100)
    print(
        "Çok ürünlü sayfa adayı:",
        total_candidates,
    )
    print(
        "NOT: Bu script yalnız aday üretir; "
        "DB/config değiştirmez."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
