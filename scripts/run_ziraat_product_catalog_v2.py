from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run(label: str, *args: str) -> None:
    print("\n" + "=" * 80)
    print(label)
    print("=" * 80)
    command = [PYTHON, "-X", "utf8", *args]
    print(">", " ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    run(
        "[1/4] Ziraat Katılım resmî ürün kataloğu canlı taranıyor",
        str(ROOT / "scripts" / "run_standard_products_live_update.py"),
        "--bank", "Ziraat Katılım",
    )
    run(
        "[2/4] Canonical finansman doğruluk kuralları uygulanıyor",
        str(ROOT / "scripts" / "apply_finance_data_accuracy_v2.py"),
    )
    run(
        "[3/4] Eski generic Ziraat ürün başlıkları SQLite'ta pasife alınıyor",
        str(ROOT / "scripts" / "cleanup_ziraat_generic_products_v2.py"),
        "--sqlite-only",
    )
    run(
        "[4/4] Ziraat finansman rule/evidence tabloları senkronize ediliyor",
        str(ROOT / "scripts" / "sync_finance_rule_engine.py"),
        "--bank", "Ziraat Katılım",
    )
    print("\nZiraat Katılım Ürün Kataloğu V2 SQLite hazırlığı tamamlandı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
