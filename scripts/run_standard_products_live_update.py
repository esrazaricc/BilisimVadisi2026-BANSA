from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def slug_for_bank(bank: dict) -> str:
    return str(
        bank.get("slug")
        or bank.get("name", "bank")
    ).strip()


def run(command: list[str]) -> None:
    print()
    print(">", " ".join(command))
    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bank",
        default=None,
        help=(
            "Yalnızca tek bankayı güncelle. "
            "Boş bırakılırsa config'teki tüm bankalar."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=(
            Path("config")
            / "standard_product_sources.json"
        ),
    )
    args = parser.parse_args()

    config_path = (
        PROJECT_ROOT / args.config
        if not args.config.is_absolute()
        else args.config
    )

    data = json.loads(
        config_path.read_text(encoding="utf-8")
    )
    banks = list(data.get("banks", []))

    if args.bank:
        wanted = args.bank.casefold()
        banks = [
            bank
            for bank in banks
            if str(bank.get("name", "")).casefold() == wanted
        ]

    if not banks:
        raise SystemExit("Güncellenecek banka bulunamadı.")

    python = sys.executable

    for bank in banks:
        bank_name = str(bank["name"])
        slug = slug_for_bank(bank)
        output = (
            Path("data")
            / "standard_products"
            / f"{slug}.json"
        )

        print()
        print("=" * 80)
        print("STANDART ÜRÜN CANLI GÜNCELLEME:", bank_name)
        print("=" * 80)

        run(
            [
                python,
                "-X",
                "utf8",
                str(
                    PROJECT_ROOT
                    / "scripts"
                    / "scan_standard_products.py"
                ),
                "--bank",
                bank_name,
                "--config",
                str(args.config),
                "--output",
                str(output),
            ]
        )

        run(
            [
                python,
                "-X",
                "utf8",
                str(
                    PROJECT_ROOT
                    / "scripts"
                    / "sync_standard_products_to_db.py"
                ),
                "--input",
                str(output),
            ]
        )

        run(
            [
                python,
                "-X",
                "utf8",
                str(
                    PROJECT_ROOT
                    / "scripts"
                    / "sync_finance_rule_engine.py"
                ),
                "--bank",
                bank_name,
            ]
        )

    print()
    print("=" * 80)
    print("STANDART ÜRÜN CANLI GÜNCELLEME TAMAMLANDI")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
