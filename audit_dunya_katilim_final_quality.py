from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BANK = "Dünya Katılım"
ALLOWED_CATEGORIES = {
    "card_campaign",
    "discount_campaign",
    "finance_campaign",
    "new_customer_campaign",
    "points_campaign",
    "other_campaign",
    "service_information",
}
SERVICE_URLS = {
    "https://dunyakatilim.com.tr/kampanyalar/avantajli-kurlar",
    "https://dunyakatilim.com.tr/kampanyalar/tahsile-cek",
}
ENERYA_URL = "https://dunyakatilim.com.tr/kampanyalar/enerya-finansmani"


def find_root() -> Path:
    start = Path(__file__).resolve().parent
    for candidate in (start, *start.parents):
        if (candidate / "data" / "campaigns.db").is_file() and (
            candidate / "config" / "banks.json"
        ).is_file():
            return candidate
    raise FileNotFoundError("Proje kökü bulunamadı.")


ROOT = find_root()
DB_PATH = ROOT / "data" / "campaigns.db"
REPORT_PATH = ROOT / "data" / "dunya_katilim_final_quality_report.json"


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in conn.execute(
        f'PRAGMA table_info("{table}")'
    ).fetchall()]


def campaign_fk(conn: sqlite3.Connection, table: str) -> str:
    for row in conn.execute(
        f'PRAGMA foreign_key_list("{table}")'
    ).fetchall():
        if row["table"] == "live_campaigns":
            return row["from"]
    existing = set(table_columns(conn, table))
    for candidate in ("campaign_id", "live_campaign_id", "live_id"):
        if candidate in existing:
            return candidate
    raise RuntimeError(f"{table} için kampanya bağlantı alanı bulunamadı.")


def child_count(conn: sqlite3.Connection, table: str) -> int:
    fk = campaign_fk(conn, table)
    return conn.execute(
        f'''SELECT COUNT(*) AS count
            FROM "{table}" AS child
            JOIN live_campaigns AS campaign
              ON campaign.id = child."{fk}"
            WHERE campaign.bank_name = ?
              AND campaign.is_current = 1''',
        (BANK,),
    ).fetchone()["count"]


def missing_child_count(conn: sqlite3.Connection, table: str) -> int:
    fk = campaign_fk(conn, table)
    return conn.execute(
        f'''SELECT COUNT(*) AS count
            FROM live_campaigns AS campaign
            WHERE campaign.bank_name = ?
              AND campaign.is_current = 1
              AND campaign.record_kind = 'campaign'
              AND campaign.comparison_eligible = 1
              AND NOT EXISTS (
                  SELECT 1 FROM "{table}" AS child
                  WHERE child."{fk}" = campaign.id
              )''',
        (BANK,),
    ).fetchone()["count"]


def duplicate_group_count(conn: sqlite3.Connection, table: str) -> int:
    fk = campaign_fk(conn, table)
    excluded = {"id", "created_at", "updated_at", "extracted_at"}
    columns = [c for c in table_columns(conn, table) if c not in excluded]
    rows = conn.execute(
        f'''SELECT child.*
            FROM "{table}" AS child
            JOIN live_campaigns AS campaign
              ON campaign.id = child."{fk}"
            WHERE campaign.bank_name = ?
              AND campaign.is_current = 1''',
        (BANK,),
    ).fetchall()
    groups = Counter(
        tuple(
            (column, "" if row[column] is None else str(row[column]))
            for column in sorted(columns)
        )
        for row in rows
    )
    return sum(1 for count in groups.values() if count > 1)


def main() -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    failures: list[str] = []

    try:
        rows = conn.execute(
            '''SELECT * FROM live_campaigns
               WHERE bank_name = ? AND is_current = 1
               ORDER BY title''',
            (BANK,),
        ).fetchall()

        total = len(rows)
        campaigns = sum(row["record_kind"] == "campaign" for row in rows)
        services = sum(
            row["record_kind"] == "service_information" for row in rows
        )
        eligible = sum(
            int(row["comparison_eligible"] or 0) == 1 for row in rows
        )
        categories = Counter(
            str(row["campaign_category"] or "NULL") for row in rows
        )
        statuses = Counter(
            str(row["current_status"] or "NULL") for row in rows
        )
        service_rows = [
            row for row in rows
            if row["record_kind"] == "service_information"
        ]
        actual_service_urls = {
            str(row["source_url"] or "") for row in service_rows
        }

        if total <= 0:
            failures.append("Dünya Katılım için güncel kayıt bulunamadı.")

        by_url = {str(row["source_url"] or ""): row for row in rows}
        known_service_misclassified = [
            url for url in SERVICE_URLS
            if url in by_url
            and by_url[url]["record_kind"] != "service_information"
        ]
        if known_service_misclassified:
            failures.append(
                "Bilinen hizmet URL'leri yanlış sınıflandırılmış: "
                + ", ".join(sorted(known_service_misclassified))
            )

        unknown_categories = sorted(
            category for category in categories
            if category not in ALLOWED_CATEGORIES
        )
        if unknown_categories:
            failures.append(
                "Beklenmeyen/unclassified kategori: "
                + ", ".join(unknown_categories)
            )

        invalid_kinds = [
            row for row in rows
            if row["record_kind"] not in {"campaign", "service_information"}
        ]
        if invalid_kinds:
            failures.append(
                "Beklenmeyen record_kind: "
                + ", ".join(
                    f"{row['title']}={row['record_kind']}"
                    for row in invalid_kinds[:5]
                )
            )

        for row in service_rows:
            if int(row["comparison_eligible"] or 0) != 0:
                failures.append(
                    f"Hizmet kaydı karşılaştırmaya açık: {row['title']}"
                )

        closed_campaigns = [
            row for row in rows
            if row["record_kind"] == "campaign"
            and int(row["comparison_eligible"] or 0) != 1
        ]
        if closed_campaigns:
            failures.append(
                "Gerçek kampanya karşılaştırmaya kapalı: "
                + ", ".join(str(row["title"]) for row in closed_campaigns[:5])
            )

        non_active = [
            row for row in rows
            if str(row["current_status"] or "") != "active"
        ]
        if non_active:
            failures.append(
                "is_current=1 olduğu halde active olmayan kayıt var: "
                + ", ".join(
                    f"{row['title']}={row['current_status']}"
                    for row in non_active[:5]
                )
            )

        benefits = child_count(conn, "live_campaign_benefits")
        audiences = child_count(conn, "live_campaign_audiences")
        finance = child_count(conn, "live_campaign_finance_details")
        missing_benefits = missing_child_count(
            conn, "live_campaign_benefits"
        )
        missing_audiences = missing_child_count(
            conn, "live_campaign_audiences"
        )
        duplicate_benefits = duplicate_group_count(
            conn, "live_campaign_benefits"
        )
        duplicate_audiences = duplicate_group_count(
            conn, "live_campaign_audiences"
        )

        # Toplam avantaj/hedef-kitle adetleri kampanya sayısıyla birlikte
        # değişebilir; tarihsel 41/46 sayıları artık bloklayıcı değildir.
        # Mükerrer kayıtlar ve Enerya finansman kaydının kaybolması ise
        # gerçek kalite hatasıdır.
        if duplicate_benefits:
            failures.append(
                f"duplicate_benefits: gerçek={duplicate_benefits}, beklenen=0"
            )
        if duplicate_audiences:
            failures.append(
                f"duplicate_audiences: gerçek={duplicate_audiences}, beklenen=0"
            )
        missing_finance = conn.execute(
            """
            SELECT COUNT(*) AS count
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
        ).fetchone()["count"]
        if missing_finance:
            failures.append(
                f"Finansman detayı eksik kampanya sayısı: {missing_finance}"
            )

        warnings: list[str] = []
        if missing_benefits:
            warnings.append(
                f"{missing_benefits} kampanyada yapılandırılmış avantaj kaydı yok."
            )
        if missing_audiences:
            warnings.append(
                f"{missing_audiences} kampanyada yapılandırılmış hedef kitle kaydı yok."
            )

        enerya = conn.execute(
            '''SELECT finance.*
               FROM live_campaign_finance_details AS finance
               JOIN live_campaigns AS campaign
                 ON campaign.id = finance.campaign_id
               WHERE campaign.bank_name = ?
                 AND campaign.source_url = ?
                 AND campaign.is_current = 1''',
            (BANK, ENERYA_URL),
        ).fetchone()

        finance_summary = None
        enerya_current = ENERYA_URL in by_url
        if enerya_current and enerya is None:
            failures.append("Enerya güncel olduğu halde finansman detayı bulunamadı.")
        elif enerya is not None:
            finance_summary = {key: enerya[key] for key in enerya.keys()}
            enerya_checks = {
                "profit_share_rate_min": (
                    enerya["profit_share_rate_min"], 0.0
                ),
                "profit_share_rate_max": (
                    enerya["profit_share_rate_max"], 0.0
                ),
                "financing_amount_min": (
                    enerya["financing_amount_min"], 6500.0
                ),
                "financing_amount_max": (
                    enerya["financing_amount_max"], 16500.0
                ),
                "maturity_min_months": (
                    enerya["maturity_min_months"], 2
                ),
                "maturity_max_months": (
                    enerya["maturity_max_months"], 6
                ),
            }
            for name, (actual, expected) in enerya_checks.items():
                if actual != expected:
                    failures.append(
                        f"Enerya {name}: gerçek={actual!r}, "
                        f"beklenen={expected!r}"
                    )

            expense = str(
                enerya["expense_status"] or ""
            ).strip().casefold()
            if expense not in {"", "belirtilmemiş", "belirtilmemis"}:
                failures.append(
                    f"Enerya masraf durumu hatalı: "
                    f"{enerya['expense_status']!r}"
                )

        report = {
            "bank": BANK,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "success": not failures,
            "current_records": total,
            "campaign_count": campaigns,
            "service_information_count": services,
            "comparison_eligible_count": eligible,
            "category_counts": dict(categories),
            "status_counts": dict(statuses),
            "benefit_count": benefits,
            "audience_count": audiences,
            "finance_count": finance,
            "missing_finance_count": missing_finance,
            "missing_benefit_count": missing_benefits,
            "missing_audience_count": missing_audiences,
            "duplicate_benefit_group_count": duplicate_benefits,
            "duplicate_audience_group_count": duplicate_audiences,
            "service_urls": sorted(actual_service_urls),
            "enerya_finance": finance_summary,
            "warnings": warnings,
            "failures": failures,
        }
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print("=" * 90)
        print("DÜNYA KATILIM SON KALİTE DENETİMİ")
        print("=" * 90)
        print("Güncel kayıt:", total)
        print("Gerçek kampanya:", campaigns)
        print("Hizmet bilgisi:", services)
        print("Karşılaştırmaya uygun:", eligible)
        print("Avantaj kaydı:", benefits)
        print("Hedef kitle kaydı:", audiences)
        print("Finansman detayı:", finance)
        print("Avantajı eksik kampanya:", missing_benefits)
        print("Hedef kitlesi eksik kampanya:", missing_audiences)
        print("Mükerrer avantaj grubu:", duplicate_benefits)
        print("Mükerrer hedef kitle grubu:", duplicate_audiences)
        if enerya is not None:
            print("Enerya: %0 kâr payı, 6.500-16.500 TL, 2-6 ay")
        else:
            print("Enerya: güncel listede yok")
        if warnings:
            print("Kalite uyarıları:")
            for warning in warnings:
                print(" -", warning)
        print("Rapor:", REPORT_PATH)

        if failures:
            print()
            print("BAŞARISIZ KONTROLLER:")
            for failure in failures:
                print("-", failure)
            return 1

        print()
        print("SONUÇ: BAŞARILI")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
