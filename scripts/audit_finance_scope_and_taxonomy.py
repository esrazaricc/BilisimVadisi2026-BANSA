from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.finance_taxonomy import (
    category_label,
    classify_finance_category,
    scope_label,
)


def load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def main() -> int:
    scope = load_json("config/bddk_participation_bank_scope.json")
    banks_cfg = load_json("config/banks.json")
    sources = load_json("config/standard_product_sources.json")

    expected = [row["name"] for row in scope["banks"]]
    configured = [row["name"] for row in banks_cfg]
    integrated = [row["name"] for row in sources.get("banks", [])]

    print("=" * 88)
    print("BANSA — BDDK KATILIM BANKASI KAPSAMI / FİNANSMAN TAKSONOMİ AUDIT")
    print("=" * 88)
    print(f"BDDK kapsam bankası : {len(expected)}")
    print(f"banks.json          : {len(configured)}")
    print(f"standart ürün entegre: {len(integrated)}")

    missing_bank_cfg = sorted(set(expected) - set(configured))
    extra_bank_cfg = sorted(set(configured) - set(expected))
    pending_integration = [name for name in expected if name not in integrated]

    print("\n[1] KAPSAM")
    print("PASS" if not missing_bank_cfg and not extra_bank_cfg else "FAIL")
    if missing_bank_cfg:
        print("banks.json eksik:", ", ".join(missing_bank_cfg))
    if extra_bank_cfg:
        print("banks.json kapsam dışı:", ", ".join(extra_bank_cfg))

    print("\n[2] STANDART FİNANSMAN ENTEGRASYONU")
    for name in expected:
        print(f"{'OK     ' if name in integrated else 'BEKLİYOR'}  {name}")

    print("\n[3] SONRAKİ ENTEGRASYON KUYRUĞU")
    for index, name in enumerate(pending_integration, start=1):
        print(f"{index}. {name}")

    print("\n[4] BANSA KARŞILAŞTIRMA HİYERARŞİSİ")
    print(scope_label("bireysel"))
    for key in (
        "konut_finansmani",
        "tasit_finansmani",
        "ihtiyac_finansmani",
        "gayrimenkul_finansmani",
        "alisveris_finansmani",
        "diger_bireysel_finansman",
    ):
        print("  -", category_label(key))

    print(scope_label("ticari"))
    for key in (
        "ticari_finansman",
        "gayri_nakdi_finansman",
        "tarim_finansmani",
        "leasing_finansal_kiralama",
        "diger_ticari_finansman",
    ):
        print("  -", category_label(key))

    # Lightweight regression examples: no external network, no guessed data.
    checks = [
        ("Konut Finansmanı", "İlk Evim", "bireysel", "konut_finansmani"),
        ("Arsa Finansmanı", "Arsa", "bireysel", "gayrimenkul_finansmani"),
        ("İş Yeri Finansmanı", "İş Yeri", "bireysel", "gayrimenkul_finansmani"),
        ("Alışveriş Finansmanı", "Bana Bunu Al", "bireysel", "alisveris_finansmani"),
        ("Ticari Finansman", "İşletme", "ticari", "ticari_finansman"),
        ("Gayri Nakdi Finansman", "Teminat Mektubu", "ticari", "gayri_nakdi_finansman"),
        ("Tarım Finansmanı", "Tarım", "ticari", "tarim_finansmani"),
        ("Leasing", "Finansal Kiralama", "ticari", "leasing_finansal_kiralama"),
    ]
    failed = []
    for family, product, scope_value, expected_key in checks:
        actual = classify_finance_category(family, product, scope_value)
        if actual != expected_key:
            failed.append((family, actual, expected_key))

    print("\n[5] TAKSONOMİ REGRESYON")
    print("PASS" if not failed else "FAIL")
    for row in failed:
        print("-", row)

    # Missing integrations are expected at this phase and do not make the
    # taxonomy patch fail. Scope/taxonomy inconsistencies do.
    return 1 if missing_bank_cfg or extra_bank_cfg or failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
