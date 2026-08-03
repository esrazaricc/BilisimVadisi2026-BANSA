from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClassificationResult:
    record_kind: str
    campaign_category: str
    comparison_eligible: bool
    confidence: float
    reason: str


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = unicodedata.normalize("NFKC", str(value))
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


def contains_any(
    text: str,
    terms: tuple[str, ...],
) -> bool:
    folded = search_key(text)
    return any(
        search_key(term) in folded
        for term in terms
    )


def contains_amount(text: str) -> bool:
    return bool(
        re.search(
            (
                r"\b\d[\d.\s]*(?:,\d+)?\s*"
                r"(?:TL|₺|ay|taksit|puan|mil)\b"
            ),
            normalize_text(text),
            flags=re.IGNORECASE,
        )
    )


def contains_percentage(text: str) -> bool:
    return bool(
        re.search(
            r"%\s*\d+(?:[,.]\d+)?",
            normalize_text(text),
        )
    )


def contains_date_evidence(text: str) -> bool:
    folded = search_key(text)

    if any(
        term in folded
        for term in (
            "tarihine kadar",
            "tarihleri arasinda",
            "son gun",
            "baslangic tarihi",
            "bitis tarihi",
        )
    ):
        return True

    return bool(
        re.search(
            r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",
            folded,
        )
    )


# Finansman sınıflandırması başlıktaki gerçek ürün türüne dayanır.
# "Vade farksız" ve "taksit" tek başına kart kampanyasıdır.
FINANCE_TITLE_TERMS = (
    "finansman",
    "finansmanı",
    "finansmani",
    "ihtiyaç kart",
    "ihtiyac kart",
    "leasing",
)

POINT_TERMS = (
    "worldpuan",
    "alışveriş puanı",
    "alisveris puani",
    "altın puan",
    "altin puan",
    "puan kazan",
)

DISCOUNT_TERMS = (
    "indirim",
    "nakit iade",
    "harcama iadesi",
)

INSTALLMENT_TERMS = (
    "taksit",
    "vade farksız",
    "vade farksiz",
)

NEW_CUSTOMER_TERMS = (
    "yeni müşteri",
    "yeni musteri",
    "müşteri ol",
    "musteri ol",
    "müşterimiz olun",
    "musterimiz olun",
)

INSURANCE_TERMS = (
    "sigorta",
    "kasko",
    "dask",
)

SERVICE_TERMS = (
    "ortak atm",
    "atm iş birlikleri",
    "atm is birlikleri",
    "atm kullanım",
    "atm kullanim",
    "şube ve atm",
    "sube ve atm",
)

SERVICE_CAMPAIGN_EVIDENCE = (
    "worldpuan",
    "indirim",
    "ödül",
    "odul",
    "iade",
    "promosyon",
)

GENERIC_CAMPAIGN_TERMS = (
    "kampanya",
    "fırsat",
    "firsat",
    "avantaj",
    "özel",
    "ozel",
)


def classify_campaign_record(
    *,
    title: str,
    clean_text: str,
    source_group: str = "",
) -> ClassificationResult:
    title_text = normalize_text(title)
    body_text = normalize_text(clean_text)
    combined = normalize_text(
        f"{title_text} {body_text}"
    )

    has_amount = contains_amount(combined)
    has_percentage = contains_percentage(combined)
    has_date = contains_date_evidence(combined)

    has_finance_title = contains_any(
        title_text,
        FINANCE_TITLE_TERMS,
    )
    has_points = contains_any(combined, POINT_TERMS)
    has_discount = contains_any(
        combined,
        DISCOUNT_TERMS,
    )
    has_installment = contains_any(
        combined,
        INSTALLMENT_TERMS,
    )
    has_new_customer = contains_any(
        combined,
        NEW_CUSTOMER_TERMS,
    )
    has_insurance = contains_any(
        combined,
        INSURANCE_TERMS,
    )
    has_generic_campaign = contains_any(
        combined,
        GENERIC_CAMPAIGN_TERMS,
    )

    if contains_any(combined, SERVICE_TERMS):
        service_campaign = (
            contains_any(
                combined,
                SERVICE_CAMPAIGN_EVIDENCE,
            )
            and (
                has_amount
                or has_percentage
                or has_date
            )
        )

        if not service_campaign:
            return ClassificationResult(
                record_kind="service_information",
                campaign_category="service_information",
                comparison_eligible=False,
                confidence=0.98,
                reason=(
                    "ATM/hizmet bilgilendirmesi; dönemsel "
                    "ödül veya indirim kanıtı yok."
                ),
            )

    # Yalnızca başlık gerçek bir finansman ürününü açıkça
    # söylüyorsa finansman kampanyası yapılır.
    if has_finance_title:
        concrete = (
            has_amount
            or has_percentage
            or has_date
            or has_installment
            or has_generic_campaign
        )
        if concrete:
            return ClassificationResult(
                record_kind="campaign",
                campaign_category="finance_campaign",
                comparison_eligible=True,
                confidence=0.96,
                reason=(
                    "Başlıkta açık finansman ürünü ve somut "
                    "kampanya kanıtı bulundu."
                ),
            )

    # Gerçek finansman başlığı yoksa indirim/puan/yeni müşteri
    # sinyalleri kart taksidinden önce değerlendirilir.
    if has_new_customer:
        return ClassificationResult(
            record_kind="campaign",
            campaign_category="new_customer_campaign",
            comparison_eligible=True,
            confidence=0.95,
            reason="Yeni müşteri avantajı bulundu.",
        )

    if has_points:
        return ClassificationResult(
            record_kind="campaign",
            campaign_category="points_campaign",
            comparison_eligible=True,
            confidence=0.96,
            reason="Puan avantajı bulundu.",
        )

    if has_discount:
        return ClassificationResult(
            record_kind="campaign",
            campaign_category="discount_campaign",
            comparison_eligible=True,
            confidence=0.94,
            reason="İndirim veya iade avantajı bulundu.",
        )

    if has_installment:
        return ClassificationResult(
            record_kind="campaign",
            campaign_category="card_campaign",
            comparison_eligible=True,
            confidence=0.94,
            reason=(
                "Kart harcamasına taksit/vade farksız "
                "avantajı bulundu."
            ),
        )

    if has_insurance and (
        has_amount
        or has_percentage
        or has_date
        or has_generic_campaign
    ):
        return ClassificationResult(
            record_kind="campaign",
            campaign_category="insurance_campaign",
            comparison_eligible=True,
            confidence=0.90,
            reason=(
                "Sigorta kampanyası avantajı veya dönemi "
                "bulundu."
            ),
        )

    if has_generic_campaign and (
        has_amount
        or has_percentage
        or has_date
    ):
        return ClassificationResult(
            record_kind="campaign",
            campaign_category="other_campaign",
            comparison_eligible=True,
            confidence=0.84,
            reason=(
                "Kampanya ifadesiyle tutar, oran veya "
                "dönem kanıtı bulundu."
            ),
        )

    return ClassificationResult(
        record_kind="needs_review",
        campaign_category="unclassified",
        comparison_eligible=False,
        confidence=0.42,
        reason=(
            "Somut kampanya türü güvenle belirlenemedi."
        ),
    )