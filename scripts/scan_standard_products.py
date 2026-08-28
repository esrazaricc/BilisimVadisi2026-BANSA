from __future__ import annotations

import argparse
import json
import sys
import time
import re
import unicodedata
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.albaraka_standard_product_overrides import (
    apply_albaraka_standard_product_overrides,
)
from src.housing_verified_source_overrides import (
    apply_verified_housing_product_overrides,
)
from src.finance_data_quality import (
    apply_finance_data_quality_overrides,
    canonicalize_ziraat_product_identity,
    is_generic_ziraat_product_name,
)

from src.extraction.standard_product_extractor import (
    extract_standard_product,
)
from src.scraping.standard_product_discovery import (
    canonicalize_url,
    discover_standard_product_links,
    find_bank,
    resolve_family,
)


def extraction_quality_score(extraction) -> int:
    score = 0

    if str(extraction.product_name or "").strip():
        score += 100

    clean_text = str(extraction.clean_text or "").strip()
    score += min(len(clean_text), 5000) // 50

    for key in (
        "maximum_financing_amount",
        "maximum_maturity_months",
        "profit_share_rate",
        "maturity_rules_text",
        "housing_first_home_rules_text",
        "vehicle_finance_rules_text",
        "shopping_finance_rules_text",
        "finance_rules_json",
    ):
        if getattr(extraction, key, None) is not None:
            score += 10

    return score


def needs_rendered_fallback(
    bank_name: str,
    url: str,
    extraction,
) -> bool:
    """
    Requests HTML'i ürün içeriğini getirmiyorsa rendered DOM'a geç.

    Türkiye Finans 200 döndürmesine rağmen requests tarafında
    ürün gövdesi boş gelebiliyor. Bu durum banka adına özel bir
    validation gevşetmesiyle değil, gerçek rendered sayfayı
    okuyarak çözülür.
    """
    product_name = str(
        extraction.product_name or ""
    ).strip()
    clean_text = str(
        extraction.clean_text or ""
    ).strip()

    if not product_name or len(clean_text) < 100:
        return True

    # Ziraat bazı ürün sayfalarında requests HTML'inde gerçek H1 yerine
    # yalnız site başlığı "Ziraat Katılım Bankası" kalabiliyor. Böyle bir
    # başlık ürün adı değildir; rendered DOM bir kez denenir.
    if bank_name == "Ziraat Katılım" and is_generic_ziraat_product_name(product_name):
        return True

    # Dünya Katılım Araç Finansmanı özel durumu:
    # SSS/vade verisi requests HTML'inde eksik kalabiliyor.
    if (
        bank_name == "Dünya Katılım"
        and "/arac-finansmanlari/arac-finansmani" in url
    ):
        return (
            extraction.maximum_maturity_months is None
            and extraction.maturity_rules_text is None
        )

    return False


def fetch_rendered_html(
    url: str,
    *,
    timeout: int,
) -> str | None:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except Exception as error:
        print(
            "  Selenium fallback kullanılamadı:",
            type(error).__name__,
            error,
        )
        return None

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,3000")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent="
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/150 Safari/537.36"
    )

    driver = None

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(timeout)
        driver.get(url)

        wait = WebDriverWait(
            driver,
            max(5, min(timeout, 30)),
        )

        wait.until(
            EC.presence_of_element_located(
                (By.TAG_NAME, "body")
            )
        )

        try:
            wait.until(
                lambda d: d.execute_script(
                    "return document.readyState"
                ) in ("interactive", "complete")
            )
        except Exception:
            pass

        # Lazy-load / accordion içeriklerinin DOM'a gelmesine
        # fırsat ver.
        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);"
        )
        time.sleep(1.5)
        driver.execute_script(
            "window.scrollTo(0, 0);"
        )
        time.sleep(0.5)

        html = driver.page_source

        if not str(html or "").strip():
            return None

        return html

    except Exception as error:
        print(
            "  Selenium rendered fallback hatası:",
            type(error).__name__,
            error,
        )
        return None

    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass



def normalize_label(value: str) -> str:
    text = unicodedata.normalize(
        "NFKC",
        str(value or ""),
    ).casefold()

    text = (
        text.replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(r"\s+", " ", text).strip()


def stable_fragment(value: str) -> str:
    key = normalize_label(value)
    return re.sub(r"\s+", "-", key).strip("-") or "urun"


def find_embedded_anchor(
    soup: BeautifulSoup,
    aliases: list[str],
):
    wanted = {
        normalize_label(alias)
        for alias in aliases
        if str(alias or "").strip()
    }

    if not wanted:
        return None

    # Heading etiketleri önce tercih edilir.
    candidates = []

    for priority, tags in (
        (300, ["h1", "h2", "h3", "h4", "h5", "h6"]),
        (200, ["strong", "b"]),
        (100, ["p", "div", "span"]),
    ):
        for tag in soup.find_all(tags):
            label = normalize_label(
                tag.get_text(" ", strip=True)
            )

            if label in wanted:
                text_len = len(
                    tag.get_text(" ", strip=True)
                )
                candidates.append(
                    (
                        priority - min(text_len, 99),
                        tag,
                    )
                )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return candidates[0][1]


def section_block_for_anchor(anchor):
    if anchor is None:
        return None

    if anchor.name in {
        "h1", "h2", "h3", "h4", "h5", "h6"
    }:
        return anchor

    parent = anchor.find_parent(
        ["p", "div", "li", "section", "article"]
    )
    return parent or anchor


def embedded_section_text_fallback(
    soup: BeautifulSoup,
    *,
    product_name: str,
    aliases: list[str],
    all_product_aliases: list[str],
) -> tuple[str, str] | None:
    """
    DOM'da ürün adı bağımsız bir h/strong/p etiketi değilse, görünür
    metni satır sırasıyla tarar. Özellikle Adil Katılım gibi aynı
    sayfada kart/metin blokları halinde ürün tanımı yayımlayan resmi
    sayfalarda güvenli fallback'tir.

    Sayısal veri üretmez; yalnız resmi sayfada gerçekten bulunan ürün
    başlığı ile onu izleyen metni, bir sonraki ürün/stop başlığına kadar
    ayırır.
    """
    own_aliases = {
        normalize_label(alias)
        for alias in aliases
        if str(alias or "").strip()
    }
    other_aliases = {
        normalize_label(alias)
        for alias in all_product_aliases
        if str(alias or "").strip()
        and normalize_label(alias) not in own_aliases
    }

    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in soup.get_text("\n", strip=True).splitlines()
        if str(line or "").strip()
    ]

    def is_own(label: str) -> bool:
        return label in own_aliases or any(
            label.startswith(alias + " ")
            for alias in own_aliases
            if alias
        )

    def is_other(label: str) -> bool:
        return label in other_aliases or any(
            label.startswith(alias + " ")
            for alias in other_aliases
            if alias
        )

    anchor_index = None
    for index, line in enumerate(lines):
        if is_own(normalize_label(line)):
            anchor_index = index
            break

    if anchor_index is None:
        return None

    chunks: list[str] = []
    for index in range(anchor_index, len(lines)):
        line = lines[index]
        label = normalize_label(line)

        if index != anchor_index and is_other(label):
            break

        if line not in chunks:
            chunks.append(line)

    section_text = " ".join(chunks).strip()

    if len(section_text) < len(product_name) + 10:
        return None

    from html import escape

    return (
        (
            "<html><body>"
            f"<h1>{escape(product_name)}</h1>"
            f"<p>{escape(section_text)}</p>"
            "</body></html>"
        ),
        section_text,
    )


def embedded_section_html(
    html: str,
    *,
    product_name: str,
    aliases: list[str],
    all_product_aliases: list[str],
) -> tuple[str, str] | None:
    """
    Tek alt ürün bölümünü ayırır ve bir sonraki alt ürün
    başlığında kesin olarak durur.
    """
    soup = BeautifulSoup(html, "html.parser")

    anchor = find_embedded_anchor(
        soup,
        aliases,
    )

    if anchor is None:
        return embedded_section_text_fallback(
            soup,
            product_name=product_name,
            aliases=aliases,
            all_product_aliases=all_product_aliases,
        )

    own_aliases = {
        normalize_label(alias)
        for alias in aliases
        if str(alias or "").strip()
    }

    other_aliases = {
        normalize_label(alias)
        for alias in all_product_aliases
        if str(alias or "").strip()
        and normalize_label(alias) not in own_aliases
    }

    def is_other(text: str) -> bool:
        label = normalize_label(text)

        if label in other_aliases:
            return True

        return any(
            label.startswith(alias + " ")
            for alias in other_aliases
            if alias
        )

    chunks = []

    anchor_text = anchor.get_text(" ", strip=True)

    if anchor_text:
        chunks.append(anchor_text)

    for node in anchor.find_all_next(
        ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]
    ):
        text = node.get_text(" ", strip=True)

        if not text:
            continue

        if is_other(text):
            break

        if any(
            is_other(
                strong.get_text(" ", strip=True)
            )
            for strong in node.find_all(
                ["strong", "b"],
                recursive=True,
            )
        ):
            break

        if len(text) <= 1200 and text not in chunks:
            chunks.append(text)

    section_text = " ".join(chunks).strip()

    if len(section_text) < len(product_name) + 10:
        return None

    from html import escape

    return (
        (
            "<html><body>"
            f"<h1>{escape(product_name)}</h1>"
            f"<p>{escape(section_text)}</p>"
            "</body></html>"
        ),
        section_text,
    )

def embedded_page_specs(
    bank: dict,
) -> list[dict]:
    specs = bank.get(
        "embedded_product_pages",
        [],
    )

    return (
        specs
        if isinstance(specs, list)
        else []
    )


def build_embedded_rows(
    *,
    bank: dict,
    session: requests.Session,
    timeout: int,
) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    errors: list[dict] = []

    for page in embedded_page_specs(bank):
        page_url = str(
            page.get("url") or ""
        ).strip()

        if not page_url:
            continue

        products = page.get("products", [])

        if not isinstance(products, list):
            continue

        try:
            response = session.get(
                page_url,
                timeout=timeout,
            )
            response.raise_for_status()

            html = response.text
            fetch_mode = "requests"

            # Çok ürünlü sayfalarda da rendered DOM gerekebilir.
            if len(str(html or "")) < 500:
                rendered = fetch_rendered_html(
                    page_url,
                    timeout=timeout,
                )

                if rendered:
                    html = rendered
                    fetch_mode = "selenium"

            final_page_url = canonicalize_url(
                response.url
            )

            all_aliases = []

            for spec in products:
                all_aliases.extend(
                    [
                        str(
                            spec.get(
                                "product_name"
                            )
                            or ""
                        ),
                        *[
                            str(alias)
                            for alias in spec.get(
                                "aliases",
                                [],
                            )
                        ],
                    ]
                )

            # Bazı çok-ürünlü resmi sayfalarda ürün bölümlerinden sonra
            # örnek ödeme tablosu / başvuru / footer gibi başka başlıklar
            # geliyor. Bunlar bir ürün değildir ama son alt ürünün içine
            # sızmaması için bölüm sonlandırıcı olarak kullanılabilir.
            all_aliases.extend(
                str(item)
                for item in page.get("stop_headings", [])
                if str(item or "").strip()
            )

            for spec in products:
                product_name = str(
                    spec.get(
                        "product_name"
                    )
                    or ""
                ).strip()

                if not product_name:
                    continue

                aliases = [
                    product_name,
                    *[
                        str(alias)
                        for alias in spec.get(
                            "aliases",
                            [],
                        )
                    ],
                ]

                result = embedded_section_html(
                    html,
                    product_name=product_name,
                    aliases=aliases,
                    all_product_aliases=all_aliases,
                )

                if result is None:
                    raise ValueError(
                        "Alt ürün bölümü bulunamadı: "
                        f"{product_name}"
                    )

                section_html, section_text = result

                extraction = extract_standard_product(
                    section_html
                )

                synthetic_url = (
                    final_page_url
                    + "#product="
                    + stable_fragment(
                        product_name
                    )
                )

                family_key = str(
                    spec.get(
                        "product_family_key"
                    )
                    or page.get(
                        "product_family_key"
                    )
                    or "diger"
                )

                family_label = str(
                    spec.get(
                        "product_family"
                    )
                    or page.get(
                        "product_family"
                    )
                    or "Diğer Finansman"
                )

                scope = str(
                    spec.get("scope")
                    or page.get("scope")
                    or "bireysel"
                )

                row = {
                    "bank_name": bank["name"],
                    "bank_slug": bank["slug"],
                    "product_family": family_label,
                    "product_family_key": family_key,
                    "url": synthetic_url,
                    "source_page": final_page_url,
                    "scope": scope,
                    **asdict(extraction),

                    # Alt bölüm extractor'da sayfa başlığı yerine
                    # config'teki gerçek ürün adı kaynak kabul edilir.
                    "product_name": product_name,
                    "clean_text": section_text,

                    "record_kind": "standard_product",
                    "is_current": True,
                    "http_status": response.status_code,
                    "fetch_mode": (
                        fetch_mode
                        + "+embedded"
                    ),
                    "discovered_url": page_url,
                    "checked_at": (
                        datetime.now(timezone.utc)
                        .replace(microsecond=0)
                        .isoformat()
                    ),
                    "embedded_product": True,
                    "embedded_parent_url": final_page_url,
                }

                row = apply_albaraka_standard_product_overrides(row)
                row = apply_verified_housing_product_overrides(row)
                row = apply_finance_data_quality_overrides(row)

                rows.append(row)

                print(
                    "  [ALT ÜRÜN] "
                    f"{family_label} | "
                    f"{product_name}"
                )
                print(
                    "    Tutar:",
                    extraction.minimum_financing_amount,
                    "→",
                    extraction.maximum_financing_amount,
                )
                print(
                    "    Vade:",
                    extraction.minimum_maturity_months,
                    "→",
                    extraction.maximum_maturity_months,
                )
                print(
                    "    Kâr:",
                    extraction.profit_share_rate_text,
                )

        except Exception as error:
            errors.append(
                {
                    "url": page_url,
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "embedded_page": True,
                }
            )

            print(
                "  [ALT ÜRÜN SAYFASI HATA] "
                f"{page_url} | {error}"
            )

    return rows, errors


def filter_ziraat_errors_covered_by_embedded_catalog(
    errors: list[dict],
    rows: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Ziraat'ta yalnız redundant detail-fetch hatalarını warning'e indirger.

    Ziraat'ın resmî kategori sayfaları ürün başlığını ve kısa açıklamayı
    açık katalog halinde yayınlıyor. Bazı "Detaylı Bilgi" URL'leri ise
    dönemsel redirect/404/boş H1 problemi yaşayabiliyor. Aynı mantıksal
    ürün resmî embedded katalogdan başarıyla çıkarılmışsa, detail URL
    hatası katalog bütünlüğünü bozmamalıdır.

    Güvenlik: embedded page hataları asla bastırılmaz. URL'si canonical
    ürün kimliğine çevrilemeyen veya embedded katalogda karşılığı olmayan
    detail hatası da fatal kalır.
    """
    embedded_keys: set[tuple[str, str]] = set()
    for row in rows:
        if not row.get("embedded_product"):
            continue
        key = (
            str(row.get("product_family_key") or ""),
            normalize_label(str(row.get("product_name") or "")),
        )
        if key[0] and key[1]:
            embedded_keys.add(key)

    fatal: list[dict] = []
    covered: list[dict] = []
    for error in errors:
        if error.get("embedded_page"):
            fatal.append(error)
            continue

        url = str(error.get("url") or "")
        identity = canonicalize_ziraat_product_identity(
            {
                "bank_name": "Ziraat Katılım",
                "product_name": "Ziraat Katılım Bankası",
                "url": url,
            }
        )
        name = str(identity.get("product_name") or "")
        family = str(identity.get("product_family_key") or "")
        key = (family, normalize_label(name))

        if (
            family
            and name
            and not is_generic_ziraat_product_name(name)
            and key in embedded_keys
        ):
            item = dict(error)
            item["covered_by_embedded_catalog"] = True
            item["canonical_product_name"] = name
            item["canonical_family_key"] = family
            covered.append(item)
        else:
            fatal.append(error)

    return fatal, covered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bank",
        default="Dünya Katılım",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=(
            Path("config")
            / "standard_product_sources.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            Path("data")
            / "standard_products"
            / "dunya_katilim.json"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
    )
    args = parser.parse_args()

    bank = find_bank(
        args.bank,
        config_path=args.config,
    )

    links = discover_standard_product_links(
        bank,
        timeout=args.timeout,
    )

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/150 Safari/537.36"
            )
        }
    )

    rows_by_url = {}
    errors = []

    print("=" * 80)
    print("STANDART ÜRÜN TARAMASI —", bank["name"])
    print("=" * 80)
    print("Keşfedilen ürün linki:", len(links))
    print()

    for index, link in enumerate(links, start=1):
        try:
            response = session.get(
                link.url,
                timeout=args.timeout,
            )
            response.raise_for_status()

            html = response.text
            extraction = extract_standard_product(html)
            fetch_mode = "requests"

            if needs_rendered_fallback(
                bank["name"],
                link.url,
                extraction,
            ):
                print(
                    "  Requests içeriği eksik; "
                    "Selenium rendered fallback deneniyor..."
                )

                rendered_html = fetch_rendered_html(
                    link.url,
                    timeout=args.timeout,
                )

                if rendered_html:
                    rendered_extraction = (
                        extract_standard_product(
                            rendered_html
                        )
                    )

                    if (
                        extraction_quality_score(
                            rendered_extraction
                        )
                        > extraction_quality_score(
                            extraction
                        )
                    ):
                        extraction = rendered_extraction
                        fetch_mode = "selenium"

            # Boş ürün adını DB tarafına bırakma. Scanner'ın
            # kendisi bu kaydı hata olarak işaretlesin.
            if (
                not str(
                    extraction.product_name or ""
                ).strip()
                or len(
                    str(
                        extraction.clean_text or ""
                    ).strip()
                ) < 20
            ):
                raise ValueError(
                    "Ürün sayfası içeriksiz kaldı; "
                    "requests ve Selenium sonrasında "
                    "ürün adı/metni çıkarılamadı."
                )

            final_url = canonicalize_url(response.url)

            final_family = resolve_family(
                __import__("urllib.parse").parse.urlparse(
                    final_url
                ).path,
                list(bank.get("family_rules", [])),
            )

            if final_family is not None:
                family_key, family_label = final_family
            else:
                family_key = link.product_family_key
                family_label = link.product_family

            row = {
                **asdict(link),
                **asdict(extraction),
                "url": final_url,
                "product_family": family_label,
                "product_family_key": family_key,
                "record_kind": "standard_product",
                "is_current": True,
                "http_status": response.status_code,
                "fetch_mode": fetch_mode,
                "discovered_url": link.url,
                "checked_at": (
                    datetime.now(timezone.utc)
                    .replace(microsecond=0)
                    .isoformat()
                ),
            }

            row = apply_albaraka_standard_product_overrides(row)
            row = apply_verified_housing_product_overrides(row)
            row = apply_finance_data_quality_overrides(row)

            # Site <title> bilgisini ürün adı sanan zehirli Ziraat satırını
            # DB'ye hiç yazma. Bilinen detail URL ise finance_data_quality
            # zaten gerçek ürüne canonicalize eder; bilinmeyen generic kayıt
            # ise resmi kategori sayfalarındaki embedded katalog tarafından
            # güvenli biçimde temsil edilir.
            if bank["name"] == "Ziraat Katılım" and is_generic_ziraat_product_name(row.get("product_name")):
                print(
                    "  [ZİRAAT GENERIC ATLANDI] Ürün adı yerine site başlığı geldi: "
                    f"{final_url}"
                )
                continue

            # Aynı ürün farklı kategori linklerinden gelip aynı son
            # URL'ye yönleniyorsa tek kayıt tut.
            #
            # Türkiye Finans SharePoint yolları büyük/küçük harf
            # varyasyonlarını aynı sayfa olarak sunabildiği için
            # burada yalnız bu banka için case-insensitive dedupe
            # uygulanır.
            row_key = (
                final_url.casefold()
                if bank["name"] == "Türkiye Finans"
                else final_url
            )

            previous = rows_by_url.get(row_key)
            if previous is None:
                rows_by_url[row_key] = row
            else:
                # Daha zengin extraction'ı koru.
                previous_score = sum(
                    previous.get(key) is not None
                    for key in (
                        "maximum_financing_amount",
                        "maximum_maturity_months",
                        "profit_share_rate",
                        "maturity_rules_text",
                        "housing_first_home_rules_text",
                    )
                )
                current_score = sum(
                    row.get(key) is not None
                    for key in (
                        "maximum_financing_amount",
                        "maximum_maturity_months",
                        "profit_share_rate",
                        "maturity_rules_text",
                        "housing_first_home_rules_text",
                    )
                )
                if current_score > previous_score:
                    rows_by_url[row_key] = row

            print(
                f"[{index}/{len(links)}] "
                f"{family_label} | "
                f"{extraction.product_name or final_url}"
            )
            print(
                "  Tutar:",
                extraction.minimum_financing_amount,
                "→",
                extraction.maximum_financing_amount,
            )
            print(
                "  Vade:",
                extraction.minimum_maturity_months,
                "→",
                extraction.maximum_maturity_months,
            )
            print(
                "  Kâr oranı:",
                extraction.profit_share_rate_text,
                "| Vade farksız:",
                extraction.interest_free,
            )
            print(
                "  Fetch:",
                fetch_mode,
                "| Vade kademeleri:",
                extraction.maturity_rules_text,
            )

        except Exception as error:
            errors.append(
                {
                    "url": link.url,
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
            )
            print(
                f"[{index}/{len(links)}] HATA | "
                f"{link.url} | {error}"
            )

    embedded_rows, embedded_errors = (
        build_embedded_rows(
            bank=bank,
            session=session,
            timeout=args.timeout,
        )
    )

    for row in embedded_rows:
        row_key = str(row["url"])

        # Sentetik URL her alt ürünü bağımsız ve stabil yapar.
        rows_by_url[row_key] = row

    errors.extend(embedded_errors)

    covered_warnings: list[dict] = []
    if bank["name"] == "Ziraat Katılım":
        errors, covered_warnings = filter_ziraat_errors_covered_by_embedded_catalog(
            errors,
            embedded_rows,
        )
        for warning in covered_warnings:
            print(
                "  [ZİRAAT DETAIL UYARI - RESMÎ KATALOG KAPSIYOR] "
                f"{warning.get('canonical_product_name')} | "
                f"{warning.get('url')} | {warning.get('message')}"
            )

    # Ziraat'ta kategori sayfası embedded kayıtları katalog bütünlüğünü
    # garanti eder; detail URL başarılı tarandıysa aynı mantıksal ürünün
    # ikinci bir sentetik satır olarak görünmesini engelle. En zengin ve
    # tercihen doğrudan ürün sayfasından gelen kaydı koru.
    if bank["name"] == "Ziraat Katılım":
        logical: dict[tuple[str, str], dict] = {}

        def row_score(item: dict) -> int:
            score = 0
            if not item.get("embedded_product"):
                score += 1000
            score += min(len(str(item.get("clean_text") or "")), 5000) // 20
            for key in (
                "maximum_financing_amount", "maximum_maturity_months",
                "profit_share_rate", "maturity_rules_text",
                "financing_ratio_rules_text", "maximum_financing_ratio",
                "vehicle_finance_rules_text", "finance_rules_json",
            ):
                if item.get(key) not in (None, "", "{}"):
                    score += 20
            return score

        for item in rows_by_url.values():
            if is_generic_ziraat_product_name(item.get("product_name")):
                continue
            key = (
                str(item.get("product_family_key") or ""),
                normalize_label(str(item.get("product_name") or "")),
            )
            previous = logical.get(key)
            if previous is None or row_score(item) > row_score(previous):
                logical[key] = item
        rows_by_url = {str(item.get("url") or index): item for index, item in enumerate(logical.values())}

    rows = sorted(
        rows_by_url.values(),
        key=lambda row: (
            str(row.get("product_family", "")),
            str(row.get("product_name", "")),
            str(row.get("url", "")),
        ),
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.output.write_text(
        json.dumps(
            {
                "bank_name": bank["name"],
                "record_kind": "standard_product",
                "product_count": len(rows),
                "error_count": len(errors),
                "products": rows,
                "errors": errors,
                "covered_warnings": covered_warnings,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 80)
    print("ÖZET")
    print("=" * 80)

    families = {}
    for row in rows:
        family = row["product_family"]
        families.setdefault(family, [])
        families[family].append(row["product_name"])

    for family, products in families.items():
        print(f"{family}: {len(products)}")
        for product in products:
            print("  -", product)

    if covered_warnings:
        print("Katalogla güvenli karşılanan detail uyarısı:", len(covered_warnings))
    print("Hata:", len(errors))
    print("Rapor:", args.output)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
