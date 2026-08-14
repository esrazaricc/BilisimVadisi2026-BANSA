from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG = PROJECT_ROOT / "config" / "banks.json"
BANK = "Türkiye Emlak Katılım"


def main() -> int:
    if not CONFIG.exists():
        raise FileNotFoundError(CONFIG)

    banks = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(banks, list):
        raise RuntimeError("banks.json kökü liste değil.")

    matches = [bank for bank in banks if bank.get("name") == BANK]
    if len(matches) != 1:
        raise RuntimeError(
            f"{BANK} config kaydı tam 1 olmalı; bulunan={len(matches)}"
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = (
        PROJECT_ROOT
        / "config"
        / "backups"
        / f"banks_before_emlak_listing_status_{stamp}.json"
    )
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CONFIG, backup)

    bank = matches[0]
    bank["listing_presence_implies_active"] = True

    # İlk DB entegrasyonu bitmeden all-bank canlı taramaya açmıyoruz.
    bank["scanner_ready"] = False

    CONFIG.write_text(
        json.dumps(banks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Türkiye Emlak Katılım liste-status ayarı yapıldı.")
    print("listing_presence_implies_active: true")
    print("scanner_ready: false")
    print("Yedek:", backup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
