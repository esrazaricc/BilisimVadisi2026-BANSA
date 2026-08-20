from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config" / "banks.json"

BANK_NAME = "T.O.M. Katılım"
HADI_LISTING = "https://tombankhadi.com/hadi-kazan/kampanyalar"


def main() -> int:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Config bulunamadı: {CONFIG_PATH}\n"
            "Bu dosyayı proje ana klasörüne koyup çalıştır."
        )

    banks = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    matches = [
        bank for bank in banks
        if bank.get("name") == BANK_NAME
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"{BANK_NAME} config kaydı tam 1 adet olmalı; bulunan={len(matches)}"
        )

    bank = matches[0]

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = PROJECT_ROOT / "config" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"banks_before_tom_discovery_{stamp}.json"
    shutil.copy2(CONFIG_PATH, backup_path)

    # Bankanın yasal ana sitesi tombank.com.tr olarak kalır.
    # Kampanya kaynağı ise TOM Bank'ın kendi sitesinden yönlendirdiği
    # resmî Hadi kampanya platformudur.
    bank["campaign_pages"] = [HADI_LISTING]
    bank["detail_paths"] = ["/kampanyalar/"]
    bank["discovery_mode"] = "detail_links"
    bank["source_status"] = "verified_official_hadi_campaign_source"

    # İlk keşif doğrulanmadan tüm-bankalar otomasyonuna dahil etmiyoruz.
    bank["scanner_ready"] = False

    bank["campaign_sources"] = [
        {
            "source_group": "T.O.M. Katılım / TOM Bank Hadi Kampanyaları",
            "url": HADI_LISTING,
            "base_url": "https://tombankhadi.com",
            "detail_paths": ["/kampanyalar/"],
            "exclude_exact_paths": [
                "/hadi-kazan/kampanyalar",
                "/kampanyalar",
            ],
            "render_mode": "selenium",
            "load_more_terms": [
                "Daha fazla göster",
                "Daha Fazla Göster",
                "Daha fazla",
                "Daha Fazla",
            ],
            "cookie_accept_terms": [
                "Tümünü Kabul Et",
                "Kabul Et",
                "Onayla",
            ],
            "maximum_load_more_clicks": 30,
        }
    ]

    CONFIG_PATH.write_text(
        json.dumps(
            banks,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print("=" * 78)
    print("T.O.M. KATILIM KAMPANYA KAYNAĞI HAZIRLANDI")
    print("=" * 78)
    print("Banka:", BANK_NAME)
    print("Kaynak:", HADI_LISTING)
    print("Detay yolu: /kampanyalar/")
    print("Yöntem: Selenium + Daha fazla göster")
    print("scanner_ready: false")
    print("Yedek:", backup_path)
    print()
    print("Bu işlem henüz DB'ye kampanya eklemedi.")
    print("Sıradaki adım yalnızca kampanya bağlantılarını keşfetmektir.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
