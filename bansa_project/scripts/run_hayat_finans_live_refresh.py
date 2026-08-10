from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scraping.campaign_discovery import (
    canonicalize_url,
    discover_all_pages,
    write_discovery_results,
)
from src.scraping.campaign_page_fetcher import (
    fetch_campaign_pages,
    write_fetch_results,
)

BANK = "Hayat Finans"
DISCOVERY_PATH = PROJECT_ROOT / "data" / "discovered_campaign_pages.json"
INDEX_PATH = PROJECT_ROOT / "data" / "campaign_page_index.json"
SPECIAL_URL = "https://hayatfinans.com.tr/hesaplar/avantajli-hesap"
SPECIAL_TITLE = "Birikimin Büyüsün, Avantajın Bitmesin!"

MONTHS = {
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

RANGE_PATTERN = re.compile(
    r"(?:kampanya\s+(?:donemi|suresi|tarihleri)\s*:?\s*)?"
    r"(?P<start_day>\d{1,2})\s+"
    r"(?P<start_month>ocak|subat|mart|nisan|mayis|haziran|temmuz|agustos|eylul|ekim|kasim|aralik)"
    r"(?:\s+(?P<start_year>\d{4}))?\s*[-–—]\s*"
    r"(?P<end_day>\d{1,2})\s+"
    r"(?P<end_month>ocak|subat|mart|nisan|mayis|haziran|temmuz|agustos|eylul|ekim|kasim|aralik)\s+"
    r"(?P<end_year>\d{4})",
    flags=re.IGNORECASE,
)

FULL_DATE_PATTERN = re.compile(
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>ocak|subat|mart|nisan|mayis|haziran|temmuz|agustos|eylul|ekim|kasim|aralik)\s+"
    r"(?P<year>\d{4})",
    flags=re.IGNORECASE,
)

GENERIC_TITLES = {
    "",
    "kampanyalar",
    "kampanya",
    "kampanya detaylari",
    "hayat finans",
}


def _text_key(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = "".join(
        character for character in normalized
        if not unicodedata.combining(character)
    )
    return (
        " ".join(ascii_text.split())
        .casefold()
        .replace("ı", "i")
    )


def _read_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _parse_iso(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _extract_hayat_dates(text: str) -> tuple[str, str, str]:
    normalized = _text_key(text)

    range_match = RANGE_PATTERN.search(normalized)
    if range_match:
        end_year = int(range_match.group("end_year"))
        start_year_text = range_match.group("start_year")
        start_month = MONTHS[range_match.group("start_month").casefold()]
        end_month = MONTHS[range_match.group("end_month").casefold()]
        start_year = int(start_year_text) if start_year_text else end_year
        if not start_year_text and start_month > end_month:
            start_year -= 1

        start = date(
            start_year,
            start_month,
            int(range_match.group("start_day")),
        )
        end = date(
            end_year,
            end_month,
            int(range_match.group("end_day")),
        )
        return start.isoformat(), end.isoformat(), range_match.group(0)

    full_dates = list(FULL_DATE_PATTERN.finditer(normalized))
    if full_dates:
        match = full_dates[-1]
        parsed = date(
            int(match.group("year")),
            MONTHS[match.group("month").casefold()],
            int(match.group("day")),
        )
        prefix = normalized[max(0, match.start() - 80):match.start()]
        if "bitis" in prefix or "son" in prefix:
            return "", parsed.isoformat(), match.group(0)

    return "", "", ""


def _status_for_dates(start_text: str, end_text: str) -> str:
    today = date.today()
    start = _parse_iso(start_text)
    end = _parse_iso(end_text)

    if start and today < start:
        return "upcoming"
    if end and today > end:
        return "expired"
    return "active"


def _previous_bank_rows(path: Path) -> list[dict]:
    return [
        row for row in _read_json_list(path)
        if row.get("bank_name") == BANK
    ]


def _validate_rolling_discovery(pages) -> tuple[int, int]:
    previous = _previous_bank_rows(DISCOVERY_PATH)
    previous_urls = {
        canonicalize_url(str(row.get("url") or ""))
        for row in previous
        if row.get("url")
    }
    current_urls = {
        canonicalize_url(page.url)
        for page in pages
        if page.bank_name == BANK
    }

    if not current_urls:
        raise RuntimeError("Hayat Finans discovery sıfır sonuç döndürdü.")

    added = current_urls - previous_urls
    removed = previous_urls - current_urls

    if not removed:
        return len(added), 0

    index_by_url = {
        canonicalize_url(str(row.get("url") or "")): row
        for row in _read_json_list(INDEX_PATH)
        if row.get("bank_name") == BANK and row.get("url")
    }

    unsafe_removed: list[str] = []
    today = date.today()

    for url in sorted(removed):
        row = index_by_url.get(url)
        if row is None:
            unsafe_removed.append(url + " | önceki fetch kaydı yok")
            continue

        status = str(
            row.get("current_status")
            or row.get("status")
            or "unknown"
        ).casefold()
        end = _parse_iso(
            row.get("end_date")
            or row.get("campaign_end_date")
        )

        expired_by_date = end is not None and end < today
        if status != "expired" and not expired_by_date:
            unsafe_removed.append(
                f"{url} | durum={status}, bitiş={end or 'belirtilmemiş'}"
            )

    if unsafe_removed:
        raise RuntimeError(
            "Hayat Finans discovery aktif/kanıtsız kayıt kaybetti; "
            "yenileme durduruldu:\n- " + "\n- ".join(unsafe_removed)
        )

    return len(added), len(removed)


def _apply_hayat_overrides(snapshots, pages):
    page_by_url = {
        canonicalize_url(page.url): page
        for page in pages
        if page.bank_name == BANK
    }

    corrected = []
    title_count = 0
    date_count = 0
    status_count = 0

    checked_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )

    for snapshot in snapshots:
        if snapshot.bank_name != BANK:
            corrected.append(snapshot)
            continue

        url = canonicalize_url(snapshot.requested_url or snapshot.url)
        if url not in page_by_url:
            raise RuntimeError(
                "Hayat Finans snapshot discovery kaydında yok: " + url
            )

        title = snapshot.title
        if url == canonicalize_url(SPECIAL_URL):
            title = SPECIAL_TITLE

        start_date = snapshot.campaign_start_date or ""
        end_date = snapshot.campaign_end_date or ""
        evidence = ""

        parsed_start, parsed_end, parsed_evidence = _extract_hayat_dates(
            snapshot.clean_text or ""
        )
        if parsed_start:
            start_date = parsed_start
        if parsed_end:
            end_date = parsed_end
        if parsed_evidence:
            evidence = "Hayat Finans kampanya metni: " + parsed_evidence

        status = _status_for_dates(start_date, end_date)
        if not evidence:
            evidence = (
                "Hayat Finans resmî kampanya listesinde güncel olarak bulundu; "
                "açık bir bitiş tarihi tespit edilmedi."
            )

        if title != snapshot.title:
            title_count += 1
        if (
            start_date != snapshot.campaign_start_date
            or end_date != snapshot.campaign_end_date
        ):
            date_count += 1
        if status != snapshot.current_status:
            status_count += 1

        corrected.append(
            replace(
                snapshot,
                title=title,
                campaign_start_date=start_date,
                campaign_end_date=end_date,
                current_status=status,
                listing_status="active" if status != "expired" else "expired",
                listing_status_evidence=evidence,
                status_reason=(
                    "Hayat Finans resmî liste ve kampanya dönemi birlikte değerlendirildi."
                ),
                status_evidence=evidence,
                status_checked_at=checked_at,
            )
        )

    return corrected, title_count, date_count, status_count


def _validate_snapshots(snapshots, pages) -> None:
    bank_pages = [page for page in pages if page.bank_name == BANK]
    bank_snapshots = [item for item in snapshots if item.bank_name == BANK]

    if len(bank_snapshots) != len(bank_pages):
        raise RuntimeError(
            "Hayat Finans discovery/fetch sayısı eşleşmedi: "
            f"discovery={len(bank_pages)}, fetch={len(bank_snapshots)}"
        )

    urls = {
        canonicalize_url(item.requested_url or item.url)
        for item in bank_snapshots
    }
    if len(urls) != len(bank_snapshots):
        raise RuntimeError("Hayat Finans fetch sonuçlarında mükerrer URL var.")

    invalid = [
        item.url for item in bank_snapshots
        if _text_key(item.title) in GENERIC_TITLES
        or not str(item.clean_text or "").strip()
    ]
    if invalid:
        raise RuntimeError(
            "Hayat Finans fetch kalite sorunu:\n- " + "\n- ".join(invalid)
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Hayat Finans kampanyalarını dinamik olarak keşfeder, "
            "fetch eder ve yeni/sona ermiş kampanyaları güvenli biçimde işler."
        )
    )
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    pages, discovery_errors, diagnostics = discover_all_pages(
        bank_name=BANK,
        timeout=args.timeout,
        delay_seconds=args.delay,
        headless=not args.headed,
    )

    if discovery_errors:
        raise RuntimeError(
            "Hayat Finans discovery hatası: "
            + json.dumps(discovery_errors, ensure_ascii=False)
        )

    added_count, expired_removed_count = _validate_rolling_discovery(pages)

    write_discovery_results(pages, discovery_errors, diagnostics)

    snapshots, fetch_errors = fetch_campaign_pages(
        bank_name=BANK,
        timeout=args.timeout,
        delay_seconds=args.delay,
        headless=not args.headed,
    )
    if fetch_errors:
        raise RuntimeError(
            "Hayat Finans fetch hatası: "
            + json.dumps(fetch_errors, ensure_ascii=False)
        )

    snapshots, title_count, date_count, status_count = (
        _apply_hayat_overrides(snapshots, pages)
    )
    _validate_snapshots(snapshots, pages)
    write_fetch_results(snapshots, fetch_errors)

    current = [item for item in snapshots if item.bank_name == BANK]
    status_counts: dict[str, int] = {}
    for item in current:
        status_counts[item.current_status] = (
            status_counts.get(item.current_status, 0) + 1
        )

    print("=" * 90)
    print("HAYAT FİNANS CANLI YENİLEME BAŞARILI")
    print("=" * 90)
    print("Keşfedilen kampanya:", len(pages))
    print("Fetch edilen kampanya:", len(current))
    print("Yeni bulunan kampanya:", added_count)
    print("Süresi dolduğu doğrulanarak listeden çıkan:", expired_removed_count)
    print("Başlık düzeltmesi:", title_count)
    print("Tarih düzeltmesi:", date_count)
    print("Durum düzeltmesi:", status_count)
    print("Durum dağılımı:", status_counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
