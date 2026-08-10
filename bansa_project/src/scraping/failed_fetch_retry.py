from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.scraping.campaign_page_fetcher import (
    CampaignPageSnapshot,
    canonicalize_url,
    normalize_text,
    search_key,
)


def read_json_list(path: str | Path) -> list[dict[str, Any]]:
    file_path = Path(path)
    if not file_path.exists():
        return []

    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    return value if isinstance(value, list) else []


def normalized_bank(value: Any) -> str:
    return normalize_text(value).casefold()


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    requested_url = canonicalize_url(
        str(row.get("requested_url", "") or "")
    )
    final_url = canonicalize_url(
        str(row.get("url", "") or "")
    )

    return (
        normalized_bank(row.get("bank_name")),
        requested_url or final_url,
    )


def merge_index_rows(
    existing_rows: list[dict[str, Any]],
    replacement_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Yalnızca tekrar çekilen URL'leri günceller.
    Aynı bankanın diğer kayıtlarını silmez.
    """
    merged: dict[
        tuple[str, str],
        dict[str, Any],
    ] = {}

    for row in existing_rows:
        key = row_key(row)
        if key[0] and key[1]:
            merged[key] = row

    for row in replacement_rows:
        key = row_key(row)
        if key[0] and key[1]:
            merged[key] = row

    return sorted(
        merged.values(),
        key=row_key,
    )


def remove_resolved_errors(
    existing_errors: list[dict[str, Any]],
    *,
    bank_name: str,
    resolved_urls: set[str],
) -> list[dict[str, Any]]:
    bank_key = normalized_bank(bank_name)
    normalized_urls = {
        canonicalize_url(url)
        for url in resolved_urls
        if canonicalize_url(url)
    }

    result: list[dict[str, Any]] = []

    for error in existing_errors:
        error_bank = normalized_bank(error.get("bank_name"))
        error_url = canonicalize_url(
            str(error.get("url", "") or "")
        )

        is_resolved = (
            error_bank == bank_key
            and error_url in normalized_urls
        )
        if not is_resolved:
            result.append(error)

    return result


def snapshot_filename(
    snapshot: CampaignPageSnapshot,
) -> str:
    digest = hashlib.sha1(
        snapshot.url.encode("utf-8")
    ).hexdigest()[:18]
    return f"{digest}.json"


def snapshot_folder_name(bank_name: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        search_key(bank_name),
    ).strip("_")


def persist_snapshots(
    snapshots: list[CampaignPageSnapshot],
    *,
    snapshot_root: str | Path,
) -> list[dict[str, Any]]:
    root = Path(snapshot_root)
    rows: list[dict[str, Any]] = []

    for snapshot in snapshots:
        bank_folder = (
            root / snapshot_folder_name(snapshot.bank_name)
        )
        bank_folder.mkdir(parents=True, exist_ok=True)

        output_file = (
            bank_folder / snapshot_filename(snapshot)
        )
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
        rows.append(row)

    return rows


def build_fetch_report(
    index_rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    *,
    generated_at: str,
    minimum_text_length: int,
) -> dict[str, Any]:
    status_counts = Counter(
        normalize_text(row.get("fetch_status"))
        for row in index_rows
    )
    campaign_status_counts = Counter(
        normalize_text(row.get("current_status"))
        for row in index_rows
    )
    bank_counts = Counter(
        normalize_text(row.get("bank_name"))
        for row in index_rows
    )

    return {
        "snapshot_count": len(index_rows),
        "error_count": len(errors),
        "fetch_status_counts": dict(
            sorted(status_counts.items())
        ),
        "campaign_status_counts": dict(
            sorted(campaign_status_counts.items())
        ),
        "bank_counts": dict(sorted(bank_counts.items())),
        "minimum_acceptable_text_length": (
            minimum_text_length
        ),
        "generated_at": generated_at,
    }
