from __future__ import annotations

import argparse
import shutil
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path


BANK_NAME = "Hayat Finans"

OVERRIDES = {
    "https://hayatfinans.com.tr/hesaplar/avantajli-hesap": (
        "other_campaign",
        "Avantajlı katılma hesabına özel kâr paylaşım oranı kampanyası; mevcut sınıflandırma sözlüğünde yatırım/tasarruf kategorisi bulunmadığı için diğer kampanya olarak tutuldu.",
    ),
    "https://hayatfinans.com.tr/kampanyalar/arkadasini-getir-avantajli-hesap-ac-nakit-odul-kazan": (
        "new_customer_campaign",
        "Davet koduyla yeni müşteri kazanımı ve ilk Avantajlı Hesap açılışına bağlı nakit ödül kampanyası.",
    ),
    "https://hayatfinans.com.tr/kampanyalar/avantajli-hesap-musterilerine-ozel-fx-dar-makas-avantaji": (
        "other_campaign",
        "Avantajlı Hesap sahiplerine özel döviz işlemi/dar makas kampanyası; mevcut sınıflandırma sözlüğünde yatırım kategorisi bulunmadığı için diğer kampanya olarak tutuldu.",
    ),
    "https://hayatfinans.com.tr/kampanyalar/bana-bunu-al-is-ortagim-ile-troy-magaza-firsatlari": (
        "finance_campaign",
        "Bana Bunu Al finansmanı ile Troy mağazalarında üst limitli ve 3 aya varan alışveriş finansmanı kampanyası.",
    ),
    "https://hayatfinans.com.tr/kampanyalar/biz-kart-dijital-uyelikler-kampanyasi": (
        "discount_campaign",
        "Dijital üyelik ödemelerinde yüzde 75 nakit iade kampanyası.",
    ),
    "https://hayatfinans.com.tr/kampanyalar/biz-kart-ile-arkadasini-getir-kazan": (
        "new_customer_campaign",
        "Davet koduyla yeni müşteri ve Biz Kart başvurusu üzerinden nakit ödül kampanyası.",
    ),
    "https://hayatfinans.com.tr/kampanyalar/biz-kart-yemek-harcamasi-nakit-iade-kampanyasi": (
        "discount_campaign",
        "Mevcut veya yeni Biz Kart sahiplerinin yemek harcamalarına nakit iade kampanyası; yalnızca yeni müşterilere özel değildir.",
    ),
    "https://hayatfinans.com.tr/kampanyalar/hayat-finans-ile-gastroclub-ayricaliklari": (
        "discount_campaign",
        "GastroClub iş yerlerinde indirim ve ayrıcalık kampanyası.",
    ),
    "https://hayatfinans.com.tr/kampanyalar/hayatfinansla-islem-yaptikca-kazan": (
        "discount_campaign",
        "Bankacılık işlemleri sonucunda Hayat Pay cüzdanına nakit ödül/iade kazandıran kampanya.",
    ),
    "https://hayatfinans.com.tr/kampanyalar/hayatfx-ile-gumus-islemleri": (
        "other_campaign",
        "Gümüş alım-satım işlemlerine dar makas kampanyası; mevcut sınıflandırma sözlüğünde yatırım kategorisi bulunmadığı için diğer kampanya olarak tutuldu.",
    ),
    "https://hayatfinans.com.tr/kampanyalar/xiaomi-urunlerinde-finansman-avantaji": (
        "finance_campaign",
        "Bana Bunu Al finansmanı ile Xiaomi mağazalarında üst limitli ve 3 aya varan alışveriş finansmanı kampanyası.",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hayat Finans için doğrulanmış URL bazlı sınıflandırma düzeltmelerini uygular."
    )
    parser.add_argument(
        "--db",
        default="data/campaigns.db",
        help="SQLite veritabanı yolu.",
    )
    parser.add_argument(
        "--bank",
        default=BANK_NAME,
        help="Banka adı; güvenlik amacıyla yalnızca Hayat Finans kabul edilir.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.bank != BANK_NAME:
        raise SystemExit(
            f"Bu script yalnızca {BANK_NAME!r} için çalışır; verilen banka: {args.bank!r}"
        )

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"Veritabanı bulunamadı: {db_path}")

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"campaigns_before_hayat_classification_{stamp}.db"
    shutil.copy2(db_path, backup_path)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row

    try:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(live_campaigns)")
        }
        required = {
            "bank_name",
            "source_url",
            "record_kind",
            "campaign_category",
            "comparison_eligible",
            "classification_confidence",
            "classification_reason",
        }
        missing_columns = sorted(required - columns)
        if missing_columns:
            raise RuntimeError(
                "live_campaigns tablosunda gerekli sütunlar eksik: "
                + ", ".join(missing_columns)
            )

        existing = connection.execute(
            """
            SELECT id, title, source_url, campaign_category
            FROM live_campaigns
            WHERE bank_name = ?
            """,
            (BANK_NAME,),
        ).fetchall()
        existing_by_url = {
            str(row["source_url"] or "").rstrip("/"): row for row in existing
        }

        missing_urls = [
            url for url in OVERRIDES if url.rstrip("/") not in existing_by_url
        ]
        if missing_urls:
            raise RuntimeError(
                "Beklenen Hayat Finans kayıtları veritabanında bulunamadı:\n- "
                + "\n- ".join(missing_urls)
            )

        changed = 0
        unchanged = 0

        for url, (category, reason) in OVERRIDES.items():
            normalized_url = url.rstrip("/")
            row = existing_by_url[normalized_url]
            old_category = row["campaign_category"]

            cursor = connection.execute(
                """
                UPDATE live_campaigns
                SET
                    record_kind = 'campaign',
                    campaign_category = ?,
                    comparison_eligible = 1,
                    classification_confidence = 0.99,
                    classification_reason = ?
                WHERE bank_name = ?
                  AND RTRIM(source_url, '/') = ?
                """,
                (
                    category,
                    reason,
                    BANK_NAME,
                    normalized_url,
                ),
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"Tek kayıt güncellenmesi bekleniyordu, güncellenen={cursor.rowcount}: {url}"
                )

            if old_category == category:
                unchanged += 1
            else:
                changed += 1

        connection.commit()

        rows = connection.execute(
            """
            SELECT campaign_category, COUNT(*) AS count
            FROM live_campaigns
            WHERE bank_name = ?
              AND is_current = 1
              AND record_kind = 'campaign'
            GROUP BY campaign_category
            ORDER BY campaign_category
            """,
            (BANK_NAME,),
        ).fetchall()

        distribution = Counter(
            {row["campaign_category"]: row["count"] for row in rows}
        )

        print("=" * 88)
        print("HAYAT FİNANS SINIFLANDIRMA DÜZELTMELERİ UYGULANDI")
        print("=" * 88)
        print("Doğrulanmış URL:", len(OVERRIDES))
        print("Kategori değişen:", changed)
        print("Zaten doğru olan:", unchanged)
        print("Yedek:", backup_path)
        print()
        print("Güncel kategori dağılımı:")
        for category, count in sorted(distribution.items()):
            print(f"  - {category}: {count}")

        expected = {
            "discount_campaign": 4,
            "finance_campaign": 2,
            "new_customer_campaign": 2,
            "other_campaign": 3,
        }
        actual = dict(distribution)
        if actual != expected:
            raise RuntimeError(
                f"Beklenmeyen kategori dağılımı. Beklenen={expected}, mevcut={actual}"
            )

        print()
        print("HAYAT FİNANS SINIFLANDIRMA KONTROLÜ BAŞARILI")

    except Exception:
        connection.rollback()
        connection.close()
        shutil.copy2(backup_path, db_path)
        print(f"Hata nedeniyle veritabanı geri yüklendi: {backup_path}")
        raise
    else:
        connection.close()


if __name__ == "__main__":
    main()
