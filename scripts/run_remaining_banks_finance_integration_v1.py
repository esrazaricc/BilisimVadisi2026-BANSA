from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANKS = (
    "Adil Katılım",
    "T.O.M. Katılım",
    "Türkiye Emlak Katılım",
    "Vakıf Katılım",
    "Ziraat Katılım",
)


def run(args: list[str]) -> None:
    print("\n>", " ".join(args))
    proc = subprocess.run(args, cwd=ROOT)
    if proc.returncode:
        raise SystemExit(proc.returncode)


def main() -> int:
    python = sys.executable
    for index, bank in enumerate(BANKS, start=1):
        print("\n" + "=" * 80)
        print(f"[{index}/{len(BANKS)}] {bank} standart finansman entegrasyonu")
        print("=" * 80)
        run([
            python, "-X", "utf8",
            str(ROOT / "scripts" / "run_standard_products_live_update.py"),
            "--bank", bank,
        ])
    print("\nKalan 5 bankanın canlı standart finansman taraması tamamlandı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
