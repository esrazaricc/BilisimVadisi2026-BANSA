from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

from src.pricing_guardrails import text_marks_example_only


ALLOWED_VALUE_TYPES = {
    "exact",
    "minimum",
    "maximum",
    "range",
    "dynamic",
    "example",
    "conditional_pricing",
    "not_published",
}

ALLOWED_SOURCE_TYPES = {
    "product_page",
    "official_fee_tariff",
    "official_pricing_table",
    "calculator",
    "example_payment_table",
    "contract_form",
    "faq",
    "campaign",
}


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text.replace("ı", "i")).strip()


def _product_key(bank_name: object, product_name: object) -> tuple[str, str]:
    return _fold(bank_name), _fold(product_name)


def _contains_any(value: str, tokens: Iterable[str]) -> bool:
    return any(_fold(token) in value for token in tokens)


def pricing_evidence_defaults(
    row: Mapping[str, Any],
    *,
    bank_name: object = "",
    product_name: object = "",
    source_url: object = "",
) -> dict[str, Any]:
    """Fiyatlama satırına kaynak/kanıt metadata'sı ekler.

    Bu fonksiyon fiyat üretmez. Yalnız mevcut resmî kaynak satırının hangi
    tür kanıt olduğunu sınıflandırır. Belirsizlikte en muhafazakâr sınıf
    tercih edilir; örnek satır hiçbir zaman headline fiyatlama sayılmaz.
    """

    out = dict(row)
    bank, product = _product_key(bank_name, product_name)
    variant = _fold(out.get("pricing_variant"))
    source_text = _fold(out.get("source_text"))
    evidence_text = f"{variant} {source_text}".strip()

    value_type = str(out.get("value_type") or "").strip()
    source_type = str(out.get("source_type") or "").strip()
    conditions = str(out.get("conditions") or "").strip()

    # Açık örnek/temsili işaret her şeyden önce gelir.
    if (
        value_type not in ALLOWED_VALUE_TYPES
        and (
            text_marks_example_only(out.get("pricing_variant"))
            or text_marks_example_only(out.get("source_text"))
        )
    ):
        value_type = "example"
        source_type = "example_payment_table"

    # Kuveyt Türk'te aşağıdaki ürünlerde bugün DB'de görülen 4,82 / 4,52
    # satırları ürün sayfalarındaki örnek maliyet tablolarından geliyor.
    if bank == _fold("Kuveyt Türk") and _contains_any(
        product,
        (
            "Eğitim Finansmanı",
            "Hac ve Umre Finansmanı",
            "Hac ve Umre",
            "Hac-Umre Finansmanı",
            "Hac Umre Finansmanı",
            "Seyahat Finansmanı",
            "Tekne Finansmanı",
            "Tekne Tüketici Finansmanı",
            "Alışveriş Finansmanı",
        ),
    ):
        value_type = "example"
        source_type = "example_payment_table"
        if not conditions:
            conditions = "Resmî ürün sayfasındaki örnek maliyet/ödeme tablosu; genel güncel oran değildir."

    # Türkiye Finans'ın aşağıdaki tabloları gerçek yayımlanmış fiyatlama
    # kademeleridir; fakat tutar, vade, sigorta/ek ürün şartlarıyla koşulludur.
    if bank == _fold("Türkiye Finans"):
        tf_rules: list[tuple[tuple[str, ...], str]] = [
            (("Konut Finansmanı",), "100.000 TL bazlı resmî fiyatlama tablosu; sigorta/ürün ve konut durumuna göre değişir."),
            (("Arsa Finansmanı",), "100.000 TL bazlı resmî fiyatlama tablosu; sigortalı/sigortasız ve vadeye göre değişir."),
            (("İş yeri Finansmanı", "İş Yeri Finansmanı"), "100.000 TL bazlı resmî fiyatlama tablosu; sigortalı/sigortasız ve vadeye göre değişir."),
            (("Taksitli Ticari Taşıt",), "40.000 TL örnek maliyet tablosunda yayımlanan koşullu fiyatlama; ek ürün/ödeme koşulları geçerlidir."),
            (("Ticari Hat", "Ticari Plaka"), "40.000 TL örnek maliyet tablosunda yayımlanan koşullu fiyatlama; ek ürün/ödeme koşulları geçerlidir."),
            (("Dijital İhtiyaç",), "Resmî fiyatlama tablosu; vade ve KKB skoruna göre değişebilir."),
            (("Trendyol Alışveriş",), "≤70.000 TL ve Finansman Güvence Sigortası koşullu resmî fiyatlama tablosu."),
        ]
        for names, condition in tf_rules:
            if _contains_any(product, names):
                value_type = "conditional_pricing"
                source_type = "official_pricing_table"
                conditions = conditions or condition
                break

    if bank == _fold("Hayat Finans") and _contains_any(product, ("Bana Bunu Al",)):
        value_type = "conditional_pricing"
        source_type = "official_pricing_table"
        conditions = conditions or "Ürünün 6/12/18 ay fiyatlama tablosu; ürün limiti ve vade sınırları ayrıca uygulanır."

    if bank == _fold("Albaraka Türk") and _contains_any(product, ("Togg Finansmanı", "TOGG Finansmanı")):
        value_type = "conditional_pricing"
        source_type = "official_pricing_table"
        model = str(out.get("pricing_variant") or "").strip()
        amount = out.get("financing_amount")
        months = out.get("maturity_months")
        parts = []
        if model and _fold(model) != "standart":
            parts.append(f"Model: {model}")
        if amount is not None:
            try:
                parts.append(f"Finansman tutarı: {float(amount):,.0f} TL".replace(",", "."))
            except Exception:
                pass
        if months is not None:
            parts.append(f"Vade: {int(months)} ay")
        conditions = conditions or " · ".join(parts) or "Model/tutar/vade koşullu resmî fiyatlama."

    # Generic örnek/temsili kanıtta koşul bağlamını boş bırakma. Böylece
    # UI veya downstream katman örnek sayıyı kaynağından koparıp genel oran
    # olarak yorumlayamaz.
    if value_type == "example" and not conditions:
        conditions = (
            "Resmî kaynakta örnek/temsili hesap olarak yayımlanmıştır; "
            "genel güncel fiyatlama değildir."
        )

    # Açık örnek işareti bulunmayan, özel bir koşullu ürüne de girmeyen tablo
    # satırı için kaynağı resmî fiyatlama tablosu olarak sınıflandırıyoruz.
    if value_type not in ALLOWED_VALUE_TYPES:
        value_type = "exact"
    if source_type not in ALLOWED_SOURCE_TYPES:
        source_type = (
            "example_payment_table"
            if value_type == "example"
            else "official_pricing_table"
        )

    out["value_type"] = value_type
    out["source_type"] = source_type
    out["conditions"] = conditions or None
    out["source_url"] = str(source_url or out.get("source_url") or "").strip() or None
    return out


def annotate_pricing_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    bank_name: object = "",
    product_name: object = "",
    source_url: object = "",
) -> list[dict[str, Any]]:
    return [
        pricing_evidence_defaults(
            row,
            bank_name=bank_name,
            product_name=product_name,
            source_url=source_url,
        )
        for row in rows
    ]


def fact_evidence_record(
    *,
    fact_key: str,
    value_text: object = None,
    value_numeric: object = None,
    value_type: str,
    source_type: str,
    conditions: object = None,
    source_url: object = None,
    source_text: object = None,
    verification_status: str = "verified",
) -> dict[str, Any]:
    if value_type not in ALLOWED_VALUE_TYPES:
        raise ValueError(f"Geçersiz value_type: {value_type}")
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError(f"Geçersiz source_type: {source_type}")
    return {
        "fact_key": fact_key,
        "value_text": None if value_text is None else str(value_text),
        "value_numeric": value_numeric,
        "value_type": value_type,
        "source_type": source_type,
        "conditions": None if conditions is None else str(conditions),
        "source_url": None if not source_url else str(source_url),
        "source_text": None if not source_text else str(source_text),
        "verification_status": verification_status,
    }
