from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PROJECT_ROOT / "config" / "standard_product_sources.json"
TARGET_PATH = "/tr/bireysel/finansmanlar/ihtiyac/hac-ve-umre-finansmani"


def main() -> int:
    if not CONFIG.exists():
        raise SystemExit(f"Config bulunamadı: {CONFIG}")

    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    banks = data.get("banks")
    if not isinstance(banks, list):
        raise SystemExit("standard_product_sources.json içinde 'banks' listesi bulunamadı.")

    bank = next((b for b in banks if str(b.get("name", "")) == "Albaraka Türk"), None)
    if bank is None:
        raise SystemExit("Albaraka Türk config içinde bulunamadı.")

    if not bool(bank.get("seed_exact_paths", False)):
        bank["seed_exact_paths"] = True
        print("seed_exact_paths: true yapıldı.")

    rules = bank.get("family_rules")
    if not isinstance(rules, list):
        raise SystemExit("Albaraka family_rules bulunamadı.")

    ihtiyac = next(
        (r for r in rules if str(r.get("family_key", "")) == "ihtiyac_finansmani"),
        None,
    )
    if ihtiyac is None:
        raise SystemExit("Albaraka ihtiyac_finansmani family rule bulunamadı.")

    exact_paths = ihtiyac.setdefault("exact_paths", [])
    if not isinstance(exact_paths, list):
        raise SystemExit("ihtiyac_finansmani exact_paths liste değil.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = CONFIG.with_name(f"standard_product_sources_before_hac_umre_v10_{stamp}.json")
    shutil.copy2(CONFIG, backup)
    print(f"Config yedeği: {backup}")

    if TARGET_PATH in exact_paths:
        print("Hac ve Umre exact path zaten mevcut; değişiklik gerekmedi.")
    else:
        exact_paths.append(TARGET_PATH)
        CONFIG.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print("Hac ve Umre exact path eklendi:")
        print(" ", TARGET_PATH)

    # Son doğrulama
    reloaded = json.loads(CONFIG.read_text(encoding="utf-8"))
    bank2 = next(b for b in reloaded["banks"] if b.get("name") == "Albaraka Türk")
    rule2 = next(r for r in bank2["family_rules"] if r.get("family_key") == "ihtiyac_finansmani")
    ok = TARGET_PATH in rule2.get("exact_paths", []) and bool(bank2.get("seed_exact_paths", False))
    print("seed_exact_paths:", bank2.get("seed_exact_paths"))
    print("Hac ve Umre exact path mevcut:", TARGET_PATH in rule2.get("exact_paths", []))
    print("SONUÇ:", "OK" if ok else "KONTROL GEREKİYOR")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
