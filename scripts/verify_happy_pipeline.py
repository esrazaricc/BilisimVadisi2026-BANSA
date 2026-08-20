from __future__ import annotations

import hashlib
import inspect
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scraping import browser_renderer
from src.scraping import campaign_page_fetcher


EXPECTED_RENDERER_SHA256 = "2f6e265aba94ad65e504976077ce3c67c4086d92af602be6e661daede175ca53"
EXPECTED_FETCHER_SHA256 = "f92bac82b2502cd8a9b7a1c72be848799c8494e1661675d2134cdb296ddb54cd"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    renderer_path = Path(browser_renderer.__file__).resolve()
    fetcher_path = Path(campaign_page_fetcher.__file__).resolve()

    print("browser_renderer:", renderer_path)
    print("campaign_page_fetcher:", fetcher_path)
    print()

    renderer_ok = sha256(renderer_path) == EXPECTED_RENDERER_SHA256
    fetcher_ok = sha256(fetcher_path) == EXPECTED_FETCHER_SHA256

    print("Renderer doğru sürüm:", renderer_ok)
    print("Fetcher doğru sürüm:", fetcher_ok)

    renderer_source = inspect.getsource(browser_renderer)
    fetcher_source = inspect.getsource(campaign_page_fetcher)

    checks = {
        "DOM gövde bekleme var": (
            "_snapshot_is_usable" in renderer_source
            and 'page_load_strategy = "none"' in renderer_source
        ),
        "SharePoint form korunuyor": (
            "node.unwrap()" in fetcher_source
            and 'getattr(node, "name", "") == "form"' in fetcher_source
        ),
        "campaign-text seçici var": (
            'for selector in (".campaign-text",):' in fetcher_source
        ),
        "HTML title yedeği var": (
            "document_title_candidate" in fetcher_source
        ),
        "SSL sonrası Selenium var": (
            "selenium_after_request_error" in fetcher_source
        ),
    }

    for label, result in checks.items():
        print(f"{label}: {result}")

    html_path = (
        PROJECT_ROOT
        / "data"
        / "debug_happy"
        / "render_dynamic_page_test.html"
    )

    print()
    print("Tanılama HTML'i:", html_path)

    if not html_path.exists():
        print("UYARI: Tanılama HTML'i bulunamadı.")
        return 2

    html = html_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    title, raw_text, clean_text = (
        campaign_page_fetcher.extract_campaign_text(
            html,
            bank_name="Türkiye Finans",
            url=(
                "https://www.happycard.com.tr/"
                "kampanyalar/Sayfalar/Halalbooking.aspx"
            ),
        )
    )

    print("Başlık:", title)
    print("Raw uzunluğu:", len(raw_text))
    print("Clean uzunluğu:", len(clean_text))
    print("İlk 250 karakter:", clean_text[:250])

    expected_title = (
        "Happy Bonus Kartınıza Halalbooking Ayrıcalığı"
    )
    extraction_ok = (
        title == expected_title
        and len(raw_text) >= 120
        and len(clean_text) >= 120
        and "Halalbooking" in clean_text
    )

    print()
    print("Yerel HTML çıkarımı başarılı:", extraction_ok)

    all_checks_ok = (
        renderer_ok
        and fetcher_ok
        and all(checks.values())
        and extraction_ok
    )

    if all_checks_ok:
        print("SONUÇ: İki dosya da doğru ve içerik çıkarımı çalışıyor.")
        return 0

    print(
        "SONUÇ: Projede hâlâ farklı/eski bir dosya kullanılıyor "
        "veya dosyalar doğru konuma kopyalanmamış."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
