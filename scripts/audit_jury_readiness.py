from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB = Path("data") / "campaigns.db"
DEFAULT_REPORT = Path("data") / "jury_readiness_audit.json"


def has_table(connection: sqlite3.Connection, name: str) -> bool:
    return (
        connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type IN ('table', 'view') AND name = ?
            LIMIT 1
            """,
            (name,),
        ).fetchone()
        is not None
    )


def pct(found: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(found * 100.0 / total, 1)


def present(value) -> bool:
    return value is not None and str(value).strip() != ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Jüri öncesi yapılandırılmış veri, extraction ve "
            "standart ürün kapsamını salt-okunur biçimde denetler."
        )
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise FileNotFoundError(args.db)

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row

    if not has_table(connection, "live_campaigns"):
        raise RuntimeError("live_campaigns tablosu bulunamadı.")

    campaigns = connection.execute(
        """
        SELECT
            id,
            bank_name,
            title,
            campaign_category,
            record_kind,
            current_status,
            is_current,
            clean_text,
            source_url
        FROM live_campaigns
        ORDER BY bank_name, id
        """
    ).fetchall()

    current_campaigns = [
        row
        for row in campaigns
        if row["record_kind"] == "campaign"
        and int(row["is_current"] or 0) == 1
        and row["current_status"] == "active"
    ]
    standard_products = [
        row
        for row in campaigns
        if row["record_kind"] == "standard_product"
        and int(row["is_current"] or 0) == 1
    ]

    finance_by_id = {}
    if has_table(connection, "live_campaign_finance_details"):
        for row in connection.execute(
            "SELECT * FROM live_campaign_finance_details"
        ):
            finance_by_id[int(row["campaign_id"])] = row

    benefits_by_id: dict[int, list[sqlite3.Row]] = defaultdict(list)
    if has_table(connection, "live_campaign_benefits"):
        for row in connection.execute(
            "SELECT * FROM live_campaign_benefits"
        ):
            benefits_by_id[int(row["campaign_id"])].append(row)

    finance_rows = [
        row
        for row in current_campaigns
        if row["campaign_category"] == "finance_campaign"
    ]

    finance_fields = {
        "profit_share_rate": (
            "profit_share_rate_text",
            "Kâr payı oranı",
        ),
        "financing_amount": (
            "financing_amount_text",
            "Finansman tutarı",
        ),
        "maturity": ("maturity_text", "Vade"),
        "installment": ("installment_count", "Taksit"),
        "allocation_fee": (
            "allocation_fee_status",
            "Tahsis ücreti",
        ),
        "expense": ("expense_status", "Masraf"),
    }

    finance_coverage = {}
    for key, (column, label) in finance_fields.items():
        found = sum(
            1
            for campaign in finance_rows
            if campaign["id"] in finance_by_id
            and present(finance_by_id[campaign["id"]][column])
        )
        finance_coverage[key] = {
            "label": label,
            "found": found,
            "total": len(finance_rows),
            "coverage_percent": pct(found, len(finance_rows)),
        }

    benefit_expectations = {
        "points_campaign": "shopping_points",
        "discount_campaign": "discount",
    }

    category_coverage = {}
    suspicious: list[dict] = []

    for category, benefit_type in benefit_expectations.items():
        rows = [
            row
            for row in current_campaigns
            if row["campaign_category"] == category
        ]
        found = sum(
            1
            for row in rows
            if any(
                benefit["benefit_type"] == benefit_type
                and (
                    present(benefit["amount"])
                    or present(benefit["rate"])
                    or present(benefit["points"])
                    or present(benefit["description"])
                )
                for benefit in benefits_by_id.get(row["id"], [])
            )
        )
        category_coverage[category] = {
            "expected_benefit_type": benefit_type,
            "found": found,
            "total": len(rows),
            "coverage_percent": pct(found, len(rows)),
        }

    rate_hint = re.compile(
        r"%\s*\d+(?:[.,]\d+)?[^.!?]{0,50}k[aâ]r\s*pay",
        re.IGNORECASE,
    )
    reward_hint = re.compile(
        r"\d[\d.\s]*(?:,\d+)?\s*(?:TL|₺)"
        r"[^.!?]{0,55}(?:ödül|hediye|çek)",
        re.IGNORECASE,
    )
    discount_hint = re.compile(
        r"%\s*\d+(?:[.,]\d+)?[^.!?]{0,55}"
        r"(?:indirim|iade)",
        re.IGNORECASE,
    )
    points_hint = re.compile(
        r"\d[\d.\s]*(?:,\d+)?\s*(?:TL|₺)?\s*"
        r"(?:Worldpuan|WorldPuan|Altın Puan|puan)",
        re.IGNORECASE,
    )

    for row in current_campaigns:
        text = str(row["clean_text"] or "")
        cid = int(row["id"])
        finance = finance_by_id.get(cid)
        benefits = benefits_by_id.get(cid, [])

        if (
            row["campaign_category"] == "finance_campaign"
            and rate_hint.search(text)
            and (
                finance is None
                or not present(finance["profit_share_rate_text"])
            )
        ):
            suspicious.append(
                {
                    "campaign_id": cid,
                    "bank": row["bank_name"],
                    "title": row["title"],
                    "field": "Kâr payı oranı",
                    "reason": (
                        "Metinde oran+kâr payı sinyali var, "
                        "yapılandırılmış alan boş."
                    ),
                    "source_url": row["source_url"],
                }
            )

        if reward_hint.search(text):
            has_reward = any(
                b["benefit_type"] == "reward"
                and present(b["amount"])
                for b in benefits
            )
            if not has_reward:
                suspicious.append(
                    {
                        "campaign_id": cid,
                        "bank": row["bank_name"],
                        "title": row["title"],
                        "field": "Ödül Tutarı",
                        "reason": (
                            "Metinde TL + ödül/hediye sinyali var, "
                            "reward amount çıkarılmamış."
                        ),
                        "source_url": row["source_url"],
                    }
                )

        if discount_hint.search(text):
            has_discount = any(
                b["benefit_type"] in {"discount", "cashback"}
                and present(b["rate"])
                for b in benefits
            )
            if not has_discount:
                suspicious.append(
                    {
                        "campaign_id": cid,
                        "bank": row["bank_name"],
                        "title": row["title"],
                        "field": "İndirim / İade Oranı",
                        "reason": (
                            "Metinde yüzde indirim/iade sinyali var, "
                            "oran çıkarılmamış."
                        ),
                        "source_url": row["source_url"],
                    }
                )

        if points_hint.search(text):
            has_points = any(
                b["benefit_type"] == "shopping_points"
                and present(b["points"])
                for b in benefits
            )
            if not has_points:
                suspicious.append(
                    {
                        "campaign_id": cid,
                        "bank": row["bank_name"],
                        "title": row["title"],
                        "field": "Alışveriş Puanı",
                        "reason": (
                            "Metinde sayısal puan sinyali var, "
                            "points alanı çıkarılmamış."
                        ),
                        "source_url": row["source_url"],
                    }
                )

    by_bank = defaultdict(
        lambda: {
            "active_campaigns": 0,
            "standard_products": 0,
        }
    )
    for row in current_campaigns:
        by_bank[row["bank_name"]]["active_campaigns"] += 1
    for row in standard_products:
        by_bank[row["bank_name"]]["standard_products"] += 1

    report = {
        "generated_at": (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
        ),
        "database": str(args.db),
        "active_campaign_count": len(current_campaigns),
        "current_standard_product_count": len(standard_products),
        "by_bank": dict(sorted(by_bank.items())),
        "finance_campaign_count": len(finance_rows),
        "finance_field_coverage": finance_coverage,
        "benefit_category_coverage": category_coverage,
        "suspicious_missing_extractions_count": len(suspicious),
        "suspicious_missing_extractions": suspicious,
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 80)
    print("JÜRİ HAZIRLIK VERİ DENETİMİ")
    print("=" * 80)
    print("Aktif kampanya:", len(current_campaigns))
    print(
        "Güncel standart ürün:",
        len(standard_products),
    )
    print()

    print("FİNANSMAN ALAN KAPSAMI")
    for item in finance_coverage.values():
        print(
            f"- {item['label']}: "
            f"{item['found']}/{item['total']} "
            f"(%{item['coverage_percent']})"
        )

    print()
    print("KAMPANYA FAYDA KAPSAMI")
    for category, item in category_coverage.items():
        print(
            f"- {category}: "
            f"{item['found']}/{item['total']} "
            f"(%{item['coverage_percent']})"
        )

    print()
    print(
        "Metinde sinyal olup yapılandırılmış alanı boş "
        "görünen kayıt:",
        len(suspicious),
    )
    for item in suspicious[:30]:
        print(
            f"- {item['bank']} | {item['title']} "
            f"| {item['field']}"
        )

    print()
    print("Rapor:", args.report)

    connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
