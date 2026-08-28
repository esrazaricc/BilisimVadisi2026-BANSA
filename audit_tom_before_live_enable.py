from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "data" / "campaigns.db"
REPORT_PATH = PROJECT_ROOT / "data" / "tom_before_live_enable_audit.json"
BANK = "T.O.M. Katılım"


STRONG_FINANCE_TERMS = (
    "taksitli alışveriş kredisi",
    "taksitli alisveris kredisi",
    "mağazadan alışveriş kredisi",
    "magazadan alisveris kredisi",
    "taksitli sağlık kredisi",
    "taksitli saglik kredisi",
    "sağlık kredisi",
    "saglik kredisi",
    "taksitli kredi",
    "hadi veresiye",
)

CARD_TERMS = (
    "kredi kartı",
    "kredi karti",
    "hadi black",
    "hadi kart",
)

TOM_REWARD_PROMO_TERMS = (
    "kazan",
    "nakit iade",
    "hediye bakiye",
    "ödül",
    "odul",
    "vade farkın bizden",
    "vade farkin bizden",
)


def is_intentional_tom_nonfinance(title: str) -> bool:
    key = fold(title)
    if "hadi veresiye" not in key:
        return False

    return any(
        fold(term) in key
        for term in TOM_REWARD_PROMO_TERMS
    )


def fold(value: str) -> str:
    table = str.maketrans(
        {
            "Ç": "c", "ç": "c",
            "Ğ": "g", "ğ": "g",
            "İ": "i", "I": "i", "ı": "i",
            "Ö": "o", "ö": "o",
            "Ş": "s", "ş": "s",
            "Ü": "u", "ü": "u",
        }
    )
    value = (value or "").translate(table).casefold()
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_title(value: str) -> str:
    value = fold(value)
    value = value.replace("| tom bank hadi", "")
    value = re.sub(
        r"\(?\s*gecm(?:is|si)\s+kampanya\s*\)?",
        "",
        value,
    )
    value = re.sub(r"[^a-z0-9%]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonical_url(value: str) -> str:
    parts = urlsplit(value or "")
    path = re.sub(r"/+", "/", parts.path or "/").rstrip("/")
    return urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            path,
            "",
            "",
        )
    )


def parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def main() -> int:
    if not DB_PATH.exists():
        raise FileNotFoundError(DB_PATH)

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT
                c.id,
                c.title,
                c.source_url,
                c.start_date,
                c.end_date,
                c.current_status,
                c.is_current,
                c.record_kind,
                c.campaign_category,
                c.comparison_eligible,
                f.finance_type,
                f.profit_share_rate_min,
                f.profit_share_rate_max,
                f.profit_share_rate_text,
                f.financing_amount_min,
                f.financing_amount_max,
                f.financing_amount_text,
                f.maturity_min_months,
                f.maturity_max_months,
                f.maturity_text,
                f.installment_count,
                f.campaign_advantage,
                f.extraction_confidence
            FROM live_campaigns AS c
            LEFT JOIN live_campaign_finance_details AS f
              ON f.campaign_id = c.id
            WHERE c.bank_name = ?
            ORDER BY c.id
            """,
            (BANK,),
        ).fetchall()
    finally:
        con.close()

    if not rows:
        raise RuntimeError("T.O.M. Katılım DB kaydı bulunamadı.")

    today = date.today()

    status_counts = Counter(
        str(row["current_status"] or "unknown") for row in rows
    )
    category_counts = Counter(
        str(row["campaign_category"] or "unclassified") for row in rows
    )

    upcoming = []
    date_inconsistencies = []
    date_order_errors = []
    finance_rows = []
    weak_finance = []
    possible_missed_finance = []
    possible_card_false_positive = []

    title_groups: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        title_groups[normalize_title(str(row["title"] or ""))].append(row)

        start = parse_iso(row["start_date"])
        end = parse_iso(row["end_date"])
        status = str(row["current_status"] or "unknown")

        if start and end and start > end:
            date_order_errors.append(
                {
                    "title": row["title"],
                    "start_date": row["start_date"],
                    "end_date": row["end_date"],
                    "status": status,
                    "url": row["source_url"],
                }
            )

        if status == "upcoming":
            upcoming.append(
                {
                    "title": row["title"],
                    "start_date": row["start_date"],
                    "end_date": row["end_date"],
                    "url": row["source_url"],
                }
            )

        expected = None
        if end and end < today:
            expected = "expired"
        elif start and start > today:
            expected = "upcoming"
        elif start or end:
            expected = "active"

        if expected and status != expected:
            date_inconsistencies.append(
                {
                    "title": row["title"],
                    "stored_status": status,
                    "date_expected": expected,
                    "start_date": row["start_date"],
                    "end_date": row["end_date"],
                    "url": row["source_url"],
                }
            )

        title_fold = fold(str(row["title"] or ""))
        category = str(row["campaign_category"] or "")

        if category == "finance_campaign":
            item = {
                "title": row["title"],
                "status": status,
                "finance_type": row["finance_type"],
                "profit_share_rate": row["profit_share_rate_text"],
                "amount": row["financing_amount_text"],
                "maturity": row["maturity_text"],
                "installment_count": row["installment_count"],
                "confidence": row["extraction_confidence"],
                "url": row["source_url"],
            }
            finance_rows.append(item)

            key_field_count = sum(
                [
                    row["profit_share_rate_text"] is not None,
                    row["financing_amount_text"] is not None,
                    row["maturity_text"] is not None,
                    row["installment_count"] is not None,
                ]
            )
            if key_field_count == 0:
                weak_finance.append(item)

            # Kart başlığı olup gerçek kredi/finansman kelimesi taşımıyorsa
            # olası false-positive olarak manuel kontrolde göster.
            if (
                any(term in title_fold for term in CARD_TERMS)
                and not any(
                    fold(term) in title_fold
                    for term in STRONG_FINANCE_TERMS
                )
            ):
                possible_card_false_positive.append(item)

        elif (
            any(
                fold(term) in title_fold
                for term in STRONG_FINANCE_TERMS
            )
            and not is_intentional_tom_nonfinance(
                str(row["title"] or "")
            )
        ):
            possible_missed_finance.append(
                {
                    "title": row["title"],
                    "category": category,
                    "status": status,
                    "url": row["source_url"],
                }
            )

    duplicate_title_groups = []
    for normalized, group in title_groups.items():
        if normalized and len(group) > 1:
            duplicate_title_groups.append(
                {
                    "normalized_title": normalized,
                    "count": len(group),
                    "items": [
                        {
                            "title": row["title"],
                            "status": row["current_status"],
                            "url": row["source_url"],
                        }
                        for row in group
                    ],
                }
            )

    duplicate_url_groups = []
    url_groups: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        url_groups[canonical_url(str(row["source_url"] or ""))].append(row)
    for normalized, group in url_groups.items():
        if normalized and len(group) > 1:
            duplicate_url_groups.append(
                {
                    "url": normalized,
                    "count": len(group),
                    "titles": [row["title"] for row in group],
                }
            )

    report = {
        "bank_name": BANK,
        "audit_date": today.isoformat(),
        "total_records": len(rows),
        "status_counts": dict(status_counts),
        "category_counts": dict(category_counts),
        "upcoming": upcoming,
        "date_inconsistencies": date_inconsistencies,
        "date_order_error_count": len(date_order_errors),
        "date_order_errors": date_order_errors,
        "finance_count": len(finance_rows),
        "weak_finance_count": len(weak_finance),
        "weak_finance": weak_finance,
        "possible_card_false_positive_count": len(
            possible_card_false_positive
        ),
        "possible_card_false_positive": possible_card_false_positive,
        "possible_missed_finance_count": len(possible_missed_finance),
        "possible_missed_finance": possible_missed_finance,
        "duplicate_title_group_count": len(duplicate_title_groups),
        "duplicate_title_groups": duplicate_title_groups,
        "duplicate_url_group_count": len(duplicate_url_groups),
        "duplicate_url_groups": duplicate_url_groups,
        "finance_rows": finance_rows,
    }

    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("=" * 78)
    print("T.O.M. KATILIM — CANLI OTOMASYON ÖNCESİ SON DENETİM")
    print("=" * 78)
    print("Toplam kayıt:", len(rows))
    print("Durumlar:", dict(status_counts))
    print("Kategoriler:", dict(category_counts))
    print("Finansman kampanyası:", len(finance_rows))
    print("Finansman olup ana alanı hiç çıkmayan:", len(weak_finance))
    print(
        "Kart kampanyası olabilecek finance false-positive:",
        len(possible_card_false_positive),
    )
    print(
        "Finance dışında kalmış güçlü kredi başlığı:",
        len(possible_missed_finance),
    )
    print("Aynı başlık grubu:", len(duplicate_title_groups))
    print("Mükerrer URL grubu:", len(duplicate_url_groups))
    print("Tarih/durum tutarsızlığı:", len(date_inconsistencies))
    print("Başlangıç > bitiş tarih hatası:", len(date_order_errors))

    if date_order_errors:
        print("\nGEÇERSİZ TARİH SIRASI")
        for item in date_order_errors:
            print(
                f"- {item['title']} | "
                f"{item['start_date']} -> {item['end_date']}"
            )
            print("  ", item["url"])

    print("\nUPCOMING KAYITLAR")
    if not upcoming:
        print("- Yok")
    else:
        for item in upcoming:
            print(
                f"- {item['title']} | "
                f"{item['start_date']} -> {item['end_date']}"
            )
            print("  ", item["url"])

    print("\nANA ALANI BOŞ FINANCE KAYITLARI")
    if not weak_finance:
        print("- Yok")
    else:
        for item in weak_finance:
            print("-", item["title"])
            print("  ", item["url"])

    print("\nOLASI KART/FİNANSMAN FALSE-POSITIVE")
    if not possible_card_false_positive:
        print("- Yok")
    else:
        for item in possible_card_false_positive:
            print("-", item["title"])
            print("  ", item["url"])

    print("\nOLASI EKSİK FINANCE SINIFLANDIRMASI")
    if not possible_missed_finance:
        print("- Yok")
    else:
        for item in possible_missed_finance:
            print(
                f"- [{item['category']}] {item['title']}"
            )
            print("  ", item["url"])

    print("\nAYNI BAŞLIK GRUPLARI")
    if not duplicate_title_groups:
        print("- Yok")
    else:
        for group in duplicate_title_groups:
            print(
                f"- {group['count']}x: "
                f"{group['normalized_title']}"
            )
            for item in group["items"]:
                print(
                    f"    [{item['status']}] "
                    f"{item['url']}"
                )

    print("\nRapor:", REPORT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
