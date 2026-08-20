from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scraping.campaign_discovery import canonicalize_url
from src.scraping.campaign_page_fetcher import hash_text


BANK_NAME = "Vakıf Katılım"
DEFAULT_DISCOVERY = Path("data") / "discovered_campaign_pages.json"
DEFAULT_INDEX = Path("data") / "campaign_page_index.json"
DEFAULT_REPORT = Path("data") / "vakif_katilim_snapshot_normalization_report.json"

GENERIC_TITLES = {
    "",
    "detay",
    "detaylı bilgi",
    "detayli bilgi",
    "kampanya detayları",
    "kampanya detaylari",
}

RELATED_CAMPAIGN_MARKERS = (
    "İlginizi Çekebilecek Kampanyalar",
    "Ilginizi Cekebilecek Kampanyalar",
)


def normalize_space(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def title_key(value: object) -> str:
    return (
        normalize_space(value)
        .casefold()
        .replace("ı", "i")
        .replace("i̇", "i")
    )


def trim_campaign_text(value: object) -> str:
    text = normalize_space(value)

    for marker in RELATED_CAMPAIGN_MARKERS:
        position = text.casefold().find(marker.casefold())
        if position >= 0:
            text = text[:position].rstrip()
            break

    text = re.sub(
        r"\s*Tümünü Göster\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return normalize_space(text)


def title_from_text(value: object) -> str:
    text = normalize_space(value)
    patterns = (
        r"Hakkımızda\s+(.+?)\s+Kampanya Geçerlilik Tarihi",
        r"Hakkımızda\s+(.+?)\s+Kampanya Detayları",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = normalize_space(match.group(1))
            if title_key(candidate) not in GENERIC_TITLES:
                return candidate
    return ""


def item_url(item: dict[str, Any]) -> str:
    for key in ("requested_url", "source_url", "url", "final_url"):
        value = normalize_space(item.get(key))
        if value:
            return canonicalize_url(value)
    return ""


def load_listing_titles(path: Path) -> dict[str, str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("Discovery dosyasının kökü liste olmalıdır.")

    titles: dict[str, str] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        if normalize_space(item.get("bank_name")) != BANK_NAME:
            continue
        url = item_url(item)
        title = normalize_space(item.get("listing_text"))
        if url and title_key(title) not in GENERIC_TITLES:
            titles[url] = title

    if not titles:
        raise RuntimeError(
            "Vakıf Katılım discovery başlıkları bulunamadı. "
            "Önce refresh_live_campaigns.py çalıştırılmalıdır."
        )
    return titles


def make_backup(index_path: Path, snapshot_paths: list[Path]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = (
        PROJECT_ROOT
        / "data"
        / "backups"
        / f"vakif_snapshot_normalization_{stamp}"
    )
    backup_root.mkdir(parents=True, exist_ok=True)

    if index_path.exists():
        shutil.copy2(index_path, backup_root / index_path.name)

    snapshot_root = backup_root / "snapshots"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    for path in snapshot_paths:
        if path.exists():
            shutil.copy2(path, snapshot_root / path.name)
    return backup_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Vakıf Katılım snapshot başlıklarını API liste başlığından "
            "düzeltir ve önerilen kampanya alanını metinden çıkarır."
        )
    )
    parser.add_argument("--discovery", type=Path, default=DEFAULT_DISCOVERY)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    discovery_path = (
        args.discovery
        if args.discovery.is_absolute()
        else PROJECT_ROOT / args.discovery
    )
    index_path = (
        args.index
        if args.index.is_absolute()
        else PROJECT_ROOT / args.index
    )
    report_path = (
        args.report
        if args.report.is_absolute()
        else PROJECT_ROOT / args.report
    )

    listing_titles = load_listing_titles(discovery_path)
    index_rows = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(index_rows, list):
        raise ValueError("Campaign page index dosyasının kökü liste olmalıdır.")

    vakif_rows = [
        row
        for row in index_rows
        if isinstance(row, dict)
        and normalize_space(row.get("bank_name")) == BANK_NAME
    ]
    if not vakif_rows:
        raise RuntimeError("Vakıf Katılım snapshot kaydı bulunamadı.")

    snapshot_paths: list[Path] = []
    for row in vakif_rows:
        relative = Path(str(row.get("snapshot_file") or ""))
        path = relative if relative.is_absolute() else PROJECT_ROOT / relative
        snapshot_paths.append(path)

    backup_path = None
    if not args.no_backup:
        backup_path = make_backup(index_path, snapshot_paths)

    changed_titles = 0
    trimmed_texts = 0
    processed = 0
    missing_listing_titles: list[str] = []

    for row, snapshot_path in zip(vakif_rows, snapshot_paths):
        if not snapshot_path.exists():
            raise FileNotFoundError(f"Snapshot bulunamadı: {snapshot_path}")

        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict):
            raise ValueError(f"Snapshot JSON nesnesi değil: {snapshot_path}")

        url = item_url(snapshot) or item_url(row)
        old_title = normalize_space(snapshot.get("title"))
        clean_text = trim_campaign_text(snapshot.get("clean_text"))
        raw_text = trim_campaign_text(snapshot.get("raw_text"))

        new_title = listing_titles.get(url, "")
        if not new_title:
            new_title = title_from_text(clean_text)
        if not new_title:
            missing_listing_titles.append(url)
            continue

        if new_title != old_title:
            changed_titles += 1
        if clean_text != normalize_space(snapshot.get("clean_text")):
            trimmed_texts += 1

        snapshot.update(
            {
                "title": new_title,
                "clean_text": clean_text,
                "raw_text": raw_text,
                "content_hash": hash_text(clean_text),
                "text_length": len(clean_text),
            }
        )
        snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        row.update(
            {
                "title": new_title,
                "content_hash": snapshot["content_hash"],
                "text_length": snapshot["text_length"],
            }
        )
        processed += 1

    if missing_listing_titles:
        raise RuntimeError(
            "Başlığı belirlenemeyen Vakıf Katılım kayıtları var:\n- "
            + "\n- ".join(missing_listing_titles)
        )

    generic_remaining = [
        row
        for row in vakif_rows
        if title_key(row.get("title")) in GENERIC_TITLES
    ]
    if generic_remaining:
        raise RuntimeError("Vakıf Katılım snapshotlarında genel başlık kaldı.")

    index_path.write_text(
        json.dumps(index_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = {
        "bank_name": BANK_NAME,
        "processed": processed,
        "listing_title_count": len(listing_titles),
        "changed_title_count": changed_titles,
        "trimmed_text_count": trimmed_texts,
        "backup": str(backup_path) if backup_path else None,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Vakıf Katılım snapshot normalizasyonu tamamlandı.")
    print("İşlenen:", processed)
    print("Başlığı düzeltilen:", changed_titles)
    print("Öneri alanı temizlenen:", trimmed_texts)
    print("Rapor:", report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
