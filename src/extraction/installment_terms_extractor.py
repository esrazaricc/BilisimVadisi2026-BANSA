from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InstallmentTermsExtraction:
    minimum_transaction_amount: float | None
    maximum_transaction_amount: float | None
    installment_count: int | None
    installment_cost_rate: float | None
    installment_cost_text: str | None
    evidence_text: str | None


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = (
        text.replace("\u200b", " ")
        .replace("\ufeff", " ")
        .replace("\xa0", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


def parse_tr_number(value: str | None) -> float | None:
    if not value:
        return None

    token = re.sub(r"[^\d,.\-]", "", normalize_text(value))
    if not token:
        return None

    if "," in token and "." in token:
        token = token.replace(".", "").replace(",", ".")
    elif "," in token:
        token = token.replace(",", ".")
    elif token.count(".") > 1:
        token = token.replace(".", "")
    elif token.count(".") == 1:
        left, right = token.split(".", 1)
        if len(right) == 3:
            token = left + right

    try:
        return float(token)
    except ValueError:
        return None


def _sentence_with_terms(text: str) -> str | None:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", normalize_text(text))
    for sentence in sentences:
        folded = sentence.casefold()
        if (
            "taksit" in folded
            or "vade farksız" in folded
            or "vade farksiz" in folded
        ) and re.search(r"\d", sentence):
            return sentence[:500]
    return None


def extract_transaction_range(
    text: str,
) -> tuple[float | None, float | None]:
    normalized = normalize_text(text)
    money = r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?"

    patterns = (
        rf"{money}\s*(?:TL|₺)\s*(?:ile|[-–—])\s*"
        rf"{money}\s*(?:TL|₺)\s+aras[ıi]ndaki\s+"
        rf"(?:işlem|islem|harcama|alışveriş|alisveris)",
        rf"{money}\s*(?:TL|₺)\s*[-–—]\s*"
        rf"{money}\s*(?:TL|₺)\s+aras[ıi]\s+"
        rf"(?:işlem|islem|harcama|alışveriş|alisveris)",
        rf"{money}\s*(?:TL|₺)\s*(?:ile|[-–—])\s*"
        rf"{money}\s*(?:TL|₺)\s+aras[ıi]nda",
    )

    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue

        lower = parse_tr_number(match.group(1))
        upper = parse_tr_number(match.group(2))
        if (
            lower is not None
            and upper is not None
            and 0 < lower <= upper
        ):
            return lower, upper

    return None, None


def extract_installment_count(text: str) -> int | None:
    normalized = normalize_text(text)
    values: list[int] = []

    for match in re.finditer(
        r"\b(\d{1,3})\s*(?:eşit\s+)?taksit(?:e|i|le|li)?\b",
        normalized,
        flags=re.IGNORECASE,
    ):
        value = int(match.group(1))
        if 1 <= value <= 120:
            values.append(value)

    for match in re.finditer(
        r"\b(\d{1,3}(?:\s*[-–—]\s*\d{1,3}){1,8})\s*"
        r"taksit(?:e|i|le|li)?\b",
        normalized,
        flags=re.IGNORECASE,
    ):
        values.extend(
            int(token)
            for token in re.findall(r"\d{1,3}", match.group(1))
            if 1 <= int(token) <= 120
        )

    return max(values) if values else None


def extract_installment_cost(
    text: str,
) -> tuple[float | None, str | None]:
    normalized = normalize_text(text)

    # "Vade farksız" ayrı bir maliyet/vade farkı alanıdır.
    # Kaynak açıkça "kâr payı" demiyorsa kâr payı olarak etiketlenmez.
    if re.search(
        r"\bvade\s+farks[ıi]z\b",
        normalized,
        flags=re.IGNORECASE,
    ):
        return 0.0, "Vade farksız (%0)"

    patterns = (
        r"%\s*(\d{1,3}(?:[.,]\d{1,4})?)\s*vade\s+fark[ıi]",
        r"(\d{1,3}(?:[.,]\d{1,4})?)\s*%\s*vade\s+fark[ıi]",
        r"vade\s+fark[ıi]\s*(?:oran[ıi])?\s*[:\-]?\s*%?\s*"
        r"(\d{1,3}(?:[.,]\d{1,4})?)",
    )

    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue

        value = parse_tr_number(match.group(1))
        if value is None or not (0 <= value <= 100):
            continue

        if value.is_integer():
            display = f"%{int(value)} vade farkı"
        else:
            display = f"%{str(value).replace('.', ',')} vade farkı"
        return value, display

    return None, None


def extract_installment_terms(
    title: str,
    text: str,
) -> InstallmentTermsExtraction:
    full_text = normalize_text(f"{title} {text}")

    minimum, maximum = extract_transaction_range(full_text)
    installment_count = extract_installment_count(full_text)
    cost_rate, cost_text = extract_installment_cost(full_text)
    evidence = _sentence_with_terms(full_text)

    return InstallmentTermsExtraction(
        minimum_transaction_amount=minimum,
        maximum_transaction_amount=maximum,
        installment_count=installment_count,
        installment_cost_rate=cost_rate,
        installment_cost_text=cost_text,
        evidence_text=evidence,
    )
