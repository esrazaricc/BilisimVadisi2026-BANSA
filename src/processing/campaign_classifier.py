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


def contains_whole_terms(
    text: str,
    terms: tuple[str, ...],
) -> bool:
    """Terimleri başka kelimelerin içinde eşleştirmez."""
    folded = search_key(text)
    return any(
        re.search(
            rf"(?<!\w){re.escape(search_key(term))}(?!\w)",
            folded,
        )
        is not None
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

GENERIC_FINANCE_PRODUCT_TITLES = (
    "taşıt finansmanı",
    "tasit finansmani",
    "konut finansmanı",
    "konut finansmani",
    "ihtiyaç finansmanı",
    "ihtiyac finansmani",
    "arsa finansmanı",
    "arsa finansmani",
    "işyeri finansmanı",
    "isyeri finansmani",
    "iş yeri finansmanı",
    "is yeri finansmani",
    "eğitim finansmanı",
    "egitim finansmani",
    "tarım finansmanı",
    "tarim finansmani",
    "hac finansmanı",
    "hac finansmani",
    "umre finansmanı",
    "umre finansmani",
)

POINT_TERMS = (
    "worldpuan",
    "alışveriş puanı",
    "alisveris puani",
    "altın puan",
    "altin puan",
    "puan kazan",
    "parafpara",
    "paraf para",
    "bankkart lira",
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

STRONG_NEW_CUSTOMER_BODY_TERMS = (
    "yeni müşteri",
    "yeni musteri",
    "ilk kez müşteri",
    "ilk kez musteri",
    "ilk defa müşteri",
    "ilk defa musteri",
    "müşteri olmayan",
    "musteri olmayan",
)

NEW_CUSTOMER_SOURCE_TERMS = (
    "müşteri ol kampanyaları",
    "musteri ol kampanyalari",
    "yeni müşteri kampanyaları",
    "yeni musteri kampanyalari",
)

STRONG_FINANCE_BODY_TERMS = (
    "pratik finansman kart",
    "ihtiyaç kart",
    "ihtiyac kart",
)

INSURANCE_TERMS = (
    "sigorta",
    "kasko",
    "dask",
    "bireysel emeklilik",
    "bes",
)

INSURANCE_SOURCE_TERMS = (
    "sigorta kampanyaları",
    "sigorta kampanyalari",
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
    source_text = normalize_text(source_group)
    combined = normalize_text(f"{title_text} {body_text}")

    has_amount = contains_amount(combined)
    has_percentage = contains_percentage(combined)
    has_date = contains_date_evidence(combined)
    has_maturity = contains_whole_terms(
        combined,
        ("vade", "vadeli"),
    )

    has_finance_title = contains_any(
        title_text,
        FINANCE_TITLE_TERMS,
    )
    has_strong_finance_body = contains_any(
        body_text,
        STRONG_FINANCE_BODY_TERMS,
    )
    # Başlıktaki sinyaller gövde/footer sinyallerinden daha güçlüdür.
    # Böylece "E-bebek'te 8 Taksit" gibi başlığı açık olan kayıtlar,
    # sayfanın altındaki genel "indirim" metni yüzünden yanlış sınıfa
    # düşmez.
    has_title_points = contains_any(title_text, POINT_TERMS)
    has_title_discount = contains_any(title_text, DISCOUNT_TERMS)
    has_title_installment = contains_any(
        title_text,
        INSTALLMENT_TERMS,
    )

    has_points = contains_any(combined, POINT_TERMS)
    has_discount = contains_any(combined, DISCOUNT_TERMS)
    has_installment = contains_any(
        combined,
        INSTALLMENT_TERMS,
    )
    has_new_customer = (
        contains_any(title_text, NEW_CUSTOMER_TERMS)
        or contains_any(
            body_text,
            STRONG_NEW_CUSTOMER_BODY_TERMS,
        )
        or contains_any(
            source_text,
            NEW_CUSTOMER_SOURCE_TERMS,
        )
    )
    has_insurance = (
        contains_any(title_text, INSURANCE_TERMS)
        or contains_any(
            source_text,
            INSURANCE_SOURCE_TERMS,
        )
    )
    has_generic_campaign = contains_whole_terms(
        combined,
        GENERIC_CAMPAIGN_TERMS,
    )

    # Hizmet bilgisi kararı başlığa dayanır. Gövdenin sonundaki
    # ortak ATM/footer metni gerçek kampanyayı hizmet kaydına
    # çeviremez.
    if contains_any(title_text, SERVICE_TERMS):
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
                    "Başlık ATM/hizmet bilgilendirmesini "
                    "gösteriyor; dönemsel ödül veya indirim "
                    "kanıtı yok."
                ),
            )

    finance_signal = (
        has_finance_title
        or has_strong_finance_body
    )

    if finance_signal:
        concrete = (
            has_amount
            or has_percentage
            or has_date
            or has_maturity
            or has_installment
            or has_generic_campaign
        )

        title_key = search_key(title_text)
        generic_product_title = any(
            title_key == search_key(term)
            for term in GENERIC_FINANCE_PRODUCT_TITLES
        )

        # Genel ürün sayfasında yalnızca tutar veya standart vade
        # yazması kampanya kanıtı değildir.
        generic_product_has_campaign_evidence = (
            has_percentage
            or has_date
            or has_installment
            or has_generic_campaign
            or has_discount
            or has_points
        )

        if (
            has_finance_title
            and generic_product_title
            and not generic_product_has_campaign_evidence
        ):
            return ClassificationResult(
                record_kind="standard_product",
                campaign_category="standard_product",
                comparison_eligible=False,
                confidence=0.96,
                reason=(
                    "Genel finansman ürün sayfası; dönemsel "
                    "kampanya veya somut avantaj kanıtı yok."
                ),
            )

        if concrete:
            return ClassificationResult(
                record_kind="campaign",
                campaign_category="finance_campaign",
                comparison_eligible=True,
                confidence=0.96,
                reason=(
                    "Açık finansman ürünü ve somut kampanya "
                    "kanıtı bulundu."
                ),
            )

        if has_finance_title:
            return ClassificationResult(
                record_kind="standard_product",
                campaign_category="standard_product",
                comparison_eligible=False,
                confidence=0.94,
                reason=(
                    "Finansman ürünü tanıtılıyor ancak "
                    "dönemsel kampanya kanıtı bulunmuyor."
                ),
            )

    # Gövdedeki genel "Müşteri Ol" footer bağlantısı yeni müşteri
    # sınıfı oluşturmaz; yalnızca güçlü gövde, başlık veya kaynak
    # grubu sinyali kullanılır. Yeni müşteri sinyali, başlıktaki
    # puan/taksit avantajından önce korunur.
    if has_new_customer:
        return ClassificationResult(
            record_kind="campaign",
            campaign_category="new_customer_campaign",
            comparison_eligible=True,
            confidence=0.95,
            reason="Yeni müşteri avantajı bulundu.",
        )

    # Başlık açıkça puan, indirim/iade veya taksit söylüyorsa footer
    # metinleri bu kararı bozamaz.
    if has_title_points:
        return ClassificationResult(
            record_kind="campaign",
            campaign_category="points_campaign",
            comparison_eligible=True,
            confidence=0.98,
            reason="Başlıkta açık puan/para puan avantajı bulundu.",
        )

    if has_title_discount:
        return ClassificationResult(
            record_kind="campaign",
            campaign_category="discount_campaign",
            comparison_eligible=True,
            confidence=0.97,
            reason="Başlıkta açık indirim veya iade avantajı bulundu.",
        )

    if has_title_installment:
        return ClassificationResult(
            record_kind="campaign",
            campaign_category="card_campaign",
            comparison_eligible=True,
            confidence=0.97,
            reason="Başlıkta açık taksit/vade farksız avantajı bulundu.",
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
