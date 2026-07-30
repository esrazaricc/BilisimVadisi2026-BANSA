from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import (
    parse_qsl,
    urlencode,
    urljoin,
    urlparse,
    urlunparse,
)

from bs4 import BeautifulSoup

from src.scraping.http_client import HttpClient


TRACKING_QUERY_PREFIXES = (
    "utm_",
    "fbclid",
    "gclid",
    "yclid",
)

NON_HTML_EXTENSIONS = (
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".zip",
)


@dataclass(frozen=True)
class DiscoveredPage:
    bank_name: str
    url: str
    source_page: str
    page_type: str
    discovery_mode: str


def load_bank_config(
    path: str | Path = Path("config") / "banks.json",
) -> list[dict[str, Any]]:
    config_path = Path(path)
    return json.loads(config_path.read_text(encoding="utf-8"))


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())

    scheme = parsed.scheme.casefold() or "https"
    host = parsed.netloc.casefold()
    if host.startswith("www."):
        host = host[4:]

    path = re.sub(r"/+", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")

    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.casefold()
        if any(
            lowered == prefix or lowered.startswith(prefix)
            for prefix in TRACKING_QUERY_PREFIXES
        ):
            continue
        query_items.append((key, value))

    return urlunparse(
        (
            scheme,
            host,
            path,
            "",
            urlencode(sorted(query_items)),
            "",
        )
    )


def normalized_host(url: str) -> str:
    host = urlparse(url).netloc.casefold()
    return host[4:] if host.startswith("www.") else host


def is_same_domain(url: str, base_url: str) -> bool:
    host = normalized_host(url)
    base_host = normalized_host(base_url)
    return host == base_host or host.endswith(f".{base_host}")


def path_contains(url: str, fragments: list[str]) -> bool:
    path = urlparse(url).path.casefold()
    return any(fragment.casefold() in path for fragment in fragments)


def is_excluded(url: str, bank: dict[str, Any]) -> bool:
    if path_contains(url, bank.get("exclude_paths", [])):
        return True

    lowered_path = urlparse(url).path.casefold()
    return lowered_path.endswith(NON_HTML_EXTENSIONS)


def is_detail_candidate(
    url: str,
    anchor_text: str,
    bank: dict[str, Any],
) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    if not is_same_domain(url, bank["base_url"]):
        return False
    if is_excluded(url, bank):
        return False

    detail_paths = bank.get("detail_paths", [])
    if detail_paths:
        return path_contains(url, detail_paths)

    combined = f"{url} {anchor_text}".casefold()
    campaign_terms = (
        "kampanya",
        "fırsat",
        "firsat",
        "avantaj",
        "indirim",
        "ödül",
        "odul",
    )
    return any(term in combined for term in campaign_terms)


def discover_from_html(
    *,
    bank: dict[str, Any],
    source_page: str,
    html: str,
) -> list[DiscoveredPage]:
    soup = BeautifulSoup(html, "html.parser")
    source_canonical = canonicalize_url(source_page)

    found: dict[str, DiscoveredPage] = {}

    for link in soup.find_all("a", href=True):
        absolute = urljoin(source_page, link.get("href", "").strip())
        canonical = canonicalize_url(absolute)
        anchor_text = " ".join(link.stripped_strings)

        if canonical == source_canonical:
            continue
        if not is_detail_candidate(canonical, anchor_text, bank):
            continue

        found[canonical] = DiscoveredPage(
            bank_name=bank["name"],
            url=canonical,
            source_page=source_canonical,
            page_type="campaign_detail",
            discovery_mode=bank.get(
                "discovery_mode",
                "detail_links",
            ),
        )

    if found:
        return sorted(found.values(), key=lambda item: item.url)

    if bank.get("discovery_mode") == "single_listing_page":
        return [
            DiscoveredPage(
                bank_name=bank["name"],
                url=source_canonical,
                source_page=source_canonical,
                page_type="campaign_listing_content",
                discovery_mode="single_listing_page",
            )
        ]

    return []


def discover_bank_pages(
    bank: dict[str, Any],
    client: HttpClient,
) -> tuple[list[DiscoveredPage], list[dict[str, str]]]:
    pages: dict[str, DiscoveredPage] = {}
    errors: list[dict[str, str]] = []

    for source_page in bank.get("campaign_pages", []):
        try:
            result = client.get(source_page)
            discovered = discover_from_html(
                bank=bank,
                source_page=result.url,
                html=result.text,
            )
            for page in discovered:
                pages[page.url] = page
        except Exception as error:
            errors.append(
                {
                    "bank_name": bank["name"],
                    "source_page": source_page,
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
            )

    return sorted(pages.values(), key=lambda item: item.url), errors


def discover_all_pages(
    *,
    config_path: str | Path = Path("config") / "banks.json",
    bank_name: str | None = None,
    timeout: int = 30,
    delay_seconds: float = 1.0,
) -> tuple[list[DiscoveredPage], list[dict[str, str]]]:
    banks = load_bank_config(config_path)

    if bank_name:
        wanted = bank_name.casefold()
        banks = [
            bank
            for bank in banks
            if bank["name"].casefold() == wanted
        ]
        if not banks:
            raise ValueError(f"Banka bulunamadı: {bank_name}")

    pages: dict[tuple[str, str], DiscoveredPage] = {}
    errors: list[dict[str, str]] = []

    with HttpClient(
        timeout=timeout,
        delay_seconds=delay_seconds,
    ) as client:
        for bank in banks:
            if not bank.get("campaign_pages"):
                continue

            bank_pages, bank_errors = discover_bank_pages(
                bank,
                client,
            )
            errors.extend(bank_errors)

            for page in bank_pages:
                pages[(page.bank_name, page.url)] = page

    return (
        sorted(
            pages.values(),
            key=lambda item: (item.bank_name, item.url),
        ),
        errors,
    )


def write_discovery_results(
    pages: list[DiscoveredPage],
    errors: list[dict[str, str]],
    *,
    output_path: str | Path = (
        Path("data") / "discovered_campaign_pages.json"
    ),
    error_path: str | Path = (
        Path("data") / "campaign_discovery_errors.json"
    ),
) -> None:
    output = Path(output_path)
    errors_output = Path(error_path)

    output.parent.mkdir(parents=True, exist_ok=True)
    errors_output.parent.mkdir(parents=True, exist_ok=True)

    output.write_text(
        json.dumps(
            [asdict(page) for page in pages],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    errors_output.write_text(
        json.dumps(errors, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
