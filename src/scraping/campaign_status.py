from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


MONTHS = {
    "ocak": 1,
    "subat": 2,
    "şubat": 2,
    "mart": 3,
    "nisan": 4,
    "mayis": 5,
    "mayıs": 5,
    "haziran": 6,
    "temmuz": 7,
    "agustos": 8,
    "ağustos": 8,
    "eylul": 9,
    "eylül": 9,
    "ekim": 10,
    "kasim": 11,
    "kasım": 11,
    "aralik": 12,
    "aralık": 12,
}

EXPIRED_MARKERS = (
    "bu kampanya sona ermiştir",
    "kampanya sona ermiştir",
    "kampanya sona erdi",
    "kampanya süresi dolmuştur",
    "kampanya suresi dolmustur",
    "kampanya bitmiştir",
    "kampanya bitmistir",
    # T.O.M. / Hadi detay sayfaları geçmiş kampanyaları başlıkta
    # açıkça "(GEÇMİŞ KAMPANYA)" olarak işaretleyebiliyor.
    # Sitede görülen bir yazım hatası olan "GEÇMŞİ" biçimi de
    # ayrıca ele alınır.
    "geçmiş kampanya",
    "gecmis kampanya",
    "geçmşi kampanya",
    "gecmsi kampanya",
)

UPCOMING_MARKERS = (
    "yakında",
    "yakinda",
    "başlayacaktır",
    "baslayacaktir",
    "başlıyor",
    "basliyor",
)

ACTIVE_MARKERS = (
    "devam ediyor",
    "aktif kampanya",
    "kampanya devam ediyor",
)


@dataclass(frozen=True)
class CampaignStatusResult:
    status: str
    start_date: str
    end_date: str
    evidence: str
    reason: str
    checked_at: str


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = unicodedata.normalize("NFKC", str(value))
    return re.sub(r"\s+", " ", text).strip()


def search_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", normalize_text(value))
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _today(reference_date: date | None = None) -> date:
    return reference_date or date.today()


def _iso_now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def detect_listing_status(text: str) -> tuple[str, str]:
    normalized = normalize_text(text)
    folded = search_key(normalized)

    for marker in EXPIRED_MARKERS:
        if search_key(marker) in folded:
            return "expired", marker

    for marker in UPCOMING_MARKERS:
        if search_key(marker) in folded:
            return "upcoming", marker

    remaining = re.search(
        r"\bson\s+(\d{1,3})\s+gün\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if remaining:
        return "active", remaining.group(0)

    for marker in ACTIVE_MARKERS:
        if search_key(marker) in folded:
            return "active", marker

    return "unknown", ""


def _parse_date_token(token: str) -> date | None:
    token = normalize_text(token)

    numeric = re.fullmatch(
        r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})",
        token,
    )
    if numeric:
        day, month, year = map(int, numeric.groups())
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None

    named = re.fullmatch(
        r"(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(\d{4})",
        token,
        flags=re.IGNORECASE,
    )
    if named:
        day = int(named.group(1))
        month = MONTHS.get(search_key(named.group(2)))
        year = int(named.group(3))
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                return None

    return None


DATE_TOKEN = (
    r"\b(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
    r"|\d{1,2}\s+(?:Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|"
    r"Haziran|Temmuz|Ağustos|Agustos|Eylül|Eylul|Ekim|"
    r"Kasım|Kasim|Aralık|Aralik)\s+\d{4})\b"
)


def extract_campaign_dates(text: str) -> tuple[date | None, date | None, str]:
    normalized = normalize_text(text)

    # En yüksek öncelik: iki tarafında da yıl bulunan sayısal aralık.
    # Örnek: 06/08/2026 - 31/08/2026
    # Bu kontrol, sayfadaki başka tarihler nedeniyle yanlış başlangıç/bitiş
    # seçilmesini engeller.
    numeric_range = re.search(
        (
            r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})"
            r"\s*[-–—]\s*"
            r"(\d{1,2})[./](\d{1,2})[./](\d{4})\b"
        ),
        normalized,
        flags=re.IGNORECASE,
    )
    if numeric_range:
        try:
            start = date(
                int(numeric_range.group(3)),
                int(numeric_range.group(2)),
                int(numeric_range.group(1)),
            )
            end = date(
                int(numeric_range.group(6)),
                int(numeric_range.group(5)),
                int(numeric_range.group(4)),
            )
            return start, end, numeric_range.group(0)
        except ValueError:
            pass

    # İki tarafında da yıl bulunan Türkçe adlandırılmış tarih aralığı.
    # Örnek: "1 Temmuz 2026 - 31 Ağustos 2026". Bu kontrol
    # yıl içeren metnin aşağıdaki yıl-yok kalıpları tarafından parçalı
    # eşleşmesini engeller.
    full_named_range = re.search(
        rf"({DATE_TOKEN})\s*(?:-|–|—|ile|ve)\s*({DATE_TOKEN})",
        normalized,
        flags=re.IGNORECASE,
    )
    if full_named_range:
        start = _parse_date_token(full_named_range.group(1))
        end = _parse_date_token(full_named_range.group(2))
        if start and end:
            return start, end, full_named_range.group(0)

    # Başlangıç tarafında yılın tekrar edilmediği adlandırılmış aralık.
    # Örnek: "03 Aralık - 31 Ağustos 2026". Başlangıç ay/günü
    # bitiş ay/gününden ilerideyse kampanya önceki yılda başlamıştır.
    partial_named_range = re.search(
        (
            r"\b(\d{1,2})\s+"
            r"(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|"
            r"Temmuz|Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|"
            r"Aralık|Aralik)"
            r"\s*(?:-|–|—|ile|ve)\s*"
            r"(\d{1,2})\s+"
            r"(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|"
            r"Temmuz|Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|"
            r"Aralık|Aralik)\s+(\d{4})\b"
        ),
        normalized,
        flags=re.IGNORECASE,
    )
    if partial_named_range:
        end_year = int(partial_named_range.group(5))
        start_day = int(partial_named_range.group(1))
        end_day = int(partial_named_range.group(3))
        start_month = MONTHS.get(search_key(partial_named_range.group(2)))
        end_month = MONTHS.get(search_key(partial_named_range.group(4)))
        if start_month and end_month:
            start_year = end_year
            if (start_month, start_day) > (end_month, end_day):
                start_year -= 1
            try:
                return (
                    date(start_year, start_month, start_day),
                    date(end_year, end_month, end_day),
                    partial_named_range.group(0),
                )
            except ValueError:
                pass

    # Yıl belirtilmeyen Türkçe kampanya tarih aralıkları.
    # Örnek: "1-31 Ağustos" veya "1 Ağustos - 31 Ağustos".
    yearless_compact_named_range = re.search(
        (
            r"\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+"
            r"(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|"
            r"Temmuz|Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|"
            r"Aralık|Aralik)\b"
        ),
        normalized,
        flags=re.IGNORECASE,
    )
    if yearless_compact_named_range:
        month = MONTHS.get(
            search_key(yearless_compact_named_range.group(3))
        )
        year = _today().year
        if month:
            try:
                start = date(
                    year,
                    month,
                    int(yearless_compact_named_range.group(1)),
                )
                end = date(
                    year,
                    month,
                    int(yearless_compact_named_range.group(2)),
                )
                return start, end, yearless_compact_named_range.group(0)
            except ValueError:
                pass

    yearless_named_range = re.search(
        (
            r"\b(\d{1,2})\s+"
            r"(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|"
            r"Temmuz|Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|"
            r"Aralık|Aralik)"
            r"\s*(?:-|–|—|ile|ve)\s*"
            r"(\d{1,2})\s+"
            r"(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|"
            r"Temmuz|Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|"
            r"Aralık|Aralik)\b"
        ),
        normalized,
        flags=re.IGNORECASE,
    )
    if yearless_named_range:
        year = _today().year
        start_month = MONTHS.get(
            search_key(yearless_named_range.group(2))
        )
        end_month = MONTHS.get(
            search_key(yearless_named_range.group(4))
        )
        if start_month and end_month:
            try:
                start = date(
                    year,
                    start_month,
                    int(yearless_named_range.group(1)),
                )
                end = date(
                    year,
                    end_month,
                    int(yearless_named_range.group(3)),
                )
                return start, end, yearless_named_range.group(0)
            except ValueError:
                pass

    # "1-31 Temmuz 2026" biçimi.
    compact_named_range = re.search(
        (
            r"\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\s+"
            r"(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|"
            r"Temmuz|Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|"
            r"Aralık|Aralik)\s+(\d{4})\b"
        ),
        normalized,
        flags=re.IGNORECASE,
    )
    if compact_named_range:
        month = MONTHS.get(
            search_key(compact_named_range.group(3))
        )
        year = int(compact_named_range.group(4))
        if month:
            try:
                start = date(
                    year,
                    month,
                    int(compact_named_range.group(1)),
                )
                end = date(
                    year,
                    month,
                    int(compact_named_range.group(2)),
                )
                return start, end, compact_named_range.group(0)
            except ValueError:
                pass

    range_match = re.search(
        rf"({DATE_TOKEN})\s*(?:-|–|—|ile|ve)\s*({DATE_TOKEN})",
        normalized,
        flags=re.IGNORECASE,
    )
    if range_match:
        start = _parse_date_token(range_match.group(1))
        end = _parse_date_token(range_match.group(2))
        if start and end:
            return start, end, range_match.group(0)

    between_match = re.search(
        rf"({DATE_TOKEN}).{{0,35}}({DATE_TOKEN})"
        r".{0,35}(?:tarihleri arasında|tarihleri arasinda)",
        normalized,
        flags=re.IGNORECASE,
    )
    if between_match:
        start = _parse_date_token(between_match.group(1))
        end = _parse_date_token(between_match.group(2))
        if start and end:
            return start, end, between_match.group(0)

    start_end_match = re.search(
        rf"({DATE_TOKEN}).{{0,60}}"
        r"(?:tarihinde başlayacak|tarihinde baslayacak|"
        r"tarihinde başlar|tarihinde baslar)"
        rf".{{0,120}}({DATE_TOKEN}).{{0,30}}"
        r"(?:tarihine kadar|tarihine dek)",
        normalized,
        flags=re.IGNORECASE,
    )
    if start_end_match:
        start = _parse_date_token(start_end_match.group(1))
        end = _parse_date_token(start_end_match.group(2))
        if start and end:
            return start, end, start_end_match.group(0)

    # "31 Temmuz tarihine kadar" / "31 Ağustos'a kadar"
    # gibi yıl yazılmayan bitiş tarihleri.
    yearless_end_match = re.search(
        (
            r"\b(\d{1,2})\s+"
            r"(Ocak|Şubat|Subat|Mart|Nisan|Mayıs|Mayis|Haziran|"
            r"Temmuz|Ağustos|Agustos|Eylül|Eylul|Ekim|Kasım|Kasim|"
            r"Aralık|Aralik)"
            r"\s*(?:tarihine\s+kadar|['’]?(?:a|e|ya|ye)\s+kadar)\b"
        ),
        normalized,
        flags=re.IGNORECASE,
    )
    if yearless_end_match:
        month = MONTHS.get(
            search_key(yearless_end_match.group(2))
        )
        if month:
            try:
                end = date(
                    _today().year,
                    month,
                    int(yearless_end_match.group(1)),
                )
                return None, end, yearless_end_match.group(0)
            except ValueError:
                pass

    end_match = re.search(
        rf"({DATE_TOKEN}).{{0,30}}"
        r"(?:tarihine kadar|tarihine dek|"
        r"['’]?(?:a|e|ya|ye)\s+kadar|"
        r"son başvuru|son katılım|son katilim|"
        r"bitiş tarihi|bitis tarihi)",
        normalized,
        flags=re.IGNORECASE,
    )
    if end_match:
        end = _parse_date_token(end_match.group(1))
        if end:
            return None, end, end_match.group(0)

    start_match = re.search(
        rf"({DATE_TOKEN}).{{0,30}}"
        r"(?:tarihinde başlayacak|tarihinde baslayacak|"
        r"tarihinde başlar|tarihinde baslar|başlangıç tarihi|"
        r"baslangic tarihi)",
        normalized,
        flags=re.IGNORECASE,
    )
    if start_match:
        start = _parse_date_token(start_match.group(1))
        if start:
            return start, None, start_match.group(0)

    tokens = re.findall(DATE_TOKEN, normalized, flags=re.IGNORECASE)
    parsed = [
        parsed_date
        for token in tokens
        if (parsed_date := _parse_date_token(token)) is not None
        and date(2024, 1, 1) <= parsed_date <= date(2035, 12, 31)
    ]

    unique = sorted(set(parsed))
    if len(unique) >= 2:
        return unique[0], unique[-1], "Metindeki tarih aralığı"
    if len(unique) == 1:
        folded = search_key(normalized)
        if any(
            marker in folded
            for marker in (
                "tarihine kadar",
                "son basvuru",
                "son katilim",
                "bitis tarihi",
            )
        ):
            return None, unique[0], "Metindeki son tarih"

    return None, None, ""


def evaluate_campaign_status(
    *,
    text: str,
    listing_status: str = "unknown",
    listing_evidence: str = "",
    reference_date: date | None = None,
) -> CampaignStatusResult:
    today = _today(reference_date)
    checked_at = _iso_now()
    folded = search_key(text)

    start_date, end_date, date_evidence = extract_campaign_dates(text)

    if any(search_key(marker) in folded for marker in EXPIRED_MARKERS):
        return CampaignStatusResult(
            status="expired",
            start_date=start_date.isoformat() if start_date else "",
            end_date=end_date.isoformat() if end_date else "",
            evidence=next(
                marker
                for marker in EXPIRED_MARKERS
                if search_key(marker) in folded
            ),
            reason="detail_expired_marker",
            checked_at=checked_at,
        )

    if end_date and end_date < today:
        return CampaignStatusResult(
            status="expired",
            start_date=start_date.isoformat() if start_date else "",
            end_date=end_date.isoformat(),
            evidence=date_evidence,
            reason="end_date_passed",
            checked_at=checked_at,
        )

    if start_date and start_date > today:
        return CampaignStatusResult(
            status="upcoming",
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat() if end_date else "",
            evidence=date_evidence,
            reason="start_date_in_future",
            checked_at=checked_at,
        )

    if start_date or end_date:
        return CampaignStatusResult(
            status="active",
            start_date=start_date.isoformat() if start_date else "",
            end_date=end_date.isoformat() if end_date else "",
            evidence=date_evidence,
            reason="today_within_campaign_dates",
            checked_at=checked_at,
        )

    listing_status = normalize_text(listing_status).casefold()
    if listing_status in {"active", "upcoming", "expired"}:
        return CampaignStatusResult(
            status=listing_status,
            start_date="",
            end_date="",
            evidence=listing_evidence,
            reason="listing_status",
            checked_at=checked_at,
        )

    return CampaignStatusResult(
        status="unknown",
        start_date="",
        end_date="",
        evidence="",
        reason="insufficient_date_or_status_evidence",
        checked_at=checked_at,
    )
