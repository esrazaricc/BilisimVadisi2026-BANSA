from __future__ import annotations

import json
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DISCOVERY_PATH = DATA_DIR / "discovered_campaign_pages.json"
BACKUP_DIR = DATA_DIR / "backups"

HOST = "vakifkatilim.com.tr"

URL_KEYS = (
    "requested_url",
    "source_url",
    "url",
    "final_url",
    "resolved_url",
)

GENERIC_TITLES = {
    "",
    "detay",
    "detayli bilgi",
}


def normalized_text(value: object) -> str:
    text = str(value or "").strip().casefold()
    text = text.replace("\u0131", "i")
    text = unicodedata.normalize("NFKD", text)

    return "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )


def canonical_url(value: object) -> str:
    text = str(value or "").strip()

    if not text:
        return ""

    parts = urlsplit(text)
    host = parts.netloc.casefold()

    if host.startswith("www."):
        host = host[4:]

    return urlunsplit(
        (
            (parts.scheme or "https").casefold(),
            host,
            parts.path.rstrip("/"),
            "",
            "",
        )
    )


def row_url(row: dict) -> str:
    for key in URL_KEYS:
        value = str(row.get(key) or "").strip()

        if value:
            return value

    return ""


def is_vakif_url(value: object) -> bool:
    try:
        host = urlsplit(
            str(value or "")
        ).netloc.casefold()
    except Exception:
        return False

    if host.startswith("www."):
        host = host[4:]

    return host == HOST


def iter_dict_lists(value: object):
    if isinstance(value, list):
        if value and all(
            isinstance(item, dict)
            for item in value
        ):
            yield value

        for item in value:
            yield from iter_dict_lists(item)

    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_dict_lists(child)


discovery = json.loads(
    DISCOVERY_PATH.read_text(encoding="utf-8")
)

if not isinstance(discovery, list):
    raise RuntimeError(
        "Discovery file must contain a list."
    )

title_map: dict[str, str] = {}

for row in discovery:
    if not isinstance(row, dict):
        continue

    url = row_url(row)

    if not is_vakif_url(url):
        continue

    title = str(
        row.get("listing_text") or ""
    ).strip()

    if title:
        title_map[canonical_url(url)] = title

if len(title_map) < 23:
    raise RuntimeError(
        "Expected at least 23 Vakif Katilim "
        f"discovery titles; found {len(title_map)}."
    )

skip_names = {
    "discovered_campaign_pages.json",
    "campaign_discovery_report.json",
    "campaign_discovery_errors.json",
}

candidates = []

for path in DATA_DIR.rglob("*.json"):
    if "backups" in {
        part.casefold()
        for part in path.parts
    }:
        continue

    if (
        path.name in skip_names
        or "audit" in path.stem.casefold()
    ):
        continue

    try:
        document = json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception:
        continue

    for rows in iter_dict_lists(document):
        vakif_rows = [
            row
            for row in rows
            if is_vakif_url(row_url(row))
            and "title" in row
        ]

        if len(vakif_rows) != 23:
            continue

        sample_keys = set().union(
            *(
                set(row.keys())
                for row in vakif_rows[:3]
            )
        )

        score = sum(
            key in sample_keys
            for key in (
                "fetch_status",
                "requested_url",
                "clean_text",
                "raw_text",
                "text_length",
                "fetched_at",
                "content_hash",
            )
        )

        candidates.append(
            {
                "path": path,
                "document": document,
                "rows": vakif_rows,
                "score": score,
            }
        )

if not candidates:
    raise RuntimeError(
        "No fetch JSON containing exactly 23 "
        "Vakif Katilim records was found."
    )

candidates.sort(
    key=lambda item: (
        item["score"],
        str(item["path"]),
    ),
    reverse=True,
)

best = candidates[0]

if (
    len(candidates) > 1
    and candidates[1]["score"] == best["score"]
):
    print("Ambiguous fetch files:")

    for item in candidates:
        print(
            "-",
            item["path"],
            "| score:",
            item["score"],
        )

    raise RuntimeError(
        "More than one equally likely fetch file "
        "was found; no file was changed."
    )

target_path: Path = best["path"]
rows: list[dict] = best["rows"]
document = best["document"]

fixed = []

for row in rows:
    current_title = str(
        row.get("title") or ""
    ).strip()

    if (
        normalized_text(current_title)
        not in GENERIC_TITLES
    ):
        continue

    url = row_url(row)

    expected_title = title_map.get(
        canonical_url(url),
        "",
    )

    if not expected_title:
        raise RuntimeError(
            "No discovery title was found for: "
            + url
        )

    row["title"] = expected_title

    fixed.append(
        {
            "url": url,
            "old_title": current_title,
            "new_title": expected_title,
        }
    )

remaining = [
    row
    for row in rows
    if normalized_text(row.get("title"))
    in GENERIC_TITLES
]

if remaining:
    raise RuntimeError(
        f"{len(remaining)} generic titles would "
        "remain; no file was changed."
    )

BACKUP_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

stamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

backup_path = (
    BACKUP_DIR
    / (
        f"{target_path.stem}"
        f"_before_vakif_title_fix_{stamp}.json"
    )
)

shutil.copy2(
    target_path,
    backup_path,
)

temporary = target_path.with_suffix(
    target_path.suffix + ".tmp"
)

temporary.write_text(
    json.dumps(
        document,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

temporary.replace(target_path)

print("=" * 92)
print("VAKIF KATILIM FETCH TITLE REPAIR COMPLETED")
print("=" * 92)
print("Fetch file:", target_path)
print("Discovery title count:", len(title_map))
print("Vakif Katilim fetch records:", len(rows))
print("Fixed generic titles:", len(fixed))
print("Remaining generic titles:", len(remaining))
print("Backup:", backup_path)

for item in fixed:
    print()
    print("-", item["old_title"] or "<empty>")
    print("+", item["new_title"])
    print(" ", item["url"])
