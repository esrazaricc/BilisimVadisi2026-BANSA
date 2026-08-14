from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("data") / "campaigns.db"
DEFAULT_REPORT = (
    Path("data") / "kuveyt_nonfinance_extraction_audit.json"
)


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize(
        "NFKC",
        str(value or ""),
    )
    return re.sub(r"\s+", " ", text).strip()


def search_key(value: Any) -> str:
    text = unicodedata.normalize(
        "NFKD",
        normalize_text(value),
    )
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    return (
        text.replace("ı", "i")
        .replace("İ", "i")
        .casefold()
    )


def preview(value: Any, limit: int = 650) -> str:
    text = normalize_text(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}…"


def contains_any(
    text: str,
    terms: tuple[str, ...],
) -> bool:
    key = search_key(text)
    return any(search_key(term) in key for term in terms)



SIGNAL_PATTERNS: dict[str, tuple[str, ...]] = {
    "reward": (
        r"\b\d[\d\.\,]*\s*(?:tl|₺)"
        r"(?:['’]?(?:lik|lık|luk|lük|ye|ya))?"
        r"(?:\s+\S+){0,3}\s+"
        r"(?:hediye|ödül|alisveris ceki|çek)\b",
        r"\b\d[\d\.\,]*\s*(?:tl|₺)\s+degerinde"
        r"(?:\s+\S+){0,6}\s+(?:paket|hediye|çek)\b",
        r"\btoplam(?:da)?\s+\d[\d\.\,]*\s*(?:tl|₺)"
        r"(?:\s+\S+){0,3}\s+kazan",
        r"\bfaturasi bizden\b",
    ),
    "discount": (
        r"%\s*\d+(?:[.,]\d+)?"
        r"(?:['’]?(?:e|a|ye|ya))?"
        r"(?:\s+kadar|\s+varan)?"
        r"(?:\s+\S+){0,5}\s+indirim",
        r"\b\d[\d\.\,]*\s*(?:tl|₺)"
        r"(?:['’]?(?:ye|ya))?"
        r"(?:\s+varan)?"
        r"(?:\s+\S+){0,5}\s+indirim",
    ),
    "cashback": (
        r"%\s*\d+(?:[.,]\d+)?\s*(?:nakit\s+)?iade",
        r"\b\d[\d\.\,]*\s*(?:tl|₺)"
        r"(?:\s+\S+){0,4}\s+(?:nakit\s+|harcama\s+)?iade\b",
        r"\bnakit iade\b",
    ),
    "points": (
        r"\b\d[\d\.\,]*\s*(?:tl|₺)?\s*altin puan\b",
        r"\b\d[\d\.\,]*\s*(?:tl|₺)?\s*worldpuan\b",
        r"\b\d[\d\.\,]*\s+puan\b",
        r"\btamami altin puan\b",
        r"\baltin puan olarak iade\b",
    ),
    "miles": (
        r"\b\d[\d\.\,]*\s*mil(?:['’]?(?:e|a))?\b",
    ),
    "installment": (
        r"\b\d{1,3}\s*(?:esit\s+)?taksit\b",
        r"\b\d{1,3}\s*taksite?\s+varan\b",
        r"\b\d{1,3}\s*aya?\s+varan\s+"
        r"(?:vade\s+farksiz\s+)?taksit\b",
        r"\b\d{1,3}\s*['’]?(?:e|a|ye|ya)\s+"
        r"varan\s+taksit\b",
    ),
    "free_service": (
        r"\bucretsiz\s+hgs\s+etiketi\b",
        r"\bkart ucreti alinmamaktadir\b",
        r"\bucretsiz\s+faydalan",
    ),
    "special_exchange_rate": (
        r"\bozel kur\b",
        r"\bavantajli kur\b",
        r"\bdoviz.*ayricalikli fiyat\b",
        r"\bkiymetli maden.*ayricalikli fiyat\b",
    ),
    "pos_advantage": (
        r"\bsanal pos\b",
        r"\bpos kampanyasi\b",
        r"\bpos cozumleri\b",
        r"\b\d+\s+gun bloke\b",
        r"%\s*0\s+komisyon\b",
        r"\bek\s+vade\s+farksiz\s+\+?\d+\s+taksit\b",
    ),
}


SIGNAL_EXPECTED_TYPES: dict[str, set[str]] = {
    "reward": {"reward"},
    "discount": {"discount"},
    "cashback": {"cashback"},
    "points": {"shopping_points", "reward"},
    "miles": {"miles", "shopping_points", "reward"},
    "installment": {"installment"},
    "free_service": {"free_service", "reward"},
    "special_exchange_rate": {
        "exchange_rate",
        "special_rate",
    },
    "pos_advantage": {
        "pos_advantage",
        "fee_discount",
        "discount",
    },
}


DISCLAIMER_TERMS = (
    "değişiklik yapma hakkına sahiptir",
    "değiştirme hakkına sahiptir",
    "hakkını saklı tutar",
    "kampanya koşullarını değiştirebilir",
    "değerlendirme sonucuna göre değişebilir",
)


def detect_signals(text: str) -> set[str]:
    key = search_key(text)
    result: set[str] = set()

    for signal, patterns in SIGNAL_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, key, flags=re.IGNORECASE):
                result.add(signal)
                break

    return result



def expected_audiences(
    *,
    title: str,
    source_group: str,
    text: str,
    category: str,
) -> set[str]:
    combined = search_key(
        f"{title} {source_group} {text[:3500]}"
    )
    source_key = search_key(source_group)
    expected: set[str] = set()

    is_bireysel_kart = (
        "bireysel kart kampanyalari" in source_key
    )
    is_ticari_kart = (
        "ticari kart kampanyalari" in source_key
    )
    is_pos = "pos kampanyalari" in source_key
    is_bireysel_musteri_ol = (
        "bireysel musteri ol kampanyalari" in source_key
    )
    is_ticari_musteri_ol = (
        "ticari musteri ol kampanyalari" in source_key
    )

    # Kart kampanyalarında asgari ve anlamlı hedef kitle kart
    # sahibidir. Bireysel müşteri ayrıca zorunlu tutulmaz.
    if is_bireysel_kart:
        expected.add("card_holder")

    if is_ticari_kart:
        expected.update(
            {"business_customer", "card_holder"}
        )

    # POS kampanyasının ana hedefi üye işyeri/ticari müşteridir.
    if is_pos:
        expected.add("business_customer")

    if is_bireysel_musteri_ol:
        expected.add("individual_customer")

    if is_ticari_musteri_ol:
        expected.add("business_customer")

    if (
        category == "new_customer_campaign"
        or (
            "musteri ol kampanyalari" in source_key
            and any(
                term in combined
                for term in (
                    "musteri olun",
                    "musteri olup",
                    "musterimiz olan",
                    "hesap ac",
                    "mobilden musteri",
                    "mobil'den musteri",
                    "xtm'den musteri",
                )
            )
        )
    ):
        expected.add("new_customer")

    if (
        "ticari kobi kampanyalari" in source_key
        or any(
            term in combined
            for term in (
                "ticari musteriler",
                "kobi musteriler",
                "kobi'lere",
                "kobilere",
                "esnaf",
                "ciftci",
                "tuzel sirket",
                "tuzel firma",
                "net ihracatci",
                "e-ihracat yapan",
            )
        )
    ):
        expected.add("business_customer")

    if (
        "bireysel tum kampanyalar" in source_key
        or any(
            term in combined
            for term in (
                "bireysel musteriler",
                "bireysel kredi karti olan",
            )
        )
    ):
        expected.add("individual_customer")

    if (
        not is_pos
        and any(
            term in combined
            for term in (
                "kart sahipleri",
                "kredi kartlari ile",
                "kredi kartlariniz ile",
                "kredi kartiyla",
                "banka kartlari ile",
                "tuzel kredi kartlari",
                "saglam kart",
                "miles&smiles",
            )
        )
    ):
        expected.add("card_holder")

    if any(
        term in combined
        for term in (
            "mobil musteriler",
            "dijital musteriler",
            "mobilden musterimiz olan",
            "mobil'den musterimiz olan",
        )
    ):
        expected.add("digital_customer")

    return expected

def benefit_is_suspicious(
    benefit: sqlite3.Row,
) -> list[str]:
    reasons: list[str] = []
    benefit_type = normalize_text(benefit["benefit_type"])
    evidence = normalize_text(benefit["evidence"])

    rate = benefit["rate"]
    amount = benefit["amount"]
    points = benefit["points"]

    if not evidence:
        reasons.append("Avantaj kanıt cümlesi boş.")

    if evidence and contains_any(evidence, DISCLAIMER_TERMS):
        reasons.append(
            "Avantaj kanıtı kampanya faydası yerine hukuki açıklama."
        )

    if rate is not None and not (0 < float(rate) <= 100):
        reasons.append("İndirim/iade oranı geçersiz görünüyor.")

    if amount is not None and float(amount) <= 0:
        reasons.append("Avantaj tutarı geçersiz görünüyor.")

    if points is not None and float(points) <= 0:
        reasons.append("Puan değeri geçersiz görünüyor.")

    if benefit_type == "installment":
        description = search_key(benefit["description"])
        match = re.search(r"(\d{1,3})\s*taksit", description)
        if not match:
            reasons.append("Taksit açıklamasında sayı bulunmuyor.")
        elif not (1 <= int(match.group(1)) <= 120):
            reasons.append("Taksit sayısı geçersiz görünüyor.")

    return reasons


def audit_campaign(
    campaign: sqlite3.Row,
    benefits: list[sqlite3.Row],
    audiences: list[sqlite3.Row],
) -> dict[str, Any]:
    title = normalize_text(campaign["title"])
    source_group = normalize_text(campaign["source_group"])
    clean_text = normalize_text(campaign["clean_text"])
    category = normalize_text(campaign["campaign_category"])

    benefit_types = {
        normalize_text(row["benefit_type"])
        for row in benefits
    }
    audience_types = {
        normalize_text(row["audience_type"])
        for row in audiences
    }

    combined = f"{title} {clean_text}"
    signals = detect_signals(combined)

    # "3.000 TL indirim kazanabilirsiniz" gibi cümleler nakit ödül
    # değil, indirimdir. Reward sinyalini yalnız bağımsız hediye/ödül
    # kanıtı varsa korur.
    if "reward" in signals:
        reward_evidence_found = False
        for sentence in re.split(
            r"(?<=[.!?])\s+|\n+",
            normalize_text(combined),
        ):
            sentence_key = search_key(sentence)
            has_currency = bool(
                re.search(
                    r"\b\d[\d\.\,]*\s*(?:tl|₺)\b",
                    sentence_key,
                )
            )
            has_reward_word = any(
                term in sentence_key
                for term in (
                    "hediye",
                    "odul",
                    "alisveris ceki",
                    "degerinde finansal urun paketi",
                    "faturasi bizden",
                )
            )
            is_other_benefit = any(
                term in sentence_key
                for term in (
                    "indirim",
                    "nakit iade",
                    "harcama iadesi",
                    "altin puan",
                    "worldpuan",
                    " mil",
                )
            )
            if has_currency and has_reward_word and not is_other_benefit:
                reward_evidence_found = True
                break

        if not reward_evidence_found:
            signals.discard("reward")

    combined_key = search_key(combined)
    if "reward" in signals:
        direct_currency_reward = re.search(
            (
                r"\b\d[\d\.\,]*\s*(?:tl|₺)"
                r"(?:['’]?(?:ye|ya))?"
                r"(?:\s+\S+){0,3}\s+"
                r"(?:hediye|odul|alisveris ceki|çek)\b"
            ),
            combined_key,
            flags=re.IGNORECASE,
        )
        package_reward = re.search(
            (
                r"\b\d[\d\.\,]*\s*(?:tl|₺)\s+degerinde"
                r"(?:\s+\S+){0,6}\s+"
                r"(?:paket|hediye|çek)\b"
            ),
            combined_key,
            flags=re.IGNORECASE,
        )
        if (
            not direct_currency_reward
            and not package_reward
            and ("miles" in signals or "points" in signals)
        ):
            signals.discard("reward")
    expected_types = set().union(
        *(
            SIGNAL_EXPECTED_TYPES[signal]
            for signal in signals
        )
    ) if signals else set()

    expected_audience_types = expected_audiences(
        title=title,
        source_group=source_group,
        text=clean_text,
        category=category,
    )

    high_reasons: list[str] = []
    medium_reasons: list[str] = []

    missing_signal_types = []
    for signal in sorted(signals):
        allowed = SIGNAL_EXPECTED_TYPES[signal]
        if not benefit_types.intersection(allowed):
            missing_signal_types.append(signal)

    if missing_signal_types:
        high_reasons.append(
            "Metinde avantaj kanıtı var fakat yapılandırılmış "
            "avantaj eksik: "
            + ", ".join(missing_signal_types)
        )

    if (
        category in {
            "card_campaign",
            "discount_campaign",
            "points_campaign",
            "new_customer_campaign",
        }
        and not benefits
    ):
        high_reasons.append(
            "Bu kampanya kategorisinde hiç avantaj kaydı yok."
        )

    missing_audiences = sorted(
        expected_audience_types - audience_types
    )
    if missing_audiences:
        medium_reasons.append(
            "Beklenen hedef kitle çıkarılmamış: "
            + ", ".join(missing_audiences)
        )

    if category == "points_campaign" and not (
        benefit_types
        & {"shopping_points", "miles", "reward"}
    ):
        high_reasons.append(
            "Puan/mil kategorisinde puan veya mil avantajı yok."
        )

    if category == "new_customer_campaign" and (
        "new_customer" not in audience_types
    ):
        high_reasons.append(
            "Yeni müşteri kampanyasında new_customer hedef kitlesi yok."
        )

    suspicious_benefits: list[dict[str, Any]] = []
    for benefit in benefits:
        reasons = benefit_is_suspicious(benefit)
        if reasons:
            suspicious_benefits.append(
                {
                    "benefit_type": benefit["benefit_type"],
                    "description": benefit["description"],
                    "evidence": benefit["evidence"],
                    "reasons": reasons,
                }
            )

    if suspicious_benefits:
        high_reasons.append(
            "Bir veya daha fazla avantaj kaydı şüpheli."
        )

    if len(benefits) == 0 and len(audiences) == 0:
        medium_reasons.append(
            "Kampanyada ne avantaj ne de hedef kitle kaydı var."
        )

    severity = "ok"
    if high_reasons:
        severity = "high"
    elif medium_reasons:
        severity = "medium"

    return {
        "campaign_id": int(campaign["id"]),
        "title": title,
        "source_url": normalize_text(
            campaign["source_url"]
        ),
        "source_group": source_group,
        "campaign_category": category,
        "current_status": normalize_text(
            campaign["current_status"]
        ),
        "severity": severity,
        "high_reasons": high_reasons,
        "medium_reasons": medium_reasons,
        "detected_signals": sorted(signals),
        "expected_benefit_types": sorted(expected_types),
        "extracted_benefit_types": sorted(benefit_types),
        "expected_audience_types": sorted(
            expected_audience_types
        ),
        "extracted_audience_types": sorted(audience_types),
        "benefits": [
            {
                "benefit_type": row["benefit_type"],
                "amount": row["amount"],
                "rate": row["rate"],
                "points": row["points"],
                "minimum_spending": row["minimum_spending"],
                "maximum_benefit": row["maximum_benefit"],
                "description": row["description"],
                "evidence": row["evidence"],
            }
            for row in benefits
        ],
        "audiences": [
            {
                "audience_type": row["audience_type"],
                "audience_label": row["audience_label"],
                "details": row["details"],
            }
            for row in audiences
        ],
        "suspicious_benefits": suspicious_benefits,
        "text_preview": preview(clean_text),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Kuveyt Türk finansman dışı kampanyalarının avantaj "
            "ve hedef kitle çıkarımlarını değiştirmeden denetler."
        )
    )
    parser.add_argument(
        "--bank",
        default="Kuveyt Türk",
    )
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
    parser.add_argument(
        "--limit",
        type=int,
        default=60,
        help="Terminalde gösterilecek en fazla kontrol kaydı.",
    )
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(
            f"Veritabanı bulunamadı: {args.db}"
        )

    connection = sqlite3.connect(args.db)
    connection.row_factory = sqlite3.Row

    campaigns = connection.execute(
        """
        SELECT
            id,
            bank_name,
            title,
            source_url,
            source_group,
            clean_text,
            campaign_category,
            current_status,
            is_current
        FROM live_campaigns
        WHERE bank_name = ?
          AND record_kind = 'campaign'
          AND campaign_category != 'finance_campaign'
          AND is_current = 1
        ORDER BY campaign_category, title
        """,
        (args.bank,),
    ).fetchall()

    benefit_rows = connection.execute(
        """
        SELECT
            id,
            campaign_id,
            benefit_type,
            amount,
            rate,
            points,
            minimum_spending,
            maximum_benefit,
            description,
            evidence
        FROM live_campaign_benefits
        WHERE campaign_id IN (
            SELECT id
            FROM live_campaigns
            WHERE bank_name = ?
              AND record_kind = 'campaign'
              AND campaign_category != 'finance_campaign'
              AND is_current = 1
        )
        ORDER BY campaign_id, id
        """,
        (args.bank,),
    ).fetchall()

    audience_rows = connection.execute(
        """
        SELECT
            id,
            campaign_id,
            audience_type,
            audience_label,
            details
        FROM live_campaign_audiences
        WHERE campaign_id IN (
            SELECT id
            FROM live_campaigns
            WHERE bank_name = ?
              AND record_kind = 'campaign'
              AND campaign_category != 'finance_campaign'
              AND is_current = 1
        )
        ORDER BY campaign_id, id
        """,
        (args.bank,),
    ).fetchall()

    connection.close()

    benefits_by_campaign: dict[int, list[sqlite3.Row]] = defaultdict(list)
    audiences_by_campaign: dict[int, list[sqlite3.Row]] = defaultdict(list)

    for row in benefit_rows:
        benefits_by_campaign[int(row["campaign_id"])].append(row)

    for row in audience_rows:
        audiences_by_campaign[int(row["campaign_id"])].append(row)

    items = [
        audit_campaign(
            campaign,
            benefits_by_campaign[int(campaign["id"])],
            audiences_by_campaign[int(campaign["id"])],
        )
        for campaign in campaigns
    ]

    severity_order = {"high": 0, "medium": 1, "ok": 2}
    items.sort(
        key=lambda item: (
            severity_order[item["severity"]],
            item["campaign_category"],
            item["title"].casefold(),
        )
    )

    category_counts = Counter(
        normalize_text(row["campaign_category"])
        for row in campaigns
    )
    benefit_type_counts = Counter(
        normalize_text(row["benefit_type"])
        for row in benefit_rows
    )
    audience_type_counts = Counter(
        normalize_text(row["audience_type"])
        for row in audience_rows
    )
    severity_counts = Counter(
        item["severity"]
        for item in items
    )

    report = {
        "bank_name": args.bank,
        "campaign_count": len(campaigns),
        "benefit_row_count": len(benefit_rows),
        "audience_row_count": len(audience_rows),
        "category_counts": dict(sorted(category_counts.items())),
        "benefit_type_counts": dict(
            sorted(benefit_type_counts.items())
        ),
        "audience_type_counts": dict(
            sorted(audience_type_counts.items())
        ),
        "severity_counts": dict(sorted(severity_counts.items())),
        "review_count": sum(
            item["severity"] != "ok"
            for item in items
        ),
        "items": items,
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

    print("Finansman dışı çıkarım denetimi tamamlandı.")
    print("Banka:", args.bank)
    print("Finansman dışı kampanya:", len(campaigns))
    print("Avantaj kaydı:", len(benefit_rows))
    print("Hedef kitle kaydı:", len(audience_rows))
    print(
        "Yüksek öncelikli kontrol:",
        severity_counts.get("high", 0),
    )
    print(
        "Orta öncelikli kontrol:",
        severity_counts.get("medium", 0),
    )
    print(
        "Temiz görünen:",
        severity_counts.get("ok", 0),
    )

    print("\nKategoriler:")
    for key, value in sorted(category_counts.items()):
        print(f"  - {key}: {value}")

    print("\nAvantaj türleri:")
    if benefit_type_counts:
        for key, value in sorted(benefit_type_counts.items()):
            print(f"  - {key}: {value}")
    else:
        print("  - Avantaj kaydı yok")

    print("\nHedef kitle türleri:")
    if audience_type_counts:
        for key, value in sorted(audience_type_counts.items()):
            print(f"  - {key}: {value}")
    else:
        print("  - Hedef kitle kaydı yok")

    review_items = [
        item
        for item in items
        if item["severity"] != "ok"
    ]

    if review_items:
        print("\nÖncelikli kontrol kayıtları:")
        for item in review_items[: max(args.limit, 0)]:
            print("\n" + "=" * 90)
            print("ID:", item["campaign_id"])
            print("Başlık:", item["title"])
            print("Kategori:", item["campaign_category"])
            print("Kaynak grubu:", item["source_group"])
            print("Önem:", item["severity"])
            print(
                "Çıkarılan avantajlar:",
                ", ".join(item["extracted_benefit_types"])
                or "Yok",
            )
            print(
                "Çıkarılan hedef kitleler:",
                ", ".join(item["extracted_audience_types"])
                or "Yok",
            )

            for reason in item["high_reasons"]:
                print("  [YÜKSEK]", reason)
            for reason in item["medium_reasons"]:
                print("  [ORTA]", reason)

            if item["detected_signals"]:
                print(
                    "Metindeki sinyaller:",
                    ", ".join(item["detected_signals"]),
                )

            if item["benefits"]:
                print("Avantaj kayıtları:")
                for benefit in item["benefits"]:
                    print(
                        "  -",
                        benefit["benefit_type"],
                        "|",
                        benefit["description"],
                        "| Kanıt:",
                        benefit["evidence"] or "Yok",
                    )

            print("Metin ön izlemesi:", item["text_preview"])

        if len(review_items) > args.limit:
            print(
                "\nTerminalde gösterilmeyen kontrol kaydı:",
                len(review_items) - args.limit,
            )

    print("\nRapor:", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())