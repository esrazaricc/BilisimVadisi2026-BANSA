from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

# Script doğrudan "python scripts\\..." ile çalıştırıldığında
# proje kök klasörünü Python modül yoluna ekler.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
from bs4 import BeautifulSoup

from src.scraping.browser_renderer import render_dynamic_page


DISCOVERY_PATH = Path("data") / "discovered_campaign_pages.json"
OUTPUT_PATH = Path("data") / "kuveyt_redirect_diagnostic.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def normalize(value) -> str:
    return " ".join(str(value or "").split())


def page_headings(html: str, limit: int = 12) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    values: list[str] = []

    for selector in (
        "h1",
        "h2",
        "h3",
        "h4",
        "meta[property='og:title']",
        "meta[name='twitter:title']",
    ):
        for node in soup.select(selector):
            value = (
                node.get("content", "")
                if node.name == "meta"
                else node.get_text(" ", strip=True)
            )
            value = normalize(value)
            if value and value not in values:
                values.append(value)

            if len(values) >= limit:
                return values

    return values


def path_of(url: str) -> str:
    return urlparse(url).path or "/"


def load_first_kuveyt_pages(limit: int = 3) -> list[dict]:
    rows = json.loads(DISCOVERY_PATH.read_text(encoding="utf-8"))
    result = [
        row
        for row in rows
        if row.get("bank_name") == "Kuveyt Türk"
    ]
    result.sort(key=lambda row: str(row.get("url", "")))
    return result[:limit]


def main() -> int:
    pages = load_first_kuveyt_pages(3)
    if not pages:
        print("Kuveyt Türk keşif kaydı bulunamadı.")
        return 1

    report: list[dict] = []

    for index, page in enumerate(pages, start=1):
        requested_url = str(page.get("url", "")).strip()

        print("=" * 88)
        print(f"[{index}/{len(pages)}]")
        print("Kaynak grubu:", page.get("source_group"))
        print("İstenen URL:", requested_url)

        request_data = {}
        try:
            response = requests.get(
                requested_url,
                headers=HEADERS,
                timeout=30,
                allow_redirects=True,
            )
            request_data = {
                "status_code": response.status_code,
                "final_url": response.url,
                "redirect_chain": [
                    {
                        "status_code": item.status_code,
                        "url": item.url,
                        "location": item.headers.get("Location", ""),
                    }
                    for item in response.history
                ],
                "headings": page_headings(response.text),
                "text_length": len(
                    BeautifulSoup(
                        response.text,
                        "html.parser",
                    ).get_text(" ", strip=True)
                ),
            }

            print("HTTP durum:", response.status_code)
            print("HTTP son URL:", response.url)
            print("HTTP son yol:", path_of(response.url))
            print(
                "HTTP yönlendirme sayısı:",
                len(response.history),
            )
            print("HTTP başlık adayları:")
            for value in request_data["headings"][:8]:
                print("  -", value)

        except Exception as error:
            request_data = {
                "error_type": type(error).__name__,
                "message": str(error),
            }
            print(
                "HTTP HATA:",
                type(error).__name__,
                str(error),
            )

        browser_data = {}
        try:
            rendered = render_dynamic_page(
                requested_url,
                detail_paths=[],
                load_more_terms=[],
                cookie_accept_terms=[
                    "Tümünü Kabul Et",
                    "Kabul Et",
                    "Onayla",
                ],
                headless=True,
                maximum_load_more_clicks=0,
                settle_seconds=2.0,
            )
            browser_data = {
                "final_url": rendered.url,
                "headings": page_headings(rendered.html),
                "html_length": len(rendered.html),
            }

            print("Tarayıcı son URL:", rendered.url)
            print("Tarayıcı son yol:", path_of(rendered.url))
            print("Tarayıcı başlık adayları:")
            for value in browser_data["headings"][:8]:
                print("  -", value)

        except Exception as error:
            browser_data = {
                "error_type": type(error).__name__,
                "message": str(error),
            }
            print(
                "TARAYICI HATA:",
                type(error).__name__,
                str(error),
            )

        report.append(
            {
                "bank_name": "Kuveyt Türk",
                "source_group": page.get("source_group"),
                "requested_url": requested_url,
                "http": request_data,
                "browser": browser_data,
            }
        )

    OUTPUT_PATH.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 88)
    print("Tanı raporu:", OUTPUT_PATH)
    print("Bu dosya mevcut kampanya verilerini değiştirmez.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())