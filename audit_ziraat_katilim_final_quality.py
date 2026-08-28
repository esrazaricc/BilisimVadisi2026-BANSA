from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "campaigns.db"

TEXT_REPORT = (
    ROOT / "data" / "ziraat_katilim_final_quality_audit.txt"
)
JSON_REPORT = (
    ROOT / "data" / "ziraat_katilim_final_quality_audit.json"
)

BANK = "Ziraat Katılım"

EXPECTED_DISTRIBUTION = {
    "card_campaign": 56,
    "discount_campaign": 10,
    "points_campaign": 5,
    "new_customer_campaign": 1,
}

EXPECTED_TOTALS = {
    "campaigns": 72,
    "benefits": 87,
    "audiences": 121,
}


def main() -> int:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Veritabanı bulunamadı: {DB_PATH}"
        )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        campaigns = conn.execute(
            """
            SELECT
                id,
                title,
                source_url,
                campaign_category
            FROM live_campaigns
            WHERE bank_name = ?
              AND is_current = 1
            ORDER BY title
            """,
            (BANK,),
        ).fetchall()

        benefits = conn.execute(
            """
            SELECT
                b.id,
                b.campaign_id,
                b.benefit_type,
                b.amount,
                b.rate,
                b.points,
                b.minimum_spending,
                b.maximum_benefit,
                b.description,
                b.evidence
            FROM live_campaign_benefits b
            JOIN live_campaigns c
              ON c.id = b.campaign_id
            WHERE c.bank_name = ?
              AND c.is_current = 1
            ORDER BY b.campaign_id, b.id
            """,
            (BANK,),
        ).fetchall()

        audiences = conn.execute(
            """
            SELECT
                a.id,
                a.campaign_id,
                a.audience_type,
                a.audience_label,
                a.details
            FROM live_campaign_audiences a
            JOIN live_campaigns c
              ON c.id = a.campaign_id
            WHERE c.bank_name = ?
              AND c.is_current = 1
            ORDER BY a.campaign_id, a.id
            """,
            (BANK,),
        ).fetchall()

        campaign_map = {
            row["id"]: dict(row)
            for row in campaigns
        }

        benefit_counts = Counter(
            row["campaign_id"]
            for row in benefits
        )
        audience_counts = Counter(
            row["campaign_id"]
            for row in audiences
        )

        missing_benefits = [
            dict(row)
            for row in campaigns
            if benefit_counts[row["id"]] == 0
        ]
        missing_audiences = [
            dict(row)
            for row in campaigns
            if audience_counts[row["id"]] == 0
        ]

        # Gerçek tekrar kontrolü: tablodaki anlamlı tüm alanlar birlikte.
        benefit_keys = Counter(
            (
                row["campaign_id"],
                row["benefit_type"],
                row["amount"],
                row["rate"],
                row["points"],
                row["minimum_spending"],
                row["maximum_benefit"],
                row["description"],
                row["evidence"],
            )
            for row in benefits
        )

        exact_duplicate_benefits = []

        for key, count in benefit_keys.items():
            if count <= 1:
                continue

            campaign = campaign_map.get(
                key[0],
                {},
            )

            exact_duplicate_benefits.append(
                {
                    **campaign,
                    "benefit_type": key[1],
                    "amount": key[2],
                    "rate": key[3],
                    "points": key[4],
                    "minimum_spending": key[5],
                    "maximum_benefit": key[6],
                    "description": key[7],
                    "count": count,
                }
            )

        audience_keys = Counter(
            (
                row["campaign_id"],
                row["audience_type"],
                row["audience_label"],
                row["details"],
            )
            for row in audiences
        )

        exact_duplicate_audiences = []

        for key, count in audience_keys.items():
            if count <= 1:
                continue

            campaign = campaign_map.get(
                key[0],
                {},
            )

            exact_duplicate_audiences.append(
                {
                    **campaign,
                    "audience_type": key[1],
                    "audience_label": key[2],
                    "details": key[3],
                    "count": count,
                }
            )

        special_rate_records = [
            {
                **campaign_map.get(
                    row["campaign_id"],
                    {},
                ),
                **dict(row),
            }
            for row in benefits
            if (
                row["benefit_type"] or ""
            ).casefold() == "special_rate"
        ]

        finance_terms = (
            "kâr payı",
            "kar payı",
            "finansman oranı",
            "vade oranı",
        )

        finance_like_benefits = [
            {
                **campaign_map.get(
                    row["campaign_id"],
                    {},
                ),
                **dict(row),
            }
            for row in benefits
            if any(
                term in (
                    (
                        row["description"] or ""
                    )
                    + " "
                    + (
                        row["evidence"] or ""
                    )
                ).casefold()
                for term in finance_terms
            )
        ]

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

        checks = {
            "campaign_count_ok": (
                len(campaigns)
                == EXPECTED_TOTALS["campaigns"]
            ),
            "benefit_count_ok": (
                len(benefits)
                == EXPECTED_TOTALS["benefits"]
            ),
            "audience_count_ok": (
                len(audiences)
                == EXPECTED_TOTALS["audiences"]
            ),
            "distribution_ok": (
                distribution
                == EXPECTED_DISTRIBUTION
            ),
            "missing_benefits_ok": (
                len(missing_benefits) == 0
            ),
            "missing_audiences_ok": (
                len(missing_audiences) == 0
            ),
            "exact_duplicate_benefits_ok": (
                len(exact_duplicate_benefits) == 0
            ),
            "exact_duplicate_audiences_ok": (
                len(exact_duplicate_audiences) == 0
            ),
            "special_rate_ok": (
                len(special_rate_records) == 0
            ),
            "finance_like_benefits_ok": (
                len(finance_like_benefits) == 0
            ),
        }

        passed = all(checks.values())

        summary = {
            "bank": BANK,
            "passed": passed,
            "campaign_count": len(campaigns),
            "benefit_count": len(benefits),
            "audience_count": len(audiences),
            "missing_benefit_campaigns": len(
                missing_benefits
            ),
            "missing_audience_campaigns": len(
                missing_audiences
            ),
            "exact_duplicate_benefits": len(
                exact_duplicate_benefits
            ),
            "exact_duplicate_audiences": len(
                exact_duplicate_audiences
            ),
            "special_rate_records": len(
                special_rate_records
            ),
            "finance_like_benefits": len(
                finance_like_benefits
            ),
            "distribution": distribution,
            "checks": checks,
        }

        lines = [
            "ZİRAAT KATILIM NİHAİ KALİTE DENETİMİ",
            "=" * 90,
            f"Sonuç: {'BAŞARILI' if passed else 'BAŞARISIZ'}",
            f"Kampanya: {len(campaigns)}",
            f"Avantaj kaydı: {len(benefits)}",
            f"Hedef kitle kaydı: {len(audiences)}",
            (
                "Avantajı eksik kampanya: "
                f"{len(missing_benefits)}"
            ),
            (
                "Hedef kitlesi eksik kampanya: "
                f"{len(missing_audiences)}"
            ),
            (
                "Gerçek tekrarlı avantaj: "
                f"{len(exact_duplicate_benefits)}"
            ),
            (
                "Gerçek tekrarlı hedef kitle: "
                f"{len(exact_duplicate_audiences)}"
            ),
            (
                "special_rate kaydı: "
                f"{len(special_rate_records)}"
            ),
            (
                "Finansman benzeri avantaj: "
                f"{len(finance_like_benefits)}"
            ),
            "",
            "Kategori dağılımı:",
        ]

        for category, count in sorted(
            distribution.items(),
            key=lambda item: (-item[1], item[0]),
        ):
            lines.append(
                f"- {category}: {count}"
            )

        lines.extend(
            [
                "",
                "Kontroller:",
            ]
        )

        for check, value in checks.items():
            lines.append(
                f"- {check}: "
                f"{'OK' if value else 'HATA'}"
            )

        TEXT_REPORT.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        JSON_REPORT.write_text(
            json.dumps(
                {
                    "summary": summary,
                    "missing_benefits": (
                        missing_benefits
                    ),
                    "missing_audiences": (
                        missing_audiences
                    ),
                    "exact_duplicate_benefits": (
                        exact_duplicate_benefits
                    ),
                    "exact_duplicate_audiences": (
                        exact_duplicate_audiences
                    ),
                    "special_rate_records": (
                        special_rate_records
                    ),
                    "finance_like_benefits": (
                        finance_like_benefits
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        print("\n".join(lines))
        print()
        print("Metin raporu:", TEXT_REPORT)
        print("JSON raporu:", JSON_REPORT)

        return 0 if passed else 1

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
