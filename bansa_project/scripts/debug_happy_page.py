from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


DEFAULT_URLS = [
    (
        "https://www.happycard.com.tr/kampanyalar/"
        "Sayfalar/Halalbooking.aspx"
    ),
    (
        "https://www.happycard.com.tr/kampanyalar/"
        "Sayfalar/"
        "Happy-Bonus-ile-Okul-Odemelerinize-7-Aya-Kadar-"
        "Kar-Paysiz-Taksit.aspx"
    ),
]


def safe_call(default: Any, function):
    try:
        return function()
    except Exception:
        return default


def safe_filename(index: int, url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    slug = "".join(
        character
        if character.isalnum() or character in {"-", "_"}
        else "_"
        for character in slug
    )
    return f"{index:02d}_{slug[:90]}"


def browser_options(headless: bool) -> Options:
    options = Options()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=tr-TR")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors=yes")
    options.add_argument("--allow-running-insecure-content")
    options.set_capability("acceptInsecureCerts", True)

    # get() çağrısının yönlendirme sırasında bloke olmasını önler.
    options.page_load_strategy = "none"
    return options


def collect_state(driver: webdriver.Chrome) -> dict[str, Any]:
    state = safe_call(
        {},
        lambda: driver.execute_script(
            """
            return {
                ready_state: document.readyState || '',
                title: document.title || '',
                body_text: document.body
                    ? (document.body.innerText || '')
                    : '',
                html: document.documentElement
                    ? document.documentElement.outerHTML
                    : '',
                iframe_count: document.querySelectorAll('iframe').length,
                iframe_sources: Array.from(
                    document.querySelectorAll('iframe')
                ).map(frame => frame.src || '')
            };
            """
        ),
    )

    return {
        "current_url": safe_call("", lambda: driver.current_url),
        "title": str(state.get("title", "")),
        "ready_state": str(state.get("ready_state", "")),
        "body_text": str(state.get("body_text", "")),
        "html": str(state.get("html", "")),
        "iframe_count": int(state.get("iframe_count", 0) or 0),
        "iframe_sources": list(state.get("iframe_sources", []) or []),
        "page_source": safe_call("", lambda: driver.page_source),
    }


def collect_iframes(
    driver: webdriver.Chrome,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    frames = safe_call(
        [],
        lambda: driver.find_elements(By.TAG_NAME, "iframe"),
    )

    for index, frame in enumerate(frames):
        item: dict[str, Any] = {
            "index": index,
            "src": safe_call(
                "",
                lambda frame=frame: frame.get_attribute("src") or "",
            ),
        }

        try:
            driver.switch_to.frame(frame)
            item["title"] = safe_call(
                "",
                lambda: driver.execute_script(
                    "return document.title || '';"
                ),
            )
            item["body_text"] = safe_call(
                "",
                lambda: driver.execute_script(
                    """
                    return document.body
                        ? (document.body.innerText || '')
                        : '';
                    """
                ),
            )
            item["html"] = safe_call(
                "",
                lambda: driver.execute_script(
                    """
                    return document.documentElement
                        ? document.documentElement.outerHTML
                        : '';
                    """
                ),
            )
        except Exception as error:
            item["error"] = (
                f"{type(error).__name__}: {error}"
            )
        finally:
            safe_call(None, driver.switch_to.default_content)

        results.append(item)

    return results


def inspect_url(
    driver: webdriver.Chrome,
    url: str,
    output_dir: Path,
    index: int,
    wait_seconds: float,
) -> dict[str, Any]:
    name = safe_filename(index, url)
    navigation_error = ""

    safe_call(
        None,
        lambda: driver.get("about:blank"),
    )

    try:
        driver.execute_cdp_cmd(
            "Security.setIgnoreCertificateErrors",
            {"ignore": True},
        )
    except Exception:
        pass

    try:
        driver.get(url)
    except (TimeoutException, WebDriverException) as error:
        navigation_error = (
            f"{type(error).__name__}: {error}"
        )

    observations: list[dict[str, Any]] = []
    deadline = time.monotonic() + wait_seconds
    stable_text_hits = 0
    last_text_length = -1

    while time.monotonic() < deadline:
        state = collect_state(driver)
        text_length = len(state["body_text"].strip())

        observations.append(
            {
                "elapsed_seconds": round(
                    wait_seconds
                    - max(0.0, deadline - time.monotonic()),
                    2,
                ),
                "current_url": state["current_url"],
                "title": state["title"],
                "ready_state": state["ready_state"],
                "body_text_length": text_length,
                "html_length": len(state["html"]),
                "page_source_length": len(state["page_source"]),
                "iframe_count": state["iframe_count"],
            }
        )

        if text_length >= 100 and text_length == last_text_length:
            stable_text_hits += 1
        else:
            stable_text_hits = 0

        if stable_text_hits >= 2:
            break

        last_text_length = text_length
        time.sleep(1.0)

    final_state = collect_state(driver)
    iframe_results = collect_iframes(driver)

    (output_dir / f"{name}_outer.html").write_text(
        final_state["html"],
        encoding="utf-8",
        errors="replace",
    )
    (output_dir / f"{name}_page_source.html").write_text(
        final_state["page_source"],
        encoding="utf-8",
        errors="replace",
    )
    (output_dir / f"{name}_body.txt").write_text(
        final_state["body_text"],
        encoding="utf-8",
        errors="replace",
    )

    for iframe in iframe_results:
        frame_number = iframe["index"]
        (output_dir / f"{name}_iframe_{frame_number}.html").write_text(
            str(iframe.get("html", "")),
            encoding="utf-8",
            errors="replace",
        )
        (output_dir / f"{name}_iframe_{frame_number}.txt").write_text(
            str(iframe.get("body_text", "")),
            encoding="utf-8",
            errors="replace",
        )

    screenshot_path = output_dir / f"{name}.png"
    screenshot_saved = safe_call(
        False,
        lambda: driver.save_screenshot(str(screenshot_path)),
    )

    return {
        "input_url": url,
        "navigation_error": navigation_error,
        "current_url": final_state["current_url"],
        "title": final_state["title"],
        "ready_state": final_state["ready_state"],
        "body_text_length": len(
            final_state["body_text"].strip()
        ),
        "html_length": len(final_state["html"]),
        "page_source_length": len(
            final_state["page_source"]
        ),
        "iframe_count": final_state["iframe_count"],
        "iframe_sources": final_state["iframe_sources"],
        "iframes": [
            {
                "index": item["index"],
                "src": item.get("src", ""),
                "title": item.get("title", ""),
                "body_text_length": len(
                    str(item.get("body_text", "")).strip()
                ),
                "html_length": len(
                    str(item.get("html", ""))
                ),
                "error": item.get("error", ""),
            }
            for item in iframe_results
        ],
        "screenshot_saved": bool(screenshot_saved),
        "observations": observations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Happy Kart sayfalarında Chrome'un gerçekte hangi "
            "URL, başlık, HTML ve gövde metnini gördüğünü kaydeder."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data") / "debug_happy",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=30.0,
    )
    parser.add_argument(
        "--headless",
        action="store_true",
    )
    parser.add_argument(
        "urls",
        nargs="*",
        default=DEFAULT_URLS,
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    driver = webdriver.Chrome(
        options=browser_options(args.headless)
    )
    driver.set_page_load_timeout(15)

    results: list[dict[str, Any]] = []

    try:
        for index, url in enumerate(args.urls, start=1):
            print(f"[{index}/{len(args.urls)}] İnceleniyor: {url}")
            result = inspect_url(
                driver,
                url,
                args.output,
                index,
                max(5.0, args.wait),
            )
            results.append(result)

            print(
                "  URL:",
                result["current_url"],
            )
            print(
                "  Başlık:",
                result["title"] or "(boş)",
            )
            print(
                "  Gövde metni:",
                result["body_text_length"],
                "karakter",
            )
            print(
                "  HTML:",
                result["html_length"],
                "karakter",
            )
            print(
                "  iframe:",
                result["iframe_count"],
            )
    finally:
        driver.quit()

    summary_path = args.output / "summary.json"
    summary_path.write_text(
        json.dumps(
            results,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("Tanılama tamamlandı.")
    print(f"Özet: {summary_path}")
    print(f"Dosyalar: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
