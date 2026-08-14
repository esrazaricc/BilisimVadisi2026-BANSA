from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


CONFIG = Path("config") / "standard_product_sources.json"


VARIANT_TERMS = (
    "sigortalı",
    "sigortasız",
    "0 km",
    "2. el",
    "ikinci el",
    "maliyet tablosu",
    "hesaplama aracı",
)

GENERIC_TERMS = (
    "bildirimler",
    "önerilen aramalar",
    "duyurular",
    "mobil uygulamamızı",
    "zorunlu çerezler",
    "işlevsellik çerezleri",
    "kişiselleştirilmiş reklam",
    "sıkça yapılan aramalar",
    "sayfayı yazdır",
    "facebook",
    "twitter",
    "linkedin",
)


def norm(value: str | None) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip().casefold(),
    )


def same_host(a: str, b: str) -> bool:
    return (
        urlparse(a).netloc.casefold()
        == urlparse(b).netloc.casefold()
    )


def clean_candidate(value: str) -> bool:
    key = norm(value)

    if not (3 <= len(key) <= 100):
        return False

    if any(term in key for term in GENERIC_TERMS):
        return False

    return True


def candidate_nodes(soup: BeautifulSoup):
    result = []

    for tag in soup.find_all(
        ["h2", "h3", "h4", "h5", "strong"]
    ):
        text = re.sub(
            r"\s+",
            " ",
            tag.get_text(" ", strip=True),
        ).strip()

        if not clean_candidate(text):
            continue

        result.append((tag, text))

    return result


def nearest_product_link(
    tag,
    *,
    page_url: str,
) -> str | None:
    # 1) heading itself nested in <a>
    anchor = tag.find_parent("a")

    if anchor is not None:
        href = str(anchor.get("href") or "").strip()
        if href and not href.startswith("javascript:"):
            return urljoin(page_url, href)

    # 2) heading's immediate container/card has a detail link
    container = tag.find_parent(
        ["article", "li", "div", "section"]
    )

    if container is not None:
        for link in container.find_all("a", href=True):
            href = str(link.get("href") or "").strip()
            label = norm(
                link.get_text(" ", strip=True)
            )

            if not href or href.startswith("javascript:"):
                continue

            if (
                "detay" in label
                or "incele" in label
                or "bilgi" in label
                or "başvur" in label
                or "basvur" in label
            ):
                return urljoin(page_url, href)

    # 3) nearby next link
    nxt = tag.find_next("a", href=True)

    if nxt is not None:
        label = norm(
            nxt.get_text(" ", strip=True)
        )

        if (
            "detay" in label
            or "incele" in label
            or "bilgi" in label
        ):
            href = str(nxt.get("href") or "").strip()

            if href and not href.startswith("javascript:"):
                return urljoin(page_url, href)

    return None


def classify_page(
    *,
    page_url: str,
    html: str,
) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    nodes = candidate_nodes(soup)

    candidates = []
    linked_urls = set()
    variant_count = 0

    for tag, text in nodes:
        key = norm(text)

        is_variant = any(
            term in key
            for term in VARIANT_TERMS
        )

        if is_variant:
            variant_count += 1

        link = nearest_product_link(
            tag,
            page_url=page_url,
        )

        if (
            link
            and same_host(page_url, link)
            and urlparse(link).path.casefold()
            != urlparse(page_url).path.casefold()
        ):
            linked_urls.add(link)

        candidates.append(
            {
                "heading": text,
                "linked_url": link,
                "looks_variant": is_variant,
            }
        )

    # Decision rules:
    #
    # LINKED_LISTING:
    # At least two distinct child/detail URLs.
    #
    # PRICING_VARIANT_PAGE:
    # Candidate headings mostly represent pricing conditions.
    #
    # EMBEDDED_CANDIDATE:
    # Multiple product-like headings but no child detail URLs.
    #
    # REVIEW:
    # Ambiguous.
    non_variant_count = len(candidates) - variant_count

    if len(linked_urls) >= 2:
        classification = "LINKED_LISTING"
    elif (
        variant_count >= 2
        and variant_count >= non_variant_count
    ):
        classification = "PRICING_VARIANT_PAGE"
    elif (
        len(candidates) >= 3
        and len(linked_urls) <= 1
    ):
        classification = "EMBEDDED_CANDIDATE"
    else:
        classification = "REVIEW"

    return {
        "classification": classification,
        "linked_urls": sorted(linked_urls),
        "candidates": candidates,
    }


def iter_candidate_urls(bank: dict) -> list[str]:
    urls = []

    for source in bank.get("listing_pages", []):
        url = str(source.get("url") or "").strip()

        if url and url not in urls:
            urls.append(url)

    for page in bank.get(
        "embedded_product_pages",
        [],
    ):
        url = str(page.get("url") or "").strip()

        if url and url not in urls:
            urls.append(url)

    return urls


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", default=None)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    data = json.loads(
        CONFIG.read_text(encoding="utf-8")
    )

    banks = data.get("banks", [])

    if args.bank:
        wanted = norm(args.bank)

        banks = [
            bank
            for bank in banks
            if norm(bank.get("name")) == wanted
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

    summary = {
        "LINKED_LISTING": 0,
        "PRICING_VARIANT_PAGE": 0,
        "EMBEDDED_CANDIDATE": 0,
        "REVIEW": 0,
    }

    print("=" * 110)
    print("ÇOK ÜRÜNLÜ SAYFA DENETİMİ V2")
    print("=" * 110)

    for bank in banks:
        for url in iter_candidate_urls(bank):
            try:
                response = session.get(
                    url,
                    timeout=args.timeout,
                )
                response.raise_for_status()

                result = classify_page(
                    page_url=response.url,
                    html=response.text,
                )

                classification = result[
                    "classification"
                ]

                summary[classification] += 1

                # Noise reduction: only print pages that are
                # potentially relevant or have multiple child links.
                if (
                    classification == "REVIEW"
                    and len(result["candidates"]) < 3
                ):
                    continue

                print()
                print("-" * 110)
                print(
                    f"{bank['name']} | "
                    f"{classification}"
                )
                print("URL:", response.url)

                if result["linked_urls"]:
                    print("Ayrı detay URL'leri:")

                    for child in result["linked_urls"]:
                        print("  ->", child)

                print("Başlıklar:")

                for row in result["candidates"][:20]:
                    suffix = []

                    if row["looks_variant"]:
                        suffix.append("VARIANT")

                    if row["linked_url"]:
                        suffix.append(
                            "LINK="
                            + row["linked_url"]
                        )

                    suffix_text = (
                        " [" + " | ".join(suffix) + "]"
                        if suffix
                        else ""
                    )

                    print(
                        "  - "
                        + row["heading"]
                        + suffix_text
                    )

            except Exception as error:
                print()
                print(
                    f"[HATA] {bank['name']} | "
                    f"{url} | {error}"
                )

    print()
    print("=" * 110)
    print("ÖZET")
    print("=" * 110)

    for key, value in summary.items():
        print(f"{key}: {value}")

    print()
    print(
        "KURAL: Ayrı resmî detay URL'si varsa onu kullan; "
        "yalnız ayrı URL bulunmayan gerçek alt ürünleri "
        "embedded olarak tanımla."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
