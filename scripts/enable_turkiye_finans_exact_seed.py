from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


CONFIG = Path("config") / "standard_product_sources.json"


def main() -> int:
    if not CONFIG.exists():
        raise SystemExit(
            f"Config bulunamadı: {CONFIG}"
        )

    data = json.loads(
        CONFIG.read_text(encoding="utf-8")
    )

    banks = data.get("banks", [])
    target = next(
        (
            bank
            for bank in banks
            if str(bank.get("name") or "").strip().casefold()
            == "türkiye finans".casefold()
        ),
        None,
    )

    if target is None:
        raise SystemExit(
            "Türkiye Finans config bloğu bulunamadı."
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = CONFIG.with_name(
        f"{CONFIG.stem}_before_exact_seed_{stamp}{CONFIG.suffix}"
    )
    shutil.copy2(CONFIG, backup)

    target["seed_exact_paths"] = True

    CONFIG.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    expected = sum(
        len(rule.get("exact_paths", []))
        for rule in target.get("family_rules", [])
    )

    print("=" * 90)
    print("TÜRKİYE FİNANS — EXACT PATH DISCOVERY SEED")
    print("=" * 90)
    print("Yedek:", backup)
    print("seed_exact_paths: True")
    print("Config exact path sayısı:", expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
