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

    matches = [b for b in banks if b.get("name") == BANK]
    if len(matches) != 1:
        raise RuntimeError(
            f"{BANK} config kaydı tam 1 olmalı; bulunan={len(matches)}"
        )

    bank = matches[0]

    # Güvenlik: finansman kaynaklarını bu aşamada canlı sisteme sokmayız.
    # Kullanıcı kapsamı yalnızca kampanyalar olarak belirledi.
    sources = bank.get("campaign_sources")
    if isinstance(sources, list):
        finance_sources = [
            src for src in sources
            if isinstance(src, dict)
            and (
                "finansman" in str(src.get("source_group") or "").casefold()
                or "/finansmanlar" in str(src.get("url") or "").casefold()
            )
        ]
        if finance_sources:
            raise RuntimeError(
                "Config içinde Emlak Katılım finansman kaynağı bulundu. "
                "Canlı kampanya taramasını açmadan önce bu kaynakları kaldırın."
            )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = (
        PROJECT_ROOT
        / "config"
        / "backups"
        / f"banks_before_emlak_live_enable_{stamp}.json"
    )
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CONFIG, backup)

    bank["scanner_ready"] = True

    CONFIG.write_text(
        json.dumps(banks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Türkiye Emlak Katılım canlı kampanya taramasına açıldı.")
    print("scanner_ready: true")
    print("Kapsam: kampanyalar")
    print("Yedek:", backup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
