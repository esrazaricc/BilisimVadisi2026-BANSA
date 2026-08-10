from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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

from src.scraping.browser_renderer import (
    RenderResult,
    render_dynamic_page,
)
from src.scraping.http_client import HttpClient
from src.scraping.campaign_status import detect_listing_status


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
    source_group: str = ""
    listing_status: str = "unknown"
    status_evidence: str = ""
    listing_text: str = ""
    listing_start_date: str = ""
    listing_end_date: str = ""
    status_checked_at: str = ""


@dataclass(frozen=True)
class DiscoveryDiagnostic:
    bank_name: str
    source_page: str
    render_mode: str
    load_more_clicks: int
    rendered_detail_link_count: int
    discovered_count: int
    reference_visible_count: int | None
    completeness_status: str
    reached_click_limit: bool


def load_bank_config(
    path: str | Path = Path("config") / "banks.json",
) -> list[dict[str, Any]]:
    config_path = Path(path)
    return json.loads(config_path.read_text(encoding="utf-8"))



def campaign_sources(bank: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Bankanın kampanya kaynaklarını döndürür.

    Yeni yapıdaki ``campaign_sources`` her liste sayfası için farklı
    detay yolu, render yöntemi ve referans sayı tanımlamaya izin verir.
    Eski ``campaign_pages`` yapısı da geriye dönük olarak desteklenir.
    """
    configured = bank.get("campaign_sources", [])
    if configured:
        sources: list[dict[str, Any]] = []

        for item in configured:
            source = dict(bank)
            source.pop("campaign_sources", None)
            source.update(item)
            source["source_page"] = item["url"]
            sources.append(source)

        return sources

    return [
        {
            **bank,
            "source_page": source_page,
        }
        for source_page in bank.get("campaign_pages", [])
    ]


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


def normalized_path(value: str) -> str:
    parsed = urlparse(value)
    raw_path = parsed.path if parsed.scheme or parsed.netloc else value
    path = re.sub(r"/+", "/", raw_path or "/").casefold()
    if path != "/":
        path = path.rstrip("/")
    return path


def is_excluded(url: str, bank: dict[str, Any]) -> bool:
    if path_contains(url, bank.get("exclude_paths", [])):
        return True

    candidate_path = normalized_path(url)
    exact_paths = {
        normalized_path(item)
        for item in bank.get("exclude_exact_paths", [])
    }
    if candidate_path in exact_paths:
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


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )


def _listing_context(link: Any) -> str:
    anchor_text = " ".join(link.stripped_strings)
    candidates: list[str] = []

    parent = link
    for _ in range(6):
        parent = getattr(parent, "parent", None)
        if parent is None:
            break

        name = getattr(parent, "name", "")
        classes = " ".join(parent.get("class", []))
        identity = f"{name} {classes}".casefold()

        if (
            name in {"article", "li"}
            or any(
                marker in identity
                for marker in (
                    "campaign",
                    "kampanya",
                    "card",
                    "item",
                    "slide",
                    "content",
                )
            )
        ):
            text = " ".join(parent.stripped_strings)
            if text:
                candidates.append(text)

    if candidates:
        suitable = [
            text for text in candidates
            if len(text) <= 1500
        ]
        if suitable:
            return min(suitable, key=len)
        return min(candidates, key=len)[:1500]

    return anchor_text


def discover_from_html(
    *,
    bank: dict[str, Any],
    source_page: str,
    html: str,
) -> list[DiscoveredPage]:
    soup = BeautifulSoup(html, "html.parser")
    source_canonical = canonicalize_url(source_page)
    checked_at = _utc_now_iso()

    found: dict[str, DiscoveredPage] = {}

    for link in soup.find_all("a", href=True):
        absolute = urljoin(source_page, link.get("href", "").strip())
        canonical = canonicalize_url(absolute)
        anchor_text = " ".join(link.stripped_strings)

        if canonical == source_canonical:
            continue
        if not is_detail_candidate(canonical, anchor_text, bank):
            continue

        listing_text = _listing_context(link)
        listing_status, evidence = detect_listing_status(
            listing_text
        )

        found[canonical] = DiscoveredPage(
            bank_name=bank["name"],
            url=canonical,
            source_page=source_canonical,
            page_type="campaign_detail",
            discovery_mode=bank.get(
                "discovery_mode",
                "detail_links",
            ),
            source_group=bank.get(
                "source_group",
                "Kampanyalar",
            ),
            listing_status=listing_status,
            status_evidence=evidence,
            listing_text=listing_text,
            status_checked_at=checked_at,
        )

    if found:
        return sorted(found.values(), key=lambda item: item.url)

    if bank.get("discovery_mode") == "single_listing_page":
        listing_text = " ".join(soup.stripped_strings)[:1500]
        listing_status, evidence = detect_listing_status(
            listing_text
        )
        return [
            DiscoveredPage(
                bank_name=bank["name"],
                url=source_canonical,
                source_page=source_canonical,
                page_type="campaign_listing_content",
                discovery_mode="single_listing_page",
                source_group=bank.get(
                    "source_group",
                    "Kampanyalar",
                ),
                listing_status=listing_status,
                status_evidence=evidence,
                listing_text=listing_text,
                status_checked_at=checked_at,
            )
        ]

    return []


_DYNAMIC_GENERIC_LINK_TEXTS = {
    "",
    "detay",
    "incele",
    "daha fazla",
    "kampanyayı incele",
    "kampanyayi incele",
    "hemen incele",
    "kampanya detayları",
    "kampanya detaylari",
}


def _compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _dynamic_text_key(value: Any) -> str:
    return (
        _compact_text(value)
        .casefold()
        .replace("ı", "i")
        .replace("i̇", "i")
    )


def _dynamic_campaign_card(link: Any) -> Any:
    """Bağlantının ait olduğu Dünya Katılım kampanya kartını bulur."""
    parent = link
    for _ in range(8):
        parent = getattr(parent, "parent", None)
        if parent is None:
            break

        classes = {
            str(item).casefold()
            for item in parent.get("class", [])
        }
        if "page-campaigns-content-item" in classes:
            return parent

    return None


def _dynamic_listing_title(link: Any) -> str:
    """
    Dünya Katılım API parçasındaki kampanya kartından gerçek başlığı alır.

    Kartın detay bağlantısında ``Kampanya Detayları`` yazdığı için
    bağlantı metni başlık olarak kullanılmaz; öncelik kart içindeki h3
    alanındadır.
    """
    card = _dynamic_campaign_card(link)
    if card is not None:
        heading = card.select_one("h3")
        if heading is not None:
            title = _compact_text(" ".join(heading.stripped_strings))
            if title:
                return title

    anchor_text = _compact_text(" ".join(link.stripped_strings))
    if _dynamic_text_key(anchor_text) not in _DYNAMIC_GENERIC_LINK_TEXTS:
        return anchor_text

    parent = link
    for _ in range(6):
        parent = getattr(parent, "parent", None)
        if parent is None:
            break

        for selector in (
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            ".campaign-title",
            ".kampanya-title",
            ".card-title",
            "[class*='title']",
        ):
            candidate = parent.select_one(selector)
            if candidate is None:
                continue

            title = _compact_text(" ".join(candidate.stripped_strings))
            if (
                title
                and _dynamic_text_key(title)
                not in _DYNAMIC_GENERIC_LINK_TEXTS
            ):
                return title

    return _compact_text(_listing_context(link))


_TURKISH_MONTH_NUMBERS = {
    "ocak": 1,
    "subat": 2,
    "mart": 3,
    "nisan": 4,
    "mayis": 5,
    "haziran": 6,
    "temmuz": 7,
    "agustos": 8,
    "eylul": 9,
    "ekim": 10,
    "kasim": 11,
    "aralik": 12,
}


def _dynamic_date_key(value: Any) -> str:
    """
    Türkçe tarih metnini regex karşılaştırması için sadeleştirir.

    Örnek:
    ``Bitiş Tarihi: 31 Ağustos 2026``
    -> ``bitis tarihi: 31 agustos 2026``
    """
    return _dynamic_text_key(value).translate(
        str.maketrans(
            {
                "ç": "c",
                "ğ": "g",
                "ö": "o",
                "ş": "s",
                "ü": "u",
            }
        )
    )


def _dynamic_iso_dates(raw_text: str) -> list[str]:
    """
    Kart metnindeki sayısal ve Türkçe ay adlı tarihleri, metindeki
    sıralarını koruyarak ISO biçimine çevirir.
    """
    normalized = _dynamic_date_key(raw_text)
    hits: list[tuple[int, str]] = []

    numeric_pattern = re.compile(
        r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)"
    )
    for match in numeric_pattern.finditer(normalized):
        day, month, year = match.groups()
        try:
            iso_value = (
                f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
            )
        except ValueError:
            continue
        hits.append((match.start(), iso_value))

    named_pattern = re.compile(
        r"(?<!\d)(\d{1,2})\s+"
        r"(ocak|subat|mart|nisan|mayis|haziran|temmuz|"
        r"agustos|eylul|ekim|kasim|aralik)\s+"
        r"(\d{4})(?!\d)"
    )
    for match in named_pattern.finditer(normalized):
        day, month_name, year = match.groups()
        month = _TURKISH_MONTH_NUMBERS[month_name]
        iso_value = (
            f"{int(year):04d}-{month:02d}-{int(day):02d}"
        )
        hits.append((match.start(), iso_value))

    ordered: list[str] = []
    for _, iso_value in sorted(hits, key=lambda item: item[0]):
        if iso_value not in ordered:
            ordered.append(iso_value)

    return ordered


def _dynamic_listing_dates(link: Any) -> tuple[str, str, str]:
    """
    Kampanya kartındaki başlangıç/bitiş tarihlerini ISO biçiminde döndürür.

    Hem ``31.08.2026`` hem de ``31 Ağustos 2026`` biçimleri desteklenir.

    Dönüş: ``(start_date, end_date, raw_date_text)``.
    """
    card = _dynamic_campaign_card(link)
    if card is None:
        return "", "", ""

    date_node = card.select_one(".date")
    raw_text = _compact_text(
        " ".join(date_node.stripped_strings)
        if date_node is not None
        else ""
    )
    if not raw_text:
        return "", "", ""

    iso_dates = _dynamic_iso_dates(raw_text)
    lowered = _dynamic_date_key(raw_text)

    if (
        "baslangic" in lowered
        and "bitis" in lowered
        and len(iso_dates) >= 2
    ):
        return iso_dates[0], iso_dates[-1], raw_text

    if "baslangic" in lowered and iso_dates:
        return iso_dates[0], "", raw_text

    if "bitis" in lowered and iso_dates:
        return "", iso_dates[-1], raw_text

    return "", (iso_dates[-1] if iso_dates else ""), raw_text

def _discover_dynamic_fragment(
    *,
    bank: dict[str, Any],
    source_page: str,
    html: str,
    source_group: str,
) -> list[DiscoveredPage]:
    """
    ``GetCampaigns`` JSON yanıtındaki HTML parçasını kampanya
    kayıtlarına dönüştürür.

    Endpoint ``showHistory=false`` ile çağrıldığı için dönen bütün
    kampanyalar aktif liste kanıtı taşır.
    """
    soup = BeautifulSoup(html, "html.parser")
    source_canonical = canonicalize_url(source_page)
    checked_at = _utc_now_iso()
    evidence = (
        "Dünya Katılım GetCampaigns endpoint'i "
        "showHistory=false ile aktif kampanyaları döndürdü."
    )

    found: dict[str, DiscoveredPage] = {}

    for link in soup.find_all("a", href=True):
        absolute = urljoin(
            source_page,
            link.get("href", "").strip(),
        )
        canonical = canonicalize_url(absolute)
        title = _dynamic_listing_title(link)
        listing_start_date, listing_end_date, date_text = (
            _dynamic_listing_dates(link)
        )

        if canonical == source_canonical:
            continue
        if not is_detail_candidate(canonical, title, bank):
            continue

        found[canonical] = DiscoveredPage(
            bank_name=bank["name"],
            url=canonical,
            source_page=source_canonical,
            page_type="campaign_detail",
            discovery_mode="detail_links_dynamic",
            source_group=source_group,
            listing_status="active",
            status_evidence=(
                f"{evidence} Kart tarih bilgisi: {date_text}"
                if date_text
                else evidence
            ),
            listing_text=title,
            listing_start_date=listing_start_date,
            listing_end_date=listing_end_date,
            status_checked_at=checked_at,
        )

    return sorted(found.values(), key=lambda item: item.url)


def _dynamic_api_request_url(
    endpoint: str,
    *,
    campaign_type: int,
    site_id: int,
    category_id: int,
    page_number: int,
    show_history: bool,
) -> str:
    query = urlencode(
        {
            "campaignType": campaign_type,
            "siteId": site_id,
            "query": "",
            "categoryId": category_id,
            "totalPage": page_number,
            "showHistory": str(show_history).casefold(),
        }
    )
    separator = "&" if "?" in endpoint else "?"
    return f"{endpoint}{separator}{query}"


def discover_dynamic_api_pages(
    bank: dict[str, Any],
    client: HttpClient,
) -> tuple[
    list[DiscoveredPage],
    list[dict[str, str]],
    list[DiscoveryDiagnostic],
]:
    """
    Dünya Katılım'ın ``GetCampaigns`` JSON endpoint'inden tüm bireysel
    ve ticari kampanya kartlarını toplar.
    """
    settings = bank.get("dynamic_api", {})
    endpoint = str(settings.get("url", "")).strip()

    if not endpoint:
        raise ValueError(
            f"{bank['name']} dynamic_api.url tanımlı değil."
        )

    source_page = canonicalize_url(
        str(
            settings.get("source_page")
            or bank.get("campaign_pages", [""])[0]
        )
    )
    campaign_types = [
        int(value)
        for value in settings.get(
            "campaign_types",
            [1, 2],
        )
    ]
    category_ids = [
        int(value)
        for value in settings.get(
            "category_ids",
            list(range(13)),
        )
    ]
    maximum_pages = max(
        1,
        int(settings.get("maximum_pages", 30)),
    )
    site_id = int(settings.get("site_id", 1))
    show_history = bool(
        settings.get("show_history", False)
    )
    reference_count = settings.get(
        "reference_visible_count"
    )
    if reference_count is not None:
        reference_count = int(reference_count)

    source_groups = {
        str(key): str(value)
        for key, value in settings.get(
            "source_groups",
            {
                "1": "Dünya Katılım Kendim İçin",
                "2": "Dünya Katılım İşim İçin",
            },
        ).items()
    }

    pages: dict[str, DiscoveredPage] = {}
    errors: list[dict[str, str]] = []
    request_count = 0

    for campaign_type in campaign_types:
        source_group = source_groups.get(
            str(campaign_type),
            f"Kampanya Türü {campaign_type}",
        )

        for category_id in category_ids:
            previous_total = len(pages)

            for page_number in range(1, maximum_pages + 1):
                request_url = _dynamic_api_request_url(
                    endpoint,
                    campaign_type=campaign_type,
                    site_id=site_id,
                    category_id=category_id,
                    page_number=page_number,
                    show_history=show_history,
                )

                try:
                    result = client.get(request_url)
                    request_count += 1
                    payload = json.loads(result.text)
                except Exception as error:
                    errors.append(
                        {
                            "bank_name": bank["name"],
                            "source_page": request_url,
                            "render_mode": "requests_json",
                            "error_type": type(error).__name__,
                            "message": str(error),
                        }
                    )
                    break

                if not isinstance(payload, dict):
                    errors.append(
                        {
                            "bank_name": bank["name"],
                            "source_page": request_url,
                            "render_mode": "requests_json",
                            "error_type": "InvalidPayload",
                            "message": (
                                "GetCampaigns yanıtı JSON nesnesi değil."
                            ),
                        }
                    )
                    break

                fragment = str(payload.get("view") or "")
                discovered = _discover_dynamic_fragment(
                    bank=bank,
                    source_page=source_page,
                    html=fragment,
                    source_group=source_group,
                )

                before_page = len(pages)
                for page in discovered:
                    pages[page.url] = page
                added_count = len(pages) - before_page

                all_read = payload.get("allRead") is True

                if not fragment.strip():
                    break
                if all_read:
                    break
                if not discovered or added_count == 0:
                    break

            if len(pages) == previous_total:
                continue

    discovered_pages = sorted(
        pages.values(),
        key=lambda item: item.url,
    )
    completeness = _completeness_status(
        len(discovered_pages),
        reference_count,
        False,
    )

    diagnostics = [
        DiscoveryDiagnostic(
            bank_name=bank["name"],
            source_page=source_page,
            render_mode="requests_json",
            load_more_clicks=request_count,
            rendered_detail_link_count=len(discovered_pages),
            discovered_count=len(discovered_pages),
            reference_visible_count=reference_count,
            completeness_status=completeness,
            reached_click_limit=False,
        )
    ]

    return discovered_pages, errors, diagnostics


def _url_with_page(url: str, page_number: int) -> str:
    """URL içindeki page parametresini güvenli biçimde değiştirir."""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page_number)
    return urlunparse(parsed._replace(query=urlencode(query)))


def discover_from_json_api(
    *,
    source: dict[str, Any],
    client: HttpClient,
) -> list[DiscoveredPage]:
    """
    Sayfalı JSON kampanya servisinden bütün detay bağlantılarını toplar.

    Toplam sayfa sayısı her çalıştırmada API yanıtından okunur. Böylece
    sonradan eklenen kampanyalar config değişikliği gerektirmeden keşfedilir.
    """
    api_url = source["source_page"]
    public_source_page = source.get("public_source_page", api_url)
    detail_url_prefix = source["detail_url_prefix"]
    maximum_pages = max(int(source.get("api_max_pages", 100)), 1)

    source_canonical = canonicalize_url(public_source_page)
    checked_at = _utc_now_iso()
    current_page = 1
    total_pages = 1
    found: dict[str, DiscoveredPage] = {}
    seen_page_signatures: set[tuple[str, ...]] = set()

    while current_page <= total_pages:
        if current_page > maximum_pages:
            raise RuntimeError(
                "JSON API güvenlik sayfa sınırı aşıldı: "
                f"{maximum_pages}"
            )

        page_url = _url_with_page(api_url, current_page)
        response = client.get(page_url)
        payload = json.loads(response.text)

        if not isinstance(payload, dict):
            raise ValueError(
                "Kampanya API yanıtı JSON nesnesi değil."
            )

        total_pages = max(
            int(payload.get("totalPageCount") or 1),
            1,
        )

        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValueError(
                "Kampanya API items alanı liste değil."
            )

        signature = tuple(
            str(item.get("link") or "").strip()
            for item in items
            if isinstance(item, dict)
        )
        if signature in seen_page_signatures and signature:
            raise RuntimeError(
                "Kampanya API aynı sayfayı tekrar döndürdü; "
                "sonsuz döngü engellendi."
            )
        seen_page_signatures.add(signature)

        for item in items:
            if not isinstance(item, dict):
                continue

            slug = str(item.get("link") or "").strip().strip("/")
            title = str(item.get("title") or "").strip()

            if not slug:
                continue

            detail_url = canonicalize_url(
                urljoin(
                    detail_url_prefix.rstrip("/") + "/",
                    slug,
                )
            )

            listing_status, evidence = detect_listing_status(title)

            found[detail_url] = DiscoveredPage(
                bank_name=source["name"],
                url=detail_url,
                source_page=source_canonical,
                page_type="campaign_detail",
                discovery_mode="json_api",
                source_group=source.get(
                    "source_group",
                    "Kampanyalar",
                ),
                listing_status=listing_status,
                status_evidence=evidence,
                listing_text=title,
                status_checked_at=checked_at,
            )

        current_page += 1

    return sorted(found.values(), key=lambda item: item.url)


def _completeness_status(
    discovered_count: int,
    reference_count: int | None,
    reached_click_limit: bool,
) -> str:
    if reached_click_limit:
        return "CLICK_LIMIT_REACHED"
    if reference_count is None:
        return "NOT_CHECKED"
    if discovered_count >= reference_count:
        return "COMPLETE_OR_HIGHER"
    return "BELOW_REFERENCE_COUNT"


def discover_bank_pages(
    bank: dict[str, Any],
    client: HttpClient,
    *,
    headless: bool = True,
    maximum_load_more_clicks: int | None = None,
) -> tuple[
    list[DiscoveredPage],
    list[dict[str, str]],
    list[DiscoveryDiagnostic],
]:
    pages: dict[str, DiscoveredPage] = {}
    errors: list[dict[str, str]] = []
    diagnostics: list[DiscoveryDiagnostic] = []

    if bank.get("discovery_mode") == "detail_links_dynamic":
        return discover_dynamic_api_pages(bank, client)

    for source in campaign_sources(bank):
        source_page = source["source_page"]
        render_mode = source.get("render_mode", "requests")
        render_result: RenderResult | None = None

        try:
            if render_mode == "json_api":
                discovered = discover_from_json_api(
                    source=source,
                    client=client,
                )
                final_url = source.get(
                    "public_source_page",
                    source_page,
                )
            elif render_mode == "selenium":
                render_result = render_dynamic_page(
                    source_page,
                    detail_paths=source.get("detail_paths", []),
                    load_more_terms=source.get(
                        "load_more_terms",
                        ["Daha Fazla Göster"],
                    ),
                    cookie_accept_terms=source.get(
                        "cookie_accept_terms",
                        [],
                    ),
                    headless=headless,
                    maximum_load_more_clicks=(
                        maximum_load_more_clicks
                        or source.get(
                            "maximum_load_more_clicks",
                            20,
                        )
                    ),
                )
                final_url = render_result.url
                html = render_result.html
            else:
                result = client.get(source_page)
                final_url = result.url
                html = result.text

            if render_mode != "json_api":
                discovered = discover_from_html(
                    bank=source,
                    source_page=final_url,
                    html=html,
                )
            for page in discovered:
                pages[page.url] = page

            reference_count = source.get("reference_visible_count")
            diagnostics.append(
                DiscoveryDiagnostic(
                    bank_name=bank["name"],
                    source_page=canonicalize_url(final_url),
                    render_mode=render_mode,
                    load_more_clicks=(
                        render_result.load_more_clicks
                        if render_result
                        else 0
                    ),
                    rendered_detail_link_count=(
                        render_result.detail_link_count
                        if render_result
                        else len(discovered)
                    ),
                    discovered_count=len(discovered),
                    reference_visible_count=reference_count,
                    completeness_status=_completeness_status(
                        len(discovered),
                        reference_count,
                        (
                            render_result.reached_click_limit
                            if render_result
                            else False
                        ),
                    ),
                    reached_click_limit=(
                        render_result.reached_click_limit
                        if render_result
                        else False
                    ),
                )
            )
        except Exception as error:
            errors.append(
                {
                    "bank_name": bank["name"],
                    "source_page": source_page,
                    "render_mode": render_mode,
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
            )

    return (
        sorted(pages.values(), key=lambda item: item.url),
        errors,
        diagnostics,
    )


def discover_all_pages(
    *,
    config_path: str | Path = Path("config") / "banks.json",
    bank_name: str | None = None,
    timeout: int = 30,
    delay_seconds: float = 1.0,
    headless: bool = True,
    maximum_load_more_clicks: int | None = None,
) -> tuple[
    list[DiscoveredPage],
    list[dict[str, str]],
    list[DiscoveryDiagnostic],
]:
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
    diagnostics: list[DiscoveryDiagnostic] = []

    with HttpClient(
        timeout=timeout,
        delay_seconds=delay_seconds,
    ) as client:
        for bank in banks:
            if not bank.get("campaign_pages"):
                continue

            bank_pages, bank_errors, bank_diagnostics = (
                discover_bank_pages(
                    bank,
                    client,
                    headless=headless,
                    maximum_load_more_clicks=(
                        maximum_load_more_clicks
                    ),
                )
            )
            errors.extend(bank_errors)
            diagnostics.extend(bank_diagnostics)

            for page in bank_pages:
                pages[(page.bank_name, page.url)] = page

    return (
        sorted(
            pages.values(),
            key=lambda item: (item.bank_name, item.url),
        ),
        errors,
        diagnostics,
    )


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    return value if isinstance(value, list) else []


def _item_bank_name(item: dict[str, Any]) -> str:
    return str(item.get("bank_name", "")).strip()


def _discovery_item_key(item: dict[str, Any]) -> tuple[str, str]:
    return (
        _item_bank_name(item).casefold(),
        canonicalize_url(str(item.get("url", ""))),
    )


def write_discovery_results(
    pages: list[DiscoveredPage],
    errors: list[dict[str, str]],
    diagnostics: list[DiscoveryDiagnostic],
    *,
    output_path: str | Path = (
        Path("data") / "discovered_campaign_pages.json"
    ),
    error_path: str | Path = (
        Path("data") / "campaign_discovery_errors.json"
    ),
    report_path: str | Path = (
        Path("data") / "campaign_discovery_report.json"
    ),
) -> None:
    """
    Banka bazlı çalıştırmalarda diğer bankaların sonuçlarını korur.

    Bir banka için başarılı ve en az bir bağlantı içeren yeni keşif
    geldiyse o bankanın eski keşif satırları yenileriyle değiştirilir.
    Hatalı veya sıfır sonuçlu taramada önceki başarılı sonuçlar silinmez.
    """
    output = Path(output_path)
    errors_output = Path(error_path)
    report_output = Path(report_path)

    output.parent.mkdir(parents=True, exist_ok=True)
    errors_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)

    new_page_rows = [asdict(page) for page in pages]
    new_error_rows = list(errors)
    new_diagnostic_rows = [
        asdict(item)
        for item in diagnostics
    ]

    error_banks = {
        _item_bank_name(item).casefold()
        for item in new_error_rows
        if _item_bank_name(item)
    }
    diagnostic_banks = {
        item.bank_name.casefold()
        for item in diagnostics
    }
    # reference_visible_count geçmişte gözlenen kampanya sayısıdır.
    # Aktif kampanya sayısı doğal olarak azalabileceği için
    # BELOW_REFERENCE_COUNT tek başına keşif hatası değildir.
    # Yalnızca teknik olarak sayfalama/tıklama limiti tamamlanamadıysa
    # eski başarılı keşfi koruruz.
    incomplete_banks = {
        item.bank_name.casefold()
        for item in diagnostics
        if item.completeness_status == "CLICK_LIMIT_REACHED"
    }
    positive_banks = {
        item.bank_name.casefold()
        for item in diagnostics
        if item.discovered_count > 0
    }
    successful_banks = (
        diagnostic_banks
        & positive_banks
    ) - error_banks - incomplete_banks

    existing_pages = _read_json_list(output)
    merged_pages = [
        item
        for item in existing_pages
        if _item_bank_name(item).casefold()
        not in successful_banks
    ]
    merged_pages.extend(
        item
        for item in new_page_rows
        if _item_bank_name(item).casefold()
        in successful_banks
    )

    page_map: dict[tuple[str, str], dict[str, Any]] = {}
    for item in merged_pages:
        key = _discovery_item_key(item)
        if key[0] and key[1]:
            page_map[key] = item

    final_pages = sorted(
        page_map.values(),
        key=lambda item: (
            _item_bank_name(item).casefold(),
            canonicalize_url(str(item.get("url", ""))),
        ),
    )

    touched_banks = {
        _item_bank_name(item).casefold()
        for item in new_error_rows
        if _item_bank_name(item)
    } | {
        _item_bank_name(item).casefold()
        for item in new_diagnostic_rows
        if _item_bank_name(item)
    }

    existing_errors = _read_json_list(errors_output)
    final_errors = [
        item
        for item in existing_errors
        if _item_bank_name(item).casefold()
        not in touched_banks
    ]
    final_errors.extend(new_error_rows)

    existing_diagnostics = _read_json_list(report_output)
    final_diagnostics = [
        item
        for item in existing_diagnostics
        if _item_bank_name(item).casefold()
        not in touched_banks
    ]
    final_diagnostics.extend(new_diagnostic_rows)

    output.write_text(
        json.dumps(
            final_pages,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    errors_output.write_text(
        json.dumps(
            final_errors,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    report_output.write_text(
        json.dumps(
            final_diagnostics,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )