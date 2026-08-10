import re
from datetime import date

from src.extraction.normalizers import (
    parse_numeric_date,
    parse_tr_number,
    parse_turkish_date,
)


def _find_number(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return parse_tr_number(match.group(1))


def _find_integer(pattern, text):
    value = _find_number(pattern, text)
    return int(value) if value is not None else None


def _clean_title(title):
    title = title.strip()
    for separator in [" | ", " - Albaraka", " | Albaraka"]:
        if separator in title:
            title = title.split(separator, 1)[0].strip()
    return title or "İsimsiz Kampanya"


def _campaign_type(text):
    lowered = text.lower()

    if "konut" in lowered:
        return "Konut Finansmanı Kampanyası", "Konut Finansmanı"
    if "taşıt" in lowered or "araç finansman" in lowered:
        return "Taşıt Finansmanı Kampanyası", "Taşıt Finansmanı"
    if "ihtiyaç finansmanı" in lowered or "pratik finansman" in lowered:
        return "İhtiyaç Finansmanı Kampanyası", "İhtiyaç Finansmanı"
    if "yatırım" in lowered or "katılma hesab" in lowered:
        return "Yatırım Ürünü Kampanyası", "Yatırım Ürünü"
    if "worldpuan" in lowered or "alışveriş puanı" in lowered:
        return "Alışveriş Puanı Kampanyası", "Kart"
    if any(word in lowered for word in ["kart", "alışveriş", "harcama", "taksit"]):
        return "Kart Kampanyası", "Kart"
    if "finansman" in lowered:
        return "Finansman Kampanyası", "Finansman"

    return "Diğer Kampanya", None


def _target_audience(text):
    rules = [
        (r"yeni\s+müşter", "Yeni Müşteriler"),
        (r"dijital\s+müşter", "Dijital Müşteriler"),
        (r"maaş\s+müşter", "Maaş Müşterileri"),
        (r"mevcut\s+müşter", "Mevcut Müşteriler"),
        (r"kart\s+sahip", "Kart Sahipleri"),
        (r"bireysel\s+(?:worldcard|kredi kart|müşter)", "Bireysel Müşteriler"),
        (r"business\s+(?:worldcard|kart)", "Business Kart Sahipleri"),
        (r"18\s*[-–]\s*25\s+yaş", "18-25 Yaş"),
    ]

    found = []
    for pattern, label in rules:
        if re.search(pattern, text, re.IGNORECASE) and label not in found:
            found.append(label)

    return ", ".join(found) if found else None


def _dates(text):
    dates = []

    numeric_matches = re.findall(
        r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b",
        text,
    )
    for day, month, year in numeric_matches:
        parsed = parse_numeric_date(day, month, year)
        if parsed and parsed not in dates:
            dates.append(parsed)

    named_matches = re.findall(
        r"\b(\d{1,2})\s+(ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık)\s+(20\d{2})\b",
        text,
        re.IGNORECASE,
    )
    for day, month_name, year in named_matches:
        parsed = parse_turkish_date(day, month_name, year)
        if parsed and parsed not in dates:
            dates.append(parsed)

    if not dates:
        return None, None
    if len(dates) == 1:
        return None, dates[0]

    return dates[0], dates[-1]


def _expense_status(text):
    lowered = text.lower()

    if re.search(r"dosya\s+masrafı\s+alınma|masrafsız\s+finansman", lowered):
        return "Masrafsız"

    if "ekspertiz ücreti" in lowered and any(word in lowered for word in ["karşılan", "ücretsiz"]):
        return "Ekspertiz Ücretsiz"

    if "vade farksız" in lowered:
        return "Vade Farksız"

    return None


def _sentences(text):
    items = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [item.strip() for item in items if item.strip()]


def _evidence_sentence(text):
    keywords = r"kampanya|%|taksit|worldpuan|ödül|iade|indirim|masraf|geçerli"

    for sentence in _sentences(text):
        if re.search(keywords, sentence, re.IGNORECASE):
            return sentence[:500]

    return None


def _campaign_conditions(text):
    condition_words = r"koşul|şart|en az|min(?:imum)?|katılım|yararlan|geçerlidir|dahil değildir"
    found = []

    for sentence in _sentences(text):
        if re.search(condition_words, sentence, re.IGNORECASE):
            found.append(sentence)
        if len(found) == 3:
            break

    return " ".join(found)[:1200] if found else None


def extract_campaign(title, text):
    full_text = f"{title}\n{text}"
    campaign_type, product_type = _campaign_type(full_text)

    profit_share_rate = _find_number(
        r"%\s*([\d]+(?:[,.][\d]+)?)\s*(?:k[aâ]r\s+payı|oran)",
        full_text,
    )

    maturity_months = _find_integer(r"([\d]{1,3})\s*aya?\s+kadar", full_text)
    if maturity_months is None:
        maturity_months = _find_integer(r"([\d]{1,3})\s*ay\s+vade", full_text)

    installment_count = _find_integer(
        r"(?:vade\s+farksız\s+)?([\d]{1,3})\s*(?:taksit|eşit\s+taksit)",
        full_text,
    )

    discount_rate = _find_number(
        r"%\s*([\d]+(?:[,.][\d]+)?)\s*(?:indirim|iade)",
        full_text,
    )

    reward_amount = _find_number(
        r"([\d][\d.]*?(?:,[\d]+)?)\s*(?:tl|₺)\s*(?:ödül|iade|çek|hediye)",
        full_text,
    )
    if reward_amount is None:
        reward_amount = _find_number(
            r"([\d][\d.]*?(?:,[\d]+)?)\s*(?:tl|₺)\s+değerinde\s+(?:alışveriş\s+)?(?:çeki|hediye)",
            full_text,
        )

    shopping_points = _find_number(
        r"([\d][\d.]*?(?:,[\d]+)?)\s*(?:tl|₺)'?(?:ye)?\s*(?:varan\s+)?(?:world)?puan",
        full_text,
    )

    financing_amount = _find_number(
        r"([\d][\d.]*?(?:,[\d]+)?)\s*(?:tl|₺)'?ye\s+kadar\s+finansman",
        full_text,
    )

    minimum_spending = _find_number(
        r"(?:en\s+az|min(?:imum)?)\s*([\d][\d.]*?(?:,[\d]+)?)\s*(?:tl|₺)\s*(?:harcama|alışveriş)",
        full_text,
    )
    if minimum_spending is None:
        minimum_spending = _find_number(
            r"([\d][\d.]*?(?:,[\d]+)?)\s*(?:tl|₺)\s+ve\s+üzeri(?:\s+\w+){0,3}\s+(?:harcama|alışveriş)",
            full_text,
        )

    maximum_benefit = _find_number(
        r"(?:en\s+fazla|maksimum|toplamda)\s*([\d][\d.]*?(?:,[\d]+)?)\s*(?:tl|₺)\s*(?:iade|indirim|ödül|worldpuan)",
        full_text,
    )
    if maximum_benefit is None:
        maximum_benefit = _find_number(
            r"([\d][\d.]*?(?:,[\d]+)?)\s*(?:tl|₺)'?ye\s+varan\s+(?:worldpuan|ödül|iade|indirim)",
            full_text,
        )

    start_date, end_date = _dates(full_text)
    is_active = None
    if end_date:
        is_active = end_date >= date.today().isoformat()

    target_audience = _target_audience(full_text)
    expense_status = _expense_status(full_text)

    extracted_values = [
        target_audience,
        profit_share_rate,
        financing_amount,
        maturity_months,
        installment_count,
        reward_amount,
        discount_rate,
        shopping_points,
        minimum_spending,
        maximum_benefit,
        expense_status,
        end_date,
    ]
    found_count = sum(value is not None for value in extracted_values)
    confidence = min(0.97, 0.55 + found_count * 0.04)

    return {
        "campaign_name": _clean_title(title),
        "campaign_type": campaign_type,
        "linked_product_type": product_type,
        "target_audience": target_audience,
        "profit_share_rate": profit_share_rate,
        "financing_amount": financing_amount,
        "maturity_months": maturity_months,
        "installment_count": installment_count,
        "reward_amount": reward_amount,
        "discount_rate": discount_rate,
        "shopping_points": shopping_points,
        "minimum_spending": minimum_spending,
        "maximum_benefit": maximum_benefit,
        "expense_status": expense_status,
        "campaign_start_date": start_date,
        "campaign_end_date": end_date,
        "campaign_conditions": _campaign_conditions(text),
        "source_evidence": _evidence_sentence(text),
        "is_active": is_active,
        "extraction_confidence": round(confidence, 2),
    }
