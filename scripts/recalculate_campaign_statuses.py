from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scraping.campaign_status import evaluate_campaign_status


SNAPSHOT_ROOT = Path("data") / "campaign_pages"
INDEX_FILE = Path("data") / "campaign_page_index.json"
REPORT_FILE = Path("data") / "campaign_status_report.json"


def main() -> int:
    snapshot_files = sorted(SNAPSHOT_ROOT.glob("**/*.json"))
    index_rows = []
    counts = Counter()

    for path in snapshot_files:
        data = json.loads(path.read_text(encoding="utf-8"))

        result = evaluate_campaign_status(
            text=(
                f"{data.get('title', '')} "
                f"{data.get('clean_text', '')}"
            ),
            listing_status=data.get(
                "listing_status",
                "unknown",
            ),
            listing_evidence=data.get(
                "listing_status_evidence",
                "",
            ),
        )

        data.update(
            {
                "campaign_start_date": result.start_date,
                "campaign_end_date": result.end_date,
                "current_status": result.status,
                "status_reason": result.reason,
                "status_evidence": result.evidence,
                "status_checked_at": result.checked_at,
            }
        )
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        counts[result.status] += 1
        index_row = dict(data)
        index_row.pop("raw_text", None)
        index_row.pop("clean_text", None)
        index_row["snapshot_file"] = path.as_posix()
        index_rows.append(index_row)

    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(
        json.dumps(index_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    REPORT_FILE.write_text(
        json.dumps(
            {
                "snapshot_count": len(snapshot_files),
                "status_counts": dict(sorted(counts.items())),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Kampanya durumları güncellendi.")
    print(f"Toplam kayıt: {len(snapshot_files)}")
    for status, count in sorted(counts.items()):
        print(f"  - {status}: {count}")
    print(f"İndeks: {INDEX_FILE}")
    print(f"Rapor: {REPORT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
