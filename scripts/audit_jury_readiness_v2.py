from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB = Path("data") / "campaigns.db"
DEFAULT_REPORT = Path("data") / "jury_readiness_audit_v2.json"


def present(value) -> bool:
    return value is not None and str(value).strip() not in {"", "None", "nan"}


def pct(found: int, total: int) -> float:
    return round(found * 100.0 / total, 1) if total else 100.0


def snippet(text: str, match: re.Match | None, radius: int = 90) -> str:
    if not match:
        return ""
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    campaigns = con.execute(
        """
        SELECT id, bank_name, title, source_url, clean_text,
               campaign_category, record_kind, current_status, is_current
        FROM live_campaigns
        WHERE record_kind = 'campaign'
          AND is_current = 1
          AND current_status = 'active'
        ORDER BY bank_name, id
        """
    ).fetchall()

    finance = {
        int(r["campaign_id"]): r
        for r in con.execute(
            "SELECT * FROM live_campaign_finance_details"
        ).fetchall()
    }
    benefits = defaultdict(list)
    for row in con.execute(
        "SELECT * FROM live_campaign_benefits"
    ).fetchall():
        benefits[int(row["campaign_id"])].append(row)

    standard_products = con.execute(
        """
        SELECT COUNT(*)
        FROM live_campaigns
        WHERE record_kind = 'standard_product'
          AND is_current = 1
        """
    ).fetchone()[0]

    # Her metrik için denominator = kaynak metninde açık sinyal bulunan kayıtlar.
    signals = {
        "profit_share": re.compile(
            r"(?:%\\s*\\d+(?:[.,]\\d+)?[^.!?]{0,45}k[aâ]r\\s*pay"
            r"|k[aâ]r\\s*pay[^.!?]{0,45}%\\s*\\d+(?:[.,]\\d+)?"
            r"|%\\s*\\d+(?:[.,]\\d+)?[^.!?]{0,35}vade\\s+fark"
            r"|vade\\s+fark[^.!?]{0,35}%\\s*\\d+(?:[.,]\\d+)?)",
            re.I,
        ),
        "financing_amount": re.compile(
            r"\\d[\\d.\\s]*(?:,\\d+)?\\s*(?:TL|₺)"
            r"[^.!?]{0,70}(?:finansman|kredi)",
            re.I,
        ),
        "maturity": re.compile(
            r"\\b\\d{1,3}\\s*ay(?:a)?\\s+"
            r"(?:kadar\\s+|varan\\s+)?(?:vade|vadeli)"
            r"|\\bvade[^.!?]{0,40}\\b\\d{1,3}\\s*ay",
            re.I,
        ),
        "installment": re.compile(
            r"\\b\\d{1,3}\\s*(?:eşit\\s+)?taksit"
            r"|\\b\\d{1,3}(?:\\s*[-–—]\\s*\\d{1,3})+\\s*taksit",
            re.I,
        ),
        "allocation_fee": re.compile(r"tahsis\\s+ücreti", re.I),
        "expense": re.compile(
            r"\\b(?:masraf|komisyon|dosya\\s+ücreti|"
            r"ekspertiz\\s+ücreti|sigorta\\s+ücreti)\\b",
            re.I,
        ),
        "points": re.compile(
            r"\\d[\\d.\\s]*(?:,\\d+)?\\s*(?:TL|₺)?\\s*"
            r"(?:Worldpuan|WorldPuan|Altın\\s+Puan|"
            r"ParafPara|Paraf\\s+Para|Bankkart\\s+Lira|puan)\\b",
            re.I,
        ),
        "cashback_rate": re.compile(
            r"%\\s*\\d+(?:[.,]\\d+)?"
            r"(?:['’]?(?:e|a|ye|ya))?"
            r"(?:\\s+kadar|\\s+varan)?[^.!?]{0,35}"
            r"(?:nakit\\s+)?iade",
            re.I,
        ),
        "cashback_amount": re.compile(
            r"\\d[\\d.\\s]*(?:,\\d+)?\\s*(?:TL|₺)"
            r"(?:['’]?(?:ye|ya|e|a))?"
            r"(?:\\s+kadar|\\s+varan)?[^.!?]{0,35}"
            r"(?:nakit\\s+|harcama\\s+)?iade",
            re.I,
        ),
        "discount_rate": re.compile(
            r"%\\s*\\d+(?:[.,]\\d+)?"
            r"(?:['’]?(?:e|a|ye|ya))?"
            r"(?:\\s+kadar|\\s+varan)?[^.!?]{0,35}indirim",
            re.I,
        ),
        "reward_amount": re.compile(
            r"\\d[\\d.\\s]*(?:,\\d+)?\\s*(?:TL|₺)"
            r"(?:['’]?(?:ye|ya|e|a))?"
            r"(?:\\s+kadar|\\s+varan)?[^.!?]{0,25}"
            r"(?:ödül|hediye|alışveriş\\s+çeki)",
            re.I,
        ),
    }

    results = {}
    suspicious = []

    def evaluate(name, rows, extractor_ok):
        found_signal = 0
        extracted = 0
        pattern = signals[name]

        for row in rows:
            text = str(row["clean_text"] or "")
            match = pattern.search(text)
            if not match:
                continue
            found_signal += 1
            ok = extractor_ok(row)
            if ok:
                extracted += 1
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

        results[name] = {
            "source_signal_count": found_signal,
            "extracted_count": extracted,
            "signal_based_success_percent": pct(
                extracted, found_signal
            ),
        }

    finance_rows = [
        r for r in campaigns
        if r["campaign_category"] == "finance_campaign"
    ]

    evaluate(
        "profit_share",
        finance_rows,
        lambda r: (
            int(r["id"]) in finance
            and present(finance[int(r["id"])]["profit_share_rate_text"])
        ),
    )
    evaluate(
        "financing_amount",
        finance_rows,
        lambda r: (
            int(r["id"]) in finance
            and present(finance[int(r["id"])]["financing_amount_text"])
        ),
    )
    evaluate(
        "maturity",
        finance_rows,
        lambda r: (
            int(r["id"]) in finance
            and present(finance[int(r["id"])]["maturity_text"])
        ),
    )
    evaluate(
        "installment",
        finance_rows,
        lambda r: (
            int(r["id"]) in finance
            and present(finance[int(r["id"])]["installment_count"])
        ),
    )
    evaluate(
        "allocation_fee",
        finance_rows,
        lambda r: (
            int(r["id"]) in finance
            and (
                present(finance[int(r["id"])]["allocation_fee_status"])
                or present(finance[int(r["id"])]["allocation_fee_amount"])
                or present(finance[int(r["id"])]["allocation_fee_rate"])
            )
        ),
    )
    evaluate(
        "expense",
        finance_rows,
        lambda r: (
            int(r["id"]) in finance
            and (
                present(finance[int(r["id"])]["expense_status"])
                or present(finance[int(r["id"])]["expense_details"])
            )
        ),
    )

    point_rows = [
        r for r in campaigns
        if r["campaign_category"] == "points_campaign"
    ]
    evaluate(
        "points",
        point_rows,
        lambda r: any(
            b["benefit_type"] == "shopping_points"
            and present(b["points"])
            for b in benefits[int(r["id"])]
        ),
    )

    discount_rows = [
        r for r in campaigns
        if r["campaign_category"] == "discount_campaign"
    ]
    evaluate(
        "cashback_rate",
        discount_rows,
        lambda r: any(
            b["benefit_type"] == "cashback"
            and present(b["rate"])
            for b in benefits[int(r["id"])]
        ),
    )
    evaluate(
        "cashback_amount",
        discount_rows,
        lambda r: any(
            b["benefit_type"] == "cashback"
            and present(b["amount"])
            for b in benefits[int(r["id"])]
        ),
    )
    evaluate(
        "discount_rate",
        discount_rows,
        lambda r: any(
            b["benefit_type"] == "discount"
            and present(b["rate"])
            for b in benefits[int(r["id"])]
        ),
    )

    # Reward kategoriden bağımsız değerlendirilir. Sadece gerçekten
    # "TL + ödül/hediye/çek" sinyali bulunan kayıtlar denominator'dır.
    evaluate(
        "reward_amount",
        campaigns,
        lambda r: any(
            b["benefit_type"] == "reward"
            and present(b["amount"])
            for b in benefits[int(r["id"])]
        ),
    )

    report = {
        "generated_at": (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
        ),
        "active_campaign_count": len(campaigns),
        "current_standard_product_count": int(standard_products),
        "signal_based_extraction": results,
        "suspicious_count": len(suspicious),
        "suspicious": suspicious,
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
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
    print("JÜRİ HAZIRLIK DENETİMİ V2 — SİNYAL BAZLI")
    print("=" * 80)
    print("Aktif kampanya:", len(campaigns))
    print("Güncel standart ürün:", standard_products)
    print()
    print("KAYNAKTA AÇIK SİNYAL BULUNAN KAYITLARDA ÇIKARIM BAŞARISI")
    for key, item in results.items():
        print(
            f"- {labels[key]}: "
            f"{item['extracted_count']}/"
            f"{item['source_signal_count']} "
            f"(%{item['signal_based_success_percent']})"
        )

    print()
    print("Gerçek inceleme adayı:", len(suspicious))
    for item in suspicious[:40]:
        print(
            f"- {item['bank']} | {item['title']} | "
            f"{labels.get(item['field'], item['field'])}"
        )
        print("  Kanıt:", item["evidence"])

    print()
    print("Rapor:", args.report)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
