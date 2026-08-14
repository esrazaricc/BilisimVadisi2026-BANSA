from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup


DEFAULT_CONFIG = (
    Path("config") / "standard_product_sources.json"
)


@dataclass(frozen=True)
class StandardProductLink:
    bank_name: str
    bank_slug: str
    product_family: str
    product_family_key: str
    url: str
    source_page: str
    scope: str


def canonicalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    path = re.sub(r"/+", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            parsed.query,
            "",
        )
    )


def load_config(
    path: str | Path = DEFAULT_CONFIG,
) -> list[dict[str, Any]]:
    data = json.loads(
        Path(path).read_text(encoding="utf-8")
    )
    rows = data.get("banks", [])
    if not isinstance(rows, list):
        raise ValueError(
            "standard_product_sources.json: banks liste olmalı."
        )
    return rows


def find_bank(
    bank_name: str,
    *,
    config_path: str | Path = DEFAULT_CONFIG,
) -> dict[str, Any]:
    wanted = bank_name.casefold()
    for bank in load_config(config_path):
        if str(bank.get("name", "")).casefold() == wanted:
            return bank
    raise ValueError(f"Banka bulunamadı: {bank_name}")


def resolve_family(
    path: str,
    rules: list[dict[str, Any]],
) -> tuple[str, str] | None:
    normalized = (
        path.rstrip("/") or "/"
    ).casefold()

    for rule in rules:
        exact_paths = {
            (str(item).rstrip("/") or "/").casefold()
            for item in rule.get("exact_paths", [])
        }
        if normalized in exact_paths:
            return (
                str(rule["family_key"]),
                str(rule["family_label"]),
            )

        if any(
            str(token).casefold() in normalized
            for token in rule.get("path_contains", [])
        ):
            return (
                str(rule["family_key"]),
                str(rule["family_label"]),
            )

    return None


def _scope_and_source_for_exact_path(
    path: str,
    listing_pages: list[dict[str, Any]],
) -> tuple[str, str]:
    """
    exact_path için en uzun eşleşen allowed_prefix'i bulur.

    Böylece config'teki doğrudan seed URL'nin kapsamı
    (bireysel/ticari) listing page yapısından türetilir.
    """
    path_key = (path.rstrip("/") or "/").casefold()

    matches: list[tuple[int, str, str]] = []

    for source in listing_pages:
        prefix = str(
            source.get("allowed_prefix", "/")
        ).casefold()

        if path_key.startswith(prefix):
            matches.append(
                (
                    len(prefix),
                    str(source.get("scope", "bireysel")),
                    str(source.get("url", "")),
                )
            )

    if matches:
        _, scope, source_url = max(
            matches,
            key=lambda item: item[0],
        )
        return scope, source_url

    # Son çare: yol semantiğinden kapsam çıkar.
    if (
        "/ticari/" in path_key
        or "/kobi/" in path_key
        or "/isim-icin/" in path_key
    ):
        return "ticari", ""

    return "bireysel", ""


def _seed_config_exact_paths(
    bank: dict[str, Any],
    *,
    result: dict[str, StandardProductLink],
    excluded: set[str],
    rules: list[dict[str, Any]],
) -> None:
    """
    Config'te özellikle exact_paths olarak tanımlanan aktif
    ürün URL'lerini doğrudan discovery adayına ekler.

    Bu davranış yalnız bank config'inde:
        "seed_exact_paths": true
    olduğunda çalışır.

    Listing HTML'inde link eksik/JS ile üretilmiş olsa bile
    beklenen aktif ürünün sessizce kaçmasını önler.
    """
    if not bool(bank.get("seed_exact_paths", False)):
        return

    base_url = str(bank["base_url"])
    listing_pages = list(
        bank.get("listing_pages", [])
    )

    for rule in rules:
        family_key = str(rule["family_key"])
        family_label = str(rule["family_label"])

        for raw_path in rule.get("exact_paths", []):
            path = str(raw_path).strip()
            if not path:
                continue

            path_key = (
                path.rstrip("/") or "/"
            ).casefold()

            if path_key in excluded:
                continue

            scope, source_url = (
                _scope_and_source_for_exact_path(
                    path,
                    listing_pages,
                )
            )

            absolute = canonicalize_url(
                urljoin(base_url, path)
            )

            result.setdefault(
                absolute,
                StandardProductLink(
                    bank_name=str(bank["name"]),
                    bank_slug=str(bank["slug"]),
                    product_family=family_label,
                    product_family_key=family_key,
                    url=absolute,
                    source_page=(
                        canonicalize_url(source_url)
                        if source_url
                        else absolute
                    ),
                    scope=scope,
                ),
            )


def discover_standard_product_links(
    bank: dict[str, Any],
    *,
    timeout: int = 30,
) -> list[StandardProductLink]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/150 Safari/537.36"
            )
        }
    )

    result: dict[str, StandardProductLink] = {}

    excluded = {
        (str(item).rstrip("/") or "/").casefold()
        for item in bank.get("exclude_exact_paths", [])
    }
    rules = list(bank.get("family_rules", []))
    base_host = urlparse(str(bank["base_url"])).netloc.casefold()

    _seed_config_exact_paths(
        bank,
        result=result,
        excluded=excluded,
        rules=rules,
    )

    for source in bank.get("listing_pages", []):
        source_url = str(source["url"])
        response = session.get(
            source_url,
            timeout=timeout,
        )
        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        allowed_prefix = str(
            source.get(
                "allowed_prefix",
                "/kendim-icin/finansmanlar/",
            )
        ).casefold()

        # Listing page aynı zamanda gerçek bir ürün sayfasıysa
        # kendisini de discovery sonucuna dahil et.
        source_canonical = canonicalize_url(response.url)
        source_parsed = urlparse(source_canonical)
        source_path = (
            source_parsed.path.rstrip("/") or "/"
        )
        source_path_key = source_path.casefold()

        if (
            source_path_key.startswith(allowed_prefix)
            and source_path_key not in excluded
        ):
            source_family = resolve_family(
                source_path,
                rules,
            )
            if source_family is not None:
                family_key, family_label = source_family
                result[source_canonical] = StandardProductLink(
                    bank_name=str(bank["name"]),
                    bank_slug=str(bank["slug"]),
                    product_family=family_label,
                    product_family_key=family_key,
                    url=source_canonical,
                    source_page=source_canonical,
                    scope=str(source.get("scope", "bireysel")),
                )

        for anchor in soup.find_all("a", href=True):
            absolute = canonicalize_url(
                urljoin(response.url, anchor["href"])
            )
            parsed = urlparse(absolute)

            if parsed.netloc.casefold() != base_host:
                continue

            path = parsed.path.rstrip("/") or "/"
            path_key = path.casefold()

            if not path_key.startswith(allowed_prefix):
                continue

            if path_key in excluded:
                continue

            family = resolve_family(path, rules)
            if family is None:
                continue

            family_key, family_label = family

            result[absolute] = StandardProductLink(
                bank_name=str(bank["name"]),
                bank_slug=str(bank["slug"]),
                product_family=family_label,
                product_family_key=family_key,
                url=absolute,
                source_page=canonicalize_url(response.url),
                scope=str(source.get("scope", "bireysel")),
            )

    return sorted(
        result.values(),
        key=lambda item: (
            item.product_family,
            item.url,
        ),
    )


def write_discovery(
    links: list[StandardProductLink],
    output_path: str | Path,
) -> None:
    output = Path(output_path)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output.write_text(
        json.dumps(
            [asdict(item) for item in links],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
