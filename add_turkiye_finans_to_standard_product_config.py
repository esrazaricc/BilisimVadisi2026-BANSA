from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "standard_product_sources.json"


TURKIYE_FINANS = {
    "name": "Türkiye Finans",
    "slug": "turkiye_finans",
    "base_url": "https://www.turkiyefinans.com.tr",
    "listing_pages": [
        {
            "url": (
                "https://www.turkiyefinans.com.tr/"
                "tr-tr/bireysel/ihtiyac-finansmani/"
                "sayfalar/ihtiyac-finansmani.aspx"
            ),
            "scope": "bireysel",
            "allowed_prefix": (
                "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/"
            ),
        },
        {
            "url": (
                "https://www.turkiyefinans.com.tr/"
                "tr-tr/bireysel/hizli-finansman/Sayfalar/default.aspx"
            ),
            "scope": "bireysel",
            "allowed_prefix": (
                "/tr-tr/bireysel/hizli-finansman/sayfalar/"
            ),
        },
        {
            "url": (
                "https://www.turkiyefinans.com.tr/"
                "tr-tr/bireysel/tasit-finansmani/"
                "sayfalar/tasit-finansmani.aspx"
            ),
            "scope": "bireysel",
            "allowed_prefix": (
                "/tr-tr/bireysel/tasit-finansmani/sayfalar/"
            ),
        },
        {
            "url": (
                "https://www.turkiyefinans.com.tr/"
                "tr-tr/bireysel/konut-finansmani/"
                "sayfalar/konut-finansmani.aspx"
            ),
            "scope": "bireysel",
            "allowed_prefix": (
                "/tr-tr/bireysel/konut-finansmani/sayfalar/"
            ),
        },
        {
            "url": (
                "https://www.turkiyefinans.com.tr/"
                "tr-tr/bireysel/Sayfalar/default.aspx"
            ),
            "scope": "bireysel",
            "allowed_prefix": "/tr-tr/bireysel/sayfalar/",
        },
        {
            "url": (
                "https://www.turkiyefinans.com.tr/"
                "tr-tr/kobi/kobi-kredileri/"
                "sayfalar/kobi-aninda-finansman.aspx"
            ),
            "scope": "ticari",
            "allowed_prefix": "/tr-tr/kobi/",
        },
        {
            "url": (
                "https://www.turkiyefinans.com.tr/"
                "tr-tr/ticari/nakdi-finansman/"
                "sayfalar/nakdi-finansman.aspx"
            ),
            "scope": "ticari",
            "allowed_prefix": (
                "/tr-tr/ticari/nakdi-finansman/sayfalar/"
            ),
        },
    ],
    "family_rules": [
        {
            "family_key": "ihtiyac_finansmani",
            "family_label": "İhtiyaç Finansmanı",
            "path_contains": [],
            "exact_paths": [
                "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/ihtiyac-finansmani.aspx",
                "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/dijital-ihtiyac-finansmani.aspx",
                "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/extra-limit.aspx",
                "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/saglik-finansmani.aspx",
                "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/yurt-ici-ve-yurt-disi-egitim-finansmani.aspx",
                "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/devre-tatil-finansmani.aspx",
                "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/devre-mulk-finansmani.aspx",
                "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/tekne-finansmani.aspx",
                "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/izoder-enerji-verimliligi-finansmani.aspx",
            ],
        },
        {
            "family_key": "alisveris_finansmani",
            "family_label": "Alışveriş Finansmanı",
            "path_contains": [],
            "exact_paths": [
                "/tr-tr/bireysel/hizli-finansman/sayfalar/trendyol-alisveris-finansmani.aspx",
            ],
        },
        {
            "family_key": "arac_finansmani",
            "family_label": "Araç Finansmanı",
            "path_contains": [],
            "exact_paths": [
                "/tr-tr/bireysel/tasit-finansmani/sayfalar/tasit-finansmani.aspx",
                "/tr-tr/bireysel/tasit-finansmani/sayfalar/dijital-tasit-finansmani.aspx",
                "/tr-tr/bireysel/tasit-finansmani/sayfalar/motosiklet-finansmani.aspx",
                "/tr-tr/bireysel/tasit-finansmani/sayfalar/taksitli-ticari-tasit-finansmani.aspx",
                "/tr-tr/bireysel/tasit-finansmani/sayfalar/ticari-hat-ticari-plaka-finansmani.aspx",
            ],
        },
        {
            "family_key": "konut_finansmani",
            "family_label": "Konut Finansmanı",
            "path_contains": [],
            "exact_paths": [
                "/tr-tr/bireysel/konut-finansmani/sayfalar/konut-finansmani.aspx",
                "/tr-tr/bireysel/konut-finansmani/sayfalar/hazir-evim-mortgage.aspx",
                "/tr-tr/bireysel/konut-finansmani/sayfalar/derneklere-vakiflara-sendikalara-mortgage.aspx",
            ],
        },
        {
            "family_key": "arsa_finansmani",
            "family_label": "Arsa Finansmanı",
            "path_contains": [],
            "exact_paths": [
                "/tr-tr/bireysel/sayfalar/arsa-finansmani.aspx",
                "/tr-tr/bireysel/sayfalar/iki-b-finansmani.aspx",
            ],
        },
        {
            "family_key": "isyeri_finansmani",
            "family_label": "İş Yeri Finansmanı",
            "path_contains": [],
            "exact_paths": [
                "/tr-tr/bireysel/sayfalar/isyeri-finansmani.aspx",
            ],
        },
        {
            "family_key": "ticari_finansman",
            "family_label": "Ticari Finansman",
            "path_contains": [],
            "exact_paths": [
                "/tr-tr/kobi/sayfalar/dijital-taksitli-ticari-finansman-destegi.aspx",
                "/tr-tr/kobi/kobi-kredileri/nakdi-krediler/sayfalar/faal-kart.aspx",
                "/tr-tr/kobi/kobi-kredileri/nakdi-krediler/sayfalar/ticari-tasit-kredisi.aspx",
                "/tr-tr/ticari/nakdi-finansman/sayfalar/finansman-destegi.aspx",
            ],
        },
    ],
    "exclude_exact_paths": [
        "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/arsiv.aspx",
        "/tr-tr/bireysel/tasit-finansmani/sayfalar/arsiv.aspx",
        "/tr-tr/bireysel/konut-finansmani/sayfalar/arsiv.aspx",
        "/tr-tr/bireysel/hizli-finansman/sayfalar/default.aspx",
        "/tr-tr/bireysel/sayfalar/default.aspx",
        "/tr-tr/kobi/kobi-kredileri/sayfalar/kobi-aninda-finansman.aspx",
        "/tr-tr/ticari/nakdi-finansman/sayfalar/nakdi-finansman.aspx",
    ],
}


def main() -> int:
    if not CONFIG.exists():
        raise SystemExit(f"Config bulunamadı: {CONFIG}")

    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    banks = data.get("banks", [])

    if not isinstance(banks, list):
        raise SystemExit("'banks' listesi bulunamadı.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = CONFIG.with_name(
        f"{CONFIG.stem}_before_turkiye_finans_{stamp}.json"
    )
    shutil.copy2(CONFIG, backup)

    output = []
    replaced = False

    for bank in banks:
        if (
            str(bank.get("name", "")).strip().casefold()
            == "türkiye finans".casefold()
        ):
            output.append(TURKIYE_FINANS)
            replaced = True
        else:
            output.append(bank)

    if not replaced:
        output.append(TURKIYE_FINANS)

    data["banks"] = output
    CONFIG.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 80)
    print("TÜRKİYE FİNANS CONFIG PATCH")
    print("=" * 80)
    print("Yedek:", backup)
    print(
        "İşlem:",
        "güncellendi" if replaced else "eklendi",
    )
    print()
    for bank in output:
        print("-", bank.get("name"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
