from __future__ import annotations

import json
import math
import re
import unicodedata
from typing import Any


MISSING_LABEL = "Belirtilmedi"

CAMPAIGN_TYPE_LABELS = {
    "finance_campaign": "Finansman Kampanyası",
    "card_campaign": "Kart / Taksit Kampanyası",
    "discount_campaign": "İndirim Kampanyası",
    "points_campaign": "Puan Kampanyası",
    "new_customer_campaign": "Yeni Müşteri Kampanyası",
    "insurance_campaign": "Sigorta Kampanyası",
    "other_campaign": "Diğer Kampanya",
    "standard_product": "Standart Ürün",
    "service_information": "Hizmet Bilgisi",
    "duplicate": "Mükerrer",
    "unclassified": "Sınıflandırılmamış",
    "needs_review": "İnceleme Gerekli",
}

PAGE_TYPE_LABELS = {
    "campaign": "Kampanya",
    "standard_product": "Standart Ürün",
    "other": "Diğer Sayfa",
    "service_information": "Hizmet Bilgisi",
    "duplicate": "Mükerrer",
    "unclassified": "Sınıflandırılmamış",
    "needs_review": "İnceleme Gerekli",
}

RECORD_KIND_LABELS = {
    "campaign": "Kampanya",
    "standard_product": "Standart Ürün",
    "service_information": "Hizmet Bilgisi",
    "duplicate": "Mükerrer",
    "needs_review": "İnceleme Gerekli",
    "unclassified": "Sınıflandırılmamış",
    "other": "Diğer",
}

STATUS_LABELS = {
    "active": "Aktif",
    "expired": "Süresi Dolmuş",
    "upcoming": "Yaklaşan",
    "removed": "Kaldırılmış",
    "unknown": "Belirsiz",
}

BENEFIT_TYPE_LABELS = {
    "reward": "Ödül",
    "cashback": "Nakit İade",
    "discount": "İndirim",
    "shopping_points": "Alışveriş Puanı",
    "installment": "Taksit",
    "miles": "Mil",
    "special_rate": "Özel Kur",
    "pos_advantage": "POS Avantajı",
    "free_service": "Ücretsiz Hizmet",
    "service": "Hizmet Avantajı",
    "membership": "Üyelik Avantajı",
    "status_upgrade": "Statü Avantajı",
    "fee_exemption": "Masraf / Komisyon Muafiyeti",
    "return_advantage": "Getiri Avantajı",
    "privilege": "Ayrıcalık",
}

CHANGE_TYPE_LABELS = {
    "new": "Yeni Kampanya",
    "added": "Yeni Kampanya",
    "created": "Yeni Kampanya",
    "content_changed": "İçerik Güncellendi",
    "status_changed": "Durum Değişti",
    "reactivated": "Yeniden Aktif",
    "expired": "Süresi Doldu",
    "removed": "Kaldırıldı",
    "pending_removal": "Kaldırma Kontrolünde",
    "unchanged": "Değişiklik Yok",
}

EXTRACTION_FIELD_LABELS = {
    "campaign_name": "Kampanya Adı",
    "campaign_type": "Kampanya Türü",
    "linked_product_type": "Finansman / Ürün Türü",
    "target_audience": "Hedef Kitle",
    "profit_share_rate": "Kâr Payı Oranı (%)",
    "financing_amount": "Finansman Tutarı (TL)",
    "maturity_months": "Vade Süresi (Ay)",
    "installment_count": "Taksit Sayısı",
    "reward_amount": "Ödül Tutarı (TL)",
    "discount_rate": "İndirim / İade Oranı (%)",
    "shopping_points": "Alışveriş Puanı",
    "minimum_spending": "Minimum Harcama (TL)",
    "maximum_benefit": "Maksimum Fayda (TL)",
    "expense_status": "Masraf Bilgisi",
    "campaign_start_date": "Kampanya Başlangıç Tarihi",
    "campaign_end_date": "Kampanya Bitiş Tarihi",
    "campaign_conditions": "Kampanya Koşulları",
    "source_url": "Resmî Kaynak",
    "source_evidence": "Kaynak Kanıtı",
    "is_active": "Durum",
    "extraction_confidence": "Çıkarım Güveni",
}


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = (
        text.replace("\u200b", " ")
        .replace("\ufeff", " ")
        .replace("\xa0", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


def is_missing(value: Any) -> bool:
    if value is None:
        return True

    try:
        if isinstance(value, float) and math.isnan(value):
            return True
    except (TypeError, ValueError):
        pass

    text = _normalize(value)
    return text.casefold() in {
        "",
        "none",
        "nan",
        "nat",
        "null",
        "—",
        "-",
    }


def display_text(value: Any) -> str:
    return MISSING_LABEL if is_missing(value) else _normalize(value)


def format_number_tr(value: Any) -> str:
    if is_missing(value):
        return MISSING_LABEL

    try:
        number = float(value)
    except (TypeError, ValueError):
        return display_text(value)

    if number.is_integer():
        return f"{int(number):,}".replace(",", ".")

    return (
        f"{number:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
        .rstrip("0")
        .rstrip(",")
    )


def _label(value: Any, mapping: dict[str, str], fallback: str) -> str:
    if is_missing(value):
        return fallback
    key = _normalize(value)
    return mapping.get(key, key)


def label_campaign_type(value: Any) -> str:
    return _label(value, CAMPAIGN_TYPE_LABELS, "Sınıflandırılmamış")


def label_page_type(value: Any) -> str:
    return _label(value, PAGE_TYPE_LABELS, "Belirsiz")


def label_record_kind(value: Any) -> str:
    return _label(value, RECORD_KIND_LABELS, "Sınıflandırılmamış")


def label_status(value: Any) -> str:
    return _label(value, STATUS_LABELS, "Belirsiz")


def label_benefit_type(value: Any) -> str:
    return _label(value, BENEFIT_TYPE_LABELS, "Diğer Fayda")


def label_change_type(value: Any) -> str:
    return _label(value, CHANGE_TYPE_LABELS, "Diğer Değişiklik")


def extraction_field_label(key: Any) -> str:
    normalized = _normalize(key)
    return EXTRACTION_FIELD_LABELS.get(
        normalized,
        normalized.replace("_", " ").title(),
    )


def format_extraction_value(key: str, value: Any) -> str:
    if key == "campaign_type":
        return label_campaign_type(value)

    if key == "is_active":
        if is_missing(value):
            return "Belirsiz"
        try:
            return "Aktif" if int(value) == 1 else "Süresi Dolmuş"
        except (TypeError, ValueError):
            return display_text(value)

    if key == "extraction_confidence":
        if is_missing(value):
            return MISSING_LABEL
        try:
            return f"%{float(value) * 100:.1f}".replace(".", ",")
        except (TypeError, ValueError):
            return display_text(value)

    if isinstance(value, dict):
        if not value:
            return MISSING_LABEL
        return "; ".join(
            f"{extraction_field_label(k)}: {display_text(v)}"
            for k, v in value.items()
        )

    if isinstance(value, (list, tuple, set)):
        values = [display_text(item) for item in value if not is_missing(item)]
        return ", ".join(values) if values else MISSING_LABEL

    return display_text(value)


def clean_campaign_title(
    title: Any,
    bank_name: Any = "",
) -> str:
    """
    Yalnızca gösterim katmanında kullanılır.
    Veritabanındaki ham başlık değiştirilmez.

    - SEO pipe sonlarını kaldırır.
    - Başta tekrarlanan banka/marka adlarını temizler.
    - T.O.M. / TOM Bank Hadi tekrarlarını sadeleştirir.
    """
    original = _normalize(title)
    if not original:
        return MISSING_LABEL

    bank = _normalize(bank_name)
    text = original

    # SEO / sayfa başlığı sonu: "Kampanya ... | TOM Bank Hadi"
    if "|" in text:
        parts = [part.strip() for part in text.split("|") if part.strip()]
        if parts:
            text = parts[0]

    prefixes: list[str] = []
    if bank:
        prefixes.append(bank)

    bank_key = bank.casefold()
    if "t.o.m" in bank_key or "tom" in bank_key:
        prefixes.extend(
            [
                "T.O.M. Katılım",
                "TOM Katılım",
                "TOM Bank Hadi",
                "TOM Bank",
            ]
        )

    # Uzun olan önce temizlensin.
    for prefix in sorted(set(prefixes), key=len, reverse=True):
        text = re.sub(
            rf"^\s*{re.escape(prefix)}\s*(?:[—–\-:]\s*)+",
            "",
            text,
            flags=re.IGNORECASE,
        )

    # Örnek:
    # "T.O.M. Katılım — TOM Bank Hadi'den ..." -> "Hadi'den ..."
    if "t.o.m" in bank_key or "tom" in bank_key:
        text = re.sub(
            r"^\s*TOM\s+Bank\s+(?=Hadi(?:['’]|\b))",
            "",
            text,
            flags=re.IGNORECASE,
        )

    # Aynı başlık parçası yanlışlıkla iki kez arka arkaya geldiyse
    # yalnızca tam tekrarları sadeleştir.
    repeated = re.match(
        r"^\s*(.{8,80}?)\s*[—–\-:]\s*\1\s*$",
        text,
        flags=re.IGNORECASE,
    )
    if repeated:
        text = repeated.group(1)

    text = re.sub(r"\s+", " ", text).strip(" |—–-:")
    return text or original
