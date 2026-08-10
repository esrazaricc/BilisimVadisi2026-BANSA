from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.scraping.campaign_discovery import canonicalize_url
from src.scraping.campaign_page_fetcher import (
    CampaignPageSnapshot,
    hash_text,
    normalize_text,
    utc_now_iso,
)


DEFAULT_OVERRIDE_PATH = (
    Path("config") / "campaign_content_overrides.json"
)


def _load_rows(
    path: str | Path = DEFAULT_OVERRIDE_PATH,
) -> list[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return []

    try:
        value = json.loads(
            file_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return []

    return value if isinstance(value, list) else []


def _url_key(value: str) -> str:
    return canonicalize_url(str(value or ""))


def find_content_override(
    bank_name: str,
    source_url: str,
    *,
    path: str | Path = DEFAULT_OVERRIDE_PATH,
) -> dict[str, Any] | None:
    bank_key = normalize_text(bank_name).casefold()
    source_key = _url_key(source_url)

    for row in _load_rows(path):
        if normalize_text(
            row.get("bank_name")
        ).casefold() != bank_key:
            continue

        source_urls = row.get("source_urls", [])
        if not isinstance(source_urls, list):
            continue

        keys = {
            _url_key(item)
            for item in source_urls
            if _url_key(item)
        }
        if source_key in keys:
            return row

    return None


def build_override_snapshot(
    page: dict[str, str],
    override: dict[str, Any],
) -> CampaignPageSnapshot:
    timestamp = utc_now_iso()
    title = normalize_text(override.get("title"))
    clean_text = normalize_text(
        override.get("clean_text")
    )
    effective_url = canonicalize_url(
        str(override.get("effective_url") or page["url"])
    )

    return CampaignPageSnapshot(
        bank_name=page["bank_name"],
        title=title,
        url=effective_url,
        requested_url=canonicalize_url(page["url"]),
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
            "active",
        ),
        listing_status_evidence=normalize_text(
            override.get("verification_note")
        ),
        fetch_method="verified_content_override",
        http_status=200,
        content_type="text/plain; verified-override",
        raw_text=clean_text,
        clean_text=clean_text,
        content_hash=hash_text(clean_text),
        text_length=len(clean_text),
        campaign_start_date=normalize_text(
            override.get("campaign_start_date")
        ),
        campaign_end_date=normalize_text(
            override.get("campaign_end_date")
        ),
        current_status=normalize_text(
            override.get("current_status")
        ) or "active",
        status_reason=(
            "Resmî sayfa manuel olarak doğrulandı; otomatik "
            "çıkarıcı kısa içerik ürettiği için doğrulanmış "
            "yedek içerik kullanıldı."
        ),
        status_evidence=normalize_text(
            override.get("verification_note")
        ),
        status_checked_at=timestamp,
        first_seen_at=timestamp,
        last_checked_at=timestamp,
        fetch_status="ok",
    )
