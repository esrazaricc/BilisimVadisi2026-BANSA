from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


CONFIG = Path("config") / "standard_product_sources.json"


ACTIVE_FAMILIES = [
    {
        "family_key": "ihtiyac_finansmani",
        "family_label": "İhtiyaç Finansmanı",
        "path_contains": [],
        "exact_paths": [
            "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/ihtiyac-finansmani.aspx",
            "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/dijital-ihtiyac-finansmani.aspx",
            "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/extra-limit.aspx",
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
            "/tr-tr/bireysel/tasit-finansmani/sayfalar/ticari-hat-ticari-plaka-finansmani.aspx",
            "/tr-tr/bireysel/tasit-finansmani/sayfalar/taksitli-ticari-tasit-finansmani.aspx",
        ],
    },
    {
        "family_key": "konut_finansmani",
        "family_label": "Konut Finansmanı",
        "path_contains": [],
        "exact_paths": [
            "/tr-tr/bireysel/konut-finansmani/sayfalar/konut-finansmani.aspx",
        ],
    },
    {
        "family_key": "arsa_finansmani",
        "family_label": "Arsa Finansmanı",
        "path_contains": [],
        "exact_paths": [
            "/tr-tr/bireysel/sayfalar/arsa-finansmani.aspx",
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
            "/tr-tr/ticari/nakdi-finansman/sayfalar/finansman-destegi.aspx",
            "/tr-tr/ticari/nakdi-finansman/sayfalar/kgf-destekli-krediler.aspx",
            "/tr-tr/ticari/nakdi-finansman/sayfalar/esnek-destek-finansmani.aspx",
            "/tr-tr/ticari/nakdi-finansman/sayfalar/taksitli-ticari-finansman.aspx",
        ],
    },
    {
        "family_key": "leasing",
        "family_label": "Leasing",
        "path_contains": [],
        "exact_paths": [
            "/tr-tr/ticari/nakdi-finansman/sayfalar/leasing.aspx",
        ],
    },
    {
        "family_key": "tarim_finansmani",
        "family_label": "Tarım Finansmanı",
        "path_contains": [],
        "exact_paths": [
            "/tr-tr/ticari/nakdi-finansman/sayfalar/elektronik-urun-senedi.aspx",
        ],
    },
]


REQUIRED_LISTING_PAGES = [
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
            "tr-tr/kobi/Sayfalar/"
            "dijital-taksitli-ticari-finansman-destegi.aspx"
        ),
        "scope": "ticari",
        "allowed_prefix": "/tr-tr/kobi/",
    },
    {
        "url": (
            "https://www.turkiyefinans.com.tr/"
            "tr-tr/ticari/nakdi-finansman/"
            "Sayfalar/nakdi-finansman.aspx"
        ),
        "scope": "ticari",
        "allowed_prefix": (
            "/tr-tr/ticari/nakdi-finansman/sayfalar/"
        ),
    },
]


EXCLUDES = [
    "/tr-tr/bireysel/ihtiyac-finansmani/sayfalar/arsiv.aspx",
    "/tr-tr/bireysel/tasit-finansmani/sayfalar/arsiv.aspx",
    "/tr-tr/bireysel/konut-finansmani/sayfalar/arsiv.aspx",
    "/tr-tr/bireysel/hizli-finansman/sayfalar/default.aspx",
    "/tr-tr/bireysel/sayfalar/default.aspx",
    "/tr-tr/ticari/nakdi-finansman/sayfalar/nakdi-finansman.aspx",

    # Site haritasında aktif görünse de kamuya açık URL
    # şu anda hatalı redirect veriyor; tarama hatasına
    # dönüştürmemek için şimdilik hariç.
    "/tr-tr/ticari/nakdi-finansman/sayfalar/kar-zarar-ortakligi.aspx",
]


def norm_path(value: str) -> str:
    return str(value or "").strip().casefold()


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

    bank = next(
        (
            item
            for item in banks
            if str(item.get("name") or "").strip().casefold()
            == "türkiye finans".casefold()
        ),
        None,
    )

    if bank is None:
        raise SystemExit(
            "Türkiye Finans config bloğu bulunamadı."
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = CONFIG.with_name(
        f"{CONFIG.stem}_before_turkiye_finans_catalog_{stamp}{CONFIG.suffix}"
    )
    shutil.copy2(CONFIG, backup)

    old_family_paths = {
        norm_path(path)
        for family in bank.get("family_rules", [])
        for path in family.get("exact_paths", [])
    }

    new_family_paths = {
        norm_path(path)
        for family in ACTIVE_FAMILIES
        for path in family.get("exact_paths", [])
    }

    removed = sorted(
        old_family_paths - new_family_paths
    )
    added = sorted(
        new_family_paths - old_family_paths
    )

    bank["listing_pages"] = REQUIRED_LISTING_PAGES
    bank["family_rules"] = ACTIVE_FAMILIES
    bank["exclude_exact_paths"] = EXCLUDES

    CONFIG.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("=" * 100)
    print("TÜRKİYE FİNANS — AKTİF KATALOG CONFIG GÜNCELLEMESİ")
    print("=" * 100)
    print("Yedek :", backup)
    print("Config:", CONFIG)
    print()

    print("Yeni eklenen exact path:", len(added))
    for path in added:
        print("  +", path)

    print()
    print("Katalogdan çıkarılan eski exact path:", len(removed))
    for path in removed:
        print("  -", path)

    print()
    print("Aktif family sayısı:", len(ACTIVE_FAMILIES))
    print(
        "Aktif exact path sayısı:",
        sum(
            len(family["exact_paths"])
            for family in ACTIVE_FAMILIES
        ),
    )

    print()
    print(
        "NOT: Gayri Nakdi Finansman'ın dört alt ürünü "
        "tek resmî sayfada bulunduğu için bu patch'te "
        "henüz ayrı sanal ürünlere bölünmedi."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
