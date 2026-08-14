from __future__ import annotations

import time
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RenderResult:
    url: str
    html: str
    load_more_clicks: int
    detail_link_count: int
    reached_click_limit: bool


def search_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    return " ".join(text.casefold().split())


def _count_detail_links(driver: Any, detail_paths: list[str]) -> int:
    if not detail_paths:
        return 0

    script = """
        const fragments = arguments[0].map(item => item.toLowerCase());
        const urls = new Set();
        for (const link of document.querySelectorAll('a[href]')) {
            const href = (link.href || '').toLowerCase();
            if (fragments.some(fragment => href.includes(fragment))) {
                urls.add(link.href.split('#')[0]);
            }
        }
        return urls.size;
    """

    try:
        return int(driver.execute_script(script, detail_paths) or 0)
    except Exception:
        # Sayfa tam yönlendirme anındaysa DOM geçici olarak erişilemez
        # olabilir. Bu durum kampanya metni çekimini tamamen durdurmamalı.
        return 0


def _matching_clickable_elements(
    driver: Any,
    terms: list[str],
) -> list[Any]:
    from selenium.webdriver.common.by import By

    wanted = [search_key(term) for term in terms if search_key(term)]
    if not wanted:
        return []

    try:
        elements = driver.find_elements(
            By.XPATH,
            "//button | //a | //*[@role='button']",
        )
    except Exception:
        return []

    matches: list[Any] = []

    for element in elements:
        try:
            if not element.is_displayed() or not element.is_enabled():
                continue

            label = search_key(
                " ".join(
                    [
                        element.text or "",
                        element.get_attribute("aria-label") or "",
                        element.get_attribute("title") or "",
                    ]
                )
            )
            if label and any(term in label for term in wanted):
                matches.append(element)
        except Exception:
            continue

    return matches


def _click_first_matching(
    driver: Any,
    terms: list[str],
) -> bool:
    elements = _matching_clickable_elements(driver, terms)
    if not elements:
        return False

    element = elements[0]
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});",
        element,
    )
    time.sleep(0.25)
    driver.execute_script("arguments[0].click();", element)
    return True



def _is_recoverable_navigation_error(error: Exception) -> bool:
    message = str(error).casefold()
    return any(
        fragment in message
        for fragment in (
            "timeout",
            "timed out",
            "aborted by navigation",
            "loader has changed",
            "target frame detached",
        )
    )


def _stop_loading(driver: Any) -> None:
    try:
        driver.execute_script("window.stop();")
    except Exception:
        pass


def _safe_current_url(
    driver: Any,
    *,
    fallback: str,
    attempts: int = 4,
) -> str:
    for _ in range(max(1, attempts)):
        try:
            value = str(driver.current_url or "").strip()
            if value:
                return value
        except Exception:
            pass
        time.sleep(0.2)

    return fallback


def _safe_page_source(
    driver: Any,
    *,
    attempts: int = 6,
) -> str:
    best = ""

    for _ in range(max(1, attempts)):
        try:
            value = str(driver.page_source or "")
            if len(value) > len(best):
                best = value
            if len(value.strip()) >= 100:
                return value
        except Exception:
            pass

        time.sleep(0.25)

    return best


def _document_snapshot(driver: Any) -> dict[str, Any]:
    """
    Tarayıcının o anda gördüğü URL, başlık, gövde metni ve DOM'u alır.

    Happy Kart ilk aşamada yaklaşık 1 KB'lık boş bir HTML kabuğu
    döndürüyor. Yalnızca page_source uzunluğuna bakmak bu kabuğu gerçek
    sayfa sanmamıza yol açıyordu.
    """
    try:
        value = driver.execute_script(
            """
            return {
                ready_state: document.readyState || '',
                title: document.title || '',
                body_text: document.body
                    ? (document.body.innerText || '')
                    : '',
                html: document.documentElement
                    ? document.documentElement.outerHTML
                    : ''
            };
            """
        )
        value = value if isinstance(value, dict) else {}
    except Exception:
        value = {}

    try:
        current_url = str(driver.current_url or "").strip()
    except Exception:
        current_url = ""

    html = str(value.get("html", "") or "")
    if not html:
        html = _safe_page_source(driver, attempts=1)

    return {
        "current_url": current_url,
        "ready_state": str(
            value.get("ready_state", "") or ""
        ).casefold(),
        "title": str(value.get("title", "") or "").strip(),
        "body_text": str(
            value.get("body_text", "") or ""
        ).strip(),
        "html": html,
    }


def _is_real_page_url(value: str) -> bool:
    normalized = str(value or "").strip().casefold()
    return bool(normalized) and normalized not in {
        "about:blank",
        "data:,",
    }


def _snapshot_is_usable(
    snapshot: dict[str, Any],
    *,
    detail_link_count: int = 0,
) -> bool:
    current_url = str(snapshot.get("current_url", ""))
    ready_state = str(snapshot.get("ready_state", ""))
    title = str(snapshot.get("title", ""))
    body_text = str(snapshot.get("body_text", ""))
    html = str(snapshot.get("html", ""))

    if not _is_real_page_url(current_url):
        return False

    if ready_state not in {"interactive", "complete"}:
        return False

    body_length = len(body_text)
    html_length = len(html)

    # Kampanya detayında gerçek gövde metni; kampanya listesinde ise
    # bulunan detay bağlantıları yeterli bir yüklenme kanıtıdır.
    if body_length >= 80:
        return True
    if detail_link_count > 0:
        return True

    # Bazı sayfalar metni daha sonra ekler ama gerçek sayfa başlığı ve
    # büyük DOM erkenden gelir. 1 KB civarındaki boş kabuk kabul edilmez.
    return bool(title) and html_length >= 5000


def _wait_for_stable_document(
    driver: Any,
    *,
    timeout: float,
    settle_seconds: float,
    detail_paths: list[str] | None = None,
) -> bool:
    """
    Boş HTML kabuğu yerine gerçek DOM ve gövde metni gelene kadar bekler.

    Aynı kullanılabilir durumun iki ardışık kontrolde görülmesi gerekir.
    Böylece readyState='interactive' olsa bile içeriğin henüz eklenmediği
    ilk an yanlışlıkla başarılı sayılmaz.
    """
    deadline = time.monotonic() + max(1.0, float(timeout))
    previous: dict[str, Any] | None = None
    stable_hits = 0
    best_usable = False
    paths = list(detail_paths or [])

    while time.monotonic() < deadline:
        snapshot = _document_snapshot(driver)
        detail_count = _count_detail_links(
            driver,
            paths,
        )
        usable = _snapshot_is_usable(
            snapshot,
            detail_link_count=detail_count,
        )
        best_usable = best_usable or usable

        if usable and previous is not None:
            same_url = (
                snapshot["current_url"]
                == previous["current_url"]
            )
            current_body_length = len(
                snapshot["body_text"]
            )
            previous_body_length = len(
                previous["body_text"]
            )
            body_tolerance = max(
                20,
                int(max(
                    current_body_length,
                    previous_body_length,
                    1,
                ) * 0.03),
            )
            body_is_stable = (
                abs(
                    current_body_length
                    - previous_body_length
                )
                <= body_tolerance
            )

            current_html_length = len(snapshot["html"])
            previous_html_length = len(previous["html"])
            html_tolerance = max(
                250,
                int(max(
                    current_html_length,
                    previous_html_length,
                    1,
                ) * 0.03),
            )
            html_is_stable = (
                abs(
                    current_html_length
                    - previous_html_length
                )
                <= html_tolerance
            )

            if same_url and (body_is_stable or html_is_stable):
                stable_hits += 1
            else:
                stable_hits = 0
        elif usable:
            stable_hits = 0
        else:
            stable_hits = 0

        if usable and stable_hits >= 1:
            time.sleep(max(0.0, settle_seconds))
            final_snapshot = _document_snapshot(driver)
            final_detail_count = _count_detail_links(
                driver,
                paths,
            )
            return _snapshot_is_usable(
                final_snapshot,
                detail_link_count=final_detail_count,
            )

        previous = snapshot
        time.sleep(0.35)

    return best_usable

def render_dynamic_page(
    url: str,
    *,
    detail_paths: list[str],
    load_more_terms: list[str],
    cookie_accept_terms: list[str] | None = None,
    headless: bool = True,
    timeout: int = 45,
    maximum_load_more_clicks: int = 20,
    settle_seconds: float = 1.0,
) -> RenderResult:
    """JavaScript ile yüklenen kampanya kartlarını tamamen açar."""
    from selenium import webdriver
    from selenium.common.exceptions import (
        TimeoutException,
        WebDriverException,
    )
    from selenium.webdriver.chrome.options import Options

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=tr-TR")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors=yes")
    options.set_capability("acceptInsecureCerts", True)
    options.page_load_strategy = "none"

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(timeout)

    try:
        driver.execute_cdp_cmd(
            "Security.setIgnoreCertificateErrors",
            {"ignore": True},
        )
    except Exception:
        pass

    clicks = 0
    reached_limit = False

    try:
        navigation_error: Exception | None = None

        try:
            driver.get(url)
        except TimeoutException as error:
            navigation_error = error
            _stop_loading(driver)
        except WebDriverException as error:
            if not _is_recoverable_navigation_error(error):
                raise
            navigation_error = error
            _stop_loading(driver)

        document_ready = _wait_for_stable_document(
            driver,
            timeout=min(float(timeout), 20.0),
            settle_seconds=settle_seconds,
            detail_paths=detail_paths,
        )

        # İlk yönlendirme tam geçiş anında kesildiyse bir kez daha
        # aynı URL'yi açmayı deneriz. HTML zaten geldiyse tekrar yoktur.
        if not document_ready:
            try:
                driver.get(url)
            except (TimeoutException, WebDriverException) as error:
                if not _is_recoverable_navigation_error(error):
                    raise
                navigation_error = navigation_error or error
                _stop_loading(driver)

            document_ready = _wait_for_stable_document(
                driver,
                timeout=min(float(timeout), 15.0),
                settle_seconds=settle_seconds,
                detail_paths=detail_paths,
            )

        initial_html = _safe_page_source(driver)
        if len(initial_html.strip()) < 100:
            detail = (
                f" Son gezinme hatası: {navigation_error}"
                if navigation_error is not None
                else ""
            )
            raise RuntimeError(
                "Selenium sayfayı açtı ancak kullanılabilir HTML "
                f"elde edilemedi.{detail}"
            )

        if cookie_accept_terms:
            try:
                if _click_first_matching(driver, cookie_accept_terms):
                    time.sleep(0.5)
            except Exception:
                pass

        previous_count = _count_detail_links(driver, detail_paths)
        unsuccessful_clicks = 0

        # Metin çekiminde load_more_terms boş gönderilir. Eski kod bu
        # durumda bile sayfayı kaydırıp yönlendirme anındaki DOM'a
        # dokunuyor ve "loader has changed" hatası üretebiliyordu.
        while load_more_terms and clicks < maximum_load_more_clicks:
            try:
                driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);"
                )
            except Exception:
                # Yönlendirme hâlâ sürüyorsa bu turda tıklama denemeyiz.
                break
            time.sleep(0.5)

            try:
                clicked = _click_first_matching(
                    driver,
                    load_more_terms,
                )
            except Exception:
                clicked = False

            if not clicked:
                break

            clicks += 1
            deadline = time.time() + 8.0
            current_count = previous_count

            while time.time() < deadline:
                time.sleep(0.4)
                current_count = _count_detail_links(
                    driver,
                    detail_paths,
                )
                if current_count > previous_count:
                    break

            if current_count > previous_count:
                previous_count = current_count
                unsuccessful_clicks = 0
            else:
                unsuccessful_clicks += 1
                if unsuccessful_clicks >= 2:
                    break

        if clicks >= maximum_load_more_clicks:
            reached_limit = bool(
                _matching_clickable_elements(
                    driver,
                    load_more_terms,
                )
            )

        if load_more_terms:
            try:
                driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);"
                )
            except Exception:
                pass
            time.sleep(settle_seconds)

        final_snapshot = _document_snapshot(driver)
        final_html = str(final_snapshot.get("html", "") or "")
        page_source = _safe_page_source(driver)
        if len(page_source) > len(final_html):
            final_html = page_source
        if len(final_html.strip()) < 100:
            raise RuntimeError(
                "Selenium kullanılabilir sayfa kaynağı üretemedi."
            )

        return RenderResult(
            url=_safe_current_url(
                driver,
                fallback=url,
            ),
            html=final_html,
            load_more_clicks=clicks,
            detail_link_count=_count_detail_links(
                driver,
                detail_paths,
            ),
            reached_click_limit=reached_limit,
        )
    finally:
        try:
            driver.quit()
        except Exception:
            pass

