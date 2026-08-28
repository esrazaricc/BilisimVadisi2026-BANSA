from __future__ import annotations


import sys
import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag

from src.scraping.browser_renderer import render_dynamic_page
from src.scraping.campaign_discovery import (
    canonicalize_url,
    load_bank_config,
)
from src.scraping.http_client import HttpClient
from src.scraping.campaign_status import evaluate_campaign_status



def _configure_utf8_console() -> None:
    """
    Kampanya başlıklarında emoji/Unicode karakterleri bulunabilir.

    Windows'un legacy cp1254/charmap stdout kodlaması bu karakterleri
    yazdıramadığında fetch işleminin kendisi başarılı olsa bile print()
    UnicodeEncodeError fırlatabiliyordu. Stdout/stderr UTF-8'e alınır;
    desteklenmeyen ortamlarda ise sessizce mevcut ayar korunur.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


_configure_utf8_console()

MIN_ACCEPTABLE_TEXT_LENGTH = 120

TITLE_SELECTORS = [
    ".campaign-detail h1",
    ".campaign-detail h2",
    ".campaign-detail h3",
    ".campaign-detail h4",
    ".campaign-detail-content h1",
    ".campaign-detail-content h2",
    ".campaign-detail-content h3",
    ".campaign-detail-content h4",
    "[class*='campaign-detail'] h1",
    "[class*='campaign-detail'] h2",
    "[class*='campaign-detail'] h3",
    "[class*='campaign-detail'] h4",
    "article h1",
    "article h2",
    "article h3",
    "article h4",
    "main h1",
    "main h2",
    "main h3",
    "main h4",
    ".campaign-title",
    ".campaign-detail-title",
    ".detail-title",
    ".page-title",
    "h1",
    "h2",
]

GENERIC_TITLE_KEYS = {
    "kuveyt turk katilim bankasi",
    "kuveyt turk",
    "albaraka turk",
    "kampanya",
    "kampanyalar",
    "kampanyalar kuveyt turk katilim bankasi",
    "kampanyalar kuveyt turk",
    "kuveyt turk katilim bankasi kampanyalar",
    "ana sayfa",
}

TITLE_NOISE_KEYS = {
    "blog",
    "kuveyt turk blog",
    "bireysel",
    "ticari",
    "kurumsal",
    "urunler",
    "hizmetler",
    "finansmanlar",
    "kampanyayi kesfet",
    "detayli bilgi",
    "hemen basvur",
    "basvur",
    "incele",
    "daha fazla",
}


CONTENT_SELECTORS = [
    ".campaign-detail",
    ".campaign-detail-content",
    ".campaign-content",
    ".detail-content",
    ".content-area",
    ".page-content",
    ".editor-content",
    "article",
    "main",
    "[role='main']",
    "#content",
]

UNWANTED_SELECTORS = [
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    ".breadcrumb",
    ".breadcrumbs",
    ".cookie",
    ".cookies",
    ".cookie-banner",
    ".cookie-policy",
    ".modal",
    ".popup",
    ".chat",
    ".chatbot",
    ".social",
    ".share",
    ".menu",
    ".navbar",
    ".footer",
    ".header",
    ".related",
    ".related-content",
    ".sticky",
    ".campaign-text [style*='display:none']",
    ".campaign-text [style*='display: none']",
]

TAIL_MARKERS = [
    "Çerez Ayarları",
    "Çerez Politikası",
    "Tüm Hakları Saklıdır",
    "Bize Ulaşın",
    "Şubeler ve ATM",
    "Müşteri İletişim Merkezi",
]

CAMPAIGN_CONTEXT_TERMS = (
    "kampanya",
    "koşul",
    "katılım",
    "ödül",
    "indirim",
    "taksit",
    "harcama",
    "geçerlilik",
)


@dataclass(frozen=True)
class CampaignPageSnapshot:
    bank_name: str
    title: str
    url: str
    requested_url: str
    source_page: str
    page_type: str
    discovery_mode: str
    source_group: str
    listing_status: str
    listing_status_evidence: str
    fetch_method: str
    http_status: int
    content_type: str
    raw_text: str
    clean_text: str
    content_hash: str
    text_length: int
    campaign_start_date: str
    campaign_end_date: str
    current_status: str
    status_reason: str
    status_evidence: str
    status_checked_at: str
    first_seen_at: str
    last_checked_at: str
    fetch_status: str


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = unicodedata.normalize("NFKC", str(value))
    text = (
        text.replace("\u200b", " ")
        .replace("\ufeff", " ")
        .replace("\xa0", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


def search_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", normalize_text(value))
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", text.casefold()).strip()



TOM_HADI_TAIL_MARKERS = (
    "İlginizi Çekebilir",
    "Ilginizi Cekebilir",
    "Kampanya Detayı Hadi Black Kredi Kartı",
    "Kampanya Detayi Hadi Black Kredi Karti",
    "Hadi bir T.O.M. Katılım Bankası",
    "Hadi bir T.O.M. Katilim Bankasi",
)



def extract_tom_hadi_date_header(text: str) -> str:
    """
    Hadi sayfalarında kampanya başlangıç/bitiş bilgisi çoğu zaman H1
    başlığından ÖNCE yer alır. Ana içerik temizlenirken bu alanı kaybetmemek
    için normalize edilmiş bir "Kampanya Tarihleri ..." satırı döndürür.
    """
    normalized = normalize_text(text)
    if not normalized:
        return ""

    month = (
        r"(?:Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|Temmuz|"
        r"Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|Aralık|Aralik)"
    )
    named_date = rf"\d{{1,2}}\s+{month}(?:\s+\d{{4}})?"
    numeric_date = r"\d{1,2}[./-]\d{1,2}[./-]\d{4}"
    date_token = rf"(?:{named_date}|{numeric_date})"

    patterns = (
        rf"Kampanya\s+Tarihleri\s+({date_token}\s*[-–—]\s*{date_token})",
        rf"Kampanya\s+Tarihleri\s+({date_token}\s+(?:ile|ve)\s+{date_token})",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )
        if match:
            return normalize_text(
                f"Kampanya Tarihleri {match.group(1)}"
            )

    return ""

def trim_tom_hadi_campaign_text(
    text: str,
    *,
    title: str = "",
) -> str:
    """
    T.O.M./Hadi sayfalarında ana kampanyaya ait olmayan navigasyon ve
    'İlginizi Çekebilir' kartlarını temizler.
    """
    original = normalize_text(text)
    if not original:
        return ""

    date_header = extract_tom_hadi_date_header(original)
    cleaned = original

    # Related/footer bölümünü kes.
    positions: list[int] = []
    for marker in TOM_HADI_TAIL_MARKERS:
        match = re.search(
            re.escape(marker),
            cleaned,
            flags=re.IGNORECASE,
        )
        if match:
            positions.append(match.start())
    if positions:
        candidate = normalize_text(cleaned[:min(positions)])
        if len(candidate) >= 60:
            cleaned = candidate

    title_core = normalize_text(title).split("|", 1)[0].strip()

    # Sayfada gerçek başlık varsa son eşleşmeden başla. Navigasyon üstte kalır.
    if title_core:
        matches = list(
            re.finditer(
                re.escape(title_core),
                cleaned,
                flags=re.IGNORECASE,
            )
        )
        if matches:
            candidate = normalize_text(
                cleaned[matches[-1].start():]
            )
            if len(candidate) >= 60:
                cleaned = candidate

    # Bazı Hadi sayfalarında H1 temizlenmiş olabilir; ana içerik
    # navigasyonun sonundaki "Hemen İndir" sonrasında başlar.
    matches = list(
        re.finditer(
            r"Hemen\s+İndir",
            cleaned,
            flags=re.IGNORECASE,
        )
    )
    if matches:
        candidate = normalize_text(
            cleaned[matches[-1].end():]
        )
        if len(candidate) >= 60:
            cleaned = candidate

    # İkinci kez tail kontrolü.
    positions = []
    for marker in TOM_HADI_TAIL_MARKERS:
        match = re.search(
            re.escape(marker),
            cleaned,
            flags=re.IGNORECASE,
        )
        if match:
            positions.append(match.start())
    if positions:
        candidate = normalize_text(cleaned[:min(positions)])
        if len(candidate) >= 60:
            cleaned = candidate

    # Başlık tekrarını kaldır.
    if title_core:
        cleaned = re.sub(
            rf"^\s*{re.escape(title_core)}\s*",
            " ",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        )

    result = normalize_text(cleaned)
    if len(result) < 60:
        result = original

    if date_header and search_key(date_header) not in search_key(result):
        result = normalize_text(f"{date_header} {result}")

    return result

def unwrap_url(value: Any) -> str:
    """Eski veya iç içe JSON kayıtlarından URL metnini güvenli alır."""
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        for key in ("url", "href", "value"):
            if key in value:
                candidate = unwrap_url(value[key])
                if candidate:
                    return candidate

    return ""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hash_text(text: str) -> str:
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_discovered_pages(
    path: str | Path = (
        Path("data") / "discovered_campaign_pages.json"
    ),
    *,
    bank_name: str | None = None,
) -> list[dict[str, str]]:
    input_path = Path(path)
    raw_items = json.loads(input_path.read_text(encoding="utf-8"))

    wanted_bank = search_key(bank_name) if bank_name else ""
    pages: dict[tuple[str, str], dict[str, str]] = {}

    for item in raw_items:
        bank = normalize_text(item.get("bank_name", ""))
        url = unwrap_url(item.get("url"))
        source_page = unwrap_url(item.get("source_page"))

        if not bank or not url:
            continue
        if wanted_bank and search_key(bank) != wanted_bank:
            continue

        canonical = canonicalize_url(url)
        pages[(search_key(bank), canonical)] = {
            "bank_name": bank,
            "url": canonical,
            "source_page": (
                canonicalize_url(source_page)
                if source_page
                else ""
            ),
            "page_type": normalize_text(
                item.get("page_type", "campaign_detail")
            ),
            "discovery_mode": normalize_text(
                item.get("discovery_mode", "")
            ),
            "source_group": normalize_text(
                item.get("source_group", "")
            ),
            "listing_status": normalize_text(
                item.get("listing_status", "unknown")
            ),
            "status_evidence": normalize_text(
                item.get("status_evidence", "")
            ),
            "listing_text": normalize_text(
                item.get("listing_text", "")
            ),
        }

    return sorted(
        pages.values(),
        key=lambda item: (item["bank_name"], item["url"]),
    )


def _remove_unwanted_nodes(soup: BeautifulSoup) -> None:
    for selector in UNWANTED_SELECTORS:
        for node in soup.select(selector):
            # SharePoint/ASP.NET sayfalarında tüm görünür kampanya
            # içeriği ana <form id="aspnetForm"> etiketi içinde olabilir.
            # Formu decompose() etmek bütün çocuklarıyla birlikte gerçek
            # kampanya metnini siler. Yalnızca form etiketini kaldırıp
            # içeriğini koruruz.
            if getattr(node, "name", "") == "form":
                node.unwrap()
            else:
                node.decompose()

    suspicious_terms = (
        "cookie",
        "cerez",
        "çerez",
        "chatbot",
        "breadcrumb",
        "social",
        "share",
        "footer",
        "header",
        "navigation",
    )

    for node in list(soup.find_all(True)):
        # Bir üst düğüm decompose() ile silindiyse BeautifulSoup,
        # alt düğümün attrs alanını None yapabilir. Böyle bir düğümde
        # node.get(...) çağrısı AttributeError üretir.
        attrs = getattr(node, "attrs", None)
        if not isinstance(attrs, dict):
            continue

        node_id = attrs.get("id", "")
        node_classes = attrs.get("class", [])
        if isinstance(node_classes, str):
            node_classes = [node_classes]

        identity = " ".join(
            [
                normalize_text(node_id),
                normalize_text(" ".join(node_classes)),
            ]
        )
        identity_key = search_key(identity)

        if identity_key and any(
            term in identity_key
            for term in suspicious_terms
        ):
            node.decompose()


def _candidate_text(node: Tag) -> str:
    return normalize_text(node.get_text(" ", strip=True))


def title_compare_key(value: Any) -> str:
    key = search_key(value)
    return key.translate(
        str.maketrans(
            {
                "ı": "i",
                "ş": "s",
                "ğ": "g",
                "ç": "c",
                "ö": "o",
                "ü": "u",
            }
        )
    )


def is_generic_title(
    title: str,
    *,
    bank_name: str = "",
) -> bool:
    key = title_compare_key(title)
    if not key:
        return True

    if key in GENERIC_TITLE_KEYS:
        return True

    bank_key = title_compare_key(bank_name)
    if bank_key and key in {
        bank_key,
        f"{bank_key} bankasi",
        f"{bank_key} bankasi a.s.",
        f"{bank_key} bankasi as",
        f"{bank_key} katilim bankasi",
        f"{bank_key} katilim bankasi a.s.",
        f"{bank_key} katilim bankasi as",
    }:
        return True

    return False



def strip_site_title_suffix(
    title: str,
    *,
    bank_name: str = "",
) -> str:
    """
    SEO başlıklarındaki site/banka ekini kaldırır.

    Örnek:
    "Kampanya Adı | Kuveyt Türk Katılım Bankası"
    ->
    "Kampanya Adı"
    """
    cleaned = normalize_text(title)
    if not cleaned:
        return ""

    bank_key = title_compare_key(bank_name)

    while True:
        separators = list(
            re.finditer(
                r"\s*(?:\||•)\s*|\s+[–—-]\s+",
                cleaned,
            )
        )
        if not separators:
            break

        separator = separators[-1]
        suffix = normalize_text(cleaned[separator.end():])
        suffix_key = title_compare_key(suffix)

        is_bank_suffix = (
            bool(bank_key)
            and bank_key in suffix_key
            and len(suffix) <= 100
        )
        is_generic_suffix = is_generic_title(
            suffix,
            bank_name=bank_name,
        )

        if not (is_bank_suffix or is_generic_suffix):
            break

        cleaned = normalize_text(
            cleaned[:separator.start()]
        )

    return cleaned


def is_usable_title(
    title: str,
    *,
    bank_name: str = "",
) -> bool:
    normalized = normalize_text(title)
    key = title_compare_key(normalized)

    if not normalized or len(normalized) < 4:
        return False
    if len(normalized) > 220:
        return False
    if is_generic_title(
        normalized,
        bank_name=bank_name,
    ):
        return False
    if key in TITLE_NOISE_KEYS:
        return False
    if key.startswith("kampanya araligi"):
        return False
    if key.startswith("kampanya tarihleri"):
        return False

    return True


def title_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    slug = unquote(path.rsplit("/", 1)[-1])
    slug = re.sub(r"[-_]+", " ", slug)
    slug = normalize_text(slug)

    if not slug:
        return ""

    special_words = {
        "hgs": "HGS",
        "kobi": "KOBİ",
        "pos": "POS",
        "mtv": "MTV",
        "troy": "TROY",
        "tl": "TL",
        "eft": "EFT",
        "atm": "ATM",
        "kktc": "KKTC",
    }
    turkish_words = {
        "arac": "Araç",
        "ozel": "Özel",
        "musteri": "Müşteri",
        "musterilere": "Müşterilere",
        "firsati": "Fırsatı",
        "kampanyasi": "Kampanyası",
        "finansmani": "Finansmanı",
        "ihtiyac": "İhtiyaç",
        "saglik": "Sağlık",
        "egitim": "Eğitim",
        "odeme": "Ödeme",
        "odemelerinizde": "Ödemelerinizde",
        "taksit": "Taksit",
        "tasit": "Taşıt",
        "alisveris": "Alışveriş",
        "akaryakit": "Akaryakıt",
        "kazanin": "Kazanın",
        "hediye": "Hediye",
        "indirim": "İndirim",
    }

    words: list[str] = []
    for raw_word in slug.split():
        key = raw_word.casefold()

        if key in special_words:
            words.append(special_words[key])
        elif key in turkish_words:
            words.append(turkish_words[key])
        elif re.fullmatch(r"\d+(?:\.\d+)?", raw_word):
            words.append(raw_word)
        else:
            words.append(raw_word[:1].upper() + raw_word[1:])

    return " ".join(words)


def _json_ld_title_candidates(
    value: Any,
) -> list[str]:
    candidates: list[str] = []

    if isinstance(value, dict):
        for key in ("headline", "name"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                candidates.append(candidate)

        for child in value.values():
            candidates.extend(_json_ld_title_candidates(child))

    elif isinstance(value, list):
        for child in value:
            candidates.extend(_json_ld_title_candidates(child))

    return candidates


def extract_title(
    soup: BeautifulSoup,
    *,
    bank_name: str = "",
    url: str = "",
) -> str:
    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()

    url_title = title_from_url(url)
    url_key = title_compare_key(url_title)
    url_tokens = {
        token
        for token in url_key.split()
        if len(token) >= 3
        and token not in {
            "kampanya",
            "kampanyasi",
            "firsat",
            "firsati",
            "icin",
            "ozel",
        }
    }

    def add_candidate(
        value: Any,
        priority: int,
        order: int,
    ) -> None:
        title = strip_site_title_suffix(
            normalize_text(value),
            bank_name=bank_name,
        )
        key = title_compare_key(title)

        if not key or key in seen:
            return
        seen.add(key)

        if not is_usable_title(
            title,
            bank_name=bank_name,
        ):
            return

        context_score = sum(
            term in key
            for term in (
                "kampanya",
                "firsat",
                "finansman",
                "taksit",
                "indirim",
                "hediye",
                "puan",
                "oran",
                "odeme",
            )
        )

        candidate_tokens = {
            token
            for token in key.split()
            if len(token) >= 3
        }
        overlap_count = len(candidate_tokens & url_tokens)

        # Sayfadaki gerçek başlık URL slug'ıyla örtüşüyorsa,
        # Blog gibi genel başlıklara göre çok daha güçlüdür.
        url_similarity_score = overlap_count * 6

        candidates.append(
            (
                priority
                + context_score
                + url_similarity_score,
                -order,
                title,
            )
        )

    order = 0

    # URL yalnızca güvenli yedektir. Sayfadaki gerçek başlık URL ile
    # örtüştüğünde daha yüksek puan alarak bunu geçer.
    if is_usable_title(
        url_title,
        bank_name=bank_name,
    ):
        add_candidate(
            url_title,
            priority=55,
            order=order,
        )

    for selector_index, selector in enumerate(TITLE_SELECTORS):
        for node in soup.select(selector):
            order += 1
            add_candidate(
                _candidate_text(node),
                priority=100 - selector_index,
                order=order,
            )

    for selector, priority in (
        ("meta[property='og:title']", 92),
        ("meta[name='twitter:title']", 90),
        ("meta[name='title']", 88),
    ):
        for node in soup.select(selector):
            order += 1
            add_candidate(
                node.get("content", ""),
                priority=priority,
                order=order,
            )

    for node in soup.select(
        "script[type='application/ld+json']"
    ):
        try:
            value = json.loads(node.get_text(" ", strip=True))
        except (TypeError, json.JSONDecodeError):
            continue

        for candidate in _json_ld_title_candidates(value):
            order += 1
            add_candidate(
                candidate,
                priority=86,
                order=order,
            )

    if candidates:
        return max(
            candidates,
            key=lambda item: (item[0], item[1]),
        )[2]

    if soup.title:
        title = strip_site_title_suffix(
            normalize_text(
                soup.title.get_text(" ", strip=True)
            ),
            bank_name=bank_name,
        )
        if is_usable_title(
            title,
            bank_name=bank_name,
        ):
            return title

    fallback = title_from_url(url)
    if is_usable_title(
        fallback,
        bank_name=bank_name,
    ):
        return fallback

    return ""

def choose_content_root(soup: BeautifulSoup) -> Tag:
    # Happy Kart/SharePoint sayfalarında gerçek kampanya metni doğrudan
    # .campaign-text alanındadır. Üst .campaign-detail kapsayıcısı tarih,
    # görsel ve sosyal alanları da içerdiği için önce daha özgül alan
    # tercih edilir.
    for selector in (".campaign-text",):
        for node in soup.select(selector):
            text = _candidate_text(node)
            if (
                len(text) >= MIN_ACCEPTABLE_TEXT_LENGTH
                and campaign_context_count(text) >= 1
            ):
                return node

    candidates: list[tuple[int, int, Tag]] = []

    for selector_index, selector in enumerate(CONTENT_SELECTORS):
        for node in soup.select(selector):
            text = _candidate_text(node)
            if not text:
                continue

            context_count = sum(
                term in search_key(text[:5000])
                for term in CAMPAIGN_CONTEXT_TERMS
            )
            score = len(text) + context_count * 250
            candidates.append((score, -selector_index, node))

    if candidates:
        return max(candidates, key=lambda item: (item[0], item[1]))[2]

    return soup.body or soup


def _remove_duplicate_title(text: str, title: str) -> str:
    text = normalize_text(text)
    title = normalize_text(title)

    if not title:
        return text

    while search_key(text).startswith(search_key(title)):
        text = normalize_text(text[len(title):])

    return text


def _cut_tail(text: str) -> str:
    folded = search_key(text)
    positions: list[int] = []

    for marker in TAIL_MARKERS:
        marker_key = search_key(marker)
        position = folded.find(marker_key)
        if position > max(200, int(len(folded) * 0.20)):
            positions.append(position)

    if not positions:
        return text

    cut_position = min(positions)
    return normalize_text(text[:cut_position])




def semantic_campaign_blocks(
    soup: BeautifulSoup,
    *,
    title: str,
) -> list[str]:
    """
    Kampanya metnini sayfanın özgün DOM'undan toplar.

    Bazı resmî alt sitelerde kampanya maddeleri, temizleme sırasında
    kaldırılan genel bir kapsayıcının içinde kalabiliyor. Bu nedenle
    p/li blokları temizlemeden önce güvenli biçimde toplanır.
    """
    blocks: list[str] = []
    seen: set[str] = set()

    forbidden_ancestors = {
        "nav",
        "header",
        "footer",
        "aside",
        "form",
    }
    noise_keys = {
        "ana sayfa",
        "kampanyalar",
        "tum kampanyalar",
        "hemen basvur",
        "iletisim",
        "kartlar",
        "kredi kartlari",
    }

    for node in soup.select("li, p"):
        if any(
            ancestor.name in forbidden_ancestors
            for ancestor in node.parents
            if getattr(ancestor, "name", None)
        ):
            continue

        value = normalize_text(
            node.get_text(" ", strip=True)
        )
        key = search_key(value)

        if not value or len(value) < 18:
            continue
        if key in noise_keys:
            continue
        if title and key == search_key(title):
            continue
        if key in seen:
            continue

        has_campaign_context = any(
            term in key
            for term in CAMPAIGN_CONTEXT_TERMS
        )
        has_date = bool(
            re.search(
                (
                    r"\b\d{1,2}\s+"
                    r"(?:ocak|şubat|subat|mart|nisan|mayıs|mayis|"
                    r"haziran|temmuz|ağustos|agustos|eylül|eylul|"
                    r"ekim|kasım|kasim|aralık|aralik)\s+\d{4}\b"
                ),
                key,
                flags=re.IGNORECASE,
            )
        )
        has_amount_or_installment = bool(
            re.search(
                r"\b\d[\d\.\,]*\s*(?:tl|ay|taksit)\b",
                key,
                flags=re.IGNORECASE,
            )
        )

        if (
            has_campaign_context
            or has_date
            or has_amount_or_installment
            or len(value) >= 90
        ):
            seen.add(key)
            blocks.append(value)

    return blocks


def semantic_campaign_text(
    soup: BeautifulSoup,
    *,
    title: str,
) -> str:
    return normalize_text(
        " ".join(
            semantic_campaign_blocks(
                soup,
                title=title,
            )
        )
    )


SAFE_BODY_FALLBACK_SELECTORS = [
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
    ".breadcrumb",
    ".breadcrumbs",
    ".cookie",
    ".cookies",
    ".cookie-banner",
    ".cookie-policy",
    ".modal",
    ".popup",
    ".chat",
    ".chatbot",
    ".social",
    ".share",
]


def document_title_candidate(
    soup: BeautifulSoup,
    *,
    bank_name: str = "",
) -> str:
    """
    HTML <title> değerini URL yedeğinden bağımsız biçimde alır.

    extract_title() içinde URL başlığı da aday olduğu için, gerçek
    sayfa başlığı yalnızca <title> etiketindeyse URL yedeği onu
    gölgeleyebiliyordu.
    """
    if not soup.title:
        return ""

    candidate = strip_site_title_suffix(
        normalize_text(
            soup.title.get_text(" ", strip=True)
        ),
        bank_name=bank_name,
    )

    if is_usable_title(
        candidate,
        bank_name=bank_name,
    ):
        return candidate

    return ""


def is_url_fallback_title(
    title: str,
    *,
    url: str,
) -> bool:
    return (
        bool(title)
        and title_compare_key(title)
        == title_compare_key(title_from_url(url))
    )


def safe_original_body_fallback(
    html: str,
    *,
    title: str,
) -> tuple[str, str]:
    """
    Agresif sınıf/id temizliği gerçek kampanya kapsayıcısını silerse
    özgün HTML gövdesinden daha temkinli bir yedek metin üretir.

    Burada yalnızca açıkça güvenli etiket ve bileşenler kaldırılır;
    class/id içinde 'header' veya 'footer' geçiyor diye kapsayıcının
    tamamı silinmez.
    """
    fallback_soup = BeautifulSoup(
        html,
        "html.parser",
    )

    for selector in SAFE_BODY_FALLBACK_SELECTORS:
        for node in fallback_soup.select(selector):
            # Aynı SharePoint yapısı güvenli gövde yedeğinde de
            # korunmalıdır. Form etiketi açılır, çocukları silinmez.
            if getattr(node, "name", "") == "form":
                node.unwrap()
            else:
                node.decompose()

    body = fallback_soup.body or fallback_soup
    raw_text = _candidate_text(body)
    clean_text = clean_campaign_text(
        raw_text,
        title,
    )

    enough_length = (
        len(clean_text)
        >= MIN_ACCEPTABLE_TEXT_LENGTH
    )
    enough_context = (
        campaign_context_count(clean_text) >= 1
    )

    if enough_length and enough_context:
        return raw_text, clean_text

    return "", ""


def clean_campaign_text(
    raw_text: str,
    title: str,
) -> str:
    clean_text = _remove_duplicate_title(
        raw_text,
        title,
    )
    clean_text = _cut_tail(clean_text)
    return normalize_text(clean_text)


def campaign_context_count(text: str) -> int:
    key = search_key(text[:10000])
    return sum(
        term in key
        for term in CAMPAIGN_CONTEXT_TERMS
    )


def choose_body_fallback(
    soup: BeautifulSoup,
    *,
    title: str,
    current_raw_text: str,
    current_clean_text: str,
) -> tuple[str, str]:
    """
    Seçilen içerik kapsayıcısı yalnızca başlık veya kısa bir alan
    içeriyorsa, temizlenmiş sayfa gövdesini yedek olarak kullanır.

    Bu durum özellikle kampanya metni <main> dışında ayrı bir bölümde
    tutulan resmî kart alt sitelerinde görülür.
    """
    if len(current_clean_text) >= MIN_ACCEPTABLE_TEXT_LENGTH:
        return current_raw_text, current_clean_text

    body = soup.body or soup
    body_raw_text = _candidate_text(body)
    body_clean_text = clean_campaign_text(
        body_raw_text,
        title,
    )

    if len(body_clean_text) <= len(current_clean_text):
        return current_raw_text, current_clean_text

    enough_length = (
        len(body_clean_text)
        >= MIN_ACCEPTABLE_TEXT_LENGTH
    )
    enough_context = (
        campaign_context_count(body_clean_text) >= 2
        and len(body_clean_text) >= 80
    )

    if enough_length or enough_context:
        return body_raw_text, body_clean_text

    return current_raw_text, current_clean_text


def extract_campaign_text(
    html: str,
    *,
    bank_name: str = "",
    url: str = "",
) -> tuple[str, str, str]:
    original_soup = BeautifulSoup(
        html,
        "html.parser",
    )
    document_title = document_title_candidate(
        original_soup,
        bank_name=bank_name,
    )

    soup = BeautifulSoup(html, "html.parser")
    _remove_unwanted_nodes(soup)

    title = extract_title(
        soup,
        bank_name=bank_name,
        url=url,
    )

    # Temizleme gerçek başlık düğümünü kaldırdıysa ve geriye yalnızca
    # URL'den üretilen ".aspx" başlığı kaldıysa HTML <title> değerini
    # kullanırız.
    if (
        document_title
        and (
            not is_usable_title(
                title,
                bank_name=bank_name,
            )
            or is_url_fallback_title(
                title,
                url=url,
            )
        )
    ):
        title = document_title

    content_root = choose_content_root(soup)
    raw_text = _candidate_text(content_root)
    clean_text = clean_campaign_text(
        raw_text,
        title,
    )

    raw_text, clean_text = choose_body_fallback(
        soup,
        title=title,
        current_raw_text=raw_text,
        current_clean_text=clean_text,
    )

    if len(clean_text) < MIN_ACCEPTABLE_TEXT_LENGTH:
        semantic_text = semantic_campaign_text(
            original_soup,
            title=title,
        )

        if len(semantic_text) > len(clean_text):
            raw_text = semantic_text
            clean_text = semantic_text

    # Happy Kart gibi bazı sayfalarda gerçek içerik, class adında
    # "header" geçen geniş bir kapsayıcıda tutuluyor. Agresif gürültü
    # temizliği bu kapsayıcıyı tamamen silebildiği için özgün gövdeden
    # temkinli bir son yedek uygulanır.
    if len(clean_text) < MIN_ACCEPTABLE_TEXT_LENGTH:
        fallback_raw, fallback_clean = (
            safe_original_body_fallback(
                html,
                title=title,
            )
        )

        if len(fallback_clean) > len(clean_text):
            raw_text = fallback_raw
            clean_text = fallback_clean

    parsed_host = (urlparse(url).hostname or "").casefold()
    if (
        search_key(bank_name) in {"t.o.m. katilim", "tom katilim"}
        or parsed_host in {
            "tombankhadi.com",
            "www.tombankhadi.com",
            "hadiyanindakibanka.com",
            "www.hadiyanindakibanka.com",
        }
    ):
        clean_text = trim_tom_hadi_campaign_text(
            clean_text,
            title=title,
        )
        raw_text = trim_tom_hadi_campaign_text(
            raw_text,
            title=title,
        )

    return title, raw_text, clean_text


def determine_fetch_status(
    title: str,
    clean_text: str,
) -> str:
    if not title and not clean_text:
        return "empty"
    if not title:
        return "missing_title"
    if len(clean_text) < MIN_ACCEPTABLE_TEXT_LENGTH:
        return "short_content"
    return "ok"


def _render_fallback(
    url: str,
    *,
    headless: bool,
) -> tuple[str, str]:
    rendered = render_dynamic_page(
        url,
        detail_paths=[],
        load_more_terms=[],
        cookie_accept_terms=[
            "Tümünü Kabul Et",
            "Kabul Et",
            "Onayla",
        ],
        headless=headless,
        maximum_load_more_clicks=1,
        settle_seconds=1.2,
    )
    return rendered.url, rendered.html




DEFAULT_URL_ALIAS_PATH = (
    Path("config") / "campaign_url_aliases.json"
)


def campaign_url_alias_key(value: str) -> str:
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]

    path = re.sub(
        r"/+",
        "/",
        parsed.path or "/",
    ).rstrip("/")
    if not path:
        path = "/"

    query = f"?{parsed.query}" if parsed.query else ""
    return f"{host}{path.casefold()}{query}"


def load_campaign_url_aliases(
    path: str | Path = DEFAULT_URL_ALIAS_PATH,
) -> dict[str, str]:
    alias_path = Path(path)
    if not alias_path.exists():
        return {}

    try:
        value = json.loads(
            alias_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {}

    rows = value if isinstance(value, list) else []
    result: dict[str, str] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue

        source_url = normalize_text(
            row.get("source_url")
        )
        target_url = normalize_text(
            row.get("target_url")
        )
        if source_url and target_url:
            result[
                campaign_url_alias_key(source_url)
            ] = target_url

    return result


def resolve_campaign_url_alias(
    discovered_url: str,
    *,
    alias_path: str | Path = DEFAULT_URL_ALIAS_PATH,
) -> str:
    aliases = load_campaign_url_aliases(alias_path)
    return aliases.get(
        campaign_url_alias_key(discovered_url),
        discovered_url,
    )


def is_official_subdomain(
    url: str,
    base_url: str,
) -> bool:
    parsed_host = (
        urlparse(url).hostname or ""
    ).casefold()
    base_host = (
        urlparse(base_url).hostname or ""
    ).casefold()

    if base_host.startswith("www."):
        base_host = base_host[4:]

    return (
        bool(parsed_host)
        and bool(base_host)
        and parsed_host != base_host
        and parsed_host.endswith(f".{base_host}")
    )


def build_request_url(
    discovered_url: str,
    bank_config: dict[str, Any] | None = None,
    *,
    source_page: str = "",
) -> str:
    """
    Keşif URL'sinin yolunu korur; istek yapılırken bankanın yapılandırılmış
    ana alan adını kullanır.

    Örnek:
    https://kuveytturk.com.tr/kampanyalar/...
    ->
    https://www.kuveytturk.com.tr/kampanyalar/...
    """
    resolved_url = resolve_campaign_url_alias(
        discovered_url,
    )
    parsed = urlparse(resolved_url.strip())
    config = bank_config or {}
    base_url = normalize_text(config.get("base_url"))

    # Happy Kart'ın apex alan adı (happycard.com.tr) yerel ortamda
    # sertifika/yönlendirme sorununa giriyor. Keşif kaynağı da apex
    # olarak kaydedilebildiği için source_page'e güvenmeden her zaman
    # resmî www alan adına dönüştürürüz.
    parsed_host = (parsed.hostname or "").casefold()
    normalized_parsed_host = (
        parsed_host[4:]
        if parsed_host.startswith("www.")
        else parsed_host
    )
    canonical_external_hosts = {
        "happycard.com.tr": "www.happycard.com.tr",
        "turkiyefinansala.com": "www.turkiyefinansala.com",
    }

    canonical_netloc = canonical_external_hosts.get(
        normalized_parsed_host
    )
    if canonical_netloc:
        return urlunparse(
            (
                parsed.scheme or "https",
                canonical_netloc,
                parsed.path or "/",
                parsed.params,
                parsed.query,
                "",
            )
        )

    if not base_url:
        return resolved_url

    def normalized_host(value: str) -> str:
        host = (urlparse(value).hostname or "").casefold()
        return host[4:] if host.startswith("www.") else host

    discovered_host = normalized_host(resolved_url)
    source_host = normalized_host(source_page)
    configured_host = normalized_host(base_url)

    # Happy Kart ve Âlâ Kart gibi bankanın ayrı resmî alan adında
    # çalışan kampanya kaynaklarını ana banka alan adına çevirmeyiz.
    #
    # Ancak keşif URL'si www içermiyor, kaynak sayfası www içeriyorsa
    # doğrudan kaynak sayfasının netloc değerini kullanırız. Böylece
    # Selenium gereksiz apex -> www yönlendirmesine girmez.
    if (
        discovered_host
        and source_host
        and discovered_host == source_host
        and discovered_host != configured_host
    ):
        source = urlparse(source_page)
        source_scheme = source.scheme or parsed.scheme or "https"
        source_netloc = source.netloc or parsed.netloc

        return urlunparse(
            (
                source_scheme,
                source_netloc,
                parsed.path or "/",
                parsed.params,
                parsed.query,
                "",
            )
        )

    # Miles&Smiles, Sağlam Kart gibi bankanın resmî alt alan
    # adları değiştirilmeden korunur.
    if is_official_subdomain(
        resolved_url,
        base_url,
    ):
        return resolved_url

    base = urlparse(base_url)
    scheme = base.scheme or parsed.scheme or "https"
    host = base.netloc or parsed.netloc

    return urlunparse(
        (
            scheme,
            host,
            parsed.path or "/",
            parsed.params,
            parsed.query,
            "",
        )
    )


def is_unexpected_home_redirect(
    requested_url: str,
    final_url: str,
) -> bool:
    requested = urlparse(requested_url)
    final = urlparse(final_url)

    requested_path = (requested.path or "/").rstrip("/") or "/"
    final_path = (final.path or "/").rstrip("/") or "/"

    homepage_paths = {
        "/",
        "/tr",
        "/en",
    }
    return (
        requested_path not in homepage_paths
        and final_path in homepage_paths
    )


def fetch_page(
    page: dict[str, str],
    client: HttpClient,
    *,
    bank_config: dict[str, Any] | None = None,
    browser_fallback: bool = True,
    headless: bool = True,
) -> CampaignPageSnapshot:
    discovered_url = page["url"]
    request_url = build_request_url(
        discovered_url,
        bank_config,
        source_page=page.get("source_page", ""),
    )

    result = None
    request_error: Exception | None = None

    try:
        result = client.get(request_url)
    except Exception as error:
        request_error = error

    if request_error is not None:
        if not browser_fallback:
            raise request_error

        try:
            rendered_url, rendered_html = _render_fallback(
                request_url,
                headless=headless,
            )
        except Exception as browser_error:
            raise RuntimeError(
                "HTTP isteği başarısız oldu ve Selenium yedeği de "
                "sayfayı açamadı. "
                f"HTTP hatası: {type(request_error).__name__}: "
                f"{request_error}. "
                f"Selenium hatası: {type(browser_error).__name__}: "
                f"{browser_error}"
            ) from browser_error

        final_url = canonicalize_url(
            rendered_url or request_url
        )
        title, raw_text, clean_text = extract_campaign_text(
            rendered_html,
            bank_name=page["bank_name"],
            url=final_url or request_url,
        )
        status = determine_fetch_status(
            title,
            clean_text,
        )
        fetch_method = "selenium_after_request_error"
        http_status = 0
        content_type = "text/html"

    else:
        final_url = canonicalize_url(result.url)
        html = result.text
        fetch_method = "requests"
        http_status = result.status_code
        content_type = result.content_type

        title, raw_text, clean_text = extract_campaign_text(
            html,
            bank_name=page["bank_name"],
            url=final_url or request_url,
        )
        status = determine_fetch_status(
            title,
            clean_text,
        )

        if is_unexpected_home_redirect(
            request_url,
            result.url,
        ):
            title = ""
            raw_text = ""
            clean_text = ""
            status = "redirected_homepage"

        if (
            browser_fallback
            and status
            in {
                "empty",
                "missing_title",
                "short_content",
                "redirected_homepage",
            }
        ):
            rendered_url, rendered_html = _render_fallback(
                request_url,
                headless=headless,
            )
            rendered_title, rendered_raw, rendered_clean = (
                extract_campaign_text(
                    rendered_html,
                    bank_name=page["bank_name"],
                    url=rendered_url or request_url,
                )
            )
            rendered_status = determine_fetch_status(
                rendered_title,
                rendered_clean,
            )

            # HTTP isteği detay URL'sinden ana sayfaya yönlendiyse,
            # Selenium fallback de aynı ana sayfayı açmış olabilir.
            # Ana sayfadaki kur/kâr payı gibi dinamik değerleri kampanya
            # içeriği olarak kabul etmiyoruz.
            rendered_final_url = rendered_url or request_url
            rendered_home_redirect = is_unexpected_home_redirect(
                request_url,
                rendered_final_url,
            )
            if rendered_home_redirect:
                rendered_title = ""
                rendered_raw = ""
                rendered_clean = ""
                rendered_status = "redirected_homepage"

            browser_result_is_better = (
                rendered_status != "redirected_homepage"
                and (
                    len(rendered_clean) > len(clean_text)
                    or (
                        status == "redirected_homepage"
                        and rendered_status
                        not in {
                            "empty",
                            "redirected_homepage",
                        }
                    )
                )
            )

            if browser_result_is_better:
                final_url = canonicalize_url(
                    rendered_url or request_url
                )
                title = rendered_title
                raw_text = rendered_raw
                clean_text = rendered_clean
                status = rendered_status
                fetch_method = "selenium_fallback"

    timestamp = utc_now_iso()
    status_result = evaluate_campaign_status(
        text=f"{title} {clean_text}",
        listing_status=page.get(
            "listing_status",
            "unknown",
        ),
        listing_evidence=page.get(
            "status_evidence",
            "",
        ),
    )

    return CampaignPageSnapshot(
        bank_name=page["bank_name"],
        title=title,
        url=final_url,
        requested_url=canonicalize_url(discovered_url),
        source_page=page.get("source_page", ""),
        page_type=page.get(
            "page_type",
            "campaign_detail",
        ),
        discovery_mode=page.get(
            "discovery_mode",
            "",
        ),
        source_group=page.get(
            "source_group",
            "",
        ),
        listing_status=page.get(
            "listing_status",
            "unknown",
        ),
        listing_status_evidence=page.get(
            "status_evidence",
            "",
        ),
        fetch_method=fetch_method,
        http_status=http_status,
        content_type=content_type,
        raw_text=raw_text,
        clean_text=clean_text,
        content_hash=hash_text(clean_text),
        text_length=len(clean_text),
        campaign_start_date=status_result.start_date,
        campaign_end_date=status_result.end_date,
        current_status=status_result.status,
        status_reason=status_result.reason,
        status_evidence=status_result.evidence,
        status_checked_at=status_result.checked_at,
        first_seen_at=timestamp,
        last_checked_at=timestamp,
        fetch_status=status,
    )

def fetch_campaign_pages(
    *,
    discovered_path: str | Path = (
        Path("data") / "discovered_campaign_pages.json"
    ),
    config_path: str | Path = Path("config") / "banks.json",
    bank_name: str | None = None,
    limit: int | None = None,
    timeout: int = 30,
    delay_seconds: float = 0.5,
    browser_fallback: bool = True,
    headless: bool = True,
) -> tuple[
    list[CampaignPageSnapshot],
    list[dict[str, str]],
]:
    pages = load_discovered_pages(
        discovered_path,
        bank_name=bank_name,
    )

    if limit is not None:
        pages = pages[: max(0, limit)]

    bank_config = {
        search_key(bank["name"]): bank
        for bank in load_bank_config(config_path)
    }

    snapshots: list[CampaignPageSnapshot] = []
    errors: list[dict[str, str]] = []

    with HttpClient(
        timeout=timeout,
        delay_seconds=delay_seconds,
    ) as client:
        for index, page in enumerate(pages, start=1):
            try:
                snapshot = fetch_page(
                    page,
                    client,
                    bank_config=bank_config.get(
                        search_key(page["bank_name"]),
                        {},
                    ),
                    browser_fallback=browser_fallback,
                    headless=headless,
                )
                snapshots.append(snapshot)
                print(
                    f"[{index}/{len(pages)}] "
                    f"{snapshot.bank_name} — "
                    f"{snapshot.fetch_status} — "
                    f"{snapshot.title or snapshot.url}"
                )
            except Exception as error:
                current_bank_config = bank_config.get(
                    search_key(page["bank_name"]),
                    {},
                )
                request_url = build_request_url(
                    page["url"],
                    current_bank_config,
                    source_page=page.get("source_page", ""),
                )
                errors.append(
                    {
                        "bank_name": page["bank_name"],
                        "url": page["url"],
                        "request_url": request_url,
                        "error_type": type(error).__name__,
                        "message": str(error),
                    }
                )
                print(
                    f"[{index}/{len(pages)}] HATA — "
                    f"{page['bank_name']} — {page['url']}"
                )

    return snapshots, errors


def _snapshot_filename(snapshot: CampaignPageSnapshot) -> str:
    digest = hashlib.sha1(
        snapshot.url.encode("utf-8")
    ).hexdigest()[:18]
    return f"{digest}.json"


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    return value if isinstance(value, list) else []


def _fetch_item_bank(item: dict[str, Any]) -> str:
    # affected_banks/error_banks search_key() kullanıyor. Burada yalnızca
    # casefold kullanılması "Türkiye" ile "Turkiye" anahtarlarını farklı
    # yapıyor ve eski hata kayıtlarının her denemede çoğalmasına yol
    # açıyordu.
    return search_key(item.get("bank_name"))


def _fetch_index_key(
    item: dict[str, Any],
) -> tuple[str, str]:
    requested = canonicalize_url(
        unwrap_url(item.get("requested_url"))
    )
    final_url = canonicalize_url(
        unwrap_url(item.get("url"))
    )
    return (
        _fetch_item_bank(item),
        requested or final_url,
    )


def write_fetch_results(
    snapshots: list[CampaignPageSnapshot],
    errors: list[dict[str, str]],
    *,
    snapshot_root: str | Path = (
        Path("data") / "campaign_pages"
    ),
    index_path: str | Path = (
        Path("data") / "campaign_page_index.json"
    ),
    error_path: str | Path = (
        Path("data") / "campaign_page_fetch_errors.json"
    ),
    report_path: str | Path = (
        Path("data") / "campaign_page_fetch_report.json"
    ),
) -> None:
    """
    Banka bazlı metin çekiminde diğer bankaların indeksini korur.
    """
    root = Path(snapshot_root)
    index_output = Path(index_path)
    error_output = Path(error_path)
    report_output = Path(report_path)

    root.mkdir(parents=True, exist_ok=True)
    index_output.parent.mkdir(parents=True, exist_ok=True)

    new_rows: list[dict[str, Any]] = []

    for snapshot in snapshots:
        bank_folder = (
            root
            / re.sub(
                r"[^a-z0-9]+",
                "_",
                search_key(snapshot.bank_name),
            ).strip("_")
        )
        bank_folder.mkdir(parents=True, exist_ok=True)

        filename = _snapshot_filename(snapshot)
        output_file = bank_folder / filename
        output_file.write_text(
            json.dumps(
                asdict(snapshot),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        row = asdict(snapshot)
        row.pop("raw_text", None)
        row.pop("clean_text", None)
        row["snapshot_file"] = output_file.as_posix()
        new_rows.append(row)

    affected_banks = {
        search_key(snapshot.bank_name)
        for snapshot in snapshots
        if normalize_text(snapshot.bank_name)
    }

    existing_rows = _read_json_list(index_output)
    merged_rows = [
        item
        for item in existing_rows
        if _fetch_item_bank(item)
        not in affected_banks
    ]
    merged_rows.extend(new_rows)

    index_map: dict[tuple[str, str], dict[str, Any]] = {}
    for item in merged_rows:
        key = _fetch_index_key(item)
        if key[0] and key[1]:
            index_map[key] = item

    final_rows = sorted(
        index_map.values(),
        key=lambda item: _fetch_index_key(item),
    )

    error_banks = {
        search_key(item.get("bank_name"))
        for item in errors
        if normalize_text(item.get("bank_name"))
    }
    touched_banks = affected_banks | error_banks

    existing_errors = _read_json_list(error_output)
    final_errors = [
        item
        for item in existing_errors
        if _fetch_item_bank(item)
        not in touched_banks
    ]
    final_errors.extend(errors)

    index_output.write_text(
        json.dumps(
            final_rows,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    error_output.write_text(
        json.dumps(
            final_errors,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    status_counts = Counter(
        normalize_text(item.get("fetch_status"))
        for item in final_rows
    )
    campaign_status_counts = Counter(
        normalize_text(item.get("current_status"))
        for item in final_rows
    )
    bank_counts = Counter(
        normalize_text(item.get("bank_name"))
        for item in final_rows
    )

    report = {
        "snapshot_count": len(final_rows),
        "error_count": len(final_errors),
        "fetch_status_counts": dict(
            sorted(status_counts.items())
        ),
        "campaign_status_counts": dict(
            sorted(campaign_status_counts.items())
        ),
        "bank_counts": dict(sorted(bank_counts.items())),
        "minimum_acceptable_text_length": (
            MIN_ACCEPTABLE_TEXT_LENGTH
        ),
        "generated_at": utc_now_iso(),
    }
    report_output.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )