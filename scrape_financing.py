"""
TEKNOFEST 2026 - Katılım bankaları finansman ürünleri ham veri toplayıcısı V22.

Bu script mevcut kampanya veri setini değiştirmez. Konut, ihtiyaç, taşıt,
iş yeri ve ticari finansman ürünlerini ayrı bir veri katmanında toplar.

Tek banka testi:
    python scrape_financing.py --bank "Türkiye Finans"

Tüm bankalar:
    python scrape_financing.py

Çıktılar:
    data/financing_raw/<banka>_<tarih>.json
    data/financing_raw_all.csv
    data/financing_errors.json
    data/financing_coverage.json
    data/financing_calculators.json

Tek banka testinde:
    data/test_financing_<banka>.csv

Notlar:
- Önce requests kullanılır.
- Sayfa metni yetersizse Selenium denenir.
- Metinde bulunmayan oran, vade veya tutar uydurulmaz.
- Bu dosya ham toplama katmanıdır; finansal alan çıkarımı sonraki aşamada
  ayrı bir script ile yapılacaktır.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import random
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag


OUTPUT_ROOT = Path("data")
RAW_DIR = OUTPUT_ROOT / "financing_raw"
MERGED_CSV = OUTPUT_ROOT / "financing_raw_all.csv"
ERROR_FILE = OUTPUT_ROOT / "financing_errors.json"
COVERAGE_FILE = OUTPUT_ROOT / "financing_coverage.json"
CALCULATOR_FILE = OUTPUT_ROOT / "financing_calculators.json"
OVERVIEW_FILE = OUTPUT_ROOT / "financing_overviews.json"

REQUEST_TIMEOUT = 25
SELENIUM_WAIT_SECONDS = 5
MIN_CONTENT_LENGTH = 120
MAX_DISCOVERED_URLS_PER_BANK = 100
MAX_DISCOVERY_PAGES_PER_BANK = 30

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.7,en;q=0.6",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

FIELDS = [
    "id",
    "banka_adi",
    "kayit_turu",
    "urun_turu",
    "urun_adi",
    "segment",
    "kaynak_url",
    "toplama_tarihi",
    "ham_metin",
    "kaynak_turu",
    "otomatik_toplama_durumu",
    "kar_payi_orani",
    "vade_suresi",
    "finansman_tutari",
    "masraf_durumu",
    "tahsis_ucreti",
    "dosya_masrafi",
    "ekspertiz_ucreti",
    "sigorta_kosulu",
    "kampanya_avantaji",
    "hedef_kitle",
    "bilgi_yayin_durumu",
]

FINANCE_KEYWORDS = (
    "finansman",
    "konut",
    "mortgage",
    "taşıt",
    "tasit",
    "araç",
    "arac",
    "otomobil",
    "motosiklet",
    "ihtiyaç",
    "ihtiyac",
    "alışveriş kredisi",
    "alisveris kredisi",
    "iş yeri",
    "isyeri",
    "ticari",
    "işletme",
    "isletme",
    "tedarikçi",
    "tedarikci",
    "kobi",
    "eğitim finansmanı",
    "egitim finansmani",
    "seyahat finansmanı",
    "seyahat finansmani",
    "kira finansmanı",
    "kira finansmani",
    "hac",
    "umre",
)

EXCLUDED_LINK_PARTS = (
    "/blog/",
    "/haber",
    "/basin",
    "/duyuru",
    "/kariyer",
    "/hakkimizda",
    "/yatirimci",
    "/faaliyet-rapor",
    "/denetim-rapor",
    "/sozlesme",
    "/formlar",
    "/sss",
    "/sikca-sorulan",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    "javascript:",
    "mailto:",
    "tel:",
)

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
    ".navbar",
    ".navigation",
    ".menu",
    ".mobile-menu",
    ".breadcrumb",
    ".breadcrumbs",
    ".cookie",
    ".cookies",
    ".cookie-banner",
    ".social",
    ".share",
    ".footer",
    ".header",
    ".sidebar",
    ".related",
    ".related-content",
    ".campaign-list",
    ".sticky",
    ".modal",
    ".popup",
]

CONTENT_SELECTORS = [
    "main",
    "article",
    "[role='main']",
    "#main-content",
    "#content",
    ".main-content",
    ".page-content",
    ".content-wrapper",
    ".content",
    ".detail-content",
    ".product-detail",
    ".product-content",
    ".rich-text",
    ".editor-content",
]

FOOTER_MARKERS = [
    "Size Nasıl Yardımcı Olabiliriz?",
    "Nasıl Yardımcı Olabiliriz?",
    "Bize Ulaşın",
    "Şubeler ve ATM",
    "Şube ve ATM",
    "Müşteri İletişim Merkezi",
    "Müşteri Memnuniyet Merkezi",
    "Hızlı Erişim",
    "Hakkımızda",
    "Bilgi Toplumu Hizmetleri",
    "Kişisel Verilerin Korunması",
    "Copyright ©",
    "© 2026",
]


BANKS: list[dict[str, Any]] = [
    {
        "name": "Kuveyt Türk",
        "domains": ["kuveytturk.com.tr"],
        "seed_urls": [
            "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar",
            "https://www.kuveytturk.com.tr/isim-icin/finansman-urunleri",
        ],
        "fixed_urls": [
            {
                "url": (
                    "https://www.kuveytturk.com.tr/"
                    "hesaplama-araclari/finansman-hesaplama"
                ),
                "source_type": "hesaplama_araci",
            },
        ],
        "use_selenium": False,
    },
    {
        "name": "Türkiye Finans",
        "domains": ["turkiyefinans.com.tr"],
        "seed_urls": [],
        "fixed_urls": [
            {
                "url": (
                    "https://www.turkiyefinans.com.tr/tr-tr/"
                    "bireysel/konut-finansmani/Sayfalar/"
                    "konut-finansmani.aspx"
                ),
                "source_type": "urun_sayfasi",
            },
            {
                "url": (
                    "https://www.turkiyefinans.com.tr/tr-tr/"
                    "bireysel/ihtiyac-finansmani/Sayfalar/"
                    "ihtiyac-finansmani.aspx"
                ),
                "source_type": "urun_sayfasi",
            },
            {
                "url": (
                    "https://www.turkiyefinans.com.tr/tr-tr/"
                    "bireysel/tasit-finansmani/Sayfalar/"
                    "tasit-finansmani.aspx"
                ),
                "source_type": "urun_sayfasi",
            },
            {
                "url": (
                    "https://www.turkiyefinans.com.tr/tr-tr/"
                    "kobi/Sayfalar/"
                    "dijital-taksitli-ticari-finansman-destegi.aspx"
                ),
                "source_type": "urun_sayfasi",
            },
            {
                "url": (
                    "https://www.turkiyefinans.com.tr/tr-tr/"
                    "hesaplama-araclari/Sayfalar/"
                    "finansman-odeme-plani.aspx"
                ),
                "source_type": "hesaplama_araci",
            },
        ],
        "use_selenium": False,
    },
    {
        "name": "Albaraka Türk",
        "domains": ["albaraka.com.tr"],
        "seed_urls": [
            "https://www.albaraka.com.tr/tr/bireysel/finansmanlar",
            "https://www.albaraka.com.tr/tr/kobi/finansmanlar",
            (
                "https://www.albaraka.com.tr/tr/"
                "ticari-ve-kurumsal/finansmanlar"
            ),
        ],
        "fixed_urls": [
            {
                "url": (
                    "https://www.albaraka.com.tr/tr/bireysel/"
                    "finansmanlar/konut-finansmani/konut-finansmani"
                ),
                "source_type": "urun_sayfasi",
            },
            {
                "url": (
                    "https://www.albaraka.com.tr/tr/bireysel/"
                    "finansmanlar/tasit-finansmani/tasit-finansmani"
                ),
                "source_type": "urun_sayfasi",
            },
            {
                "url": (
                    "https://www.albaraka.com.tr/tr/bireysel/"
                    "finansmanlar/ihtiyac"
                ),
                "source_type": "urun_sayfasi",
            },
            {
                "url": (
                    "https://www.albaraka.com.tr/tr/kobi/"
                    "finansmanlar/kobi-nakdi-finansman/"
                    "tedarikci-finansmani"
                ),
                "source_type": "urun_sayfasi",
            },
        ],
        "use_selenium": True,
        "prefer_selenium": True,
        "request_delay_min": 2.0,
        "request_delay_max": 4.0,
    },
    {
        "name": "Ziraat Katılım",
        "domains": ["ziraatkatilim.com.tr"],
        "seed_urls": [
            (
                "https://www.ziraatkatilim.com.tr/"
                "bireysel/finansman-urunleri"
            ),
            (
                "https://www.ziraatkatilim.com.tr/"
                "ticari/finansman-urunleri"
            ),
            (
                "https://www.ziraatkatilim.com.tr/"
                "ticari/finansal-kiralama-leasing"
            ),
            (
                "https://www.ziraatkatilim.com.tr/"
                "tarim/tarimsal-finansman-%C3%BCr%C3%BCnleri"
            ),
        ],
        "fixed_urls": [
            {
                "url": (
                    "https://www.ziraatkatilim.com.tr/"
                    "tarim/tarim-finansmani"
                ),
                "source_type": "urun_sayfasi",
            },
            {
                "url": (
                    "https://www.ziraatkatilim.com.tr/"
                    "tarim/tarimsal-finansman-%C3%BCr%C3%BCnleri"
                ),
                "source_type": "kategori_sayfasi",
            },
            {
                "url": (
                    "https://www.ziraatkatilim.com.tr/"
                    "ticari/dijital-bankacilik/aninda-finansman"
                ),
                "source_type": "urun_sayfasi",
            },
        ],
        "use_selenium": False,
    },
    {
        "name": "Vakıf Katılım",
        "domains": ["vakifkatilim.com.tr"],
        "seed_urls": [
            (
                "https://www.vakifkatilim.com.tr/tr/"
                "kendim-icin/finansmanlar"
            ),
            (
                "https://www.vakifkatilim.com.tr/tr/"
                "isim-icin/finansmanlar"
            ),
        ],
        "fixed_urls": [
            {
                "url": (
                    "https://www.vakifkatilim.com.tr/tr/"
                    "yardimci-sayfalar/hesaplama-araclari/"
                    "finansman-hesaplama"
                ),
                "source_type": "hesaplama_araci",
            },
            {
                "url": (
                    "https://www.vakifkatilim.com.tr/tr/"
                    "isim-icin/finansmanlar/finansal-kiralamalar"
                ),
                "source_type": "kategori_sayfasi",
            },
            {
                "url": (
                    "https://www.vakifkatilim.com.tr/tr/"
                    "isim-icin/finansmanlar/kobi-destekli-finansmanlar"
                ),
                "source_type": "kategori_sayfasi",
            },
            {
                "url": (
                    "https://www.vakifkatilim.com.tr/tr/"
                    "isim-icin/finansmanlar/tarim-finansmanlari"
                ),
                "source_type": "kategori_sayfasi",
            },
            {
                "url": (
                    "https://www.vakifkatilim.com.tr/tr/"
                    "isim-icin/finansmanlar/tarim-finansmanlari/"
                    "tarim-finansman-urunleri"
                ),
                "source_type": "kategori_sayfasi",
            },
            {
                "url": (
                    "https://www.vakifkatilim.com.tr/tr/"
                    "isim-icin/finansmanlar/gayrinakdi-finansmanlar"
                ),
                "source_type": "kategori_sayfasi",
            },
            {
                "url": (
                    "https://www.vakifkatilim.com.tr/tr/"
                    "isim-icin/finansmanlar/nakdi-finansmanlar"
                ),
                "source_type": "kategori_sayfasi",
            },
        ],
        "use_selenium": False,
    },
    {
        "name": "Dünya Katılım",
        "domains": ["dunyakatilim.com.tr"],
        "seed_urls": [
            "https://dunyakatilim.com.tr/kendim-icin/finansmanlar",
            "https://dunyakatilim.com.tr/isim-icin/finansmanlar",
        ],
        "fixed_urls": [
            {
                "url": (
                    "https://dunyakatilim.com.tr/kendim-icin/"
                    "finansmanlar/ihtiyac-finansmanlari"
                ),
                "source_type": "kategori_sayfasi",
            },
            {
                "url": (
                    "https://dunyakatilim.com.tr/kendim-icin/"
                    "finansmanlar/arac-finansmanlari"
                ),
                "source_type": "kategori_sayfasi",
            },
            {
                "url": (
                    "https://dunyakatilim.com.tr/kendim-icin/"
                    "finansmanlar/konut-finansmanlari"
                ),
                "source_type": "kategori_sayfasi",
            },
            {
                "url": (
                    "https://dunyakatilim.com.tr/isim-icin/"
                    "finansmanlar/nakdi-finansman"
                ),
                "source_type": "kategori_sayfasi",
            },
            {
                "url": (
                    "https://dunyakatilim.com.tr/isim-icin/"
                    "finansmanlar/gayri-nakdi-finansman"
                ),
                "source_type": "kategori_sayfasi",
            },
        ],
        "use_selenium": False,
    },
    {
        "name": "T.O.M. Katılım",
        "domains": ["tombank.com.tr"],
        "seed_urls": [],
        "fixed_urls": [
            {
                "url": "https://tombank.com.tr/taksitle.html",
                "source_type": "urun_sayfasi",
            },
            {
                "url": "https://tombank.com.tr/veresiye.html",
                "source_type": "urun_sayfasi",
            },
            {
                "url": "https://tombank.com.tr/hesaplama-araclari.html",
                "source_type": "hesaplama_araci",
            },
        ],
        "use_selenium": False,
    },
    {
        "name": "Hayat Finans Katılım",
        "domains": ["hayatfinans.com.tr"],
        "seed_urls": [
            "https://hayatfinans.com.tr/krediler",
            "https://hayatfinans.com.tr/finansmanlar",
            "https://hayatfinans.com.tr/finansmanlar-is",
        ],
        "fixed_urls": [
            {
                "url": (
                    "https://hayatfinans.com.tr/"
                    "krediler/bana-bunu-al"
                ),
                "source_type": "urun_sayfasi",
            },
            {
                "url": "https://hayatfinans.com.tr/krediler",
                "source_type": "kategori_sayfasi",
            },
            {
                "url": "https://hayatfinans.com.tr/finansmanlar",
                "source_type": "kategori_sayfasi",
            },
            {
                "url": "https://hayatfinans.com.tr/finansmanlar-is",
                "source_type": "kategori_sayfasi",
            },
        ],
        "use_selenium": True,
    },
    {
        "name": "Adil Katılım",
        "domains": ["adilkatilim.com.tr"],
        "seed_urls": [],
        "fixed_urls": [
            {
                "url": (
                    "https://www.adilkatilim.com.tr/"
                    "katilim-bankaciligi/urun-ve-hizmetler"
                ),
                "source_type": "urun_sayfasi",
            },
        ],
        "use_selenium": True,
        "mode": "adil_products",
    },
    {
        "name": "Türkiye Emlak Katılım",
        "domains": ["emlakkatilim.com.tr"],
        "seed_urls": [
            (
                "https://www.emlakkatilim.com.tr/tr/"
                "bireysel/finansmanlar"
            ),
            (
                "https://www.emlakkatilim.com.tr/tr/"
                "kurumsal/finansmanlar"
            ),
        ],
        "fixed_urls": [
            {
                "url": (
                    "https://www.emlakkatilim.com.tr/tr/"
                    "bireysel/finansmanlar"
                ),
                "source_type": "kategori_sayfasi",
            },
            {
                "url": (
                    "https://www.emlakkatilim.com.tr/tr/"
                    "kurumsal/finansmanlar"
                ),
                "source_type": "kategori_sayfasi",
            },
        ],
        "use_selenium": False,
    },
]


ADIL_MANUAL_PRODUCTS = {
    "Ticari Finansman": (
        "İşletmelerin mal ve hizmet alımlarına yönelik finansman "
        "ihtiyaçları faizsiz yöntemlerle karşılanır. Finansman, gerçek "
        "ticarete ve belgelendirilebilir işlemlere dayanır. İşletmelerin "
        "nakit akışını desteklemeyi amaçlar."
    ),
    "Bireysel Finansman": (
        "Bireysel müşterilere eğitim, sağlık, tatil ve ev eşyası gibi "
        "ihtiyaçların karşılanması amacıyla sağlanan faizsiz finansman "
        "türüdür. Talep edilen katılım esaslarına uygun ürün veya hizmet "
        "banka tarafından satın alınır ve üzerine kâr eklenerek vadeli "
        "olarak müşteriye satılır."
    ),
}


ERRORS: list[dict[str, Any]] = []
COVERAGE: list[dict[str, Any]] = []
CALCULATORS: list[dict[str, Any]] = []
OVERVIEWS: list[dict[str, Any]] = []


@dataclass(frozen=True)
class PageTarget:
    url: str
    source_type: str = "urun_sayfasi"


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\xa0", " ")
    text = re.sub(
        r"[\u00ad\u200b\u200c\u200d\u200e\u200f"
        r"\u202a-\u202e\u2060\u2066-\u2069\ufeff]",
        "",
        text,
    )
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_key(value: Any) -> str:
    """
    Arama ve sınıflandırma için Türkçe metni güvenli biçimde sadeleştirir.

    Özellikle büyük "İ" harfinin casefold sonrasında ürettiği birleşik
    nokta karakterini kaldırır:
        İhtiyaç -> ihtiyac
    """
    text = normalize_text(value).casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )

    return text.translate(
        str.maketrans(
            {
                "ç": "c",
                "ğ": "g",
                "ı": "i",
                "ö": "o",
                "ş": "s",
                "ü": "u",
                "â": "a",
                "î": "i",
                "û": "u",
            }
        )
    )


def safe_filename(value: str) -> str:
    text = normalize_key(value)
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "bank"


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower().replace(":443", "")
    path = re.sub(r"/+", "/", parsed.path or "/")

    if path != "/":
        path = path.rstrip("/")

    return urlunparse(
        (
            scheme,
            netloc,
            path,
            "",
            parsed.query,
            "",
        )
    )


def domain_allowed(
    url: str,
    allowed_domains: list[str],
) -> bool:
    netloc = urlparse(url).netloc.casefold()

    return any(
        netloc == domain.casefold()
        or netloc.endswith("." + domain.casefold())
        for domain in allowed_domains
    )


def add_error(
    bank_name: str,
    url: str,
    reason: str,
    stage: str,
) -> None:
    ERRORS.append(
        {
            "banka_adi": bank_name,
            "kaynak_url": url,
            "asama": stage,
            "neden": reason,
        }
    )


def get_soup_requests(url: str) -> BeautifulSoup | None:
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type",
            "",
        ).casefold()

        if "html" not in content_type and not response.text.lstrip().startswith(
            ("<!DOCTYPE", "<html", "<HTML")
        ):
            return None

        if response.encoding is None or response.encoding.casefold() in {
            "iso-8859-1",
            "latin-1",
        }:
            response.encoding = "utf-8"

        return BeautifulSoup(
            response.text,
            "html.parser",
        )
    except Exception:
        return None


def get_soup_selenium(url: str) -> BeautifulSoup | None:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except Exception:
        return None

    driver = None

    try:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,2200")
        options.add_argument(f"--user-agent={USER_AGENT}")
        options.add_argument("--lang=tr-TR")

        driver = webdriver.Chrome(
            options=options,
        )
        driver.set_page_load_timeout(
            REQUEST_TIMEOUT,
        )
        driver.get(url)
        time.sleep(SELENIUM_WAIT_SECONDS)

        return BeautifulSoup(
            driver.page_source,
            "html.parser",
        )
    except Exception:
        return None
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def soup_text_length(soup: BeautifulSoup | None) -> int:
    if soup is None:
        return 0
    return len(
        normalize_text(
            soup.get_text(" ", strip=True)
        )
    )



REJECTED_PAGE_SIGNALS = (
    "request rejected",
    "access denied",
    "forbidden",
    "the requested url was rejected",
    "security policy",
    "robot dogrulamasi",
)


def soup_rejected(
    soup: BeautifulSoup | None,
) -> bool:
    if soup is None:
        return False

    title_text = ""
    title_element = soup.select_one("title")

    if title_element is not None:
        title_text = title_element.get_text(
            " ",
            strip=True,
        )

    sample = normalize_key(
        f"{title_text} "
        f"{soup.get_text(' ', strip=True)[:2000]}"
    )

    return any(
        signal in sample
        for signal in REJECTED_PAGE_SIGNALS
    )


def polite_delay(
    bank: dict[str, Any],
) -> None:
    minimum = float(
        bank.get(
            "request_delay_min",
            0,
        )
    )
    maximum = float(
        bank.get(
            "request_delay_max",
            minimum,
        )
    )

    if maximum <= 0:
        return

    time.sleep(
        random.uniform(
            minimum,
            maximum,
        )
    )


def get_soup(
    url: str,
    use_selenium: bool,
    prefer_selenium: bool = False,
) -> tuple[BeautifulSoup | None, str]:
    """
    Sayfayı alır. Albaraka gibi WAF yanıtı verebilen sitelerde Selenium
    öncelikli kullanılabilir. "Request Rejected" sayfaları geçerli içerik
    olarak kabul edilmez.
    """
    if prefer_selenium and use_selenium:
        selenium_soup = get_soup_selenium(url)

        if (
            selenium_soup is not None
            and not soup_rejected(selenium_soup)
            and soup_text_length(selenium_soup) >= 250
        ):
            return selenium_soup, "selenium_oncelikli"

    request_soup = get_soup_requests(url)

    if (
        request_soup is not None
        and not soup_rejected(request_soup)
        and soup_text_length(request_soup) >= 250
    ):
        return request_soup, "requests"

    if use_selenium:
        selenium_soup = get_soup_selenium(url)

        if (
            selenium_soup is not None
            and not soup_rejected(selenium_soup)
            and soup_text_length(selenium_soup)
            > soup_text_length(request_soup)
        ):
            return selenium_soup, "selenium"

    if (
        request_soup is not None
        and not soup_rejected(request_soup)
    ):
        return request_soup, "requests_kismi"

    return None, "request_rejected"




BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "div",
    "dl",
    "dt",
    "dd",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}


def extract_semantic_text(element: Tag) -> str:
    """
    Blok etiketlerinin arasına boşluk ekleyerek sayfa metnini çıkarır.

    Türkiye Finans sayfalarında metinler çok sayıda span/strong/a etiketi
    içinde parçalanabildiği için doğrudan get_text(" ") kullanıldığında
    bazı kelimeler yapay biçimde bölünebilir. Bu yardımcı fonksiyon blok
    sınırlarını korur ve görünmeyen teknik etiketleri atlar.
    """
    parts: list[str] = []

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                parts.append(str(child))
                continue

            if not isinstance(child, Tag):
                continue

            if child.name in {
                "script",
                "style",
                "noscript",
                "svg",
                "iframe",
                "canvas",
            }:
                continue

            if child.name == "br":
                parts.append(" ")
                continue

            is_block = child.name in BLOCK_TAGS

            if is_block:
                parts.append(" ")

            walk(child)

            if is_block:
                parts.append(" ")

    walk(element)
    return normalize_text("".join(parts))


def clone_soup(soup: BeautifulSoup) -> BeautifulSoup:
    return BeautifulSoup(
        str(soup),
        "html.parser",
    )


def clean_soup(soup: BeautifulSoup) -> BeautifulSoup:
    cleaned = clone_soup(soup)

    for selector in UNWANTED_SELECTORS:
        try:
            elements = cleaned.select(selector)
        except Exception:
            continue

        for element in elements:
            element.decompose()

    return cleaned


def candidate_score(text: str) -> float:
    key = normalize_key(text)
    keyword_hits = sum(
        key.count(normalize_key(keyword))
        for keyword in FINANCE_KEYWORDS
    )
    length_score = min(len(text), 10000) / 1000
    return (keyword_hits * 7) + length_score


def extract_main_text(
    soup: BeautifulSoup,
) -> str:
    cleaned = clean_soup(soup)
    candidates: list[str] = []

    for selector in CONTENT_SELECTORS:
        try:
            elements = cleaned.select(selector)
        except Exception:
            continue

        for element in elements:
            text = normalize_text(
                element.get_text(
                    " ",
                    strip=True,
                )
            )
            if len(text) >= MIN_CONTENT_LENGTH:
                candidates.append(text)

    if cleaned.body is not None:
        body_text = normalize_text(
            cleaned.body.get_text(
                " ",
                strip=True,
            )
        )
        if len(body_text) >= MIN_CONTENT_LENGTH:
            candidates.append(body_text)

    if not candidates:
        return ""

    best = max(
        candidates,
        key=candidate_score,
    )

    marker_positions = [
        best.find(marker)
        for marker in FOOTER_MARKERS
        if best.find(marker) > 120
    ]

    if marker_positions:
        best = best[:min(marker_positions)]

    return normalize_text(best)



def extract_turkiye_finans_text(
    soup: BeautifulSoup,
    title: str,
) -> tuple[str, str]:
    """
    Türkiye Finans ASP.NET sayfalarında ürün içeriğini çıkarır.

    Genel CSS aday seçimi bu sitede aynı 424 karakterlik ortak CMS
    alanını seçebildiği için, metin doğrudan sayfa gövdesinden alınır.
    Gerçek içerik "Sayfa İçeriği" işaretinden sonra başlar ve teknik
    footer/CMS işaretlerinden önce kesilir.
    """
    body = soup.body

    if body is None:
        return "", "turkiye-finans-body-yok"

    text = extract_semantic_text(body)

    if not text:
        return "", "turkiye-finans-metin-yok"

    text_key = normalize_key(text)
    title_key = normalize_key(title)

    start_position = -1
    marker_length = 0

    for marker in (
        "Sayfa İçeriği",
        "Sayfa Icerigi",
    ):
        marker_key = normalize_key(marker)
        key_position = text_key.find(marker_key)

        if key_position >= 0:
            # Normalize edilmiş anahtarın konumu çoğu durumda gerçek metinle
            # aynıdır. Gerçek marker bulunabiliyorsa onu kullan.
            real_position = text.find(marker)
            start_position = (
                real_position
                if real_position >= 0
                else key_position
            )
            marker_length = len(marker)
            break

    if start_position >= 0:
        content = text[
            start_position + marker_length:
        ]
    else:
        # Marker görünmüyorsa başlığın son tekrarından başla. Menüdeki ilk
        # başlık yerine içerik bölümündeki son tekrar tercih edilir.
        title_position = (
            text_key.rfind(title_key)
            if title_key
            else -1
        )

        if title_position >= 0:
            content = text[title_position:]
        else:
            content = text

    content = normalize_text(content)

    # İçeriğin başında paylaşım ve yazdırma metinleri bulunabiliyor.
    removable_phrases = [
        "Sayfayı Yazdır",
        "Facebook'da Paylaş",
        "Twitter'da Paylaş",
        "Linkedin'de Paylaş",
        "Sayfa Görüntüsü",
        "Edit Field Panel",
        "Spot SubPage Bottom Starts",
        "Spot SubPage Bottom Ends",
    ]

    for phrase in removable_phrases:
        content = content.replace(
            phrase,
            " ",
        )

    footer_markers = [
        "MAIN CONTENT FOOTER",
        "Müşteri Memnuniyet Merkezi",
        "Sıkça Ziyaret Edilen Sayfalar",
        "Öne Çıkan Kategoriler",
        "Türkiye Finans Linkleri",
        "Başvuru Merkezi Hesaplama Araçları",
        "Başvuru Merkezi",
        "Site Haritası",
        "BAŞA DÖN",
        "© 2026 Türkiye Finans",
        "© 2025 Türkiye Finans",
    ]

    end_positions = [
        content.find(marker)
        for marker in footer_markers
        if content.find(marker) > MIN_CONTENT_LENGTH
    ]

    if end_positions:
        content = content[:min(end_positions)]

    content = normalize_text(content)

    # Aynı ortak CMS özetinin alınmasını önlemek için gerçek ürün başlığı
    # veya ürün türü metinde görünmelidir.
    content_key = normalize_key(content)
    required_signals = [
        title_key,
        "finansman",
        "vade",
        "kar orani",
        "tahsis ucreti",
    ]
    signal_count = sum(
        1
        for signal in required_signals
        if signal and signal in content_key
    )

    if (
        len(content) < MIN_CONTENT_LENGTH
        or signal_count < 2
    ):
        return content, "turkiye-finans-yetersiz-icerik"

    return content, "turkiye-finans-page-content"


def content_fingerprint(text: str) -> str:
    return hashlib.sha256(
        normalize_key(text).encode("utf-8")
    ).hexdigest()


def extract_title(
    soup: BeautifulSoup,
    fallback_url: str,
) -> str:
    title_candidates: list[str] = []

    for selector in (
        "h1",
        "main h2",
        "article h2",
        "meta[property='og:title']",
        "title",
    ):
        element = soup.select_one(selector)

        if element is None:
            continue

        if element.name == "meta":
            value = element.get("content", "")
        else:
            value = element.get_text(
                " ",
                strip=True,
            )

        value = normalize_text(value)

        if value:
            title_candidates.append(value)

    generic_titles = {
        "finansmanlar",
        "finansman ürünleri",
        "bireysel",
        "ana sayfa",
        "türkiye finans",
        "kuveyt türk",
        "ziraat katılım",
    }

    for candidate in title_candidates:
        if normalize_key(candidate) not in {
            normalize_key(item)
            for item in generic_titles
        }:
            return candidate

    slug = urlparse(fallback_url).path.rstrip("/").split("/")[-1]
    slug = slug.replace(".aspx", "").replace(".html", "")
    return normalize_text(
        slug.replace("-", " ").title()
    )


def extract_canonical_url(
    soup: BeautifulSoup,
    fallback_url: str,
) -> str:
    canonical = soup.select_one(
        "link[rel='canonical']"
    )

    if canonical is not None:
        href = normalize_text(
            canonical.get("href", "")
        )
        if href:
            return canonicalize_url(
                urljoin(fallback_url, href)
            )

    return canonicalize_url(fallback_url)


def classify_product(
    title: str,
    text: str,
    url: str,
) -> str:
    """
    Ürün türünü öncelikle başlık ve URL'den belirler.

    Sayfa gövdesinde menü ve başka ürün bağlantıları bulunabildiği için
    sınıflandırmada başlık + URL ana sinyal olarak kullanılır.
    """
    primary = normalize_key(
        f"{title} {url}"
    )

    if any(
        signal in primary
        for signal in (
            "leasing",
            "finansal kiralama",
        )
    ):
        return "Leasing"

    if any(
        signal in primary
        for signal in (
            "/gayri-nakdi-finansman/",
            "/gayrinakdi-finansmanlar/",
            "/e-teminat-mektubu",
            "e-teminat mektubu",
            "gayri nakdi finans",
            "gayrinakdi finans",
            "teminat mektup",
            "jet teminat mektubu",
            "elektronik teminat mektubu",
            "eximbank teminat mektubu",
            "harici garanti",
            "kontrgaranti",
            "referans mektup",
            "akreditif",
            "dogrudan borclandirma",
            "kabul aval",
            "kabul-aval",
        )
    ):
        return "Gayri Nakdi Finansman"

    if "gayrimenkul sertifikasi finans" in primary:
        if "/kurumsal/" in primary:
            return "Ticari Finansman"
        return "Arsa/Gayrimenkul Finansmanı"

    if any(
        signal in primary
        for signal in (
            "arsa finans",
            "2b finans",
            "2b arazi",
        )
    ):
        return "Arsa/Gayrimenkul Finansmanı"

    if any(
        signal in primary
        for signal in (
            "is-yeri-finans",
            "is yeri finans",
            "isyeri finans",
        )
    ):
        return "İş Yeri Finansmanı"

    if any(
        signal in primary
        for signal in (
            "konut finans",
            "konut gayrimenkul finans",
            "mortgage",
            "ilk evim",
            "gayrimenkul finans",
            "gurbetten silaya",
            "yesil konut",
            "kentsel donusum finans",
        )
    ):
        return "Konut Finansmanı"

    if any(
        signal in primary
        for signal in (
            "tasit finans",
            "arac finans",
            "otomobil finans",
            "motosiklet finans",
            "togg finans",
            "surdurulebilir arac",
            "deniz tasitlari",
            "tasit kiralama",
            "motosiklet atv bisiklet",
            "motosiklet-atv-bisiklet",
        )
    ):
        return "Taşıt Finansmanı"

    if any(
        signal in primary
        for signal in (
            "elektrikli arac sarj unitesi",
            "cati ges",
            "ges finans",
            "enerji finans",
            "yenilenebilir enerji",
            "enerji verimliligi",
        )
    ):
        return "Enerji Finansmanı"

    if any(
        signal in primary
        for signal in (
            "mavi finansman",
            "cevreci ihracat finans",
            "atik yonetimi finans",
            "atik su aritma",
            "geri kazanimi yatirim",
        )
    ):
        return "Sürdürülebilir Finansman"

    if any(
        signal in primary
        for signal in (
            "tarim",
            "hayvancilik",
            "elus",
            "elektronik urun senedi",
            "/tarim-finansmanlari/",
        )
    ):
        return "Tarım Finansmanı"

    if "proje finans" in primary:
        return "Proje Finansmanı"

    if any(
        signal in primary
        for signal in (
            "kazancli fon finans",
            "hizli fon finans",
            "bes teminatli finans",
        )
    ):
        return "Yatırım Teminatlı Finansman"

    if "bayide finansman" in primary:
        if any(
            segment_path in primary
            for segment_path in (
                "/kobi/",
                "/ticari-ve-kurumsal/",
            )
        ):
            return "Ticari Finansman"
        return "İhtiyaç Finansmanı"

    if any(
        signal in primary
        for signal in (
            "katilim finans kefalet",
            "kfk",
        )
    ):
        return "Ticari Finansman"

    if any(
        signal in primary
        for signal in (
            "ticari finans",
            "isletme finans",
            "tedarikci finans",
            "nakdi finans",
            "kobi finans",
            "online finansman",
            "aninda finansman",
            "kurumsal finansman",
            "mobil finansman",
            "mikro finansman",
            "doviz finansman",
            "/kurumsal/finansmanlar/nakdi-finansman/",
            "/nakdi-finansmanlar/",
            "/kobi-destekli-finansmanlar/",
            "savunma sanayii",
            "e-ticaret-finansmani-basvurusu",
            "e ticaret finansmani basvurusu",
            "dbs fatura teminatli",
            "kira sertifikasi teminatli",
            "pratik kobi kart",
            "kar zarar ortakligi",
            "kar-zarar ortakligi",
        )
    ):
        return "Ticari Finansman"

    if any(
        signal in primary
        for signal in (
            "ihtiyac finans",
            "ihtiyac kart",
            "alisveris kredi",
            "alisveris finans",
            "egitim finans",
            "seyahat finans",
            "kira finans",
            "hac finans",
            "umre finans",
            "hac-umre",
            "veresiye",
            "taksitli alisveris",
            "bana bunu al",
            "tekne tuketici",
            "bisiklet finans",
            "pratik finansman kart",
            "sms li finansman",
            "sms'li finansman",
            "sms-li-finansman",
            "jet finansman",
            "karz i hasen",
            "karz-i hasen",
            "bireysel finansman",
        )
    ):
        return "İhtiyaç Finansmanı"

    if "surdurulebilir" in primary:
        return "Sürdürülebilir Finansman"

    body_key = normalize_key(text[:1000])

    if "ticari finansman" in body_key:
        return "Ticari Finansman"

    if "bireysel finansman" in body_key:
        return "İhtiyaç Finansmanı"

    return "Diğer Finansman"


def classify_segment(
    title: str,
    text: str,
    url: str,
) -> str:
    combined = normalize_key(
        f"{title} {url} {text[:700]}"
    )

    if any(
        signal in combined
        for signal in (
            "/kobi/",
            "/kurumsal/",
            "isim-icin",
            "ticari finans",
            "isletme finans",
            "tedarikci",
            "kobi",
            "kurumsal musteri",
        )
    ):
        return "Ticari/KOBİ"

    return "Bireysel"


def create_id(
    bank_name: str,
    source_url: str,
    title: str,
) -> str:
    raw = (
        f"{normalize_key(bank_name)}|"
        f"{canonicalize_url(source_url)}|"
        f"{normalize_key(title)}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:20]



def normalize_product_title(
    bank_name: str,
    title: str,
    url: str,
) -> str:
    """
    Sayfanın H1/meta başlığı ürün yerine üst kategori adı döndürdüğünde,
    URL'ye dayalı güvenli ürün başlığı düzeltmesi yapar.
    """
    normalized_title = normalize_text(title)
    path = urlparse(url).path.casefold().rstrip("/")

    if bank_name == "Kuveyt Türk":
        title_overrides = {
            # Sayfanın keşfedilen URL'si canonical etiketi nedeniyle
            # leasing altındaki bu adrese dönüşebiliyor.
            (
                "/isim-icin/leasing/"
                "surdurulebilir-urunlerimiz"
            ): "Sürdürülebilir Leasing Finansmanı",

            # Eski/alternatif ürün yolu da desteklenir.
            (
                "/isim-icin/surdurulebilir-urunler/"
                "surdurulebilir-leasing-finansmani"
            ): "Sürdürülebilir Leasing Finansmanı",

            (
                "/isim-icin/surdurulebilir-urunler/"
                "isletme-finansmani"
            ): "Sürdürülebilir İşletme Finansmanı",
        }

        if path in title_overrides:
            return title_overrides[path]

    if bank_name == "Albaraka Türk":
        albaraka_title_overrides = {
            (
                "/tr/ticari-ve-kurumsal/finansmanlar/"
                "ticari-nakdi-finansman/kurumsal-finansman-destegi"
            ): "İş Yeri Finansmanı",
            (
                "/tr/kobi/finansmanlar/kobi-nakdi-finansman/"
                "kobi-finansman-destegi"
            ): "İş Yeri Finansmanı",
        }

        if path in albaraka_title_overrides:
            return albaraka_title_overrides[path]

        if normalize_key(normalized_title) in {
            "isyeri finansmani",
            "is yeri finansmani",
        }:
            return "İş Yeri Finansmanı"

    if bank_name == "Ziraat Katılım":
        ziraat_title_overrides = {
            "/bireysel/finansman-urunleri/konut-gayrimenkul-finansmani":
                "Konut ve Gayrimenkul Finansmanı",
            "/bireysel/finansman-urunleri/tasit-finansmani":
                "Taşıt Finansmanı",
            "/bireysel/finansman-urunleri/ihtiyac-finansmani":
                "İhtiyaç Finansmanı",
            "/ticari/finansal-kiralama-leasing/finansal-kiralama-leasing":
                "Finansal Kiralama (Leasing)",
            "/ticari/finansal-kiralama-leasing/eximbank-finansal-kiralama-programi":
                "Eximbank Finansal Kiralama Programı",
            "/ticari/dijital-bankacilik/aninda-finansman":
                "Anında Finansman",
            "/tarim/tarim-finansmani":
                "Tarım Finansmanı",
            "/tarim/tarimsal-finansman-%c3%bcr%c3%bcnleri":
                "Tarımsal Finansman Ürünleri",
            (
                "/bireysel/finansman-urunleri/"
                "surdurulebilirlik-temali-bireysel-urunler/"
                "enerji-verimliligi-yonetim-finansmani"
            ): "Enerji Verimliliği Yönetim Finansmanı",
            (
                "/ticari/finansman-urunleri/"
                "nakdi-finansman-urunleri/kurumsal-finansman"
            ): "Kurumsal Finansman",
            (
                "/ticari/finansman-urunleri/"
                "nakdi-finansman-urunleri/mobil-finansman"
            ): "Mobil Finansman",
            (
                "/ticari/finansman-urunleri/"
                "nakdi-finansman-urunleri/doviz-finansman%c4%b1"
            ): "Döviz Finansmanı",
            (
                "/ticari/finansman-urunleri/"
                "gayri-nakdi-finansman-urunleri/teminat-mektuplari"
            ): "Teminat Mektupları",
            (
                "/ticari/finansman-urunleri/"
                "gayri-nakdi-finansman-urunleri/referans-mektuplari"
            ): "Referans Mektupları",
            (
                "/ticari/finansman-urunleri/"
                "gayri-nakdi-finansman-urunleri/kabul-aval-finansmani"
            ): "Kabul-Aval Finansmanı",
            (
                "/ticari/finansman-urunleri/"
                "gayri-nakdi-finansman-urunleri/akreditif"
            ): "Akreditif",
        }

        if path in ziraat_title_overrides:
            return ziraat_title_overrides[path]

        # Ziraat bazı sayfalarda H1/meta başlığı olarak yalnızca banka adını
        # döndürüyor. Böyle durumlarda son URL parçasından okunabilir başlık
        # üretilir.
        generic_titles = {
            "ziraat katilim bankasi",
            "ziraat katilim",
        }

        if normalize_key(normalized_title) in generic_titles:
            slug = path.rsplit("/", 1)[-1]
            slug = slug.replace("%c3%bc", "ü")
            slug = slug.replace("_", "-")
            words = [
                word
                for word in slug.split("-")
                if word
            ]
            return normalize_text(
                " ".join(words).title()
            )

    if bank_name == "Türkiye Emlak Katılım":
        emlak_title_overrides = {
            (
                "/tr/bireysel/finansmanlar/"
                "tamamlayici-konut-finansmani"
            ): "Tamamlayıcı Konut Finansmanı",
            (
                "/tr/bireysel/finansmanlar/"
                "isyeri-finansmani"
            ): "İş Yeri Finansmanı",
        }

        if path in emlak_title_overrides:
            return emlak_title_overrides[path]

        if normalize_key(normalized_title) in {
            "isyeri finansmani",
            "is yeri finansmani",
        }:
            return "İş Yeri Finansmanı"

    return normalized_title



def invalid_page_reason(
    title: str,
    text: str,
) -> str | None:
    """
    Bankanın gerçek ürün sayfası yerine hata/WAF yanıtı döndürdüğü
    durumları veri setine almadan yakalar.
    """
    combined = normalize_key(
        f"{title} {text[:500]}"
    )

    for signal in REJECTED_PAGE_SIGNALS:
        if signal in combined:
            return f"Geçersiz sayfa yanıtı: {signal}"

    return None


def create_record(
    bank_name: str,
    title: str,
    url: str,
    text: str,
    source_type: str,
    collection_method: str,
) -> dict[str, Any]:
    normalized_title = normalize_product_title(
        bank_name,
        title,
        url,
    )

    product_type = (
        "Finansman Hesaplama"
        if source_type == "hesaplama_araci"
        else classify_product(
            normalized_title,
            text,
            url,
        )
    )
    segment = classify_segment(
        normalized_title,
        text,
        url,
    )

    return {
        "id": create_id(
            bank_name,
            url,
            normalized_title,
        ),
        "banka_adi": bank_name,
        "kayit_turu": "finansman_urunu",
        "urun_turu": product_type,
        "urun_adi": normalized_title,
        "segment": segment,
        "kaynak_url": canonicalize_url(url),
        "toplama_tarihi": date.today().isoformat(),
        "ham_metin": text,
        "kaynak_turu": source_type,
        "otomatik_toplama_durumu": collection_method,
        "kar_payi_orani": "",
        "vade_suresi": "",
        "finansman_tutari": "",
        "masraf_durumu": "",
        "tahsis_ucreti": "",
        "dosya_masrafi": "",
        "ekspertiz_ucreti": "",
        "sigorta_kosulu": "",
        "kampanya_avantaji": "",
        "hedef_kitle": "",
        "bilgi_yayin_durumu": "ham_metin_toplandi",
    }


def should_include_link(
    label: str,
    href: str,
) -> bool:
    combined = normalize_key(
        f"{label} {href}"
    )

    if any(
        excluded in combined
        for excluded in EXCLUDED_LINK_PARTS
    ):
        return False

    return any(
        normalize_key(keyword) in combined
        for keyword in FINANCE_KEYWORDS
    )


KUVEYT_INDEX_PATHS = {
    "/kendim-icin/finansmanlar",
    "/kendim-icin/finansmanlar/konut-finansmanlari",
    "/kendim-icin/finansmanlar/arac-finansmanlari",
    "/kendim-icin/finansmanlar/alisveris-finansmanlari",
    "/kendim-icin/finansmanlar/ihtiyac-finansmanlari",
    "/kendim-icin/finansmanlar/ihtiyac-finansmani",
    "/kendim-icin/finansmanlar/surdurulebilir-finansmanlar",
    "/isim-icin/finansman-urunleri",
    "/isim-icin/finansman-urunleri/gayri-nakdi-finansman",
    "/isim-icin/finansman-urunleri/nakdi-finansman",
    "/isim-icin/leasing/leasing-finansman-urunlerimiz",
}

KUVEYT_EXCLUDED_PREFIXES = (
    "/kendim-icin/altin-bankaciligi/",
    "/isim-icin/kartlar-ve-pos/",
    "/isim-icin/esnaf-ve-kobiler",
    "/isim-icin/dis-ticaret/finansmanlar",
)

# Aynı ürünlerin çalışan ana URL'leri zaten bulunduğu için bu bozuk veya
# yönlendirme niteliğindeki alias yolları ayrıca taranmaz.
KUVEYT_EXCLUDED_ALIAS_PATHS = {
    (
        "/kendim-icin/finansmanlar/surdurulebilir-finansmanlar/"
        "elektrikli-arac-sarj-unitesi-finansmani"
    ),
    (
        "/kendim-icin/finansmanlar/surdurulebilir-finansmanlar/"
        "bisiklet-finansmani"
    ),
    (
        "/kendim-icin/finansmanlar/ihtiyac-finansmani/"
        "elektrikli-arac-sarj-unitesi-finansmani"
    ),
    (
        "/kendim-icin/finansmanlar/ihtiyac-finansmani/"
        "bisiklet-finansmani"
    ),
}

KUVEYT_CALCULATOR_PATHS = {
    "/hesaplama-araclari/finansman-hesaplama",
    "/isim-icin/leasing/leasing-sureci-ve-hesaplama-araci",
}


ALBARAKA_INDEX_PATHS = {
    "/tr/bireysel/finansmanlar",
    "/tr/bireysel/finansmanlar/konut-finansmani",
    "/tr/bireysel/finansmanlar/tasit-finansmani",
    "/tr/bireysel/finansmanlar/gayrimenkul-finansmani",
    "/tr/kobi/finansmanlar",
    "/tr/kobi/finansmanlar/kobi-nakdi-finansman",
    "/tr/kobi/finansmanlar/kobi-gayri-nakdi-finansman",
    "/tr/ticari-ve-kurumsal/finansmanlar",
    (
        "/tr/ticari-ve-kurumsal/finansmanlar/"
        "ticari-nakdi-finansman"
    ),
    (
        "/tr/ticari-ve-kurumsal/finansmanlar/"
        "ticari-gayri-nakdi-finansman"
    ),
}

ALBARAKA_ALLOWED_PREFIXES = (
    "/tr/bireysel/finansmanlar/",
    "/tr/kobi/finansmanlar/",
    "/tr/ticari-ve-kurumsal/finansmanlar/",
)


ZIRAAT_INDEX_PATHS = {
    "/bireysel/finansman-urunleri",
    "/bireysel/finansman-urunleri/surdurulebilirlik-temali-bireysel-urunler",
    "/ticari/finansman-urunleri",
    "/ticari/finansman-urunleri/nakdi-finansman-urunleri",
    "/ticari/finansman-urunleri/gayri-nakdi-finansman-urunleri",
    "/ticari/finansman-urunleri/surdurulebilirlik-temali-ticari-urunler",
    "/ticari/finansman-urunleri/dis-ticaret-finansmanlari",
    "/ticari/finansal-kiralama-leasing",
    "/tarim/tarimsal-finansman-%c3%bcr%c3%bcnleri",
}

ZIRAAT_ALLOWED_PREFIXES = (
    "/bireysel/finansman-urunleri/",
    "/ticari/finansman-urunleri/",
    "/ticari/finansal-kiralama-leasing/",
    "/tarim/tarimsal-finansman-%c3%bcr%c3%bcnleri/",
)

ZIRAAT_EXCLUDED_PATHS = {
    "/ticari/finansman-urunleri/finansman_is_birlikleri",
}


VAKIF_INDEX_PATHS = {
    "/tr/kendim-icin/finansmanlar",
    "/tr/isim-icin/finansmanlar",
    "/tr/isim-icin/finansmanlar/finansal-kiralamalar",
    "/tr/isim-icin/finansmanlar/kobi-destekli-finansmanlar",
    "/tr/isim-icin/finansmanlar/tarim-finansmanlari",
    (
        "/tr/isim-icin/finansmanlar/"
        "tarim-finansmanlari/tarim-finansman-urunleri"
    ),
    "/tr/isim-icin/finansmanlar/gayrinakdi-finansmanlar",
    "/tr/isim-icin/finansmanlar/nakdi-finansmanlar",
}

VAKIF_ALLOWED_PREFIXES = (
    "/tr/kendim-icin/finansmanlar/",
    "/tr/isim-icin/finansmanlar/",
)

VAKIF_CALCULATOR_PATHS = {
    (
        "/tr/yardimci-sayfalar/hesaplama-araclari/"
        "finansman-hesaplama"
    ),
}

VAKIF_EXCLUDED_PATHS = {
    "/tr/yardimci-sayfalar/hesaplama-araclari",
    "/tr/isim-icin/ticari",
    "/tr/isim-icin/kobi",
    "/tr/isim-icin/ticari-kartlar",

    # Başvuru/form sayfası; ayrı finansman ürünü değildir.
    (
        "/tr/isim-icin/finansmanlar/"
        "finansal-kiralamalar/finansal-kiralama-basvurusu"
    ),

    # İhracat alacak sigortası ürünüdür; finansman ürünü değildir.
    (
        "/tr/isim-icin/finansmanlar/nakdi-finansmanlar/"
        "eximbank-katilim-esasli-ihracat-alacak-sigortasi-keas"
    ),
}



DUNYA_INDEX_PATHS = {
    "/kendim-icin/finansmanlar",
    "/kendim-icin/finansmanlar/ihtiyac-finansmanlari",
    "/kendim-icin/finansmanlar/arac-finansmanlari",
    "/kendim-icin/finansmanlar/konut-finansmanlari",
    "/isim-icin/finansmanlar",
    "/isim-icin/finansmanlar/nakdi-finansman",
    "/isim-icin/finansmanlar/gayri-nakdi-finansman",
}

DUNYA_PRODUCT_PATHS = {
    "/kendim-icin/finansmanlar/ihtiyac-finansmani",
}

DUNYA_ALLOWED_PREFIXES = (
    "/kendim-icin/finansmanlar/ihtiyac-finansmanlari/",
    "/kendim-icin/finansmanlar/arac-finansmanlari/",
    "/kendim-icin/finansmanlar/konut-finansmanlari/",
    "/isim-icin/finansmanlar/nakdi-finansman/",
    "/isim-icin/finansmanlar/gayri-nakdi-finansman/",
)

DUNYA_EXCLUDED_PREFIXES = (
    "/kampanyalar/",
    "/politikalarimiz/",
    "/isim-icin/kobi-bankaciligi",
    "/isim-icin-icerik/surdurulebilir-cozumler",
)



HAYAT_INDEX_PATHS = {
    "/krediler",
    "/finansmanlar",
    "/finansmanlar-is",
}

HAYAT_PRODUCT_PATHS = {
    "/krediler/bana-bunu-al",
    "/krediler/hayat-finans-egitim-finansmani-sistemi",
    "/finansmanlar/bana-bunu-al-is-ortagim",
    "/finansmanlar-is/mikro-finansman",
    "/finansmanlar-is/isletme-finansmani",
    "/finansmanlar-is/ticari-finansman",
    "/finansmanlar-is/e-teminat-mektubu",
}



EMLAK_INDEX_PATHS = {
    "/tr/bireysel/finansmanlar",
    "/tr/kurumsal/finansmanlar",
}

EMLAK_ALLOWED_PREFIXES = (
    "/tr/bireysel/finansmanlar/",
    "/tr/kurumsal/finansmanlar/nakdi-finansman/",
    "/tr/kurumsal/finansmanlar/gayrinakdi-finansman/",
)

EMLAK_EXCLUDED_PATHS = {
    "/tr",
    "/finansmanonbasvuru",
    "/tr/satilik-gayrimenkuller-araclar",
    "/tr/bireysel/finansmanlar/toki-islemleri",
}


ALBARAKA_EXCLUDED_PATHS = {
    "/tr/bireysel/finansmanlar/kredi-notu-ogrenme",

    # Aynı gayri nakdi ürünlerin çalışan KOBİ sayfaları zaten taranıyor.
    # Ticari menüdeki bu kopyalar bazı isteklerde "Request Rejected"
    # döndürdüğü için hedef listesine alınmaz.
    (
        "/tr/ticari-ve-kurumsal/finansmanlar/"
        "ticari-gayri-nakdi-finansman/teminat-mektuplari"
    ),
    (
        "/tr/ticari-ve-kurumsal/finansmanlar/"
        "ticari-gayri-nakdi-finansman/jet-teminat-mektubu"
    ),
    (
        "/tr/ticari-ve-kurumsal/finansmanlar/"
        "ticari-gayri-nakdi-finansman/akreditifler"
    ),
    (
        "/tr/ticari-ve-kurumsal/finansmanlar/"
        "ticari-gayri-nakdi-finansman/kabul-aval-finansmanlari"
    ),
    (
        "/tr/ticari-ve-kurumsal/finansmanlar/"
        "ticari-gayri-nakdi-finansman/referans-mektuplari"
    ),
}


def resolve_link_role(
    bank: dict[str, Any],
    label: str,
    url: str,
) -> str | None:
    """
    Bağlantının veri setindeki rolünü belirler.

    Dönen değerler:
        "urun_sayfasi"   -> veri kaydı oluştur
        "hesaplama_araci" -> ayrı araç raporuna yaz
        "index"          -> ürün keşfetmek için tara, kayıt oluşturma
        None             -> ilgisiz bağlantı
    """
    if not should_include_link(
        label,
        url,
    ):
        return None

    path = urlparse(url).path.casefold().rstrip("/")

    if bank["name"] == "Kuveyt Türk":
        if path in KUVEYT_CALCULATOR_PATHS:
            return "hesaplama_araci"

        if path in KUVEYT_EXCLUDED_ALIAS_PATHS:
            return None

        if any(
            path.startswith(prefix)
            for prefix in KUVEYT_EXCLUDED_PREFIXES
        ):
            return None

        if path in KUVEYT_INDEX_PATHS:
            return "index"

        # Kuveyt Türk'te yalnızca açık finansman ürün rotalarını kabul et.
        allowed_prefixes = (
            "/kendim-icin/finansmanlar/",
            "/isim-icin/finansman-urunleri/",
            "/isim-icin/leasing/",
            "/isim-icin/tarim-bankaciligi/",
            "/isim-icin/surdurulebilir-urunler/",
            "/isim-icin/diger-urun-ve-hizmetlerimiz/proje-finansmani",
        )

        if any(
            path.startswith(prefix)
            for prefix in allowed_prefixes
        ):
            return "urun_sayfasi"

        return None

    if bank["name"] == "Albaraka Türk":
        if path in ALBARAKA_EXCLUDED_PATHS:
            return None

        if path in ALBARAKA_INDEX_PATHS:
            return "index"

        if any(
            path.startswith(prefix)
            for prefix in ALBARAKA_ALLOWED_PREFIXES
        ):
            return "urun_sayfasi"

        # Kampanya, sigorta, POS, kart, yatırım ve nakit yönetimi gibi
        # finansman ürünü olmayan menü alanları veri setine girmez.
        return None

    if bank["name"] == "Ziraat Katılım":
        if path in ZIRAAT_EXCLUDED_PATHS:
            return None

        if path in ZIRAAT_INDEX_PATHS:
            return "index"

        if any(
            path.startswith(prefix)
            for prefix in ZIRAAT_ALLOWED_PREFIXES
        ):
            return "urun_sayfasi"

        # Yatırım, POS, kart, dijital bankacılık, nakit yönetimi ve benzeri
        # genel menü alanları finansman veri setine alınmaz.
        return None

    if bank["name"] == "Vakıf Katılım":
        if path in VAKIF_CALCULATOR_PATHS:
            return "hesaplama_araci"

        if path in VAKIF_EXCLUDED_PATHS:
            return None

        if path in VAKIF_INDEX_PATHS:
            return "index"

        if any(
            path.startswith(prefix)
            for prefix in VAKIF_ALLOWED_PREFIXES
        ):
            return "urun_sayfasi"

        # Genel ticari/KOBİ tanıtım, kart ve hesaplama kategori sayfaları
        # finansman ürünü olarak kaydedilmez.
        return None

    if bank["name"] == "Dünya Katılım":
        if any(
            path.startswith(prefix)
            for prefix in DUNYA_EXCLUDED_PREFIXES
        ):
            return None

        if path in DUNYA_INDEX_PATHS:
            return "index"

        if path in DUNYA_PRODUCT_PATHS:
            return "urun_sayfasi"

        if any(
            path.startswith(prefix)
            for prefix in DUNYA_ALLOWED_PREFIXES
        ):
            return "urun_sayfasi"

        # Kampanya, politika, genel KOBİ ve sürdürülebilirlik tanıtım
        # sayfaları finansman ürün veri setine alınmaz.
        return None

    if bank["name"] == "Hayat Finans Katılım":
        if path in HAYAT_INDEX_PATHS:
            return "index"

        if path in HAYAT_PRODUCT_PATHS:
            return "urun_sayfasi"

        # Kart, kampanya, hesap, dış ticaret ve diğer genel menü
        # bağlantıları finansman ürün veri setine alınmaz.
        return None

    if bank["name"] == "Türkiye Emlak Katılım":
        if path in EMLAK_EXCLUDED_PATHS:
            return None

        if path in EMLAK_INDEX_PATHS:
            return "index"

        if any(
            path.startswith(prefix)
            for prefix in EMLAK_ALLOWED_PREFIXES
        ):
            return "urun_sayfasi"

        # Ana site, ön başvuru, TOKİ işlemleri, satılık varlıklar ve
        # finansman kapsamı dışındaki genel bağlantılar alınmaz.
        return None

    if "hesaplama" in normalize_key(
        f"{label} {url}"
    ):
        return "hesaplama_araci"

    return "urun_sayfasi"


def discover_targets(
    bank: dict[str, Any],
) -> list[PageTarget]:
    """
    Sabit URL'leri ekler ve listeleme sayfalarını en fazla iki düzeyli
    kuyruk mantığıyla tarar.

    Kuveyt Türk'te kategori sayfaları veri kaydı olmaz; yalnızca alt ürün
    sayfalarını keşfetmek için kullanılır.
    """
    targets: dict[str, PageTarget] = {}

    overview_seed_urls: list[str] = []

    for item in bank.get(
        "fixed_urls",
        [],
    ):
        target = PageTarget(
            url=canonicalize_url(
                item["url"]
            ),
            source_type=item.get(
                "source_type",
                "urun_sayfasi",
            ),
        )
        targets[target.url] = target

        if target.source_type == "kategori_sayfasi":
            overview_seed_urls.append(
                target.url
            )

    queue = [
        canonicalize_url(seed_url)
        for seed_url in bank.get(
            "seed_urls",
            [],
        )
    ] + overview_seed_urls
    visited: set[str] = set()
    queued: set[str] = set(queue)

    while (
        queue
        and len(visited)
        < MAX_DISCOVERY_PAGES_PER_BANK
        and len(targets)
        < MAX_DISCOVERED_URLS_PER_BANK
    ):
        listing_url = queue.pop(0)
        queued.discard(listing_url)

        if listing_url in visited:
            continue

        visited.add(listing_url)

        polite_delay(bank)
        soup, method = get_soup(
            listing_url,
            bank.get(
                "use_selenium",
                False,
            ),
            bank.get(
                "prefer_selenium",
                False,
            ),
        )

        if soup is None:
            add_error(
                bank["name"],
                listing_url,
                "Listeleme sayfası alınamadı.",
                "discovery",
            )
            continue

        print(
            f" Listeleme: {listing_url} [{method}]"
        )

        for anchor in soup.select("a[href]"):
            href = normalize_text(
                anchor.get("href", "")
            )
            label = normalize_text(
                anchor.get_text(
                    " ",
                    strip=True,
                )
            )

            if not href:
                continue

            absolute = canonicalize_url(
                urljoin(listing_url, href)
            )

            if absolute == listing_url:
                continue

            if not domain_allowed(
                absolute,
                bank["domains"],
            ):
                continue

            role = resolve_link_role(
                bank,
                label,
                absolute,
            )

            if role is None:
                continue

            if role == "index":
                if (
                    absolute not in visited
                    and absolute not in queued
                ):
                    queue.append(absolute)
                    queued.add(absolute)
                continue

            targets.setdefault(
                absolute,
                PageTarget(
                    url=absolute,
                    source_type=role,
                ),
            )

            if (
                len(targets)
                >= MAX_DISCOVERED_URLS_PER_BANK
            ):
                break

    return list(targets.values())


def scrape_adil_products(
    bank: dict[str, Any],
    target: PageTarget,
) -> list[dict[str, Any]]:
    polite_delay(bank)
    soup, method = get_soup(
        target.url,
        bank.get(
            "use_selenium",
            True,
        ),
        bank.get(
            "prefer_selenium",
            False,
        ),
    )

    records: list[dict[str, Any]] = []

    if soup is not None:
        page_text = extract_main_text(soup)
    else:
        page_text = ""

    for title, fallback_text in (
        ADIL_MANUAL_PRODUCTS.items()
    ):
        title_position = normalize_key(
            page_text
        ).find(
            normalize_key(title)
        )

        if title_position >= 0:
            # Sayfa tek parça döndüğü için güvenilir bölme yapılamıyorsa
            # resmî sayfadaki kısa doğrulanmış metin kullanılır.
            text = fallback_text
            method_used = (
                f"{method}_resmi_metin_geri_donusu"
            )
        else:
            text = fallback_text
            method_used = (
                "resmi_metin_geri_donusu"
            )

        records.append(
            create_record(
                bank_name=bank["name"],
                title=title,
                url=target.url,
                text=text,
                source_type=target.source_type,
                collection_method=method_used,
            )
        )

    return records


def scrape_bank(
    bank: dict[str, Any],
) -> list[dict[str, Any]]:
    print(
        f"\n=== {bank['name']} finansman ürünleri taranıyor ==="
    )

    targets = discover_targets(bank)

    print(
        f" Toplanacak sayfa: {len(targets)}"
    )

    records: list[dict[str, Any]] = []

    for index, target in enumerate(
        targets,
        start=1,
    ):
        print(
            f" [{index}/{len(targets)}] {target.url}"
        )

        if (
            bank.get("mode")
            == "adil_products"
        ):
            records.extend(
                scrape_adil_products(
                    bank,
                    target,
                )
            )
            continue

        polite_delay(bank)
        soup, method = get_soup(
            target.url,
            bank.get(
                "use_selenium",
                False,
            ),
            bank.get(
                "prefer_selenium",
                False,
            ),
        )

        if soup is None:
            add_error(
                bank["name"],
                target.url,
                "Sayfa alınamadı.",
                "fetch",
            )
            print("   - Alınamadı")
            continue

        canonical_url = extract_canonical_url(
            soup,
            target.url,
        )
        title = extract_title(
            soup,
            canonical_url,
        )

        # Hesaplama araçları bir finansman ürünü değildir. Sayfa metinleri
        # çoğu zaman bütün ürün seçeneklerini ve form alanlarını birlikte
        # içerdiği için ürün veri setini kirletebilir. Bu nedenle yalnızca
        # erişim ve kaynak bilgisi ayrı bir raporda saklanır.
        if target.source_type == "hesaplama_araci":
            CALCULATORS.append(
                {
                    "banka_adi": bank["name"],
                    "arac_adi": title,
                    "kaynak_url": canonical_url,
                    "toplama_tarihi": date.today().isoformat(),
                    "erisim_yontemi": method,
                    "durum": "erisim_basarili",
                }
            )
            print(
                "   ↪ Hesaplama aracı ayrı kaydedildi; "
                "finansman ürün veri setine eklenmedi."
            )
            continue

        if target.source_type == "kategori_sayfasi":
            OVERVIEWS.append(
                {
                    "banka_adi": bank["name"],
                    "sayfa_adi": normalize_product_title(
                        bank["name"],
                        title,
                        canonical_url,
                    ),
                    "kaynak_url": canonical_url,
                    "toplama_tarihi": date.today().isoformat(),
                    "erisim_yontemi": method,
                    "durum": "kategori_sayfasi",
                }
            )
            print(
                "   ↪ Kategori/ürün ailesi sayfası ayrı kaydedildi; "
                "ürün veri setine eklenmedi."
            )
            continue

        if bank["name"] == "Türkiye Finans":
            text, extraction_diagnostic = (
                extract_turkiye_finans_text(
                    soup,
                    title,
                )
            )
            method = (
                f"{method}/"
                f"{extraction_diagnostic}"
            )
        else:
            text = extract_main_text(soup)
            extraction_diagnostic = (
                "generic-main-content"
            )

        invalid_reason = invalid_page_reason(
            title,
            text,
        )

        if invalid_reason:
            add_error(
                bank["name"],
                canonical_url,
                invalid_reason,
                "invalid_page",
            )
            print(
                f"   - Geçersiz sayfa yanıtı atlandı: "
                f"{title}"
            )
            continue

        if len(text) < MIN_CONTENT_LENGTH:
            add_error(
                bank["name"],
                canonical_url,
                (
                    "İçerik kalite eşiğinin altında: "
                    f"{len(text)} karakter."
                ),
                "content",
            )
            print(
                f"   - Kısa içerik: {len(text)} karakter"
            )
            continue

        record = create_record(
            bank_name=bank["name"],
            title=title,
            url=canonical_url,
            text=text,
            source_type=target.source_type,
            collection_method=method,
        )
        records.append(record)

        print(
            f"   + {record['urun_adi']} "
            f"[{record['urun_turu']}] "
            f"({len(text)} karakter)"
        )

    deduplicated: dict[str, dict[str, Any]] = {}
    seen_content: dict[str, str] = {}
    exact_duplicate_count = 0
    alias_duplicate_count = 0

    # Yalnızca farklı menü yollarında aynı ürünü temsil ettiği doğrulanan
    # başlıklar alias olarak birleştirilir. Aynı başlıklı fakat farklı ürün
    # varyantları (ör. Sürdürülebilir İşletme Finansmanı) korunur.
    known_alias_titles = {
        "tarim ve hayvancilik finansmani",
        "togg finansmani",
        "ihtiyac kart",
    }

    merge_all_same_title_segment = (
        bank["name"] in {
            "Albaraka Türk",
            "Ziraat Katılım",
        }
    )

    if bank["name"] == "Albaraka Türk":
        known_alias_titles.update(
            {
                "leasing finansal kiralama",
                "katilim finans kefalet kfk",
                "bayide finansman",
            }
        )
    alias_groups: dict[
        tuple[str, str],
        dict[str, Any],
    ] = {}

    for record in records:
        fingerprint = content_fingerprint(
            record["ham_metin"]
        )
        previous_url = seen_content.get(
            fingerprint
        )

        if (
            previous_url
            and previous_url
            != record["kaynak_url"]
        ):
            exact_duplicate_count += 1
            print(
                "   - Atlandı: başka ürün sayfasıyla "
                "birebir aynı içerik"
            )
            continue

        seen_content[fingerprint] = (
            record["kaynak_url"]
        )

        normalized_title = normalize_key(
            record["urun_adi"]
        )

        if (
            not merge_all_same_title_segment
            and normalized_title not in known_alias_titles
        ):
            deduplicated[record["id"]] = record
            continue

        alias_key = (
            normalized_title,
            normalize_key(
                record["segment"]
            ),
        )
        previous_record = alias_groups.get(
            alias_key
        )

        if previous_record is None:
            alias_groups[alias_key] = record
            continue

        # Bilinen alias ürünlerde daha uzun ve zengin metin korunur.
        alias_duplicate_count += 1

        if len(record["ham_metin"]) > len(
            previous_record["ham_metin"]
        ):
            alias_groups[alias_key] = record

        if merge_all_same_title_segment:
            print(
                "   - Birleştirildi: aynı ürün adı ve segment "
                f"({record['urun_adi']})"
            )
        else:
            print(
                "   - Birleştirildi: doğrulanmış alias ürün "
                f"({record['urun_adi']})"
            )

    for record in alias_groups.values():
        deduplicated[record["id"]] = record

    output_records = list(
        deduplicated.values()
    )

    type_counts: dict[str, int] = {}

    for record in output_records:
        key = record["urun_turu"]
        type_counts[key] = (
            type_counts.get(key, 0) + 1
        )

    COVERAGE.append(
        {
            "banka_adi": bank["name"],
            "hedef_sayfa_sayisi": len(targets),
            "toplanan_kayit_sayisi": len(
                output_records
            ),
            "urun_turu_dagilimi": type_counts,
            "birebir_icerik_tekrari_atlanan": exact_duplicate_count,
            "urun_adi_segment_tekrari_birlestirilen": alias_duplicate_count,
            "durum": (
                "basarili"
                if output_records
                else "kayit_yok"
            ),
        }
    )

    save_bank_json(
        bank["name"],
        output_records,
    )

    return output_records


def save_bank_json(
    bank_name: str,
    records: list[dict[str, Any]],
) -> None:
    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        RAW_DIR
        / (
            f"{safe_filename(bank_name)}_"
            f"{date.today().isoformat()}.json"
        )
    )

    if not records:
        print(
            " Kaydedilecek kayıt bulunamadı. "
            "Varsa önceki başarılı banka JSON'u korunuyor."
        )
        return

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            records,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f" Kaydedildi: {path} "
        f"({len(records)} kayıt)"
    )


def write_csv(
    path: Path,
    records: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=FIELDS,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(records)


def write_reports() -> None:
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    with ERROR_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            ERRORS,
            file,
            ensure_ascii=False,
            indent=2,
        )

    with COVERAGE_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            COVERAGE,
            file,
            ensure_ascii=False,
            indent=2,
        )

    with CALCULATOR_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            CALCULATORS,
            file,
            ensure_ascii=False,
            indent=2,
        )

    with OVERVIEW_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            OVERVIEWS,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"Hata raporu: {ERROR_FILE} "
        f"({len(ERRORS)} kayıt)"
    )
    print(
        f"Kapsam raporu: {COVERAGE_FILE}"
    )
    print(
        f"Hesaplama araçları: {CALCULATOR_FILE} "
        f"({len(CALCULATORS)} kayıt)"
    )
    print(
        f"Kategori/ürün ailesi sayfaları: {OVERVIEW_FILE} "
        f"({len(OVERVIEWS)} kayıt)"
    )


def find_bank(
    bank_name: str,
) -> dict[str, Any] | None:
    requested = normalize_key(
        bank_name
    )

    for bank in BANKS:
        if normalize_key(bank["name"]) == requested:
            return copy.deepcopy(bank)

    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Katılım bankalarının finansman "
            "ürün sayfalarını toplar."
        )
    )

    parser.add_argument(
        "--bank",
        type=str,
        default="",
        help=(
            'Örnek: --bank "Türkiye Finans"'
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.bank:
        bank = find_bank(args.bank)

        if bank is None:
            available = ", ".join(
                item["name"]
                for item in BANKS
            )
            print(
                f"[HATA] Banka bulunamadı: "
                f"{args.bank}"
            )
            print(
                f"Kullanılabilir bankalar: "
                f"{available}"
            )
            sys.exit(1)

        records = scrape_bank(bank)

        test_path = (
            OUTPUT_ROOT
            / (
                "test_financing_"
                f"{safe_filename(bank['name'])}.csv"
            )
        )
        if records:
            write_csv(
                test_path,
                records,
            )
            print(
                f"\nTek banka test CSV'si: "
                f"{test_path} "
                f"({len(records)} kayıt)"
            )
        else:
            print(
                "\nYeni kayıt üretilemedi. "
                "Varsa önceki başarılı test CSV'si korunuyor."
            )
        print(
            "financing_raw_all.csv değiştirilmedi."
        )

        write_reports()

        print(
            f"\nToplam {len(records)} "
            "kalite kontrolünden geçen "
            "finansman kaydı toplandı."
        )
        return

    all_records: list[dict[str, Any]] = []

    for bank in BANKS:
        all_records.extend(
            scrape_bank(
                copy.deepcopy(bank)
            )
        )

    unique_records: dict[
        str,
        dict[str, Any],
    ] = {}

    for record in all_records:
        unique_records[
            record["id"]
        ] = record

    merged_records = list(
        unique_records.values()
    )

    write_csv(
        MERGED_CSV,
        merged_records,
    )

    print(
        f"\nBirleşik CSV kaydedildi: "
        f"{MERGED_CSV} "
        f"({len(merged_records)} kayıt)"
    )

    write_reports()

    print(
        f"\nToplam {len(merged_records)} "
        "kalite kontrolünden geçen "
        "finansman kaydı toplandı."
    )


if __name__ == "__main__":
    main()

