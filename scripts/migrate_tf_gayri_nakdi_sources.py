from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin


CONFIG = Path("config") / "standard_product_sources.json"
DB = Path("data") / "campaigns.db"

BANK_NAME = "Türkiye Finans"

COMMON_EMBEDDED_URL = (
    "https://www.turkiyefinans.com.tr/"
    "tr-tr/ticari/gayri-nakdi-finansman/"
    "sayfalar/default.aspx"
)

DIRECT_PRODUCTS = {
    "Teminat Mektubu": (
        "/tr-tr/kobi/kobi-kredileri/"
        "gayri-nakdi-krediler/sayfalar/"
        "teminat-mektuplari.aspx"
    ),
    "Kabul-Aval Kredileri": (
        "/tr-tr/kobi/kobi-kredileri/"
        "gayri-nakdi-krediler/sayfalar/"
        "aval-kabul.aspx"
    ),
    "Referans Mektubu": (
        "/tr-tr/kobi/kobi-kredileri/"
        "gayri-nakdi-krediler/sayfalar/"
        "referans-mektuplari.aspx"
    ),
}

EMBEDDED_PRODUCT = "Elektronik Teminat Mektubu"


def casefold(value) -> str:
    return str(value or "").strip().casefold()


def find_bank(data: dict) -> dict:
    for bank in data.get("banks", []):
        if casefold(bank.get("name")) == casefold(BANK_NAME):
            return bank
    raise RuntimeError("Türkiye Finans config bloğu bulunamadı.")


def prepare_config(data: dict) -> tuple[dict, list[str]]:
    bank = find_bank(data)

    base_url = str(bank.get("base_url") or "").strip()
    if not base_url:
        base_url = "https://www.turkiyefinans.com.tr"

    bank["seed_exact_paths"] = True

    family_rules = bank.setdefault("family_rules", [])

    target_rule = None
    for rule in family_rules:
        if casefold(rule.get("family_key")) == "gayri_nakdi_finansman":
            target_rule = rule
            break

    if target_rule is None:
        target_rule = {
            "family_key": "gayri_nakdi_finansman",
            "family_label": "Gayri Nakdi Finansman",
            "exact_paths": [],
            "path_contains": [],
        }
        family_rules.append(target_rule)

    exact_paths = target_rule.setdefault("exact_paths", [])

    for path in DIRECT_PRODUCTS.values():
        if path.casefold() not in {
            str(item).casefold()
            for item in exact_paths
        }:
            exact_paths.append(path)

    # Ortak sayfadan artık yalnız Elektronik Teminat Mektubu
    # embedded olarak üretilecek.
    embedded_pages = bank.setdefault(
        "embedded_product_pages",
        [],
    )

    common_key = COMMON_EMBEDDED_URL.casefold()
    target_page = None

    for page in embedded_pages:
        if casefold(page.get("url")) == common_key:
            target_page = page
            break

    if target_page is None:
        target_page = {
            "url": COMMON_EMBEDDED_URL,
            "scope": "ticari",
            "product_family_key": "gayri_nakdi_finansman",
            "product_family": "Gayri Nakdi Finansman",
            "products": [],
        }
        embedded_pages.append(target_page)

    target_page["scope"] = "ticari"
    target_page["product_family_key"] = "gayri_nakdi_finansman"
    target_page["product_family"] = "Gayri Nakdi Finansman"

    existing_embedded = target_page.get("products", [])

    electronic_spec = None
    for spec in existing_embedded:
        if casefold(spec.get("product_name")) == casefold(EMBEDDED_PRODUCT):
            electronic_spec = spec
            break

    if electronic_spec is None:
        electronic_spec = {
            "product_name": EMBEDDED_PRODUCT,
        }

    target_page["products"] = [electronic_spec]

    direct_urls = [
        urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
        for path in DIRECT_PRODUCTS.values()
    ]

    return data, direct_urls


def migrate_db(
    con: sqlite3.Connection,
    *,
    base_url: str,
) -> list[tuple[int, str, str, str]]:
    con.row_factory = sqlite3.Row

    migrated = []

    for product_name, path in DIRECT_PRODUCTS.items():
        direct_url = urljoin(
            base_url.rstrip("/") + "/",
            path.lstrip("/"),
        )

        # Eğer direct URL zaten farklı kayıtta varsa duplicate
        # üretmemek için güvenli biçimde dur.
        direct_rows = con.execute(
            """
            SELECT
                c.id,
                d.product_name
            FROM live_campaigns c
            JOIN live_standard_product_details d
                ON d.product_id = c.id
            WHERE
                c.bank_name = ?
                AND c.record_kind = 'standard_product'
                AND LOWER(COALESCE(c.source_url, ''))
                    = LOWER(?)
            """,
            (BANK_NAME, direct_url),
        ).fetchall()

        old_rows = con.execute(
            """
            SELECT
                c.id,
                c.source_url,
                c.is_current,
                d.product_name
            FROM live_campaigns c
            JOIN live_standard_product_details d
                ON d.product_id = c.id
            WHERE
                c.bank_name = ?
                AND c.record_kind = 'standard_product'
                AND LOWER(TRIM(COALESCE(d.product_name, '')))
                    = LOWER(TRIM(?))
            ORDER BY c.id
            """,
            (BANK_NAME, product_name),
        ).fetchall()

        if direct_rows:
            direct_ids = {
                int(row["id"])
                for row in direct_rows
            }

            old_ids = {
                int(row["id"])
                for row in old_rows
            }

            if not direct_ids.issubset(old_ids):
                raise RuntimeError(
                    f"{product_name}: direct URL başka bir kayıtta mevcut. "
                    f"Direct IDs={sorted(direct_ids)}, "
                    f"Product IDs={sorted(old_ids)}"
                )

        embedded_rows = [
            row
            for row in old_rows
            if "#product=" in casefold(row["source_url"])
        ]

        if len(embedded_rows) == 0:
            print(
                f"[UYARI] {product_name}: "
                "embedded kayıt bulunamadı. "
                "Config direct URL'yi yine tarayacak."
            )
            continue

        if len(embedded_rows) > 1:
            raise RuntimeError(
                f"{product_name}: birden fazla embedded kayıt bulundu: "
                + ", ".join(
                    str(row["id"])
                    for row in embedded_rows
                )
            )

        row = embedded_rows[0]
        product_id = int(row["id"])
        old_url = str(row["source_url"])

        con.execute(
            """
            UPDATE live_campaigns
            SET source_url = ?
            WHERE id = ?
            """,
            (direct_url, product_id),
        )

        migrated.append(
            (
                product_id,
                product_name,
                old_url,
                direct_url,
            )
        )

    return migrated


def verify(con: sqlite3.Connection) -> list[sqlite3.Row]:
    con.row_factory = sqlite3.Row
    return con.execute(
        """
        SELECT
            c.id,
            c.is_current,
            c.source_url,
            d.product_name,
            d.product_family,
            d.scope
        FROM live_campaigns c
        JOIN live_standard_product_details d
            ON d.product_id = c.id
        WHERE
            c.bank_name = ?
            AND c.record_kind = 'standard_product'
            AND (
                LOWER(COALESCE(d.product_name, '')) LIKE '%teminat%'
                OR LOWER(COALESCE(d.product_name, '')) LIKE '%kabul%'
                OR LOWER(COALESCE(d.product_name, '')) LIKE '%referans%'
            )
        ORDER BY d.product_name, c.id
        """,
        (BANK_NAME,),
    ).fetchall()


def main() -> int:
    if not CONFIG.exists():
        raise SystemExit(f"Config bulunamadı: {CONFIG}")

    if not DB.exists():
        raise SystemExit(f"DB bulunamadı: {DB}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    config_backup = CONFIG.with_name(
        f"{CONFIG.stem}_before_tf_gayri_nakdi_{stamp}"
        f"{CONFIG.suffix}"
    )

    db_backup = DB.with_name(
        f"{DB.stem}_before_tf_gayri_nakdi_{stamp}"
        f"{DB.suffix}"
    )

    shutil.copy2(CONFIG, config_backup)
    shutil.copy2(DB, db_backup)

    print("=" * 100)
    print("TÜRKİYE FİNANS — GAYRİ NAKDİ KAYNAK MİGRASYONU")
    print("=" * 100)
    print("Config yedeği:", config_backup)
    print("DB yedeği:", db_backup)

    try:
        data = json.loads(
            CONFIG.read_text(encoding="utf-8")
        )

        data, _ = prepare_config(data)

        bank = find_bank(data)
        base_url = str(
            bank.get("base_url")
            or "https://www.turkiyefinans.com.tr"
        )

        con = sqlite3.connect(DB)

        try:
            con.execute("BEGIN")

            migrated = migrate_db(
                con,
                base_url=base_url,
            )

            con.commit()

        except Exception:
            con.rollback()
            raise

        finally:
            con.close()

        CONFIG.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
        rows = verify(con)
        con.close()

        print()
        print("DB URL migrasyonları:")

        if migrated:
            for product_id, name, old_url, new_url in migrated:
                print()
                print(f"  ID {product_id} | {name}")
                print("    Eski:", old_url)
                print("    Yeni:", new_url)
        else:
            print("  Migrasyon gerektiren kayıt yok.")

        print()
        print("Elektronik Teminat Mektubu:")
        print(
            "  Embedded olarak ortak Gayri Nakdi "
            "Finansman sayfasında bırakıldı."
        )

        print()
        print("Güncel 4 kayıt:")
        for row in rows:
            print(dict(row))

        print()
        print("SONUÇ: migration tamamlandı.")
        print(
            "Şimdi Türkiye Finans standard product "
            "update çalıştırılabilir."
        )

        return 0

    except Exception:
        # Tam geri alma: kullanıcı her iki yedeğe de sahip.
        shutil.copy2(config_backup, CONFIG)
        shutil.copy2(db_backup, DB)

        print()
        print(
            "HATA: İşlem başarısız oldu; "
            "config ve DB yedekten geri yüklendi."
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
