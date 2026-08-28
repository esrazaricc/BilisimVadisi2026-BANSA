from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.processing.campaign_classifier import classify_campaign_record
from src.scraping.campaign_status import evaluate_campaign_status


BANK = "Türkiye Emlak Katılım"
INDEX = PROJECT_ROOT / "data" / "campaign_page_index.json"
REPORT = PROJECT_ROOT / "data" / "emlak_katilim_pre_db_audit.json"

EXPECTED_DETAIL_PATHS = (
    "/tr/bireysel/kampanyalar/kampanya/",
    "/tr/kurumsal/kampanyalar/kampanya/",
)

GENERIC_TITLES = {
    "kampanya",
    "kampanyalar",
    "turkiye emlak katilim bankasi",
    "turkiye emlak katilim",
    "emlak katilim bankasi",
}


def fold(value: str) -> str:
    value = (value or "").casefold()
    table = str.maketrans(
        {
            "ç": "c", "ğ": "g", "ı": "i", "ö": "o",
            "ş": "s", "ü": "u", "İ": "i",
        }
    )
    value = value.translate(table)
    return re.sub(r"\s+", " ", value).strip()


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_snapshot(row: dict):
    raw = str(row.get("snapshot_file") or "").strip()
    if not raw:
        return {}, None
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return {}, path
    value = load_json(path, {})
    return value if isinstance(value, dict) else {}, path


def main() -> int:
    rows = load_json(INDEX, [])
    if not isinstance(rows, list):
        raise RuntimeError("campaign_page_index.json liste değil.")

    bank_rows = [
        r for r in rows
        if isinstance(r, dict)
        and str(r.get("bank_name") or "") == BANK
    ]

    if not bank_rows:
        raise RuntimeError("Türkiye Emlak Katılım fetch kaydı bulunamadı.")

    status_counts = Counter()
    category_counts = Counter()
    kind_counts = Counter()

    invalid_candidates = []
    unknown_status = []
    point_mismatches = []
    date_order_errors = []
    snapshot_missing = []

    for row in bank_rows:
        snap, snap_path = resolve_snapshot(row)
        if not snap:
            snapshot_missing.append(
                {
                    "url": row.get("requested_url") or row.get("url"),
                    "snapshot": str(snap_path or ""),
                }
            )
            continue

        title = str(snap.get("title") or row.get("title") or "").strip()
        text = str(snap.get("clean_text") or "").strip()
        requested_url = str(
            snap.get("requested_url")
            or row.get("requested_url")
            or row.get("url")
            or ""
        )
        final_url = str(
            snap.get("final_url")
            or row.get("final_url")
            or requested_url
        )
        source_group = str(
            row.get("source_group")
            or snap.get("source_group")
            or ""
        )

        status = evaluate_campaign_status(
            text=f"{title} {text}",
            listing_status=str(
                snap.get("listing_status")
                or row.get("listing_status")
                or "unknown"
            ),
            listing_evidence=str(
                snap.get("listing_status_evidence")
                or row.get("status_evidence")
                or ""
            ),
        )

        classification = classify_campaign_record(
            title=title,
            clean_text=text,
            source_group=source_group,
        )

        status_counts[status.status] += 1
        category_counts[classification.campaign_category] += 1
        kind_counts[classification.record_kind] += 1

        title_key = fold(title)
        path = urlparse(final_url).path or "/"

        generic_title = title_key in GENERIC_TITLES
        outside_detail = not any(
            prefix in path
            for prefix in EXPECTED_DETAIL_PATHS
        )

        evidence_key = fold(f"{title} {text[:2500]}")
        has_campaign_evidence = any(
            term in evidence_key
            for term in (
                "kampanya",
                "parafpara",
                "indirim",
                "nakit iade",
                "taksit",
                "avantaj",
                "hediye",
                "harcama",
            )
        )

        if generic_title or outside_detail or not has_campaign_evidence:
            invalid_candidates.append(
                {
                    "title": title,
                    "requested_url": requested_url,
                    "final_url": final_url,
                    "generic_title": generic_title,
                    "outside_detail_path": outside_detail,
                    "has_campaign_evidence": has_campaign_evidence,
                    "text_length": len(text),
                }
            )

        if status.status == "unknown":
            unknown_status.append(
                {
                    "title": title,
                    "url": requested_url,
                }
            )

        if (
            status.start_date
            and status.end_date
            and status.start_date > status.end_date
        ):
            date_order_errors.append(
                {
                    "title": title,
                    "start": status.start_date,
                    "end": status.end_date,
                    "url": requested_url,
                }
            )

        if (
            "parafpara" in fold(title)
            and classification.campaign_category != "points_campaign"
        ):
            point_mismatches.append(
                {
                    "title": title,
                    "category": classification.campaign_category,
                    "url": requested_url,
                }
            )

    report = {
        "bank_name": BANK,
        "fetched_rows": len(bank_rows),
        "snapshot_missing_count": len(snapshot_missing),
        "invalid_candidate_count": len(invalid_candidates),
        "unknown_status_count": len(unknown_status),
        "point_mismatch_count": len(point_mismatches),
        "date_order_error_count": len(date_order_errors),
        "status_counts": dict(status_counts),
        "record_kind_counts": dict(kind_counts),
        "category_counts": dict(category_counts),
        "invalid_candidates": invalid_candidates,
        "unknown_status": unknown_status,
        "point_mismatches": point_mismatches,
        "date_order_errors": date_order_errors,
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 78)
    print("TÜRKİYE EMLAK KATILIM — DB ÖNCESİ KALİTE DENETİMİ")
    print("=" * 78)
    print("Fetch kaydı:", len(bank_rows))
    print("Durumlar:", dict(status_counts))
    print("Kayıt türleri:", dict(kind_counts))
    print("Kategoriler:", dict(category_counts))
    print("Snapshot eksik:", len(snapshot_missing))
    print("Şüpheli/geçersiz aday:", len(invalid_candidates))
    print("Status unknown:", len(unknown_status))
    print("ParafPara kategori hatası:", len(point_mismatches))
    print("Başlangıç > bitiş:", len(date_order_errors))

    print("\nŞÜPHELİ / GEÇERSİZ ADAYLAR")
    if not invalid_candidates:
        print("- Yok")
    else:
        for item in invalid_candidates:
            print("-", item["title"])
            print("  requested:", item["requested_url"])
            print("  final:", item["final_url"])
            print(
                "  generic=",
                item["generic_title"],
                "outside_detail=",
                item["outside_detail_path"],
                "evidence=",
                item["has_campaign_evidence"],
                "text_length=",
                item["text_length"],
            )

    print("\nSTATUS UNKNOWN ÖRNEKLERİ")
    if not unknown_status:
        print("- Yok")
    else:
        for item in unknown_status[:20]:
            print("-", item["title"])
            print(" ", item["url"])

    print("\nPARAFPARA KATEGORİ HATALARI")
    if not point_mismatches:
        print("- Yok")
    else:
        for item in point_mismatches:
            print(
                f"- [{item['category']}] {item['title']}"
            )
            print(" ", item["url"])

    print("\nRapor:", REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
