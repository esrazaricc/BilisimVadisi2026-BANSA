from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "campaigns.db"
BACKUP_DIR = ROOT / "data" / "backups"
REPORT_PATH = ROOT / "data" / "dunya_katilim_extraction_guardrail_report.json"

BANK = "Dünya Katılım"

SERVICE_URLS = {
    "https://dunyakatilim.com.tr/kampanyalar/avantajli-kurlar",
    "https://dunyakatilim.com.tr/kampanyalar/tahsile-cek",
}

BENEFIT_FIXES = {
    "https://dunyakatilim.com.tr/kampanyalar/altin-kesemTicari": [
        {
            "benefit_type": "reward",
            "amount": 0.01,
            "rate": None,
            "points": None,
            "minimum_spending": 7500.0,
            "maximum_benefit": 5.0,
            "description": "DKart Debit ile 7.500 TL harcamaya 0,01 gram altın; yıllık en fazla 5 gram",
            "evidence": "Bireysel DKart Debit kartlar ile yapılacak toplamda 7.500 TL harcamadan 0,01 gr altın kazanılacaktır.",
        },
        {
            "benefit_type": "reward",
            "amount": 0.01,
            "rate": None,
            "points": None,
            "minimum_spending": 12500.0,
            "maximum_benefit": 5.0,
            "description": "Kredi kartlarıyla 12.500 TL harcamaya 0,01 gram altın; yıllık en fazla 5 gram",
            "evidence": "Kredi kartları ile yapılacak toplamda 12.500 TL harcamadan 0,01 gr altın kazanılacaktır.",
        },
    ],
    "https://dunyakatilim.com.tr/kampanyalar/jack-jones": [
        {
            "benefit_type": "cashback",
            "amount": None,
            "rate": 18.0,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": None,
            "description": "%18 nakit iade",
            "evidence": "Jack & Jones mağazalarında işlem tutarının %18'i kadar nakit iade aynı gün hesaba yatırılır.",
        }
    ],
    "https://dunyakatilim.com.tr/kampanyalar/koton": [
        {
            "benefit_type": "cashback",
            "amount": None,
            "rate": 8.0,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": None,
            "description": "%8 nakit iade",
            "evidence": "Koton mağazalarında işlem tutarının %8'i kadar nakit iade aynı gün hesaba yatırılır.",
        }
    ],
    "https://dunyakatilim.com.tr/kampanyalar/davetetkazan": [
        {
            "benefit_type": "reward",
            "amount": 0.1,
            "rate": None,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": 1.0,
            "description": "Her başarılı davet için 0,1 gram altın; en fazla 1 gram",
            "evidence": "Davetle müşteri olup Paraf Kart başvurusu yapan her kişi için 0,1 gram altın, kampanya boyunca en fazla 1 gram kazanılır.",
        }
    ],
    "https://dunyakatilim.com.tr/kampanyalar/enerya-finansmani": [
        {
            "benefit_type": "finance_advantage",
            "amount": None,
            "rate": 0.0,
            "points": None,
            "minimum_spending": None,
            "maximum_benefit": None,
            "description": "2-6 ay vadeli, %0 kâr paylı finansman",
            "evidence": "Yeni abonelik işlemlerinde 6.500-16.500 TL aralığında, 2-6 ay vadeli vade farksız finansman sağlanır.",
        }
    ],
}

AUDIENCE_FIXES = {
    "https://dunyakatilim.com.tr/kampanyalar/a-101-paraf": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/alfemo": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/divarese": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/dyson": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/dsdamat": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/enerya-finansmani": ("customer_segment", "Yeni Aboneler", "Antalya, Aydın, Denizli ve Konya illerindeki yeni doğal gaz aboneleri"),
    "https://dunyakatilim.com.tr/kampanyalar/kip": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/n11": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/network": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/demirdokum": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/evidea": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/koctas": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/adv": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/damat-tween": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/zsa-zsa-zsu": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/pazarama-paraf": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/ramsey": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/touristica": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/twist": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/vakko": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/vaillant": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/vakkorama": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/vestel": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/yatas": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/ider": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
    "https://dunyakatilim.com.tr/kampanyalar/ipekyol": ("card_holder", "Kart Sahipleri", "Dünya Katılım Paraf kart sahipleri"),
}

ENERYA_URL = "https://dunyakatilim.com.tr/kampanyalar/enerya-finansmani"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def backup_database(source: Path, destination: Path) -> None:
    source_conn = sqlite3.connect(source)
    destination_conn = sqlite3.connect(destination)
    try:
        source_conn.backup(destination_conn)
    finally:
        destination_conn.close()
        source_conn.close()


def other_banks_digest(conn: sqlite3.Connection) -> str:
    payload: dict[str, list[list[object]]] = {}

    campaign_rows = conn.execute(
        """
        SELECT *
        FROM live_campaigns
        WHERE bank_name <> ?
        ORDER BY id
        """,
        (BANK,),
    ).fetchall()
    payload["live_campaigns"] = [list(row) for row in campaign_rows]

    for table in (
        "live_campaign_benefits",
        "live_campaign_audiences",
        "live_campaign_finance_details",
    ):
        rows = conn.execute(
            f"""
            SELECT child.*
            FROM {table} AS child
            JOIN live_campaigns AS campaign
              ON campaign.id = child.campaign_id
            WHERE campaign.bank_name <> ?
            ORDER BY child.campaign_id, child.rowid
            """,
            (BANK,),
        ).fetchall()
        payload[table] = [list(row) for row in rows]

    encoded = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def current_campaigns(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT *
        FROM live_campaigns
        WHERE bank_name = ?
          AND is_current = 1
        """,
        (BANK,),
    ).fetchall()
    return {str(row["source_url"]): row for row in rows}


def semantic_duplicate_count(conn: sqlite3.Connection, table: str, fields: list[str]) -> int:
    columns = ", ".join(["campaign_id", *fields])
    group_columns = ", ".join(["campaign_id", *fields])
    row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT {columns}, COUNT(*) AS n
            FROM {table}
            WHERE campaign_id IN (
                SELECT id FROM live_campaigns
                WHERE bank_name = ? AND is_current = 1
            )
            GROUP BY {group_columns}
            HAVING COUNT(*) > 1
        )
        """,
        (BANK,),
    ).fetchone()
    return int(row[0])


def main() -> int:
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Veritabanı bulunamadı: {DB_PATH}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"campaigns_before_dunya_extraction_guardrails_{stamp}.db"
    backup_database(DB_PATH, backup_path)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    before_other_digest = other_banks_digest(conn)

    try:
        conn.execute("BEGIN IMMEDIATE")

        normalized_service_flags = conn.execute(
            """
            UPDATE live_campaigns
            SET comparison_eligible = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE bank_name = ?
              AND is_current = 1
              AND record_kind = 'service_information'
              AND COALESCE(comparison_eligible, 0) <> 0
            """,
            (BANK,),
        ).rowcount

        campaigns = current_campaigns(conn)

        if not campaigns:
            raise RuntimeError("Dünya Katılım için güncel kayıt bulunamadı.")

        invalid_record_kinds = [
            row for row in campaigns.values()
            if row["record_kind"] not in {"campaign", "service_information"}
        ]
        if invalid_record_kinds:
            preview = ", ".join(
                f"{row['title']} ({row['record_kind']})"
                for row in invalid_record_kinds[:5]
            )
            raise RuntimeError(
                "Beklenmeyen kayıt türleri bulundu: " + preview
            )

        real_campaigns = [
            row for row in campaigns.values()
            if row["record_kind"] == "campaign"
        ]
        service_records = [
            row for row in campaigns.values()
            if row["record_kind"] == "service_information"
        ]
        open_service_records = [
            row for row in service_records
            if int(row["comparison_eligible"] or 0) != 0
        ]
        closed_campaign_records = [
            row for row in real_campaigns
            if int(row["comparison_eligible"] or 0) != 1
        ]

        actual_service_urls = {
            str(row["source_url"] or "")
            for row in service_records
        }
        known_service_misclassified = [
            url for url in SERVICE_URLS
            if url in campaigns
            and campaigns[url]["record_kind"] != "service_information"
        ]
        if known_service_misclassified:
            raise RuntimeError(
                "Bilinen hizmet URL'leri kampanya olarak sınıflandırılmış: "
                + ", ".join(sorted(known_service_misclassified))
            )

        if open_service_records:
            raise RuntimeError(
                "Hizmet kaydı karşılaştırmaya açık bırakılmış: "
                + ", ".join(str(row["title"]) for row in open_service_records)
            )

        if closed_campaign_records:
            raise RuntimeError(
                "Gerçek kampanya karşılaştırmaya kapalı bırakılmış: "
                + ", ".join(
                    str(row["title"]) for row in closed_campaign_records[:5]
                )
            )

        # Manuel guardrail düzeltmeleri yalnızca URL hâlâ güncelse uygulanır.
        # Geçmişte var olan bir kampanya sona erdiğinde pipeline bunun için
        # başarısız olmamalıdır.

        now = utc_now()

        inserted_benefits = 0
        for url, benefit_rows in BENEFIT_FIXES.items():
            if url not in campaigns:
                continue
            campaign_id = int(campaigns[url]["id"])
            conn.execute(
                "DELETE FROM live_campaign_benefits WHERE campaign_id = ?",
                (campaign_id,),
            )
            for item in benefit_rows:
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
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        campaign_id,
                        item["benefit_type"],
                        item["amount"],
                        item["rate"],
                        item["points"],
                        item["minimum_spending"],
                        item["maximum_benefit"],
                        item["description"],
                        item["evidence"],
                        now,
                    ),
                )
                inserted_benefits += 1

        inserted_audiences = 0
        for url, (audience_type, audience_label, details) in AUDIENCE_FIXES.items():
            if url not in campaigns:
                continue
            campaign_id = int(campaigns[url]["id"])
            conn.execute(
                "DELETE FROM live_campaign_audiences WHERE campaign_id = ?",
                (campaign_id,),
            )
            conn.execute(
                """
                INSERT INTO live_campaign_audiences (
                    campaign_id,
                    audience_type,
                    audience_label,
                    details,
                    extracted_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (campaign_id, audience_type, audience_label, details, now),
            )
            inserted_audiences += 1

        enerya_id: int | None = None
        updated_finance = 0
        if ENERYA_URL in campaigns:
            enerya_id = int(campaigns[ENERYA_URL]["id"])
            updated_finance = conn.execute(
                """
                UPDATE live_campaign_finance_details
                SET profit_share_rate_min = 0.0,
                    profit_share_rate_max = 0.0,
                    profit_share_rate_text = '%0',
                    financing_amount_min = 6500.0,
                    financing_amount_max = 16500.0,
                    financing_amount_text = '6.500-16.500 TL',
                    maturity_min_months = 2,
                    maturity_max_months = 6,
                    maturity_text = '2-6 ay',
                    expense_status = NULL,
                    expense_details = NULL,
                    campaign_advantage = 'Antalya, Aydın, Denizli ve Konya illerindeki yeni abonelik işlemlerinde 6.500-16.500 TL aralığında, 2-6 ay vadeli vade farksız finansman.',
                    evidence_text = 'Finansman işlemlerinde minimum 6.500 TL, maksimum 16.500 TL kullandırılır; minimum 2 ay, maksimum 6 ay vade uygulanır.',
                    extraction_confidence = 1.0,
                    extracted_at = ?
                WHERE campaign_id = ?
                """,
                (now, enerya_id),
            ).rowcount

            if updated_finance != 1:
                raise RuntimeError(
                    f"Enerya finansman kaydı güncellenemedi; güncellenen={updated_finance}"
                )


        campaigns_after = current_campaigns(conn)
        benefit_count = int(conn.execute(
            """
            SELECT COUNT(*)
            FROM live_campaign_benefits AS benefit
            JOIN live_campaigns AS campaign ON campaign.id = benefit.campaign_id
            WHERE campaign.bank_name = ?
              AND campaign.is_current = 1
              AND campaign.record_kind = 'campaign'
              AND campaign.comparison_eligible = 1
            """,
            (BANK,),
        ).fetchone()[0])

        audience_count = int(conn.execute(
            """
            SELECT COUNT(*)
            FROM live_campaign_audiences AS audience
            JOIN live_campaigns AS campaign ON campaign.id = audience.campaign_id
            WHERE campaign.bank_name = ?
              AND campaign.is_current = 1
              AND campaign.record_kind = 'campaign'
              AND campaign.comparison_eligible = 1
            """,
            (BANK,),
        ).fetchone()[0])

        finance_count = int(conn.execute(
            """
            SELECT COUNT(*)
            FROM live_campaign_finance_details AS finance
            JOIN live_campaigns AS campaign ON campaign.id = finance.campaign_id
            WHERE campaign.bank_name = ?
              AND campaign.is_current = 1
              AND campaign.record_kind = 'campaign'
              AND campaign.comparison_eligible = 1
            """,
            (BANK,),
        ).fetchone()[0])

        missing_finance_details = int(conn.execute(
            """
            SELECT COUNT(*)
            FROM live_campaigns AS campaign
            WHERE campaign.bank_name = ?
              AND campaign.is_current = 1
              AND campaign.record_kind = 'campaign'
              AND campaign.comparison_eligible = 1
              AND campaign.campaign_category = 'finance_campaign'
              AND NOT EXISTS (
                  SELECT 1
                  FROM live_campaign_finance_details AS finance
                  WHERE finance.campaign_id = campaign.id
              )
            """,
            (BANK,),
        ).fetchone()[0])

        missing_benefits = int(conn.execute(
            """
            SELECT COUNT(*)
            FROM live_campaigns AS campaign
            WHERE campaign.bank_name = ?
              AND campaign.is_current = 1
              AND campaign.record_kind = 'campaign'
              AND campaign.comparison_eligible = 1
              AND NOT EXISTS (
                  SELECT 1 FROM live_campaign_benefits AS benefit
                  WHERE benefit.campaign_id = campaign.id
              )
            """,
            (BANK,),
        ).fetchone()[0])

        missing_audiences = int(conn.execute(
            """
            SELECT COUNT(*)
            FROM live_campaigns AS campaign
            WHERE campaign.bank_name = ?
              AND campaign.is_current = 1
              AND campaign.record_kind = 'campaign'
              AND campaign.comparison_eligible = 1
              AND NOT EXISTS (
                  SELECT 1 FROM live_campaign_audiences AS audience
                  WHERE audience.campaign_id = campaign.id
              )
            """,
            (BANK,),
        ).fetchone()[0])

        benefit_duplicates = semantic_duplicate_count(
            conn,
            "live_campaign_benefits",
            [
                "benefit_type",
                "amount",
                "rate",
                "points",
                "minimum_spending",
                "maximum_benefit",
                "description",
                "evidence",
            ],
        )
        audience_duplicates = semantic_duplicate_count(
            conn,
            "live_campaign_audiences",
            ["audience_type", "audience_label", "details"],
        )

        finance_row = None
        finance_mismatches: dict[str, dict[str, object]] = {}
        if enerya_id is not None:
            finance_row = conn.execute(
                """
                SELECT *
                FROM live_campaign_finance_details
                WHERE campaign_id = ?
                """,
                (enerya_id,),
            ).fetchone()
            if finance_row is None:
                finance_mismatches["enerya_finance_row"] = {
                    "expected": "present",
                    "actual": "missing",
                }
            else:
                expected_finance = {
                    "profit_share_rate_min": 0.0,
                    "profit_share_rate_max": 0.0,
                    "profit_share_rate_text": "%0",
                    "financing_amount_min": 6500.0,
                    "financing_amount_max": 16500.0,
                    "financing_amount_text": "6.500-16.500 TL",
                    "maturity_min_months": 2,
                    "maturity_max_months": 6,
                    "maturity_text": "2-6 ay",
                    "expense_status": None,
                    "expense_details": None,
                }
                finance_mismatches = {
                    key: {"expected": value, "actual": finance_row[key]}
                    for key, value in expected_finance.items()
                    if finance_row[key] != value
                }

        after_other_digest = other_banks_digest(conn)
        other_banks_unchanged = before_other_digest == after_other_digest

        actual_counts = {
            "current_records": len(campaigns_after),
            "real_campaigns": sum(
                1 for row in campaigns_after.values()
                if row["record_kind"] == "campaign"
            ),
            "service_information": sum(
                1 for row in campaigns_after.values()
                if row["record_kind"] == "service_information"
            ),
            "comparison_eligible": sum(
                1 for row in campaigns_after.values()
                if int(row["comparison_eligible"] or 0) == 1
            ),
            "open_service_records": sum(
                1 for row in campaigns_after.values()
                if row["record_kind"] == "service_information"
                and int(row["comparison_eligible"] or 0) != 0
            ),
            "closed_campaign_records": sum(
                1 for row in campaigns_after.values()
                if row["record_kind"] == "campaign"
                and int(row["comparison_eligible"] or 0) != 1
            ),
            "benefits": benefit_count,
            "audiences": audience_count,
            "finance_details": finance_count,
            "missing_finance_details": missing_finance_details,
            "missing_benefits": missing_benefits,
            "missing_audiences": missing_audiences,
            "benefit_duplicate_groups": benefit_duplicates,
            "audience_duplicate_groups": audience_duplicates,
        }

        # Tarihsel toplam adetleri (39 kayıt, 37 kampanya, 41 avantaj vb.)
        # artık kalite kriteri olarak kullanmıyoruz. Canlı kampanya sayısı
        # doğal olarak artıp azalabilir. Buradaki bloklayıcı kontroller yalnızca
        # yapısal/veri bütünlüğü hatalarıdır.
        blocking_failures: list[str] = []
        if actual_counts["open_service_records"] != 0:
            blocking_failures.append(
                f"open_service_records={actual_counts['open_service_records']}"
            )
        if actual_counts["closed_campaign_records"] != 0:
            blocking_failures.append(
                f"closed_campaign_records={actual_counts['closed_campaign_records']}"
            )
        if actual_counts["benefit_duplicate_groups"] != 0:
            blocking_failures.append(
                f"benefit_duplicate_groups={actual_counts['benefit_duplicate_groups']}"
            )
        if actual_counts["audience_duplicate_groups"] != 0:
            blocking_failures.append(
                f"audience_duplicate_groups={actual_counts['audience_duplicate_groups']}"
            )
        if actual_counts["missing_finance_details"] != 0:
            blocking_failures.append(
                f"missing_finance_details={actual_counts['missing_finance_details']}"
            )

        quality_warnings: list[str] = []
        if actual_counts["missing_benefits"]:
            quality_warnings.append(
                f"{actual_counts['missing_benefits']} kampanyada yapılandırılmış avantaj kaydı yok."
            )
        if actual_counts["missing_audiences"]:
            quality_warnings.append(
                f"{actual_counts['missing_audiences']} kampanyada yapılandırılmış hedef kitle kaydı yok."
            )

        expected_counts = {
            "open_service_records": 0,
            "closed_campaign_records": 0,
            "missing_finance_details": 0,
            "benefit_duplicate_groups": 0,
            "audience_duplicate_groups": 0,
        }
        count_mismatches = {
            "blocking_failures": blocking_failures
        } if blocking_failures else {}

        report = {
            "bank": BANK,
            "executed_at": now,
            "backup": str(backup_path),
            "normalized_service_flags": normalized_service_flags,
            "inserted_benefits": inserted_benefits,
            "inserted_audiences": inserted_audiences,
            "updated_finance_rows": updated_finance,
            "enerya_guardrail_applied": enerya_id is not None,
            "expected_counts": expected_counts,
            "actual_counts": actual_counts,
            "count_mismatches": count_mismatches,
            "quality_warnings": quality_warnings,
            "finance_mismatches": finance_mismatches,
            "other_banks_unchanged": other_banks_unchanged,
        }
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if blocking_failures or finance_mismatches or not other_banks_unchanged:
            raise RuntimeError(
                "Guardrail doğrulaması başarısız. Rapor: " + str(REPORT_PATH)
            )

        conn.commit()

        print("=" * 90)
        print("DÜNYA KATILIM EXTRACTION GUARDRAIL BAŞARILI")
        print("=" * 90)
        print("Gerçek kampanya:", actual_counts["real_campaigns"])
        print("Hizmet bilgisi:", actual_counts["service_information"])
        print("Karşılaştırmaya uygun:", actual_counts["comparison_eligible"])
        print("Karşılaştırmaya açık hizmet kaydı:", actual_counts["open_service_records"])
        print("Düzeltilen hizmet karşılaştırma bayrağı:", normalized_service_flags)
        print("Avantaj kaydı:", actual_counts["benefits"])
        print("Hedef kitle kaydı:", actual_counts["audiences"])
        print("Finansman detayı:", actual_counts["finance_details"])
        print("Avantajı eksik kampanya:", actual_counts["missing_benefits"])
        print("Hedef kitlesi eksik kampanya:", actual_counts["missing_audiences"])
        print("Mükerrer avantaj grubu:", actual_counts["benefit_duplicate_groups"])
        print("Mükerrer hedef kitle grubu:", actual_counts["audience_duplicate_groups"])
        if quality_warnings:
            print("Kalite uyarıları:")
            for warning in quality_warnings:
                print(" -", warning)
        if enerya_id is not None:
            print("Enerya finansman: %0 kâr payı, 6.500-16.500 TL, 2-6 ay")
            print("Enerya masraf bilgisi: belirtilmemiş")
        else:
            print("Enerya: güncel listede yok; manuel guardrail uygulanmadı")
        print("Diğer bankalar: değişmedi")
        print("Yedek:", backup_path)
        print("Rapor:", REPORT_PATH)

        return 0

    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
