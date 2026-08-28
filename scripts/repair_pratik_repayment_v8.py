from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB = PROJECT_ROOT / "data" / "campaigns.db"
EXPECTED = "İlk taksit 2 ay sonraya otomatik atanır · İlk taksit toplamda 3 aya kadar ötelenebilir"


def main() -> int:
    if not DB.exists():
        raise FileNotFoundError(DB)

    backup_dir = PROJECT_ROOT / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"campaigns_before_pratik_repayment_v8_{stamp}.db"
    shutil.copy2(DB, backup)

    subprocess.run(
        [
            sys.executable, "-X", "utf8",
            str(PROJECT_ROOT / "scripts" / "sync_finance_rule_engine.py"),
            "--db", str(DB),
            "--bank", "Albaraka Türk",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    con = sqlite3.connect(DB)
    row = con.execute(
        """
        SELECT f.feature_value
        FROM live_product_features f
        JOIN live_standard_product_details d ON d.product_id=f.product_id
        JOIN live_campaigns c ON c.id=d.product_id
        WHERE c.is_current=1
          AND c.record_kind='standard_product'
          AND d.bank_name='Albaraka Türk'
          AND d.product_name='Pratik Finansman Kart'
          AND f.feature_key='repayment_structure'
        """
    ).fetchone()
    con.close()

    actual = str(row[0] if row else "")
    print("=" * 88)
    print("PRATİK FİNANSMAN KART — ÖDEME/KULLANIM FIX V8")
    print("=" * 88)
    print("DB yedeği:", backup.relative_to(PROJECT_ROOT))
    print("Ödeme / Kullanım:", actual or "YOK")
    if actual != EXPECTED:
        print("SONUÇ: KONTROL GEREKİYOR")
        return 1
    print("SONUÇ: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
