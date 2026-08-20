from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG = PROJECT_ROOT / "config" / "banks.json"
BANK = "Türkiye Emlak Katılım"


def is_finance_product_source(source: dict) -> bool:
    """
    Ayrı finansman ÜRÜN kataloğunu tespit eder.
    Finansmanla ilgili kampanya başlıklarını etkilemez.
    """
    source_group = str(source.get("source_group") or "").casefold()
    url = str(source.get("url") or "").casefold()

    return (
        "finansman ürün" in source_group
        or "finansman urun" in source_group
        or "/finansmanlar" in url
    )


def main() -> int:
    if not CONFIG.exists():
        raise FileNotFoundError(CONFIG)

    banks = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(banks, list):
        raise RuntimeError("banks.json kökü liste değil.")

    matches = [b for b in banks if b.get("name") == BANK]
    if len(matches) != 1:
        raise RuntimeError(
            f"{BANK} config kaydı tam 1 olmalı; bulunan={len(matches)}"
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = (
        PROJECT_ROOT
        / "config"
        / "backups"
        / f"banks_before_emlak_campaign_only_live_{stamp}.json"
    )
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CONFIG, backup)

    bank = matches[0]

    sources = bank.get("campaign_sources")
    removed_sources = []

    if isinstance(sources, list):
        kept_sources = []

        for source in sources:
            if not isinstance(source, dict):
                continue

            if is_finance_product_source(source):
                removed_sources.append(
                    {
                        "source_group": source.get("source_group"),
                        "url": source.get("url"),
                    }
                )
                continue

            # Kampanya kaynağı, finansman ürün detaylarına taşmasın.
            excludes = list(source.get("exclude_paths") or [])
            for path in (
                "/tr/bireysel/finansmanlar/",
                "/tr/kurumsal/finansmanlar/",
            ):
                if path not in excludes:
                    excludes.append(path)

            source["exclude_paths"] = excludes
            source["listing_presence_implies_active"] = True
            kept_sources.append(source)

        bank["campaign_sources"] = kept_sources

    # Banka seviyesinde de ürün kataloglarını dışarıda tut.
    excludes = list(bank.get("exclude_paths") or [])
    for path in (
        "/tr/bireysel/finansmanlar/",
        "/tr/kurumsal/finansmanlar/",
    ):
        if path not in excludes:
            excludes.append(path)
    bank["exclude_paths"] = excludes

    # Sadece kampanya taraması canlı.
    bank["scanner_ready"] = True

    CONFIG.write_text(
        json.dumps(banks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=" * 78)
    print("TÜRKİYE EMLAK KATILIM — KAMPANYA CANLI TARAMASI")
    print("=" * 78)

    if removed_sources:
        print("Ayrı finansman ÜRÜN kaynakları config'ten çıkarıldı:")
        for item in removed_sources:
            print("-", item["source_group"])
            print(" ", item["url"])
    else:
        print("Ayrı finansman ürün kaynağı bulunmadı.")

    print()
    print("Finansmanla ilgili KAMPANYALAR korunur.")
    print("Ayrı finansman ÜRÜN kataloğu taranmaz.")
    print("scanner_ready: true")
    print("Yedek:", backup)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
