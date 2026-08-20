from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB = Path("data") / "campaigns.db"
DEFAULT_REPORT = Path("data") / "jury_readiness_audit_v4.json"


def present(value) -> bool:
    return value is not None and str(value).strip() not in {
        "",
        "None",
        "nan",
    }


def pct(found: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(found * 100.0 / total, 1)


def pct_text(value: float | None) -> str:
    if value is None:
        return "Ölçülemedi"
    return f"%{value}"


def snippet(
    text: str,
    match: re.Match | None,
    radius: int = 90,
) -> str:
    if not match:
        return ""

    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return re.sub(
        r"\s+",
        " ",
        text[start:end],
    ).strip()


POINT_REWARD_TERMS = (
    "worldpuan",
    "world puan",
    "altın puan",
    "altin puan",
    "parafpara",
    "paraf para",
    "bankkart lira",
)


def reward_signal_is_monetary(
    text: str,
    match: re.Match,
) -> bool:
    context = snippet(text, match, radius=80).casefold()
    return not any(term in context for term in POINT_REWARD_TERMS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise FileNotFoundError(args.db)

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    campaigns = con.execute(
        """
        SELECT
            id,
            bank_name,
            title,
            source_url,
            clean_text,
            campaign_category,
            record_kind,
            current_status,
            is_current
        FROM live_campaigns
        WHERE record_kind = 'campaign'
          AND is_current = 1
          AND current_status = 'active'
        ORDER BY bank_name, id
        """
    ).fetchall()

    finance = {
        int(row["campaign_id"]): row
        for row in con.execute(
            """
            SELECT *
            FROM live_campaign_finance_details
            """
        ).fetchall()
    }

    benefits: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in con.execute(
        """
        SELECT *
        FROM live_campaign_benefits
        """
    ).fetchall():
        benefits[int(row["campaign_id"])].append(row)

    standard_products = int(
        con.execute(
            """
            SELECT COUNT(*)
            FROM live_campaigns
            WHERE record_kind = 'standard_product'
              AND is_current = 1
            """
        ).fetchone()[0]
    )

    # Denominator: kaynak metninde ilgili alan için açık sinyal
    # bulunan güncel aktif kampanyalar.
    signals = {
        "profit_share": re.compile(
            r"(?:"
            r"%\s*\d+(?:[.,]\d+)?[^.!?]{0,45}"
            r"k[aâ]r\s*pay"
            r"|"
            r"k[aâ]r\s*pay[^.!?]{0,45}"
            r"%\s*\d+(?:[.,]\d+)?"
            r"|"
            r"%\s*\d+(?:[.,]\d+)?[^.!?]{0,35}"
            r"vade\s+fark"
            r"|"
            r"vade\s+fark[^.!?]{0,35}"
            r"%\s*\d+(?:[.,]\d+)?"
            r")",
            re.IGNORECASE,
        ),
        "financing_amount": re.compile(
            r"\d[\d.\s]*(?:,\d+)?\s*(?:TL|₺)"
            r"[^.!?]{0,70}(?:finansman|kredi)",
            re.IGNORECASE,
        ),
        "maturity": re.compile(
            r"(?:"
            r"\b\d{1,3}\s*ay(?:a)?\s+"
            r"(?:kadar\s+|varan\s+)?(?:vade|vadeli)"
            r"|"
            r"\bvade[^.!?]{0,40}\b\d{1,3}\s*ay"
            r")",
            re.IGNORECASE,
        ),
        "installment": re.compile(
            r"(?:"
            r"\b\d{1,3}\s*(?:eşit\s+)?taksit"
            r"|"
            r"\b\d{1,3}(?:\s*[-–—]\s*\d{1,3})+"
            r"\s*taksit"
            r")",
            re.IGNORECASE,
        ),
        "allocation_fee": re.compile(
            r"tahsis\s+ücreti",
            re.IGNORECASE,
        ),
        "expense": re.compile(
            r"\b(?:"
            r"masraf|komisyon|dosya\s+ücreti|"
            r"ekspertiz\s+ücreti|sigorta\s+ücreti"
            r")\b",
            re.IGNORECASE,
        ),
        "points": re.compile(
            r"\d[\d.\s]*(?:,\d+)?\s*(?:TL|₺)?"
            r"(?:\s*['’]\s*(?:e|a|ye|ya))?"
            r"(?:\s+kadar|\s+varan)?\s*"
            r"(?:"
            r"Worldpuan|WorldPuan|Altın\s+Puan|"
            r"ParafPara|Paraf\s+Para|Bankkart\s+Lira|puan"
            r")\b",
            re.IGNORECASE,
        ),
        "cashback_rate": re.compile(
            r"%\s*\d+(?:[.,]\d+)?"
            r"(?:['’]?(?:e|a|ye|ya))?"
            r"(?:\s+kadar|\s+varan)?"
            r"[^.!?]{0,35}(?:nakit\s+)?iade",
            re.IGNORECASE,
        ),
        "cashback_amount": re.compile(
            r"\d[\d.\s]*(?:,\d+)?\s*(?:TL|₺)"
            r"(?:['’]?(?:ye|ya|e|a))?"
            r"(?:\s+kadar|\s+varan)?"
            r"[^.!?]{0,35}(?:nakit\s+|harcama\s+)?iade",
            re.IGNORECASE,
        ),
        "discount_rate": re.compile(
            r"%\s*\d+(?:[.,]\d+)?"
            r"(?:['’]?(?:e|a|ye|ya))?"
            r"(?:\s+kadar|\s+varan)?"
            r"[^.!?]{0,35}indirim",
            re.IGNORECASE,
        ),
        "reward_amount": re.compile(
            r"\d[\d.\s]*(?:,\d+)?\s*(?:TL|₺)"
            r"(?:['’]?(?:ye|ya|e|a))?"
            r"(?:\s+kadar|\s+varan)?"
            r"[^.!?]{0,25}"
            r"(?:ödül|hediye|alışveriş\s+çeki)",
            re.IGNORECASE,
        ),
    }

    results = {}
    suspicious = []

    def evaluate(
        name: str,
        rows,
        extractor_ok,
        signal_filter=None,
    ) -> None:
        source_signal_count = 0
        extracted_count = 0
        pattern = signals[name]

        for row in rows:
            text = str(row["clean_text"] or "")
            match = pattern.search(text)

            if not match:
                continue

            if signal_filter is not None and not signal_filter(
                text,
                match,
            ):
                continue

            source_signal_count += 1
            ok = extractor_ok(row)

            if ok:
                extracted_count += 1
            else:
                suspicious.append(
                    {
                        "bank": row["bank_name"],
                        "title": row["title"],
                        "field": name,
                        "evidence": snippet(text, match),
                        "source_url": row["source_url"],
                    }
                )

        success = pct(
            extracted_count,
            source_signal_count,
        )

        results[name] = {
            "source_signal_count": source_signal_count,
            "extracted_count": extracted_count,
            "signal_based_success_percent": success,
        }

    finance_rows = [
        row
        for row in campaigns
        if row["campaign_category"] == "finance_campaign"
    ]

    evaluate(
        "profit_share",
        finance_rows,
        lambda row: (
            int(row["id"]) in finance
            and present(
                finance[int(row["id"])]["profit_share_rate_text"]
            )
        ),
    )

    evaluate(
        "financing_amount",
        finance_rows,
        lambda row: (
            int(row["id"]) in finance
            and present(
                finance[int(row["id"])]["financing_amount_text"]
            )
        ),
    )

    evaluate(
        "maturity",
        finance_rows,
        lambda row: (
            int(row["id"]) in finance
            and present(
                finance[int(row["id"])]["maturity_text"]
            )
        ),
    )

    evaluate(
        "installment",
        finance_rows,
        lambda row: (
            int(row["id"]) in finance
            and present(
                finance[int(row["id"])]["installment_count"]
            )
        ),
    )

    evaluate(
        "allocation_fee",
        finance_rows,
        lambda row: (
            int(row["id"]) in finance
            and (
                present(
                    finance[int(row["id"])]["allocation_fee_status"]
                )
                or present(
                    finance[int(row["id"])]["allocation_fee_amount"]
                )
                or present(
                    finance[int(row["id"])]["allocation_fee_rate"]
                )
            )
        ),
    )

    evaluate(
        "expense",
        finance_rows,
        lambda row: (
            int(row["id"]) in finance
            and (
                present(
                    finance[int(row["id"])]["expense_status"]
                )
                or present(
                    finance[int(row["id"])]["expense_details"]
                )
            )
        ),
    )

    point_rows = [
        row
        for row in campaigns
        if row["campaign_category"] == "points_campaign"
    ]

    evaluate(
        "points",
        point_rows,
        lambda row: any(
            benefit["benefit_type"] == "shopping_points"
            and present(benefit["points"])
            for benefit in benefits[int(row["id"])]
        ),
    )

    discount_rows = [
        row
        for row in campaigns
        if row["campaign_category"] == "discount_campaign"
    ]

    evaluate(
        "cashback_rate",
        discount_rows,
        lambda row: any(
            benefit["benefit_type"] == "cashback"
            and present(benefit["rate"])
            for benefit in benefits[int(row["id"])]
        ),
    )

    evaluate(
        "cashback_amount",
        discount_rows,
        lambda row: any(
            benefit["benefit_type"] == "cashback"
            and present(benefit["amount"])
            for benefit in benefits[int(row["id"])]
        ),
    )

    evaluate(
        "discount_rate",
        discount_rows,
        lambda row: any(
            benefit["benefit_type"] == "discount"
            and present(benefit["rate"])
            for benefit in benefits[int(row["id"])]
        ),
    )

    evaluate(
        "reward_amount",
        campaigns,
        lambda row: any(
            benefit["benefit_type"] == "reward"
            and present(benefit["amount"])
            for benefit in benefits[int(row["id"])]
        ),
        signal_filter=reward_signal_is_monetary,
    )

    report = {
        "generated_at": (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
        ),
        "active_campaign_count": len(campaigns),
        "finance_campaign_count": len(finance_rows),
        "points_campaign_count": len(point_rows),
        "discount_campaign_count": len(discount_rows),
        "current_standard_product_count": standard_products,
        "signal_based_extraction": results,
        "suspicious_count": len(suspicious),
        "suspicious": suspicious,
    }

    args.report.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    args.report.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    labels = {
        "profit_share": "Kâr payı / vade farkı oranı",
        "financing_amount": "Finansman tutarı",
        "maturity": "Vade",
        "installment": "Taksit",
        "allocation_fee": "Tahsis ücreti",
        "expense": "Masraf / komisyon",
        "points": "Sayısal puan",
        "cashback_rate": "Nakit iade oranı",
        "cashback_amount": "Nakit iade tutarı",
        "discount_rate": "İndirim oranı",
        "reward_amount": "Ödül / hediye tutarı",
    }

    print("=" * 80)
    print(
        "JÜRİ HAZIRLIK DENETİMİ V4 — "
        "SİNYAL BAZLI"
    )
    print("=" * 80)
    print("Aktif kampanya:", len(campaigns))
    print("Finansman kampanyası:", len(finance_rows))
    print("Puan kampanyası:", len(point_rows))
    print("İndirim kampanyası:", len(discount_rows))
    print("Güncel standart ürün:", standard_products)

    print()
    print(
        "KAYNAKTA AÇIK SİNYAL BULUNAN "
        "KAYITLARDA ÇIKARIM BAŞARISI"
    )

    for key, item in results.items():
        success_text = pct_text(
            item["signal_based_success_percent"]
        )
        print(
            f"- {labels[key]}: "
            f"{item['extracted_count']}/"
            f"{item['source_signal_count']} "
            f"({success_text})"
        )

    print()
    print("Gerçek inceleme adayı:", len(suspicious))

    for item in suspicious[:50]:
        print(
            f"- {item['bank']} | "
            f"{item['title']} | "
            f"{labels.get(item['field'], item['field'])}"
        )
        print("  Kanıt:", item["evidence"])

    print()
    print("Rapor:", args.report)

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
