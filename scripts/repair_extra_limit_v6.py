from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = PROJECT_ROOT / "data" / "standard_products" / "turkiye_finans.json"
DB_PATH = PROJECT_ROOT / "data" / "campaigns.db"


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def main() -> int:
    if not JSON_PATH.exists():
        raise FileNotFoundError(f"Dosya bulunamadı: {JSON_PATH}")

    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    products = data.get("products", [])
    target = next(
        (row for row in products if clean(row.get("product_name")) == "eXtra Limit"),
        None,
    )
    if target is None:
        raise RuntimeError("Türkiye Finans eXtra Limit ürünü JSON içinde bulunamadı.")

    text = clean(target.get("clean_text"))
    if not re.search(
        r"maksimum\s+finansman\s+limiti\s+120\s*bin\s*TL",
        text,
        flags=re.IGNORECASE,
    ):
        raise RuntimeError("Kaynak metinde 120 bin TL maksimum limit doğrulanamadı.")

    if not re.search(
        r"Minimum\s+taksitlendirme\s+tutar[ıi]\s+100\s*TL",
        text,
        flags=re.IGNORECASE,
    ):
        raise RuntimeError("Kaynak metinde 100 TL minimum taksitlendirme tutarı doğrulanamadı.")

    target["minimum_financing_amount"] = None
    target["maximum_financing_amount"] = 120_000.0

    raw_rules = target.get("finance_rules_json")
    if isinstance(raw_rules, dict):
        rules = dict(raw_rules)
    else:
        try:
            rules = json.loads(raw_rules or "{}")
        except Exception:
            rules = {}

    for key in (
        "category_rules",
        "amount_maturity_rules",
        "pricing_tiers",
        "fee_rules",
        "offer_rules",
    ):
        rules.setdefault(key, [])

    parts = ["Minimum taksitlendirme tutarı 100 TL"]
    if re.search(
        r"Minimum\s+taksitlendirme\s+tutar[ıi][^.!?]{0,120}alt[ıi]nda"
        r"[^.!?]{0,180}peşin",
        text,
        flags=re.IGNORECASE,
    ):
        parts.append("100 TL altı harcamalar peşin yansıtılır")
    if re.search(
        r"taksitlerinizi\s+ödedikçe[^.!?]{0,140}limit\s+yeniden\s+kullan[ıi]ma\s+aç[ıi]l[ıi]r",
        text,
        flags=re.IGNORECASE,
    ):
        parts.append("Ödedikçe limit yeniden kullanıma açılır")

    rules["offer_rules"] = [
        rule
        for rule in rules["offer_rules"]
        if "Minimum taksitlendirme tutarı"
        not in str(rule.get("condition_text") or "")
    ]
    rules["offer_rules"].append(
        {
            "rule_type": "product_offer",
            "rule_label": "Ürüne Özel Finansman Koşulu",
            "min_amount": None,
            "max_amount": None,
            "min_inclusive": False,
            "max_inclusive": True,
            "max_installments": None,
            "max_maturity_months": None,
            "interest_free": False,
            "condition_text": " · ".join(parts),
            "source_text": "Minimum taksitlendirme tutarı 100 TL’dir.",
        }
    )
    target["finance_rules_json"] = json.dumps(
        rules, ensure_ascii=False, sort_keys=True
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = JSON_PATH.with_name(f"turkiye_finans_before_extra_limit_v5_{stamp}.json")
    shutil.copy2(JSON_PATH, backup)
    JSON_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("eXtra Limit JSON düzeltildi.")
    print("Maksimum finansman limiti: 120.000 TL")
    print("Minimum finansman tutarı: Kaynakta yayımlanmamış")
    print("Minimum taksitlendirme tutarı: 100 TL")
    print(f"JSON yedeği: {backup}")

    python = sys.executable
    subprocess.run(
        [
            python,
            "-X",
            "utf8",
            str(PROJECT_ROOT / "scripts" / "sync_standard_products_to_db.py"),
            "--input",
            str(JSON_PATH),
            "--db",
            str(DB_PATH),
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
            str(DB_PATH),
            "--bank",
            "Türkiye Finans",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
