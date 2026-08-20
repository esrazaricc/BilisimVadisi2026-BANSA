from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.processing.campaign_classifier import classify_campaign_record
from src.scraping.campaign_discovery import canonicalize_url
from src.scraping.campaign_page_fetcher import hash_text


BANK_NAME = "Vakıf Katılım"
DEFAULT_DB = Path("data") / "campaigns.db"
DEFAULT_DISCOVERY = Path("data") / "discovered_campaign_pages.json"
DEFAULT_REPORT = Path("data") / "vakif_katilim_finalization_report.json"

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
    for pattern in (
        r"Hakkımızda\s+(.+?)\s+Kampanya Geçerlilik Tarihi",
        r"Hakkımızda\s+(.+?)\s+Kampanya Detayları",
    ):
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
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        return {}

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
    return titles


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_backup(db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"campaigns_before_vakif_finalization_{stamp}.db"
    shutil.copy2(db_path, backup_path)
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Vakıf Katılım kayıtlarını resmî kampanya API kaynağına göre "
            "başlık, içerik ve sınıflandırma açısından tamamlar."
        )
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--discovery", type=Path, default=DEFAULT_DISCOVERY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    db_path = args.db if args.db.is_absolute() else PROJECT_ROOT / args.db
    discovery_path = (
        args.discovery
        if args.discovery.is_absolute()
        else PROJECT_ROOT / args.discovery
    )
    report_path = (
        args.report
        if args.report.is_absolute()
        else PROJECT_ROOT / args.report
    )

    if not db_path.exists():
        raise FileNotFoundError(f"Veritabanı bulunamadı: {db_path}")

    backup_path = None if args.no_backup else make_backup(db_path)
    listing_titles = load_listing_titles(discovery_path)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM live_campaigns
            WHERE bank_name = ?
            ORDER BY id
            """,
            (BANK_NAME,),
        ).fetchall()
        if not rows:
            raise RuntimeError("Vakıf Katılım veritabanı kaydı bulunamadı.")

        changed_titles = 0
        trimmed_texts = 0
        fallback_classifications = 0
        category_counts: dict[str, int] = {}
        timestamp = utc_now_iso()

        with connection:
            for row in rows:
                url = canonicalize_url(row["source_url"] or "")
                old_title = normalize_space(row["title"])
                clean_text = trim_campaign_text(row["clean_text"])
                new_title = listing_titles.get(url, "")
                if not new_title:
                    new_title = title_from_text(clean_text)
                if not new_title:
                    new_title = old_title

                if title_key(new_title) in GENERIC_TITLES:
                    raise RuntimeError(
                        "Vakıf Katılım başlığı belirlenemedi: " + url
                    )

                result = classify_campaign_record(
                    title=new_title,
                    clean_text=clean_text,
                    source_group=row["source_group"] or "",
                )

                record_kind = result.record_kind
                campaign_category = result.campaign_category
                comparison_eligible = int(result.comparison_eligible)
                confidence = result.confidence
                reason = result.reason

                # CampaignListJson yalnızca resmî kampanya kartlarını döndürür.
                # Genel sınıflandırıcı somut alt türü bulamazsa kayıt yine gerçek
                # kampanyadır ve güvenli biçimde "Diğer Kampanyalar" altında yer alır.
                if record_kind != "campaign":
                    record_kind = "campaign"
                    campaign_category = "other_campaign"
                    comparison_eligible = 1
                    confidence = max(float(confidence or 0), 0.90)
                    reason = (
                        "Vakıf Katılım resmî CampaignListJson kampanya "
                        "listesinde yer aldı; alt tür güvenle belirlenemediği "
                        "için Diğer Kampanyalar olarak sınıflandırıldı."
                    )
                    fallback_classifications += 1

                if new_title != old_title:
                    changed_titles += 1
                if clean_text != normalize_space(row["clean_text"]):
                    trimmed_texts += 1

                category_counts[campaign_category] = (
                    category_counts.get(campaign_category, 0) + 1
                )

                connection.execute(
                    """
                    UPDATE live_campaigns
                    SET
                        title = ?,
                        clean_text = ?,
                        content_hash = ?,
                        record_kind = ?,
                        campaign_category = ?,
                        comparison_eligible = ?,
                        classification_confidence = ?,
                        classification_reason = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        new_title,
                        clean_text,
                        hash_text(clean_text),
                        record_kind,
                        campaign_category,
                        comparison_eligible,
                        confidence,
                        reason,
                        timestamp,
                        row["id"],
                    ),
                )

        invalid = connection.execute(
            """
            SELECT id, title, record_kind, comparison_eligible
            FROM live_campaigns
            WHERE bank_name = ?
              AND (
                    record_kind != 'campaign'
                 OR comparison_eligible != 1
                 OR TRIM(COALESCE(title, '')) = ''
              )
            """,
            (BANK_NAME,),
        ).fetchall()
        if invalid:
            raise RuntimeError(
                "Dashboard için hazır olmayan Vakıf Katılım kaydı kaldı: "
                + ", ".join(str(row["id"]) for row in invalid)
            )

        report = {
            "bank_name": BANK_NAME,
            "processed": len(rows),
            "listing_title_count": len(listing_titles),
            "changed_title_count": changed_titles,
            "trimmed_text_count": trimmed_texts,
            "fallback_classification_count": fallback_classifications,
            "category_counts": category_counts,
            "backup": str(backup_path) if backup_path else None,
            "generated_at": timestamp,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print("Vakıf Katılım kayıtları dashboard için hazırlandı.")
        print("İşlenen:", len(rows))
        print("Başlığı düzeltilen:", changed_titles)
        print("Öneri alanı temizlenen:", trimmed_texts)
        print("Diğer Kampanyalar fallback:", fallback_classifications)
        print("Kategoriler:", json.dumps(category_counts, ensure_ascii=False))
        print("Rapor:", report_path)
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
