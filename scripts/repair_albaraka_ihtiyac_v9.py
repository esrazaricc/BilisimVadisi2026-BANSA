from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def main() -> int:
    cmd = [
        PYTHON,
        "-X",
        "utf8",
        str(PROJECT_ROOT / "scripts" / "sync_finance_rule_engine.py"),
        "--db",
        str(PROJECT_ROOT / "data" / "campaigns.db"),
        "--bank",
        "Albaraka Türk",
    ]
    print("Albaraka Türk İhtiyaç Finansmanı nitel metrikleri yeniden senkronize ediliyor...")
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)
    print("SONUÇ: SENKRON TAMAMLANDI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
