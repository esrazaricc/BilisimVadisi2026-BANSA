from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(script: str, *args: str) -> None:
    command = [
        sys.executable,
        "-X",
        "utf8",
        str(PROJECT_ROOT / "scripts" / script),
        *args,
    ]
    print("\n>", " ".join(command))
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def main() -> int:
    print("=" * 88)
    print("ALBARAKA ARAÇ FİNANSMANI — UÇTAN UCA ONARIM V1")
    print("=" * 88)

    # 1) Mevcut tarama JSON'una kaynak-evidence tabanlı override uygula,
    #    SQLite standart ürün + normalize kural tablolarını yenile.
    run("repair_albaraka_standard_products_v7.py")

    # 2) PostgreSQL source-of-truth okuma katmanını aynı verilerle eşitle.
    #    Bu adım eski product_pricing_tiers şemasına financing_amount da ekler.
    run("sync_albaraka_vehicle_to_postgresql.py")

    # 3) Son kalite kapısı.
    run("audit_albaraka_vehicle_postgresql.py")

    print("\nSONUÇ: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
