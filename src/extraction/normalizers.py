import re
from datetime import date

MONTHS = {
    "ocak": 1,
    "şubat": 2,
    "mart": 3,
    "nisan": 4,
    "mayıs": 5,
    "haziran": 6,
    "temmuz": 7,
    "ağustos": 8,
    "eylül": 9,
    "ekim": 10,
    "kasım": 11,
    "aralık": 12,
}


def parse_tr_number(value):
    """1.250,50 veya 1,89 gibi Türkçe sayı biçimlerini float'a çevirir."""
    if value is None:
        return None

    cleaned = value.strip()
    cleaned = cleaned.replace("₺", "").replace("TL", "").replace("tl", "")
    cleaned = re.sub(r"\s+", "", cleaned)

    if not cleaned:
        return None

    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    elif "." in cleaned:
        left, right = cleaned.split(".", 1)
        if len(right) == 3:
            cleaned = left + right

    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_turkish_date(day, month_name, year):
    month = MONTHS.get(month_name.lower())
    if month is None:
        return None

    try:
        return date(int(year), month, int(day)).isoformat()
    except ValueError:
        return None


def parse_numeric_date(day, month, year):
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None
