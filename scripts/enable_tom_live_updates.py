from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PROJECT_ROOT / "config" / "banks.json"
BANK = "T.O.M. Katılım"


def main() -> int:
    banks = json.loads(CONFIG.read_text(encoding="utf-8"))
    found = False

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = (
        PROJECT_ROOT
        / "config"
        / "backups"
        / f"banks_before_tom_live_enable_{stamp}.json"
    )
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CONFIG, backup)

    for bank in banks:
        if bank.get("name") == BANK:
            bank["scanner_ready"] = True
            found = True
            break

    if not found:
        raise RuntimeError(f"{BANK} config kaydı bulunamadı.")

    CONFIG.write_text(
        json.dumps(banks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("T.O.M. Katılım scanner_ready=true yapıldı.")
    print("Bundan sonra run_all_banks_live_update.py bankayı otomatik seçer.")
    print("Config yedeği:", backup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
