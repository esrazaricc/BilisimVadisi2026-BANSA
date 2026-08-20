from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run(args: list[str], label: str) -> None:
    print("\n" + "=" * 80)
    print(label)
    print("=" * 80)
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


run(
    [PYTHON, "-X", "utf8", "-m", "pytest", "-q", "tests/test_tom_product_identity_hotfix_v1.py"],
    "[1/3] TOM ürün kimliği / URL regresyon testleri",
)
run(
    [PYTHON, "-X", "utf8", "scripts/run_standard_products_live_update.py", "--bank", "T.O.M. Katılım"],
    "[2/3] T.O.M. Katılım canlı standart finansman güncellemesi",
)
run(
    [PYTHON, "-X", "utf8", "scripts/audit_remaining_banks_finance_integration_v1.py"],
    "[3/3] Kalan bankalar SQLite audit",
)
print("\nPASS - TOM ürün kimliği ve ürün-özel limit hotfix tamamlandı.")
