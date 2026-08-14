from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "campaigns.db"
CONFIG_PATH = (
    ROOT
    / "config"
    / "campaign_classification_overrides.json"
)

DB_BACKUP_DIR = ROOT / "data" / "backups"
CONFIG_BACKUP_DIR = ROOT / "config" / "backups"

BANK = "Ziraat Katılım"

URL_AILE = (
    "https://ziraatkatilim.com.tr/kart-kampanyalari/"
    "aile-karta-ozel-2000-tlye-varan-bankkart-lira-1"
)
URL_BAGIMSIZ = (
    "https://ziraatkatilim.com.tr/kart-kampanyalari/"
    "bagimsiz-karta-ozel-5000-tlye-varan-bankkart-lira-1"
)
URL_ENTERPRISE = (
    "https://ziraatkatilim.com.tr/kart-kampanyalari/"
    "enterpriseta-arac-kiralamalarinizda-30-indirim"
)
URL_HALALBOOKING = (
    "https://ziraatkatilim.com.tr/kart-kampanyalari/"
    "halalbookingde-size-ozel-avantajli-tatiller"
)
URL_HAVA_YOLU = (
    "https://ziraatkatilim.com.tr/kart-kampanyalari/"
    "hava-yolu-bilet-aliminiza-1500-tl-bankkart-lira-2"
)
URL_THY = (
    "https://ziraatkatilim.com.tr/kart-kampanyalari/"
    "turk-hava-yollarinda-6-taksit"
)
URL_YOLCU_DIS = (
    "https://ziraatkatilim.com.tr/kart-kampanyalari/"
    "yolcu360ta-yurt-disi-arac-kiralamalarinizda-15-indirim"
)
URL_YOLCU_IC = (
    "https://ziraatkatilim.com.tr/kart-kampanyalari/"
    "yolcu360ta-yurt-ici-arac-kiralamalarinizda-10-indirim"
)
URL_BANKKART_GENEL = (
    "https://ziraatkatilim.com.tr/kart-kampanyalari/"
    "ziraat-katilim-avantajli-bankkart-kampanyalari"
)

CLASSIFICATION_OVERRIDES = [
    {
        "bank_name": BANK,
        "source_url": URL_HAVA_YOLU,
        "title": "Hava Yolu Bilet Alımınıza 1.500 TL Bankkart Lira!",
        "record_kind": "campaign",
        "campaign_category": "points_campaign",
        "classification_confidence": 1.0,
        "reason": (
            "Kampanyanın ana faydası belirli harcama tutarları "
            "karşılığında 1.500 TL'ye varan Bankkart Lira kazancıdır."
        ),
    },
    {
        "bank_name": BANK,
        "source_url": URL_THY,
        "title": "Türk Hava Yolları'nda 6 Taksit",
        "record_kind": "campaign",
        "campaign_category": "card_campaign",
        "classification_confidence": 1.0,
        "reason": (
            "Kampanyanın ana faydası Bankkart kredi kartıyla "
            "Türk Hava Yolları harcamalarında 6 taksittir."
        ),
    },
]

BENEFIT_REPLACEMENTS = {
    URL_ENTERPRISE: [
        {
            "benefit_type": "discount",
            "amount": None,
            "rate": 30.0,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": None,
            "description": "%30 indirim",
            "evidence": (
                "Enterprise'ta araç kiralamalarında %30 indirim."
            ),
        },
    ],
    URL_HALALBOOKING: [
        {
            "benefit_type": "discount",
            "amount": 1000.0,
            "rate": None,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": 1000.0,
            "description": "1.000 TL indirim",
            "evidence": (
                "Ziraat Katılım Bankkart Klasik ve Ücretsiz kart "
                "sahipleri Gold statüsü ve ilk rezervasyonlarında "
                "belirli otellerde 1.000 TL indirim kazanır."
            ),
        },
        {
            "benefit_type": "discount",
            "amount": None,
            "rate": 20.0,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": None,
            "description": "%20'ye varan indirim",
            "evidence": (
                "Gold statüsünde %20 oranına varan özel indirimler "
                "sunulur."
            ),
        },
        {
            "benefit_type": "discount",
            "amount": None,
            "rate": 15.0,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": None,
            "description": "%15'e varan indirim",
            "evidence": (
                "İlgili statü kapsamında %15 oranına varan özel "
                "indirimler sunulur."
            ),
        },
    ],
    URL_HAVA_YOLU: [
        {
            "benefit_type": "reward",
            "amount": 1500.0,
            "rate": None,
            "points": None,
            "minimum_spending": 4000.0,
            "maximum_benefit": 1500.0,
            "description": "1.500 TL'ye varan Bankkart Lira",
            "evidence": (
                "4.000 TL ve üzeri harcamaya 350 TL, 10.000 TL ve "
                "üzeri harcamaya 800 TL, 25.000 TL ve üzeri "
                "harcamaya 1.500 TL Bankkart Lira verilir."
            ),
        },
    ],
    URL_THY: [
        {
            "benefit_type": "installment",
            "amount": None,
            "rate": None,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": None,
            "description": "6 taksit",
            "evidence": (
                "Türk Hava Yolları harcamalarında 6 taksit fırsatı."
            ),
        },
    ],
    URL_YOLCU_DIS: [
        {
            "benefit_type": "discount",
            "amount": None,
            "rate": 15.0,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": None,
            "description": "%15 indirim",
            "evidence": (
                "Yurt dışı araç kiralamalarında Bankkart "
                "kullanıcılarına özel %15 indirim."
            ),
        },
    ],
    URL_YOLCU_IC: [
        {
            "benefit_type": "discount",
            "amount": None,
            "rate": 10.0,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": None,
            "description": "%10 indirim",
            "evidence": (
                "Yurt içi araç kiralamalarında Bankkart "
                "kullanıcılarına özel %10 indirim."
            ),
        },
    ],
    URL_BANKKART_GENEL: [
        {
            "benefit_type": "privilege",
            "amount": None,
            "rate": None,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": None,
            "description": (
                "Farklı sektörlerde Bankkart kampanya avantajları"
            ),
            "evidence": (
                "Sayfa; havayolu, QR ile ödeme, e-ticaret, giyim, "
                "restoran, kültür-sanat, optik, akaryakıt ve diğer "
                "alanlardaki Bankkart kampanyalarını sunar."
            ),
        },
    ],
}

AUDIENCE_REPLACEMENTS = {
    URL_AILE: [
        {
            "audience_type": "card_holder",
            "audience_label": "Aile Kart Sahipleri",
            "details": (
                "Ziraat Katılım Bankkart Aile kredi kartı sahipleri"
            ),
        },
    ],
    URL_BAGIMSIZ: [
        {
            "audience_type": "card_holder",
            "audience_label": "Bağımsız Kart Sahipleri",
            "details": (
                "Ziraat Katılım Bankkart Bağımsız kredi kartı sahipleri"
            ),
        },
    ],
    URL_BANKKART_GENEL: [
        {
            "audience_type": "card_holder",
            "audience_label": "Bankkart Sahipleri",
            "details": "Ziraat Katılım Bankkart sahipleri",
        },
    ],
}

EXPECTED_DISTRIBUTION = {
    "card_campaign": 56,
    "discount_campaign": 10,
    "points_campaign": 5,
    "new_customer_campaign": 1,
}


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def table_columns(
    conn: sqlite3.Connection,
    table: str,
) -> set[str]:
    return {
        row[1]
        for row in conn.execute(
            f"PRAGMA table_info({quote(table)})"
        )
    }


def other_banks_digest(
    conn: sqlite3.Connection,
) -> str:
    payload: dict[str, list[tuple]] = {}

    payload["campaigns"] = [
        tuple(row)
        for row in conn.execute(
            """
            SELECT *
            FROM live_campaigns
            WHERE bank_name <> ?
            ORDER BY rowid
            """,
            (BANK,),
        ).fetchall()
    ]

    payload["benefits"] = [
        tuple(row)
        for row in conn.execute(
            """
            SELECT b.*
            FROM live_campaign_benefits b
            JOIN live_campaigns c
              ON c.id = b.campaign_id
            WHERE c.bank_name <> ?
            ORDER BY b.rowid
            """,
            (BANK,),
        ).fetchall()
    ]

    payload["audiences"] = [
        tuple(row)
        for row in conn.execute(
            """
            SELECT a.*
            FROM live_campaign_audiences a
            JOIN live_campaigns c
              ON c.id = a.campaign_id
            WHERE c.bank_name <> ?
            ORDER BY a.rowid
            """,
            (BANK,),
        ).fetchall()
    ]

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def upsert_config(data: list[dict]) -> tuple[list[dict], int, int]:
    index = {
        (
            item.get("bank_name"),
            item.get("source_url"),
        ): position
        for position, item in enumerate(data)
        if isinstance(item, dict)
    }

    added = 0
    updated = 0

    for override in CLASSIFICATION_OVERRIDES:
        key = (
            override["bank_name"],
            override["source_url"],
        )

        if key not in index:
            data.append(override)
            index[key] = len(data) - 1
            added += 1
            continue

        position = index[key]

        if data[position] != override:
            data[position] = override
            updated += 1

    return data, added, updated


def fetch_campaign_ids(
    conn: sqlite3.Connection,
) -> dict[str, int]:
    target_urls = sorted(
        set(BENEFIT_REPLACEMENTS)
        | set(AUDIENCE_REPLACEMENTS)
        | {
            item["source_url"]
            for item in CLASSIFICATION_OVERRIDES
        }
    )

    placeholders = ",".join(
        "?"
        for _ in target_urls
    )

    rows = conn.execute(
        f"""
        SELECT id, source_url
        FROM live_campaigns
        WHERE bank_name = ?
          AND is_current = 1
          AND source_url IN ({placeholders})
        """,
        [BANK, *target_urls],
    ).fetchall()

    result = {
        row["source_url"]: row["id"]
        for row in rows
    }

    missing = set(target_urls) - set(result)

    if missing:
        raise RuntimeError(
            "Veritabanında bulunamayan hedef URL'ler:\n- "
            + "\n- ".join(sorted(missing))
        )

    return result


def insert_benefit(
    conn: sqlite3.Connection,
    campaign_id: int,
    benefit: dict,
    extracted_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO live_campaign_benefits (
            campaign_id,
            benefit_type,
            amount,
            rate,
            points,
            minimum_spending,
            maximum_benefit,
            description,
            evidence,
            extracted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            campaign_id,
            benefit["benefit_type"],
            benefit["amount"],
            benefit["rate"],
            benefit["points"],
            benefit["minimum_spending"],
            benefit["maximum_benefit"],
            benefit["description"],
            benefit["evidence"],
            extracted_at,
        ),
    )


def insert_audience(
    conn: sqlite3.Connection,
    campaign_id: int,
    audience: dict,
    extracted_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO live_campaign_audiences (
            campaign_id,
            audience_type,
            audience_label,
            details,
            extracted_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            campaign_id,
            audience["audience_type"],
            audience["audience_label"],
            audience["details"],
            extracted_at,
        ),
    )


def validate_replacements(
    conn: sqlite3.Connection,
    ids: dict[str, int],
) -> None:
    for url, expected_rows in BENEFIT_REPLACEMENTS.items():
        rows = conn.execute(
            """
            SELECT
                benefit_type,
                amount,
                rate,
                points,
                minimum_spending,
                maximum_benefit,
                description
            FROM live_campaign_benefits
            WHERE campaign_id = ?
            ORDER BY id
            """,
            (ids[url],),
        ).fetchall()

        if len(rows) != len(expected_rows):
            raise RuntimeError(
                f"Avantaj doğrulaması başarısız: {url} "
                f"beklenen={len(expected_rows)}, gerçek={len(rows)}"
            )

    for url, expected_rows in AUDIENCE_REPLACEMENTS.items():
        rows = conn.execute(
            """
            SELECT
                audience_type,
                audience_label,
                details
            FROM live_campaign_audiences
            WHERE campaign_id = ?
            ORDER BY id
            """,
            (ids[url],),
        ).fetchall()

        if len(rows) != len(expected_rows):
            raise RuntimeError(
                f"Hedef kitle doğrulaması başarısız: {url} "
                f"beklenen={len(expected_rows)}, gerçek={len(rows)}"
            )


def main() -> int:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Veritabanı bulunamadı: {DB_PATH}"
        )

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Override dosyası bulunamadı: {CONFIG_PATH}"
        )

    config = json.loads(
        CONFIG_PATH.read_text(encoding="utf-8")
    )

    if not isinstance(config, list):
        raise RuntimeError(
            "Override dosyasının ana yapısı liste olmalıdır."
        )

    updated_config, config_added, config_updated = upsert_config(
        config
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    DB_BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    CONFIG_BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    db_backup = (
        DB_BACKUP_DIR
        / f"campaigns_before_ziraat_extraction_guardrails_{stamp}.db"
    )
    config_backup = (
        CONFIG_BACKUP_DIR
        / (
            "campaign_classification_overrides_"
            f"before_ziraat_extraction_guardrails_{stamp}.json"
        )
    )

    shutil.copy2(
        DB_PATH,
        db_backup,
    )
    shutil.copy2(
        CONFIG_PATH,
        config_backup,
    )

    config_written = False

    try:
        CONFIG_PATH.write_text(
            json.dumps(
                updated_config,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        config_written = True

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        try:
            required_tables = {
                "live_campaigns",
                "live_campaign_benefits",
                "live_campaign_audiences",
            }

            existing_tables = {
                row[0]
                for row in conn.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                )
            }

            missing_tables = required_tables - existing_tables

            if missing_tables:
                raise RuntimeError(
                    "Eksik tablolar: "
                    + ", ".join(sorted(missing_tables))
                )

            before_other_digest = other_banks_digest(conn)
            ids = fetch_campaign_ids(conn)
            extracted_at = datetime.now(
                timezone.utc
            ).isoformat(timespec="seconds")

            conn.execute("BEGIN IMMEDIATE")

            campaign_columns = table_columns(
                conn,
                "live_campaigns",
            )

            for override in CLASSIFICATION_OVERRIDES:
                assignments = [
                    "campaign_category = ?",
                ]
                values = [
                    override["campaign_category"],
                ]

                if "classification_confidence" in campaign_columns:
                    assignments.append(
                        "classification_confidence = ?"
                    )
                    values.append(
                        override["classification_confidence"]
                    )

                values.extend(
                    [
                        BANK,
                        override["source_url"],
                    ]
                )

                cursor = conn.execute(
                    f"""
                    UPDATE live_campaigns
                    SET {", ".join(assignments)}
                    WHERE bank_name = ?
                      AND source_url = ?
                      AND is_current = 1
                    """,
                    values,
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Kategori güncelleme sayısı beklenenden farklı: "
                        f"{override['source_url']} -> {cursor.rowcount}"
                    )

            deleted_benefits = 0
            inserted_benefits = 0

            for url, benefits in BENEFIT_REPLACEMENTS.items():
                campaign_id = ids[url]

                cursor = conn.execute(
                    """
                    DELETE FROM live_campaign_benefits
                    WHERE campaign_id = ?
                    """,
                    (campaign_id,),
                )
                deleted_benefits += cursor.rowcount

                for benefit in benefits:
                    insert_benefit(
                        conn,
                        campaign_id,
                        benefit,
                        extracted_at,
                    )
                    inserted_benefits += 1

            deleted_audiences = 0
            inserted_audiences = 0

            for url, audiences in AUDIENCE_REPLACEMENTS.items():
                campaign_id = ids[url]

                cursor = conn.execute(
                    """
                    DELETE FROM live_campaign_audiences
                    WHERE campaign_id = ?
                    """,
                    (campaign_id,),
                )
                deleted_audiences += cursor.rowcount

                for audience in audiences:
                    insert_audience(
                        conn,
                        campaign_id,
                        audience,
                        extracted_at,
                    )
                    inserted_audiences += 1

            validate_replacements(
                conn,
                ids,
            )

            distribution_rows = conn.execute(
                """
                SELECT
                    campaign_category,
                    COUNT(*) AS count
                FROM live_campaigns
                WHERE bank_name = ?
                  AND is_current = 1
                GROUP BY campaign_category
                """,
                (BANK,),
            ).fetchall()

            distribution = {
                row["campaign_category"]: row["count"]
                for row in distribution_rows
            }

            if distribution != EXPECTED_DISTRIBUTION:
                raise RuntimeError(
                    "Kategori dağılımı beklenenle uyuşmuyor: "
                    f"{distribution}"
                )

            missing_benefits = conn.execute(
                """
                SELECT COUNT(*)
                FROM live_campaigns c
                WHERE c.bank_name = ?
                  AND c.is_current = 1
                  AND NOT EXISTS (
                      SELECT 1
                      FROM live_campaign_benefits b
                      WHERE b.campaign_id = c.id
                  )
                """,
                (BANK,),
            ).fetchone()[0]

            missing_audiences = conn.execute(
                """
                SELECT COUNT(*)
                FROM live_campaigns c
                WHERE c.bank_name = ?
                  AND c.is_current = 1
                  AND NOT EXISTS (
                      SELECT 1
                      FROM live_campaign_audiences a
                      WHERE a.campaign_id = c.id
                  )
                """,
                (BANK,),
            ).fetchone()[0]

            if missing_benefits != 0:
                raise RuntimeError(
                    f"Avantajı eksik kampanya kaldı: {missing_benefits}"
                )

            if missing_audiences != 0:
                raise RuntimeError(
                    f"Hedef kitlesi eksik kampanya kaldı: {missing_audiences}"
                )

            after_other_digest = other_banks_digest(conn)

            if before_other_digest != after_other_digest:
                raise RuntimeError(
                    "Diğer bankaların kayıtları değişti."
                )

            total_benefits = conn.execute(
                """
                SELECT COUNT(*)
                FROM live_campaign_benefits b
                JOIN live_campaigns c
                  ON c.id = b.campaign_id
                WHERE c.bank_name = ?
                  AND c.is_current = 1
                """,
                (BANK,),
            ).fetchone()[0]

            total_audiences = conn.execute(
                """
                SELECT COUNT(*)
                FROM live_campaign_audiences a
                JOIN live_campaigns c
                  ON c.id = a.campaign_id
                WHERE c.bank_name = ?
                  AND c.is_current = 1
                """,
                (BANK,),
            ).fetchone()[0]

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            conn.close()

    except Exception:
        if config_written:
            shutil.copy2(
                config_backup,
                CONFIG_PATH,
            )
        raise

    print("Ziraat Katılım extraction guardrail işlemi tamamlandı.")
    print("Sınıflandırma override eklenen:", config_added)
    print("Sınıflandırma override güncellenen:", config_updated)
    print("Silinen eski/karışmış avantaj:", deleted_benefits)
    print("Eklenen doğrulanmış avantaj:", inserted_benefits)
    print("Silinen eski hedef kitle:", deleted_audiences)
    print("Eklenen doğrulanmış hedef kitle:", inserted_audiences)
    print("Avantajı eksik kampanya:", missing_benefits)
    print("Hedef kitlesi eksik kampanya:", missing_audiences)
    print("Diğer bankalar: değişmedi")
    print("Toplam Ziraat avantaj kaydı:", total_benefits)
    print("Toplam Ziraat hedef kitle kaydı:", total_audiences)
    print()
    print("Kategori dağılımı:")

    for category, count in sorted(
        distribution.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        print(f"- {category}: {count}")

    print()
    print("Veritabanı yedeği:", db_backup)
    print("Override yedeği:", config_backup)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
