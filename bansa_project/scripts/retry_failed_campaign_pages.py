from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scraping.campaign_discovery import load_bank_config
from src.scraping.campaign_page_fetcher import (
    MIN_ACCEPTABLE_TEXT_LENGTH,
    canonicalize_url,
    fetch_page,
    normalize_text,
    search_key,
    utc_now_iso,
)
from src.scraping.failed_fetch_retry import (
    build_fetch_report,
    merge_index_rows,
    persist_snapshots,
    read_json_list,
    remove_resolved_errors,
)
from src.scraping.http_client import HttpClient
from src.scraping.campaign_content_override import (
    build_override_snapshot,
    find_content_override,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Başarısız kampanya sayfalarını, aynı bankanın başarılı "
            "indeks kayıtlarını silmeden tekrar çeker."
        )
    )
    parser.add_argument(
        "--bank",
        default="Kuveyt Türk",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
    )
    parser.add_argument(
        "--discovery",
        type=Path,
        default=(
            Path("data")
            / "discovered_campaign_pages.json"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config") / "banks.json",
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=Path("data") / "campaign_page_index.json",
    )
    parser.add_argument(
        "--errors",
        type=Path,
        default=(
            Path("data")
            / "campaign_page_fetch_errors.json"
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=(
            Path("data")
            / "campaign_page_fetch_report.json"
        ),
    )
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=Path("data") / "campaign_pages",
    )
    args = parser.parse_args()

    existing_errors = read_json_list(args.errors)
    bank_errors = [
        error
        for error in existing_errors
        if normalize_text(error.get("bank_name")).casefold()
        == args.bank.casefold()
    ]

    if not bank_errors:
        print(
            f"{args.bank} için tekrar çekilecek hata kaydı yok."
        )
        return 0

    discovery_rows = read_json_list(args.discovery)
    discovery_map = {
        canonicalize_url(str(row.get("url", "") or "")): row
        for row in discovery_rows
        if normalize_text(row.get("bank_name")).casefold()
        == args.bank.casefold()
    }

    bank_configs = {
        search_key(bank["name"]): bank
        for bank in load_bank_config(args.config)
    }
    bank_config = bank_configs.get(
        search_key(args.bank),
        {},
    )

    pages = []
    unmatched_errors = []

    for error in bank_errors:
        error_url = canonicalize_url(
            str(error.get("url", "") or "")
        )
        page = discovery_map.get(error_url)
        if page:
            pages.append(page)
        else:
            unmatched_errors.append(error)

    if unmatched_errors:
        print(
            "Keşif dosyasında eşleşmeyen hata sayısı:",
            len(unmatched_errors),
        )
        for error in unmatched_errors:
            print("  -", error.get("url"))

    snapshots = []
    unresolved_errors = []

    with HttpClient(
        timeout=args.timeout,
        delay_seconds=args.delay,
    ) as client:
        for page_index, page in enumerate(pages, start=1):
            last_error = None
            resolved = False

            for attempt in range(
                1,
                max(1, args.attempts) + 1,
            ):
                try:
                    snapshot = fetch_page(
                        page,
                        client,
                        bank_config=bank_config,
                        browser_fallback=True,
                        headless=True,
                    )

                    if snapshot.fetch_status == "ok":
                        snapshots.append(snapshot)
                        print(
                            f"[{page_index}/{len(pages)}] "
                            f"BAŞARILI — {snapshot.title}"
                        )
                        resolved = True
                        break

                    last_error = {
                        "bank_name": page["bank_name"],
                        "url": page["url"],
                        "error_type": "FetchStatusError",
                        "message": (
                            "Tekrar çekim durumu: "
                            f"{snapshot.fetch_status}"
                        ),
                    }
                    print(
                        f"[{page_index}/{len(pages)}] "
                        f"Deneme {attempt}: "
                        f"{snapshot.fetch_status}"
                    )

                except Exception as error:
                    last_error = {
                        "bank_name": page["bank_name"],
                        "url": page["url"],
                        "error_type": type(error).__name__,
                        "message": str(error),
                    }
                    print(
                        f"[{page_index}/{len(pages)}] "
                        f"Deneme {attempt} HATA — "
                        f"{type(error).__name__}: {error}"
                    )

                if attempt < max(1, args.attempts):
                    time.sleep(1.0)

            if not resolved:
                override = find_content_override(
                    page["bank_name"],
                    page["url"],
                )

                if override is not None:
                    snapshot = build_override_snapshot(
                        page,
                        override,
                    )
                    snapshots.append(snapshot)
                    resolved = True
                    print(
                        f"[{page_index}/{len(pages)}] "
                        f"DOĞRULANMIŞ YEDEK — "
                        f"{snapshot.title}"
                    )

            if not resolved and last_error:
                unresolved_errors.append(last_error)

    existing_index = read_json_list(args.index)
    replacement_rows = persist_snapshots(
        snapshots,
        snapshot_root=args.snapshot_root,
    )
    final_index = merge_index_rows(
        existing_index,
        replacement_rows,
    )

    resolved_urls = {
        snapshot.requested_url or snapshot.url
        for snapshot in snapshots
    }
    final_errors = remove_resolved_errors(
        existing_errors,
        bank_name=args.bank,
        resolved_urls=resolved_urls,
    )

    # Aynı başarısız URL için eski kaydı kaldırıp güncel hatayı ekle.
    unresolved_urls = {
        canonicalize_url(
            str(error.get("url", "") or "")
        )
        for error in unresolved_errors
    }
    final_errors = [
        error
        for error in final_errors
        if not (
            normalize_text(
                error.get("bank_name")
            ).casefold()
            == args.bank.casefold()
            and canonicalize_url(
                str(error.get("url", "") or "")
            )
            in unresolved_urls
        )
    ]
    final_errors.extend(unresolved_errors)

    args.index.write_text(
        json.dumps(
            final_index,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    args.errors.write_text(
        json.dumps(
            final_errors,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_fetch_report(
        final_index,
        final_errors,
        generated_at=utc_now_iso(),
        minimum_text_length=(
            MIN_ACCEPTABLE_TEXT_LENGTH
        ),
    )
    args.report.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    bank_index_count = sum(
        normalize_text(row.get("bank_name")).casefold()
        == args.bank.casefold()
        for row in final_index
    )
    remaining_bank_errors = sum(
        normalize_text(error.get("bank_name")).casefold()
        == args.bank.casefold()
        for error in final_errors
    )

    print()
    print("Güvenli tekrar çekim tamamlandı.")
    print("Başarılı tekrar:", len(snapshots))
    print(
        f"{args.bank} indeks kaydı:",
        bank_index_count,
    )
    print(
        f"{args.bank} kalan hata:",
        remaining_bank_errors,
    )

    return 1 if remaining_bank_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())