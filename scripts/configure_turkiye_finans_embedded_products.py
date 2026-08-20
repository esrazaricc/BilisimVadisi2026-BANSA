from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


CONFIG = (
    Path("config")
    / "standard_product_sources.json"
)


TF_PAGE = {
    "url": (
        "https://www.turkiyefinans.com.tr/"
        "tr-tr/ticari/gayri-nakdi-finansman/"
        "sayfalar/default.aspx"
    ),
    "scope": "ticari",
    "product_family_key": "gayri_nakdi_finansman",
    "product_family": "Gayri Nakdi Finansman",
    "products": [
        {
            "product_name": "Teminat Mektubu",
        },
        {
            "product_name": "Elektronik Teminat Mektubu",
        },
        {
            "product_name": "Kabul-Aval Kredileri",
            "aliases": [
                "Kabul Aval Kredileri",
            ],
        },
        {
            "product_name": "Referans Mektubu",
        },
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

    target = next(
        (
            bank
            for bank in data.get("banks", [])
            if str(
                bank.get("name") or ""
            ).strip().casefold()
            == "türkiye finans".casefold()
        ),
        None,
    )

    if target is None:
        raise SystemExit(
            "Türkiye Finans config bloğu bulunamadı."
        )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup = CONFIG.with_name(
        f"{CONFIG.stem}_before_embedded_{stamp}"
        f"{CONFIG.suffix}"
    )

    shutil.copy2(CONFIG, backup)

    pages = target.setdefault(
        "embedded_product_pages",
        [],
    )

    page_url_key = TF_PAGE["url"].casefold()

    pages[:] = [
        page
        for page in pages
        if str(
            page.get("url") or ""
        ).casefold()
        != page_url_key
    ]

    pages.append(TF_PAGE)

    CONFIG.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print("=" * 90)
    print("ÇOK ÜRÜNLÜ SAYFA CONFIG")
    print("=" * 90)
    print("Yedek:", backup)
    print(
        "Türkiye Finans Gayri Nakdi Finansman "
        "4 alt ürün olarak tanımlandı."
    )
    print()
    for item in TF_PAGE["products"]:
        print(
            " -",
            item["product_name"],
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
