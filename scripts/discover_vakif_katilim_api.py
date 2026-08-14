from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]

CONFIG_PATH = ROOT / "config" / "banks.json"
DISCOVERY_PATH = ROOT / "data" / "discovered_campaign_pages.json"
ERROR_PATH = ROOT / "data" / "campaign_discovery_errors.json"
REPORT_PATH = ROOT / "data" / "campaign_discovery_report.json"
BACKUP_DIR = ROOT / "data" / "backups"

BANK_SLUG = "vakif_katilim"
BANK_NAME = "Vak\u0131f Kat\u0131l\u0131m"
REFERENCE_MINIMUM = 23

API_URL = (
    "https://www.vakifkatilim.com.tr/"
    "plugins/CampaignListJson"
)

LANG_ID = "bf2689d9-071e-4a20-9450-b1dbdd39778f"


def read_list(path: Path) -> list[dict]:
    if not path.exists():
        return []

    value = json.loads(
        path.read_text(encoding="utf-8")
    )

    if not isinstance(value, list):
        raise RuntimeError(
            f"Liste bekleniyordu: {path}"
        )

    return value


def write_atomic(path: Path, value: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(path)


def item_bank_name(item: dict) -> str:
    return str(
        item.get("bank_name") or ""
    ).strip()


banks = json.loads(
    CONFIG_PATH.read_text(encoding="utf-8")
)

if not isinstance(banks, list):
    raise RuntimeError(
        "banks.json ana yapısı liste değil."
    )

bank = next(
    (
        item
        for item in banks
        if item.get("slug") == BANK_SLUG
    ),
    None,
)

if bank is None:
    raise RuntimeError(
        "vakif_katilim config kaydı bulunamadı."
    )

base_url = str(
    bank.get("base_url")
    or "https://www.vakifkatilim.com.tr"
).rstrip("/")

source_page = str(
    (bank.get("campaign_pages") or [""])[0]
).strip()

if not source_page:
    raise RuntimeError(
        "Vakıf Katılım campaign_pages boş."
    )

session = requests.Session()
session.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/150 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": source_page,
        "X-Requested-With": "XMLHttpRequest",
    }
)

common_params = {
    "langId": LANG_ID,
    "language": "tr",
    "pageItemSize": 9,
    "kendimIcin": "false",
    "isimIcin": "false",
}

first_response = session.get(
    API_URL,
    params={
        **common_params,
        "page": 1,
    },
    timeout=40,
)

first_response.raise_for_status()
first_data = first_response.json()

total_pages = int(
    first_data.get("totalPageCount") or 0
)

if total_pages < 1:
    raise RuntimeError(
        "API totalPageCount döndürmedi."
    )

checked_at = datetime.now(
    timezone.utc
).isoformat()

page_map: dict[str, dict] = {}

for page_number in range(1, total_pages + 1):
    response = session.get(
        API_URL,
        params={
            **common_params,
            "page": page_number,
        },
        timeout=40,
    )

    response.raise_for_status()
    data = response.json()

    items = data.get("items") or []

    if not isinstance(items, list):
        raise RuntimeError(
            f"Sayfa {page_number}: items liste değil."
        )

    print(
        f"API sayfası {page_number}/{total_pages}: "
        f"{len(items)} kayıt"
    )

    for item in items:
        slug = str(
            item.get("link") or ""
        ).strip().strip("/")

        if not slug:
            continue

        title = str(
            item.get("title") or ""
        ).strip()

        url = (
            f"{base_url}/tr/kendim-icin/"
            f"kampanyalar/detay/{slug}"
        )

        page_map[url] = {
            "bank_name": BANK_NAME,
            "url": url,
            "source_page": source_page,
            "page_type": "campaign_detail",
            "discovery_mode": "detail_links_dynamic",
            "source_group": "Kampanyalar",
            "listing_status": "unknown",
            "status_evidence": (
                "Vakıf Katılım resmî kampanya "
                "listeleme kaynağı"
            ),
            "listing_text": title,
            "listing_start_date": "",
            "listing_end_date": "",
            "status_checked_at": checked_at,
        }

new_rows = sorted(
    page_map.values(),
    key=lambda item: item["url"],
)

new_count = len(new_rows)

print()
print("API'de bulunan kampanya:", new_count)
print("Güvenlik alt sınırı:", REFERENCE_MINIMUM)

if new_count < REFERENCE_MINIMUM:
    raise RuntimeError(
        "Eksik tarama ihtimali nedeniyle mevcut "
        "Vakıf Katılım kayıtları korunuyor. "
        f"Bulunan: {new_count}, alt sınır: "
        f"{REFERENCE_MINIMUM}"
    )

existing_pages = read_list(DISCOVERY_PATH)

old_bank_rows = [
    item
    for item in existing_pages
    if item_bank_name(item).casefold()
    == BANK_NAME.casefold()
]

old_urls = {
    str(item.get("url") or "").rstrip("/")
    for item in old_bank_rows
}

new_urls = {
    str(item.get("url") or "").rstrip("/")
    for item in new_rows
}

added_urls = sorted(new_urls - old_urls)
removed_from_listing = sorted(old_urls - new_urls)

final_pages = [
    item
    for item in existing_pages
    if item_bank_name(item).casefold()
    != BANK_NAME.casefold()
]

final_pages.extend(new_rows)

final_pages.sort(
    key=lambda item: (
        item_bank_name(item).casefold(),
        str(item.get("url") or "").casefold(),
    )
)

existing_errors = read_list(ERROR_PATH)

final_errors = [
    item
    for item in existing_errors
    if item_bank_name(item).casefold()
    != BANK_NAME.casefold()
]

existing_report = read_list(REPORT_PATH)

final_report = [
    item
    for item in existing_report
    if item_bank_name(item).casefold()
    != BANK_NAME.casefold()
]

final_report.append(
    {
        "bank_name": BANK_NAME,
        "source_page": source_page,
        "render_mode": "official_json_source",
        "load_more_clicks": 0,
        "rendered_detail_link_count": new_count,
        "discovered_count": new_count,
        "reference_visible_count": REFERENCE_MINIMUM,
        "completeness_status": "COMPLETE_OR_HIGHER",
        "reached_click_limit": False,
    }
)

BACKUP_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

for path in (
    DISCOVERY_PATH,
    ERROR_PATH,
    REPORT_PATH,
):
    if path.exists():
        backup = (
            BACKUP_DIR
            / f"{path.stem}_before_vakif_api_{stamp}"
            f"{path.suffix}"
        )
        shutil.copy2(path, backup)

write_atomic(DISCOVERY_PATH, final_pages)
write_atomic(ERROR_PATH, final_errors)
write_atomic(REPORT_PATH, final_report)

print()
print("=" * 90)
print("VAKIF KATILIM DINAMIK DISCOVERY TAMAMLANDI")
print("=" * 90)
print("Önceki kayıt:", len(old_bank_rows))
print("Güncel kayıt:", new_count)
print("Yeni kampanya:", len(added_urls))
print(
    "Listede artık görünmeyen eski kayıt:",
    len(removed_from_listing),
)

if added_urls:
    print()
    print("YENİ KAMPANYALAR")

    title_map = {
        row["url"].rstrip("/"): row["listing_text"]
        for row in new_rows
    }

    for url in added_urls:
        print("-", title_map.get(url, ""))
        print(" ", url)

print()
print("Discovery:", DISCOVERY_PATH)
print("Rapor:", REPORT_PATH)
