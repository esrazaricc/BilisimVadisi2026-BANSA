from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.live_campaign_sync import (
    database_summary,
    sync_bank,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Keşfedilen kampanyaları campaigns.db içindeki "
            "canlı senkronizasyon tablolarına aktarır."
        )
    )
    parser.add_argument("--bank", required=True)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data") / "campaigns.db",
    )
    parser.add_argument(
        "--no-mark-removed",
        action="store_true",
        help=(
            "Yeni taramada bulunmayan eski kayıtları removed "
            "olarak işaretlemeyi kapatır."
        ),
    )
    args = parser.parse_args()

    result = sync_bank(
        bank_name=args.bank,
        db_path=args.db,
        mark_removed=not args.no_mark_removed,
    )

    print("\nVeritabanı senkronizasyonu tamamlandı.")
    print(f"Banka: {result.bank_name}")
    print(f"Keşfedilen: {result.discovered}")
    print(f"İşlenen: {result.processed}")
    print(f"Yeni: {result.created}")
    print(f"İçeriği değişen: {result.content_changed}")
    print(f"Durumu değişen: {result.status_changed}")
    print(f"Yeniden aktifleşen: {result.reactivated}")
    print(f"Kaldırılan: {result.removed}")
    print(f"Değişmeyen: {result.unchanged}")
    print(f"Detayı alınamayan: {result.unavailable}")
    print(f"Tarama hatası: {result.errors}")

    if result.removal_skipped:
        print(
            "Kaldırma kontrolü atlandı: "
            f"{result.removal_skip_reason}"
        )

    print("\nVeritabanı özeti:")
    print(
        json.dumps(
            database_summary(args.db, args.bank),
            ensure_ascii=False,
            indent=2,
        )
    )
    print("\nRapor: data\\live_db_sync_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
