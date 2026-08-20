from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG = (
    PROJECT_ROOT
    / "config"
    / "standard_product_sources.json"
)


HAYAT_FINANS = {
    "name": "Hayat Finans",
    "slug": "hayat_finans",
    "base_url": "https://hayatfinans.com.tr",
    "listing_pages": [
        {
            "url": "https://hayatfinans.com.tr/krediler",
            "scope": "bireysel",
            "allowed_prefix": "/",
        },
        {
            "url": "https://hayatfinans.com.tr/finansmanlar-is",
            "scope": "ticari",
            "allowed_prefix": "/finansmanlar-is/",
        },
    ],
    "family_rules": [
        {
            "family_key": "alisveris_finansmani",
            "family_label": "Alışveriş Finansmanı",
            "path_contains": [],
            "exact_paths": [
                "/krediler/bana-bunu-al",
                "/finansmanlar/bana-bunu-al-is-ortagim",
            ],
        },
        {
            "family_key": "ihtiyac_finansmani",
            "family_label": "İhtiyaç Finansmanı",
            "path_contains": [],
            "exact_paths": [
                "/krediler/hayat-finans-egitim-finansmani-sistemi",
            ],
        },
        {
            "family_key": "ticari_finansman",
            "family_label": "Ticari Finansman",
            "path_contains": [],
            "exact_paths": [
                "/finansmanlar-is/mikro-finansman",
                "/finansmanlar-is/isletme-finansmani",
                "/finansmanlar-is/ticari-finansman",
            ],
        },
        {
            "family_key": "gayri_nakdi_finansman",
            "family_label": "Gayri Nakdi Finansman",
            "path_contains": [],
            "exact_paths": [
                "/finansmanlar-is/e-teminat-mektubu",
            ],
        },
    ],
    "exclude_exact_paths": [
        "/krediler",
        "/finansmanlar",
        "/finansmanlar-is",
    ],
}


def main() -> int:
    if not CONFIG.exists():
        raise SystemExit(
            f"Config bulunamadı: {CONFIG}"
        )

    data = json.loads(
        CONFIG.read_text(encoding="utf-8")
    )

    banks = data.get("banks")
    if not isinstance(banks, list):
        raise SystemExit(
            "Config içinde 'banks' listesi bulunamadı."
        )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    backup = CONFIG.with_name(
        f"{CONFIG.stem}_before_hayat_{timestamp}"
        f"{CONFIG.suffix}"
    )
    shutil.copy2(CONFIG, backup)

    replaced = False
    new_banks = []

    for bank in banks:
        if (
            str(bank.get("name", "")).strip().casefold()
            == "hayat finans".casefold()
        ):
            new_banks.append(HAYAT_FINANS)
            replaced = True
        else:
            new_banks.append(bank)

    if not replaced:
        new_banks.append(HAYAT_FINANS)

    data["banks"] = new_banks

    CONFIG.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 80)
    print("STANDARD PRODUCT CONFIG PATCH")
    print("=" * 80)
    print("Config :", CONFIG)
    print("Yedek  :", backup)
    print(
        "İşlem  :",
        (
            "Hayat Finans güncellendi"
            if replaced
            else "Hayat Finans eklendi"
        ),
    )
    print()
    print("BANKALAR")
    for bank in data["banks"]:
        print("-", bank.get("name"))

    found = any(
        str(bank.get("name", "")).strip().casefold()
        == "hayat finans"
        for bank in data["banks"]
    )

    print()
    print(
        "Hayat Finans doğrulama:",
        "OK" if found else "HATA",
    )

    return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
