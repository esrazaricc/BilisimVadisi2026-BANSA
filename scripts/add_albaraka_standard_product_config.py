from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


def find_config() -> Path:
    candidates = [
        Path.cwd() / "config" / "standard_product_sources.json",
        Path(__file__).resolve().parents[1]
        / "config"
        / "standard_product_sources.json",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise SystemExit(
        "Config bulunamadı: config\\standard_product_sources.json"
    )


ALBARAKA = {
    "name": "Albaraka Türk",
    "slug": "albaraka_turk",
    "base_url": "https://www.albaraka.com.tr",
    "seed_exact_paths": True,
    "listing_pages": [
        {
            "url": (
                "https://www.albaraka.com.tr/"
                "tr/bireysel/finansmanlar"
            ),
            "scope": "bireysel",
            "allowed_prefix": (
                "/tr/bireysel/finansmanlar/"
            ),
        },
        {
            "url": (
                "https://www.albaraka.com.tr/"
                "tr/kobi/finansmanlar/kobi-nakdi-finansman"
            ),
            "scope": "ticari",
            "allowed_prefix": (
                "/tr/kobi/finansmanlar/"
            ),
        },
        {
            "url": (
                "https://www.albaraka.com.tr/"
                "tr/kobi/finansmanlar/kobi-gayri-nakdi-finansman"
            ),
            "scope": "ticari",
            "allowed_prefix": (
                "/tr/kobi/finansmanlar/"
            ),
        },
        {
            "url": (
                "https://www.albaraka.com.tr/"
                "tr/kobi/finansmanlar"
            ),
            "scope": "ticari",
            "allowed_prefix": (
                "/tr/kobi/finansmanlar/"
            ),
        },
    ],
    "family_rules": [
        {
            "family_key": "konut_finansmani",
            "family_label": "Konut Finansmanı",
            "path_contains": [],
            "exact_paths": [
                (
                    "/tr/bireysel/finansmanlar/"
                    "konut-finansmani/konut-finansmani"
                ),
            ],
        },
        {
            "family_key": "arac_finansmani",
            "family_label": "Araç Finansmanı",
            "path_contains": [
                (
                    "/tr/bireysel/finansmanlar/"
                    "tasit-finansmani/"
                ),
            ],
            "exact_paths": [
                (
                    "/tr/bireysel/finansmanlar/"
                    "tasit-finansmani/tasit-finansmani"
                ),
                (
                    "/tr/bireysel/finansmanlar/"
                    "tasit-finansmani/togg-finansmani"
                ),
                (
                    "/tr/bireysel/finansmanlar/"
                    "tasit-finansmani/dijital-arac-finansmani"
                ),
                (
                    "/tr/bireysel/finansmanlar/"
                    "tasit-finansmani/deniz-tasitlari-finansmani"
                ),
                (
                    "/tr/bireysel/finansmanlar/"
                    "tasit-finansmani/tasit-kiralama-finansmani"
                ),
            ],
        },
        {
            "family_key": "isyeri_finansmani",
            "family_label": "İş Yeri Finansmanı",
            "path_contains": [],
            "exact_paths": [
                (
                    "/tr/bireysel/finansmanlar/"
                    "gayrimenkul-finansmani/is-yeri-finansman"
                ),
            ],
        },
        {
            "family_key": "arsa_finansmani",
            "family_label": "Arsa Finansmanı",
            "path_contains": [],
            "exact_paths": [
                (
                    "/tr/bireysel/finansmanlar/"
                    "gayrimenkul-finansmani/arsa-finansmani"
                ),
                (
                    "/tr/bireysel/finansmanlar/"
                    "gayrimenkul-finansmani/2b-arazi-finansmani"
                ),
            ],
        },
        {
            "family_key": "ihtiyac_finansmani",
            "family_label": "İhtiyaç Finansmanı",
            "path_contains": [
                "/tr/bireysel/finansmanlar/ihtiyac/",
            ],
            "exact_paths": [
                "/tr/bireysel/finansmanlar/ihtiyac",
                (
                    "/tr/bireysel/finansmanlar/"
                    "ihtiyac/pratik-finansman-kart"
                ),
                (
                    "/tr/bireysel/finansmanlar/"
                    "ihtiyac/sms-li-finansman"
                ),
                (
                    "/tr/bireysel/finansmanlar/"
                    "ihtiyac/subesiz-umre-finansmani"
                ),
                (
                    "/tr/bireysel/finansmanlar/"
                    "ihtiyac/jet-finansman"
                ),
                (
                    "/tr/bireysel/finansmanlar/"
                    "ihtiyac/motosiklet-atv-bisiklet"
                ),
                (
                    "/tr/bireysel/finansmanlar/"
                    "ihtiyac/egitim-finansmani"
                ),
                (
                    "/tr/bireysel/finansmanlar/"
                    "birikimlerinizi-koruyan-bes-teminatli-"
                    "finansman-albarakada"
                ),
            ],
        },
        {
            "family_key": "alisveris_finansmani",
            "family_label": "Alışveriş Finansmanı",
            "path_contains": [],
            "exact_paths": [
                (
                    "/tr/bireysel/finansmanlar/"
                    "bayide-finansman"
                ),
            ],
        },
        {
            "family_key": "ticari_finansman",
            "family_label": "Ticari Finansman",
            "path_contains": [
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-nakdi-finansman/"
                ),
            ],
            "exact_paths": [
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-nakdi-finansman/"
                    "kobi-finansman-destegi/is-yeri-finansmani"
                ),
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-nakdi-finansman/proje-finansmani"
                ),
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-nakdi-finansman/"
                    "dbs-fatura-teminatli-kredi"
                ),
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-nakdi-finansman/"
                    "kira-sertifikasi-teminatli-kredi"
                ),
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-nakdi-finansman/elus-teminatli-kredi"
                ),
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-nakdi-finansman/jet-ticari-finansman"
                ),
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-nakdi-finansman/pratik-kobi-kart"
                ),
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-nakdi-finansman/tedarikci-finansmani"
                ),
                (
                    "/tr/kobi/finansmanlar/"
                    "katilim-finans-kefalet-kfk"
                ),
                (
                    "/tr/kobi/finansmanlar/"
                    "bayide-finansman"
                ),
            ],
        },
        {
            "family_key": "gayri_nakdi_finansman",
            "family_label": "Gayri Nakdi Finansman",
            "path_contains": [
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-gayri-nakdi-finansman/"
                ),
            ],
            "exact_paths": [
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-gayri-nakdi-finansman/teminat-mektuplari"
                ),
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-gayri-nakdi-finansman/jet-teminat-mektubu"
                ),
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-gayri-nakdi-finansman/akreditifler"
                ),
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-gayri-nakdi-finansman/"
                    "kabul-aval-finansmanlari"
                ),
                (
                    "/tr/kobi/finansmanlar/"
                    "kobi-gayri-nakdi-finansman/referans-mektuplari"
                ),
            ],
        },
        {
            "family_key": "leasing",
            "family_label": "Leasing",
            "path_contains": [],
            "exact_paths": [
                (
                    "/tr/kobi/finansmanlar/"
                    "leasing-finansal-kiralama"
                ),
            ],
        },
    ],
    "embedded_product_pages": [
        {
            "url": (
                "https://www.albaraka.com.tr/"
                "tr/kobi/tarim-bankaciligi/tarim-finansmanlari"
            ),
            "scope": "ticari",
            "product_family_key": "tarim_finansmani",
            "product_family": "Tarım Finansmanı",
            "products": [
                {
                    "product_name": "Makine Ekipman Finansmanı",
                    "aliases": [
                        "Makine Ekipman",
                    ],
                },
                {
                    "product_name": "Bitkisel Üretim Finansmanı",
                    "aliases": [
                        "Bitkisel Üretim",
                    ],
                },
                {
                    "product_name": "Tarla Alım Finansmanı",
                    "aliases": [
                        "Tarla Alım",
                    ],
                },
                {
                    "product_name": "Seracılık Finansmanı",
                    "aliases": [
                        "Seracılık",
                    ],
                },
                {
                    "product_name": "Traktör Finansmanı",
                    "aliases": [
                        "Traktör",
                    ],
                },
                {
                    "product_name": "Biçerdöver Finansmanı",
                    "aliases": [
                        "Biçerdöver",
                    ],
                },
            ],
        },
    ],
    "exclude_exact_paths": [
        "/tr/bireysel/finansmanlar",
        "/tr/bireysel/finansmanlar/konut-finansmani",
        "/tr/bireysel/finansmanlar/tasit-finansmani",
        "/tr/bireysel/finansmanlar/gayrimenkul-finansmani",
        "/tr/kobi/finansmanlar",
        "/tr/kobi/finansmanlar/kobi-nakdi-finansman",
        "/tr/kobi/finansmanlar/kobi-gayri-nakdi-finansman",
        "/tr/kobi/tarim-bankaciligi/tarim-finansmanlari",
    ],
}


def main() -> int:
    config = find_config()

    data = json.loads(
        config.read_text(encoding="utf-8")
    )

    banks = data.get("banks", [])

    if not isinstance(banks, list):
        raise SystemExit(
            "Config içinde 'banks' listesi bulunamadı."
        )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup = config.with_name(
        f"{config.stem}_before_albaraka_{stamp}"
        f"{config.suffix}"
    )

    shutil.copy2(
        config,
        backup,
    )

    output = []
    replaced = False

    for bank in banks:
        if (
            str(
                bank.get("name") or ""
            ).strip().casefold()
            == "albaraka türk".casefold()
        ):
            output.append(ALBARAKA)
            replaced = True
        else:
            output.append(bank)

    if not replaced:
        output.append(ALBARAKA)

    data["banks"] = output

    config.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    family_count = len(
        ALBARAKA["family_rules"]
    )

    exact_count = sum(
        len(rule.get("exact_paths", []))
        for rule in ALBARAKA["family_rules"]
    )

    embedded_count = sum(
        len(page.get("products", []))
        for page in ALBARAKA[
            "embedded_product_pages"
        ]
    )

    print("=" * 88)
    print("ALBARAKA TÜRK STANDART ÜRÜN CONFIG")
    print("=" * 88)
    print("Config:", config)
    print("Yedek:", backup)
    print(
        "İşlem:",
        "Albaraka bloğu güncellendi."
        if replaced
        else "Albaraka bloğu eklendi.",
    )
    print("Aile kuralı:", family_count)
    print("Doğrudan exact path:", exact_count)
    print("Embedded tarım ürünü:", embedded_count)
    print()
    print("Bankalar:")
    for bank in output:
        print(" -", bank.get("name"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
