from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.albaraka_standard_product_overrides import (
    apply_albaraka_standard_product_overrides,
)

SCAN_FILE = PROJECT_ROOT / "data" / "standard_products" / "albaraka_turk.json"
DB_FILE = PROJECT_ROOT / "data" / "campaigns.db"


def main() -> int:
    if not SCAN_FILE.exists():
        raise FileNotFoundError(SCAN_FILE)
    if not DB_FILE.exists():
        raise FileNotFoundError(DB_FILE)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = PROJECT_ROOT / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    json_backup = backup_dir / f"albaraka_turk_before_metric_repair_{stamp}.json"
    shutil.copy2(SCAN_FILE, json_backup)

    payload = json.loads(SCAN_FILE.read_text(encoding="utf-8"))
    products = payload.get("products") or []
    if not products:
        raise RuntimeError("Güvenlik kontrolü: Albaraka standart ürün JSON'u boş.")
    if len(products) < 40:
        raise RuntimeError(
            f"Güvenlik kontrolü: En az 40 Albaraka ürünü bekleniyordu, {len(products)} bulundu."
        )

    repaired = [
        apply_albaraka_standard_product_overrides(dict(row))
        for row in products
    ]
    payload["products"] = repaired
    payload["product_count"] = len(repaired)
    SCAN_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    python = sys.executable
    subprocess.run(
        [
            python,
            "-X",
            "utf8",
            str(PROJECT_ROOT / "scripts" / "sync_standard_products_to_db.py"),
            "--input",
            str(SCAN_FILE),
            "--db",
            str(DB_FILE),
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )
    subprocess.run(
        [
            python,
            "-X",
            "utf8",
            str(PROJECT_ROOT / "scripts" / "sync_finance_rule_engine.py"),
            "--db",
            str(DB_FILE),
            "--bank",
            "Albaraka Türk",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    print("=" * 80)
    print("ALBARAKA METRİK ONARIMI TAMAMLANDI")
    print("=" * 80)
    print("Ürün:", len(repaired))
    print("JSON yedeği:", json_backup.relative_to(PROJECT_ROOT))
    print("DB:", DB_FILE.relative_to(PROJECT_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
