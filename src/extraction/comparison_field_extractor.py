from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class FinanceExtraction:
    finance_type: str
    profit_share_rate_min: float | None
    profit_share_rate_max: float | None
    profit_share_rate_text: str | None
    financing_amount_min: float | None
    financing_amount_max: float | None
    financing_amount_text: str | None
    maturity_min_months: int | None
    maturity_max_months: int | None
    maturity_text: str | None
    grace_period_months: int | None
    installment_count: int | None
    allocation_fee_amount: float | None
    allocation_fee_rate: float | None
    allocation_fee_status: str | None
    expense_status: str | None
    expense_details: str | None
    campaign_advantage: str | None
    evidence_text: str | None
    extraction_confidence: float


@dataclass(frozen=True)
class BenefitExtraction:
    benefit_type: str
    amount: float | None
    rate: float | None
    points: float | None
    minimum_spending: float | None
    maximum_benefit: float | None
    description: str
    evidence: str | None


@dataclass(frozen=True)
class AudienceExtraction:
    audience_type: str
    audience_label: str
    details: str | None = None


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = unicodedata.normalize("NFKC", str(value))
    text = (
        text.replace("\u200b", " ")
        .replace("\ufeff", " ")
        .replace("\xa0", " ")
    )
    text = re.sub(r"\s+", " ", text).strip()

    # HTML metninde parçalanmış para tutarlarını birleştirir:
    # "5 0.000 TL" -> "50.000 TL".
    text = re.sub(
        r"(?<=\d)\s+(?=\d{1,2}\.\d{3}\b)",
        "",
        text,
    )
    return text

# NONFINANCE_GUARDRAILS_V1
EXTRACTION_BOILERPLATE_PHRASES = (
    "Dijital Bankacılık Kampanyaları",
    "Kredi Kartı Kampanyaları",
    "Maaş Ödemesi Kampanyaları",
    "Yatırım Kampanyaları",
    "Birikim / Fon Kampanyaları",
    "Sigorta Kampanyaları",
    "Finansman Kampanyaları",
    "Ticari Kampanyalar",
    "Diğer Kampanyalar",
    "Biten Kampanyalar",
    "Başvuru Merkezi",
    "Hesaplama Araçları",
    "Satılık Gayrimenkuller",
    "Sayfa Görüntüsü",
    "Sayfa İçeriği",
    "Müşterimiz Olun",
    "Anında Şifre",
    "Mobil Uygulama",
)


def strip_extraction_boilerplate(value: str) -> str:
    cleaned = normalize_text(value)

    for phrase in EXTRACTION_BOILERPLATE_PHRASES:
        cleaned = re.sub(
            re.escape(phrase),
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )

    return normalize_text(cleaned)


def search_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", normalize_text(value))
    return "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    ).casefold().replace("ı", "i")


def parse_tr_number(value: str | None) -> float | None:
    if not value:
        return None

    token = re.sub(
        r"[^\d,.\-]",
        "",
        normalize_text(value),
    )
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


def unique(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value is not None and value not in result:
            result.append(value)
    return result


def clean_content_text(title: str, text: str) -> str:
    cleaned = normalize_text(text)

    if "tom bank hadi" in search_key(title):
        tail_markers = (
            "İlginizi Çekebilir",
            "Ilginizi Cekebilir",
            "Kampanya Detayı Hadi Black Kredi Kartı",
            "Kampanya Detayi Hadi Black Kredi Karti",
            "Hadi bir T.O.M. Katılım Bankası",
            "Hadi bir T.O.M. Katilim Bankasi",
        )
        positions = []
        for marker in tail_markers:
            match = re.search(
                re.escape(marker),
                cleaned,
                flags=re.IGNORECASE,
            )
            if match:
                positions.append(match.start())
        if positions:
            cleaned = cleaned[:min(positions)]

        title_core = normalize_text(title).split("|", 1)[0].strip()
        if title_core:
            matches = list(
                re.finditer(
                    re.escape(title_core),
                    cleaned,
                    flags=re.IGNORECASE,
                )
            )
            if matches:
                cleaned = cleaned[matches[-1].start():]

        matches = list(
            re.finditer(
                r"Hemen\s+İndir",
                cleaned,
                flags=re.IGNORECASE,
            )
        )
        if matches:
            candidate = normalize_text(
                cleaned[matches[-1].end():]
            )
            if len(candidate) >= 60:
                cleaned = candidate

    patterns = (
        r"\bAlbaraka Mobil\s+Mobil Bankacılık Aç\b",
        r"\bMüşteri Ol\s+Müşteri Ol\b",
        (
            r"\bKampanya Başlangıç ve Bitiş\s+"
            r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s*-\s*"
            r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b"
        ),
    )

    for pattern in patterns:
        cleaned = re.sub(
            pattern,
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )

    title_value = normalize_text(title)
    if title_value:
        cleaned = re.sub(
            rf"^\s*{re.escape(title_value)}\s*",
            " ",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        )

    title_core = normalize_text(title).split("|", 1)[0].strip()
    if title_core:
        cleaned = re.sub(
            rf"^\s*{re.escape(title_core)}\s*",
            " ",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        )

    return normalize_text(cleaned)


def sentences(text: str) -> list[str]:
    parts = re.split(
        r"(?<=[.!?])\s+|(?<=;)\s+|\s*[•●▪]\s*|\n+",
        normalize_text(text),
    )
    return [
        item.strip(" -–—")
        for item in parts
        if item.strip(" -–—")
    ]


def evidence_sentence(
    text: str,
    keywords: tuple[str, ...],
    maximum_length: int = 420,
) -> str | None:
    folded_keywords = tuple(search_key(item) for item in keywords)

    for sentence in sentences(text):
        folded = search_key(sentence)
        if any(keyword in folded for keyword in folded_keywords):
            return sentence[:maximum_length]

    return None


def detect_finance_type(title: str, text: str) -> str:
    title_key = search_key(title)

    title_rules = (
        (
            ("kfk destekli yatirim", "yatirim finansmani"),
            "Yatırım Finansmanı",
        ),
        (
            ("turizm sektorune kfk", "turizm sektorune"),
            "Turizm İşletme Finansmanı",
        ),
        (
            ("saglam business kart",),
            "Ticari Kart Taksitlendirme",
        ),
        (
            (
                "taksitli alisveris kredisi",
                "magazadan alisveris kredisi",
                "hadi taksitli kredi",
            ),
            "Alışveriş Finansmanı",
        ),
        (
            ("saglik kredisi",),
            "Sağlık Finansmanı",
        ),
        (
            ("hadi veresiye",),
            "Veresiye Finansmanı",
        ),
        (
            ("taksitlio", "alisveris finansmani"),
            "Alışveriş Finansmanı",
        ),
        (
            ("tarimda kuveyt turk", "tarim leasing"),
            "Tarım Leasing Finansmanı",
        ),
        (("payini sen sec",), "Esnek Ödeme Finansmanı"),
        (("togg",), "Togg Taşıt Finansmanı"),
        (
            ("konut ve tasit",),
            "Konut ve Taşıt Finansmanı",
        ),
        (("pratik finansman kart",), "İhtiyaç Finansmanı"),
        (("alisveris finansmani",), "İhtiyaç Finansmanı"),
        (("konut",), "Konut Finansmanı"),
        (("tasit",), "Taşıt Finansmanı"),
        (("umre",), "Umre Finansmanı"),
        (("hac",), "Hac Finansmanı"),
        (("arsa",), "Arsa Finansmanı"),
        (("isyeri", "is yeri"), "İşyeri Finansmanı"),
        (("egitim",), "Eğitim Finansmanı"),
        (("enerji", "ges"), "Enerji Finansmanı"),
        (("ihtiyac",), "İhtiyaç Finansmanı"),
        (("tarim",), "Tarım Finansmanı"),
    )

    for terms, label in title_rules:
        if any(term in title_key for term in terms):
            return label

    body_key = search_key(clean_content_text(title, text))
    body_rules = (
        (
            ("kfk destekli yatirim",),
            "Yatırım Finansmanı",
        ),
        (
            ("turizm isletme belgesi", "turizm sektorune"),
            "Turizm İşletme Finansmanı",
        ),
        (
            ("saglam business kart",),
            "Ticari Kart Taksitlendirme",
        ),
        (
            (
                "taksitli alisveris kredisi",
                "magazadan alisveris kredisi",
                "hadi taksitli kredi",
            ),
            "Alışveriş Finansmanı",
        ),
        (
            ("saglik kredisi",),
            "Sağlık Finansmanı",
        ),
        (
            ("hadi veresiye",),
            "Veresiye Finansmanı",
        ),
        (
            ("taksitlio", "alisveris finansmani"),
            "Alışveriş Finansmanı",
        ),
        (
            ("leasing finansmani", "tarim makineleri"),
            "Tarım Leasing Finansmanı",
        ),
        (("pratik finansman kart",), "İhtiyaç Finansmanı"),
        (("ihtiyac finansmani",), "İhtiyaç Finansmanı"),
        (("togg finansmani",), "Togg Taşıt Finansmanı"),
        (("umre finansmani",), "Umre Finansmanı"),
        (("konut finansmani",), "Konut Finansmanı"),
        (("tasit finansmani",), "Taşıt Finansmanı"),
    )

    for terms, label in body_rules:
        if any(term in body_key for term in terms):
            return label

    return "Diğer Finansman"


def extract_profit_share_rates(
    text: str,
) -> tuple[float | None, float | None, str | None]:
    patterns = (
        (
            r"(?:aylık\s+)?k[aâ]r(?:\s+payı)?\s+oran(?:ı|ları)?"
            r"\s*[:\-]?\s*%\s*(\d{1,3}(?:[.,]\d{1,4})?)"
        ),
        (
            r"%\s*(\d{1,3}(?:[.,]\d{1,4})?)"
            r"\s*(?:aylık\s+)?k[aâ]r(?:\s+payı)?"
        ),
        (
            r"(?:aylık\s+)?k[aâ]r(?:\s+payı)?\s+oran(?:ı|ları)?"
            r"\s*[:\-]?\s*(\d{1,3}(?:[.,]\d{1,4})?)\s*%"
        ),
        (
            r"%\s*(\d{1,3}(?:[.,]\d{1,4})?)"
            r"[^.!?]{0,40}?"
            r"k[aâ]r\s+payı"
        ),
    )

    values: list[float] = []

    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = parse_tr_number(match.group(1))
            if value is not None and 0 <= value <= 100:
                values.append(value)

    values = unique(values)

    zero_rate_patterns = (
        r"\bk[a\u00e2]r\s+pays[\u0131i]z\b",
        (
            r"\bk[a\u00e2]r(?:\s+pay[\u0131i])?\s+"
            r"(?:yok|yoktur)\b"
        ),
        (
            r"(?:ayl[\u0131i]k\s+)?"
            r"k[a\u00e2]r(?:\s+pay[\u0131i])?\s+"
            r"oran(?:[\u0131i]|lar[\u0131i])?"
            r"\s*[:\-]?\s*%?\s*"
            r"0(?:[.,]0+)?\b"
        ),
        (
            r"%\s*0(?:[.,]0+)?\s*"
            r"(?:ayl[\u0131i]k\s+)?"
            r"k[a\u00e2]r(?:\s+pay[\u0131i])?"
        ),
    )

    if not values and any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in zero_rate_patterns
    ):
        values = [0.0]

    if not values:
        return None, None, None

    def format_rate(value: float) -> str:
        if float(value).is_integer():
            return f"%{int(value)}"
        return f"%{str(value).replace('.', ',')}"

    display = ", ".join(
        format_rate(value)
        for value in values[:6]
    )
    return min(values), max(values), display



def extract_tom_vade_farki_rates(
    title: str,
    text: str,
) -> tuple[float | None, float | None, str | None]:
    """
    T.O.M. Hadi finansman kampanyaları oranı çoğu zaman
    "kâr payı" yerine "vade farkı" olarak yayımlar.
    Bu oran yalnızca finance_campaign alan çıkarımında kullanılır.
    """
    full_text = normalize_text(f"{title} {text}")
    folded = search_key(full_text)

    if (
        "tom bank hadi" not in folded
        and "t.o.m. katilim bankasi" not in folded
    ):
        return None, None, None

    patterns = (
        r"%\s*(\d{1,3}(?:[.,]\d{1,4})?)\s*vade\s+fark[ıi]",
        r"(\d{1,3}(?:[.,]\d{1,4})?)\s*%\s*vade\s+fark[ıi]",
        r"(\d{1,2}(?:[.,]\d{1,4})?)\s+vade\s+fark[ıi](?:yla|ile)?",
        r"vade\s+fark[ıi]\s*(?:oran[ıi])?\s*[:\\-]?\s*%?\s*(\d{1,3}(?:[.,]\d{1,4})?)",
    )

    values: list[float] = []
    for pattern in patterns:
        for match in re.finditer(
            pattern,
            full_text,
            flags=re.IGNORECASE,
        ):
            value = parse_tr_number(match.group(1))
            if value is not None and 0 <= value <= 100:
                values.append(value)

    values = unique(values)

    if (
        not values
        and re.search(
            r"vade\s+farks[ıi]z",
            full_text,
            flags=re.IGNORECASE,
        )
    ):
        values = [0.0]

    if not values:
        return None, None, None

    def format_rate(value: float) -> str:
        if float(value).is_integer():
            return f"%{int(value)}"
        return f"%{str(value).replace('.', ',')}"

    return (
        min(values),
        max(values),
        ", ".join(format_rate(value) for value in values[:6]),
    )

def extract_financing_amounts(
    text: str,
) -> tuple[float | None, float | None, str | None]:
    money = r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?"

    patterns = (
        (
            rf"{money}\s*(?:TL|₺)['’]?(?:ye|ya)?\s+kadar"
            rf"(?:\s+\S+){{0,5}}\s+finansman"
        ),
        (
            rf"finansman\s+tutar(?:ı|i)\s*[:\-]?\s*"
            rf"{money}\s*(?:TL|₺)"
        ),
        (
            rf"(?:azami|maksimum|en\s+fazla)\s+"
            rf"{money}\s*(?:TL|₺)['’]?(?:ye|ya)?\s+"
            rf"(?:kadar\s+)?finansman"
        ),
        (
            rf"{money}\s*(?:TL|₺)\s+(?:tutarında\s+)?"
            rf"finansman\s+(?:desteği|destegi|imk[aâ]nı)"
        ),
        (
            rf"{money}\s*(?:TL|₺)['’]?(?:lik|lık|luk|lük)\s+"
            rf"finansman"
        ),
        (
            rf"{money}\s*(?:TL|₺)\s+"
            rf"(?:finansman\s+)?seçenekleri"
        ),
    )

    values: list[float] = []
    evidence: list[str] = []

    # T.O.M./Hadi örneği:
    # "1.000 TL – 150.000 TL arasındaki kredi kullandırımları"
    for match in re.finditer(
        (
            rf"{money}\s*(?:TL|₺)\s*[-–—]\s*"
            rf"{money}\s*(?:TL|₺)\s+aras[ıi]ndaki\s+"
            rf"(?:kredi|finansman)"
        ),
        text,
        flags=re.IGNORECASE,
    ):
        lower = parse_tr_number(match.group(1))
        upper = parse_tr_number(match.group(2))
        if lower is not None and lower > 0:
            values.append(lower)
        if upper is not None and upper > 0:
            values.append(upper)
        evidence.append(match.group(0))

    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = parse_tr_number(match.group(1))
            if value is not None and value > 0:
                values.append(value)
                evidence.append(match.group(0))

    if "alisveris finansmani" in search_key(text):
        for match in re.finditer(
            (
                rf"{money}\s*(?:TL|₺)['’]?(?:ye|ya)?\s+kadar"
                rf"(?:\s+\S+){{0,8}}\s+alışveriş"
            ),
            text,
            flags=re.IGNORECASE,
        ):
            value = parse_tr_number(match.group(1))
            if value is not None and value > 0:
                values.append(value)

    values = unique(values)
    if not values:
        return None, None, None

    minimum = min(values)
    maximum = max(values)

    def format_money(value: float) -> str:
        return f"{int(round(value)):,}".replace(",", ".") + " TL"

    if minimum == maximum:
        display = f"{format_money(maximum)}'ye kadar"
    else:
        display = (
            f"{format_money(minimum)}-"
            f"{format_money(maximum)}"
        )

    return minimum, maximum, display




def extract_maturities(
    text: str,
) -> tuple[int | None, int | None, str | None]:
    normalized = normalize_text(text)

    # Erteleme/ödemesiz dönem finansmanın toplam vadesi değildir.
    maturity_text_source = re.sub(
        (
            r"\b\d{1,3}\s*ay(?:a)?\s+"
            r"(?:ertelemeli|erteleme|ertelemeyle|ödemesiz\s+dönem)"
        ),
        " ",
        normalized,
        flags=re.IGNORECASE,
    )

    values: list[int] = []

    # "1-6 ay vade", "7–12 ay vadeli" gibi açık aralıklar.
    for match in re.finditer(
        (
            r"\b(\d{1,3})\s*[-–—]\s*(\d{1,3})\s*"
            r"ay(?:a)?\s+(?:vade|vadeli)\b"
        ),
        maturity_text_source,
        flags=re.IGNORECASE,
    ):
        lower = int(match.group(1))
        upper = int(match.group(2))
        if 1 <= lower <= upper <= 600:
            values.extend((lower, upper))

    patterns = (
        r"(\d{1,3})\s*aya?\s+kadar\s+(?:vade|vadeli)",
        r"(\d{1,3})\s*aya?\s+varan\s+vade",
        r"(\d{1,3})\s*ay\s+(?:vade|vadeli)",
        r"vade(?:\s+süresi)?\s*[:\-]?\s*(\d{1,3})\s*aya?\s+kadar",
        r"vade(?:\s+süresi)?\s*[:\-]?\s*(\d{1,3})\s*ay",
        r"(\d{1,3})\s*aylık\s+vade",
    )

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            maturity_text_source,
            flags=re.IGNORECASE,
        ):
            value = int(match.group(1))
            if 1 <= value <= 600:
                values.append(value)

    # "6 ay, 12 ay ve 36 ay vade seçenekleri" gibi listelerde
    # son değer dışındaki ayları da toplar.
    for sentence in sentences(maturity_text_source):
        sentence_key = search_key(sentence)
        if "vade" not in sentence_key:
            continue

        month_values = [
            int(match.group(1))
            for match in re.finditer(
                r"\b(\d{1,3})\s*ay\b",
                sentence,
                flags=re.IGNORECASE,
            )
            if 1 <= int(match.group(1)) <= 600
        ]

        if (
            len(month_values) >= 2
            and (
                "secenek" in sentence_key
                or "," in sentence
                or " ve " in sentence_key
                or re.search(
                    r"\d\s*[-–—]\s*\d",
                    sentence,
                )
            )
        ):
            values.extend(month_values)

    installment_sequence_values: list[int] = []
    for match in re.finditer(
        r"\b(\d{1,3}(?:\s*[-–—]\s*\d{1,3}){1,8})\s*Taksit\b",
        normalized,
        flags=re.IGNORECASE,
    ):
        installment_sequence_values.extend(
            int(token)
            for token in re.findall(r"\d{1,3}", match.group(1))
            if 1 <= int(token) <= 120
        )

    installment_values = [
        int(match.group(1))
        for pattern in (
            r"(\d{1,3})\s*taksite?\s+kadar",
            r"(\d{1,3})\s*aya?\s+varan\s+taksit",
            r"(\d{1,3})\s*aya?\s+kadar\s+taksit",
        )
        for match in re.finditer(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )
        if 1 <= int(match.group(1)) <= 120
    ]

    if not installment_values:
        installment_values = [
            int(match.group(1))
            for match in re.finditer(
                r"vade\s+farks[ıi]z\s+(\d{1,3})\s*taksit",
                normalized,
                flags=re.IGNORECASE,
            )
            if 1 <= int(match.group(1)) <= 120
        ]

    installment_values.extend(installment_sequence_values)

    if installment_values:
        max_installment = max(installment_values)
        if not values:
            values = [max_installment]
        elif max_installment > max(values):
            values.append(max_installment)

    values = unique(values)
    if not values:
        return None, None, None

    minimum = min(values)
    maximum = max(values)

    if minimum == maximum:
        display = f"{maximum} aya kadar"
    else:
        display = f"{minimum}-{maximum} ay"

    return minimum, maximum, display


def extract_grace_period_months(text: str) -> int | None:
    values: list[int] = []

    patterns = (
        r"(\d{1,3})\s*ay\s+ertelemeli",
        r"(\d{1,3})\s*ay\s+erteleme",
        r"(\d{1,3})\s*ay\s+ertelemeyle",
        r"(\d{1,3})\s*aya?\s+kadar\s+ödemesiz\s+dönem",
        r"(\d{1,3})\s*aya?\s+varan\s+ödemesiz\s+dönem",
        r"(\d{1,3})\s*ay\s+ödemesiz\s+dönem",
        r"(\d{1,3})\s*\+\s*\d{1,3}\s*ay",
    )

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            value = int(match.group(1))
            if 1 <= value <= 120:
                values.append(value)

    return max(values) if values else None



def extract_installment_count(text: str) -> int | None:
    values: list[int] = []

    # T.O.M./Hadi gibi sayfalarda "3-6-9-12 Taksit" kullanılır.
    for match in re.finditer(
        r"\b(\d{1,3}(?:\s*[-–—]\s*\d{1,3}){1,8})\s*Taksit\b",
        text,
        flags=re.IGNORECASE,
    ):
        for token in re.findall(r"\d{1,3}", match.group(1)):
            value = int(token)
            if 1 <= value <= 120:
                values.append(value)

    patterns = (
        r"(\d{1,3})\s*(?:eşit\s+)?taksit",
        r"(\d{1,3})\s*taksite?\s+varan",
        r"(\d{1,3})\s*taksite?\s+kadar",
        r"(\d{1,3})\s*aya?\s+varan\s+(?:vade\s+farks[ıi]z\s+)?taksit",
        r"(\d{1,3})\s*aya?\s+kadar\s+(?:vade\s+farks[ıi]z\s+)?taksit",
        r"(\d{1,3})\s*['’]?(?:e|a|ye|ya)\s+varan\s+taksit",
        r"(\d{1,3})\s*['’]?(?:e|a|ye|ya)\s+kadar\s+taksit",
    )

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            value = int(match.group(1))
            if 1 <= value <= 120:
                values.append(value)

    return max(values) if values else None



def extract_allocation_fee(
    text: str,
) -> tuple[float | None, float | None, str | None]:
    no_fee_patterns = (
        (
            r"tahsis\s+ücreti\s+"
            r"(?:alınmayacaktır|alınmaz|yoktur|yok|ücretsiz)"
        ),
        r"(?:ücretsiz|masrafsız)\s+tahsis",
    )

    if any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in no_fee_patterns
    ):
        return None, None, "Tahsis ücreti yok"

    rate_patterns = (
        (
            r"tahsis\s+ücreti(?:\s+oranı)?\s*[:\-]?\s*"
            r"%\s*(\d{1,3}(?:[.,]\d{1,4})?)"
        ),
        (
            r"tahsis\s+ücreti[^.]{0,140}?"
            r"%\s*(\d{1,3}(?:[.,]\d{1,4})?)"
            r"(?:['’]?[ıiuü])?\s+oranında"
        ),
        (
            r"%\s*(\d{1,3}(?:[.,]\d{1,4})?)\s*"
            r"tahsis\s+ücreti"
        ),
    )

    for pattern in rate_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return (
                None,
                parse_tr_number(match.group(1)),
                "Tahsis ücreti oranı belirtilmiş",
            )

    amount_match = re.search(
        (
            r"tahsis\s+ücreti\s*[:\-]?\s*"
            r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?"
            r"\s*(?:TL|₺)"
        ),
        text,
        flags=re.IGNORECASE,
    )
    if amount_match:
        return (
            parse_tr_number(amount_match.group(1)),
            None,
            "Tahsis ücreti tutarı belirtilmiş",
        )

    return None, None, None


def extract_expense(
    text: str,
) -> tuple[str | None, str | None]:
    no_expense_patterns = (
        r"masrafsız",
        (
            r"dosya\s+masrafı\s+"
            r"(?:alınmayacaktır|alınmaz|yoktur|yok)"
        ),
        (
            r"ekspertiz\s+ücreti\s+"
            r"(?:karşılanacaktır|karşılanır|ücretsiz)"
        ),
        (
            r"tahsis\s+ücreti\s+"
            r"(?:alınmayacaktır|alınmaz|yoktur|yok|ücretsiz)"
        ),
    )

    detail = evidence_sentence(
        text,
        (
            "masraf",
            "komisyon",
            "tahsis ücreti",
            "ekspertiz ücreti",
            "sigorta ücreti",
            "dosya ücreti",
        ),
    )

    if any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in no_expense_patterns
    ):
        return "Masraf avantajı var", detail

    if re.search(
        r"(?:masraf|ücret)\s+(?:alınır|tahsil edilir|uygulanır)",
        text,
        flags=re.IGNORECASE,
    ):
        return "Masraf var", detail

    if detail:
        return "Masraf bilgisi mevcut", detail

    return None, None


def extract_campaign_advantage(
    title: str,
    text: str,
) -> tuple[str | None, str | None]:
    cleaned = clean_content_text(title, text)
    keywords = (
        "özel",
        "avantaj",
        "finansman",
        "kâr payı",
        "kar payı",
        "vade",
        "tahsis",
        "masraf",
        "ücretsiz",
        "indirim",
        "worldpuan",
        "ödül",
        "taksit",
    )

    candidates: list[tuple[int, str]] = []

    for sentence in sentences(cleaned):
        folded = search_key(sentence)

        if len(sentence) < 20 or len(sentence) > 480:
            continue
        if sentence.rstrip().endswith("?"):
            continue

        score = sum(
            1
            for keyword in keywords
            if search_key(keyword) in folded
        )

        positive_terms = (
            "avantaj",
            "fırsat",
            "firsat",
            "özel",
            "ozel",
            "vade farksız",
            "vade farksiz",
            "kâr payı",
            "kar payi",
            "peşinat",
            "pesinat",
            "ödemesiz dönem",
            "odemesiz donem",
            "aya varan vade",
            "daha düşük kâr oranı",
            "daha dusuk kar orani",
            "kendi isteğine göre",
            "kendi istegine gore",
        )
        score += 2 * sum(
            1
            for term in positive_terms
            if search_key(term) in folded
        )

        lowered_sentence = sentence.casefold()

        if "tahsis ücreti" in lowered_sentence:
            score -= 2

        if any(
            phrase in folded
            for phrase in (
                "kampanya kosullari",
                "kampanyaya basvurabilecektir",
                "tarihleri arasinda",
                "hazir kampanya firsatlarimiz",
            )
        ):
            score -= 4

        if any(
            phrase in folded
            for phrase in (
                "degisiklik yapma hakkina sahiptir",
                "degistirme hakkina sahiptir",
                "degerlendirme sonucuna gore degisebilir",
                "degisiklik gosterebilir",
                "hakkini sakli tutar",
                "onay surecine tabidir",
            )
        ):
            score -= 12

        if re.search(r"\d", sentence):
            score += 1

        if any(
            token in folded
            for token in (
                "ana sayfa",
                "iletisim",
                "gizlilik",
                "cerez",
                "sube ve atm",
                "mobil bankacilik ac",
            )
        ):
            score -= 4

        if score > 0:
            candidates.append((score, sentence))

    if not candidates:
        return None, None

    candidates.sort(key=lambda item: (-item[0], len(item[1])))
    best = candidates[0][1]
    return best[:320], best[:420]


def extraction_confidence(values: Iterable[Any]) -> float:
    found = sum(
        value not in (None, "", [])
        for value in values
    )
    return round(min(0.98, 0.50 + found * 0.055), 2)


def extract_finance_fields(
    title: str,
    text: str,
) -> FinanceExtraction:
    cleaned = clean_content_text(title, text)
    full_text = normalize_text(f"{title} {cleaned}")

    rate_min, rate_max, rate_text = extract_profit_share_rates(
        full_text
    )

    tom_rate_min, tom_rate_max, tom_rate_text = (
        extract_tom_vade_farki_rates(
            title,
            cleaned,
        )
    )
    if tom_rate_text is not None:
        rate_min = tom_rate_min
        rate_max = tom_rate_max
        rate_text = tom_rate_text
    amount_min, amount_max, amount_text = (
        extract_financing_amounts(full_text)
    )
    maturity_min, maturity_max, maturity_text = (
        extract_maturities(full_text)
    )
    grace_period_months = extract_grace_period_months(full_text)
    installment_count = extract_installment_count(full_text)
    allocation_amount, allocation_rate, allocation_status = (
        extract_allocation_fee(full_text)
    )
    expense_status, expense_details = extract_expense(full_text)
    advantage, evidence = extract_campaign_advantage(title, cleaned)
    finance_type = detect_finance_type(title, cleaned)

    confidence = extraction_confidence(
        (
            finance_type,
            rate_text,
            amount_text,
            maturity_text,
            grace_period_months,
            installment_count,
            allocation_status,
            expense_status,
            advantage,
        )
    )

    return FinanceExtraction(
        finance_type=finance_type,
        profit_share_rate_min=rate_min,
        profit_share_rate_max=rate_max,
        profit_share_rate_text=rate_text,
        financing_amount_min=amount_min,
        financing_amount_max=amount_max,
        financing_amount_text=amount_text,
        maturity_min_months=maturity_min,
        maturity_max_months=maturity_max,
        maturity_text=maturity_text,
        grace_period_months=grace_period_months,
        installment_count=installment_count,
        allocation_fee_amount=allocation_amount,
        allocation_fee_rate=allocation_rate,
        allocation_fee_status=allocation_status,
        expense_status=expense_status,
        expense_details=expense_details,
        campaign_advantage=advantage,
        evidence_text=evidence,
        extraction_confidence=confidence,
    )


def extract_minimum_spending(text: str) -> float | None:
    money = r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?"
    patterns = (
        (
            rf"(?:en\s+az|min(?:imum)?)\s*{money}\s*(?:TL|₺)"
            rf"(?:'lik|'lık|'luk|'lük)?\s*(?:harcama|alışveriş)"
        ),
        (
            rf"{money}\s*(?:TL|₺)\s+ve\s+üzeri"
            rf"(?:\s+\w+){{0,4}}\s*(?:harcama|alışveriş)"
        ),
    )

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return parse_tr_number(match.group(1))

    return None


def extract_maximum_benefit(text: str) -> float | None:
    money = r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?"
    patterns = (
        (
            rf"(?:en\s+fazla|maksimum|toplamda)\s*"
            rf"{money}\s*(?:TL|₺)\s*"
            rf"(?:ödül|iade|indirim|worldpuan|puan)"
        ),
        (
            rf"{money}\s*(?:TL|₺)['’]?(?:ye|ya)\s+varan\s*"
            rf"(?:ödül|iade|indirim|worldpuan|puan)"
        ),
    )

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return parse_tr_number(match.group(1))

    return None



def extract_benefits(
    title: str,
    text: str,
) -> list[BenefitExtraction]:
    content_text = strip_extraction_boilerplate(
        clean_content_text(title, text)
    )
    full_text = normalize_text(
        f"{title} {content_text}"
    )
    minimum_spending = extract_minimum_spending(full_text)
    maximum_benefit = extract_maximum_benefit(full_text)
    results: list[BenefitExtraction] = []

    money = r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?"

    def format_rate(value: float) -> str:
        if float(value).is_integer():
            return str(int(value))
        return str(value).replace(".", ",")

    # Sabit tutarlı indirimler ödül olarak değil, indirim olarak
    # tutulur: "4.000 TL indirim", "3.000 TL'ye varan indirim".
    fixed_discount_patterns = (
        (
            rf"{money}\s*(?:TL|₺)['’]?(?:ye|ya)?\s+"
            rf"(?:varan\s+)?"
            rf"(?:\S+\s+){{0,5}}?indirim"
        ),
        (
            rf"(?:toplamda\s+)?{money}\s*(?:TL|₺)\s+"
            rf"(?:\S+\s+){{0,4}}?indirim"
        ),
    )
    fixed_discount_values: list[tuple[float, str]] = []
    for sentence in sentences(full_text):
        for pattern in fixed_discount_patterns:
            for match in re.finditer(
                pattern,
                sentence,
                flags=re.IGNORECASE,
            ):
                value = parse_tr_number(match.group(1))
                if value is not None and value > 0:
                    fixed_discount_values.append(
                        (value, sentence[:420])
                    )

    if fixed_discount_values:
        amount, evidence = max(
            fixed_discount_values,
            key=lambda item: item[0],
        )
        results.append(
            BenefitExtraction(
                "discount",
                amount,
                None,
                None,
                minimum_spending,
                maximum_benefit or amount,
                f"{int(round(amount)):,} TL indirim".replace(
                    ",",
                    ".",
                ),
                evidence,
            )
        )

    # "%75'e varan kargo indirimi", "%20'ye varan indirim" ve
    # doğrudan "%10 indirim" ifadeleri.
    percent_discount_matches: list[tuple[float, str]] = []
    percent_discount_pattern = (
        r"%\s*(\d{1,3}(?:[.,]\d+)?)"
        r"(?:['’]?(?:e|a|ye|ya))?"
        r"(?:\s+kadar|\s+varan)?"
        r"(?:\s+\S+){0,5}\s+indirim"
    )
    for sentence in sentences(full_text):
        for match in re.finditer(
            percent_discount_pattern,
            sentence,
            flags=re.IGNORECASE,
        ):
            value = parse_tr_number(match.group(1))
            if value is not None and 0 < value <= 100:
                percent_discount_matches.append(
                    (value, sentence[:420])
                )

    for rate, evidence in sorted(
        {
            (value, evidence)
            for value, evidence in percent_discount_matches
        },
        key=lambda item: item[0],
        reverse=True,
    ):
        results.append(
            BenefitExtraction(
                "discount",
                None,
                rate,
                None,
                minimum_spending,
                maximum_benefit,
                f"%{format_rate(rate)} indirim",
                evidence,
            )
        )

    # Nakit iade: "%1 nakit iade", "1.000 TL harcama iadesi".
    cashback_rate_matches: list[tuple[float, str]] = []
    cashback_amount_matches: list[tuple[float, str]] = []

    for sentence in sentences(full_text):
        for match in re.finditer(
            (
                r"%\s*(\d{1,3}(?:[.,]\d+)?)"
                r"(?:\s*['’]\s*(?:e|a|ye|ya|i|ı|u|ü))?"
                r"(?:\s+kadar|\s+varan)?"
                r"[^.!?%]{0,70}?"
                r"\b(?:nakit\s+)?iade\b"
            ),
            sentence,
            flags=re.IGNORECASE,
        ):
            value = parse_tr_number(match.group(1))
            if value is not None and 0 < value <= 100:
                cashback_rate_matches.append(
                    (value, sentence[:420])
                )

        for match in re.finditer(
            (
                rf"{money}\s*(?:TL|₺)"
                rf"(?:['’]?(?:ye|ya|e|a))?"
                rf"(?:\s+kadar|\s+varan)?"
                rf"(?:\s+\S+){{0,4}}\s+"
                rf"(?:nakit\s+|harcama\s+)?iade"
            ),
            sentence,
            flags=re.IGNORECASE,
        ):
            value = parse_tr_number(match.group(1))
            if value is not None and value > 0:
                cashback_amount_matches.append(
                    (value, sentence[:420])
                )

    # "İlk harcamanızın yarısı nakit iade" açıkça %50 anlamına gelir.
    # Bu dönüşüm yalnızca "yarısı + iade" aynı cümlede bulunduğunda
    # uygulanır; genel "yarısı" ifadelerinden oran üretilmez.
    for sentence in sentences(full_text):
        sentence_key = search_key(sentence)
        if (
            "yarisi" in sentence_key
            and "iade" in sentence_key
            and (
                "harcama" in sentence_key
                or "alisveris" in sentence_key
                or "odeme" in sentence_key
            )
        ):
            cashback_rate_matches.append(
                (50.0, sentence[:420])
            )

    if cashback_rate_matches or cashback_amount_matches:
        best_rate = (
            max(cashback_rate_matches, key=lambda item: item[0])
            if cashback_rate_matches
            else None
        )
        best_amount = (
            max(cashback_amount_matches, key=lambda item: item[0])
            if cashback_amount_matches
            else None
        )
        evidence = (
            best_rate[1]
            if best_rate
            else best_amount[1]
            if best_amount
            else None
        )
        results.append(
            BenefitExtraction(
                "cashback",
                best_amount[0] if best_amount else None,
                best_rate[0] if best_rate else None,
                None,
                minimum_spending,
                maximum_benefit,
                "Nakit iade avantajı",
                evidence,
            )
        )

    # Puan ve Altın Puan.
    point_matches = list(
        re.finditer(
            (
                rf"{money}\s*(?:TL|₺)?"
                r"(?:\s*['’]\s*(?:e|a|ye|ya))?"
                r"(?:\s+kadar|\s+varan)?\s*"
                r"(?:Altın\s+Puan|Worldpuan|WorldPuan|"
                r"ParafPara|Paraf\s+Para|Bankkart\s+Lira|puan)"
            ),
            full_text,
            flags=re.IGNORECASE,
        )
    )
    point_values = [
        parse_tr_number(match.group(1))
        for match in point_matches
    ]
    point_values = [
        value
        for value in point_values
        if value is not None and value > 0
    ]

    qualitative_points_evidence = evidence_sentence(
        full_text,
        (
            "tamamı altın puan",
            "altın puan olarak iade",
        ),
    )

    if point_values or qualitative_points_evidence:
        results.append(
            BenefitExtraction(
                "shopping_points",
                None,
                None,
                max(point_values) if point_values else None,
                minimum_spending,
                None,
                (
                    "Altın Puan, Worldpuan, ParafPara, Bankkart Lira veya alışveriş puanı"
                    if point_values
                    else "Ödemenin tamamı Altın Puan olarak iade"
                ),
                (
                    evidence_sentence(
                        full_text,
                        (
                            "altın puan",
                            "worldpuan",
                            "parafpara",
                            "bankkart lira",
                            "puan kazan",
                        ),
                    )
                    or qualitative_points_evidence
                ),
            )
        )

    # Mil avantajı yalnızca açık sayısal Mil kanıtıyla çıkarılır.
    mile_matches = list(
        re.finditer(
            (
                rf"{money}\s*Mil(?:['’]?(?:e|a))?"
                r"(?:\s+varan)?"
            ),
            full_text,
            flags=re.IGNORECASE,
        )
    )
    mile_values = [
        parse_tr_number(match.group(1))
        for match in mile_matches
    ]
    mile_values = [
        value
        for value in mile_values
        if value is not None and value > 0
    ]
    if mile_values:
        mile_rate_match = re.search(
            (
                r"%\s*(\d{1,3}(?:[.,]\d+)?)"
                r"[\s\S]{0,120}?\bMil\b"
            ),
            full_text,
            flags=re.IGNORECASE,
        )
        maximum_miles = max(mile_values)
        results.append(
            BenefitExtraction(
                "miles",
                None,
                (
                    parse_tr_number(mile_rate_match.group(1))
                    if mile_rate_match
                    else None
                ),
                maximum_miles,
                minimum_spending,
                None,
                f"{int(maximum_miles):,} Mil'e kadar".replace(
                    ",",
                    ".",
                ),
                evidence_sentence(full_text, ("mil",)),
            )
        )

    # Ödül/hediye çıkarımı indirim, iade, puan ve Mil'den ayrılır.
    reward_candidates: list[tuple[float, str]] = []
    reward_patterns = (
        (
            rf"{money}\s*(?:TL|₺)['’]?(?:ye|ya)?\s+"
            rf"(?:varan\s+)?(?:\S+\s+){{0,3}}?"
            rf"(?:ödül|hediye|alışveriş\s+çeki|çek\b)"
        ),
        (
            rf"{money}\s*(?:TL|₺)\s+değerinde"
            rf"(?:\s+\S+){{0,6}}\s+"
            rf"(?:paket|ürün\s+paketi|hediye|çek\b)"
        ),
        (
            rf"(?:toplamda\s+)?{money}\s*(?:TL|₺)"
            rf"(?:\s+\S+){{0,3}}\s+"
            rf"(?:kazan(?:ın|abilirsiniz|ıyor|ır)?|kazandırıyor)"
        ),
    )

    for sentence in sentences(full_text):
        sentence_key = search_key(sentence)
        for pattern in reward_patterns:
            for match in re.finditer(
                pattern,
                sentence,
                flags=re.IGNORECASE,
            ):
                matched_key = search_key(match.group(0))
                if any(
                    term in matched_key
                    for term in (
                        "indirim",
                        "iade",
                        "altin puan",
                        "worldpuan",
                        " mil",
                    )
                ):
                    continue

                # ATM işlem limitleri ödül değildir.
                if any(
                    term in sentence_key
                    for term in (
                        "para cekme",
                        "para yatirma",
                        "atm'lerinden",
                        "atm’lerinden",
                        "gunluk para cekme",
                    )
                ):
                    continue

                # "1.000 TL üzeri harcamada 10.000 Mil hediye"
                # gibi cümlelerde harcama tutarı ödül değildir.
                if (
                    "mil" in sentence_key
                    and "hediye" in sentence_key
                    and "tl" in matched_key
                    and "harcama" in matched_key
                ):
                    continue

                value = parse_tr_number(match.group(1))
                if value is not None and value > 0:
                    reward_candidates.append(
                        (value, sentence[:420])
                    )

    if reward_candidates:
        amount, evidence = max(
            reward_candidates,
            key=lambda item: item[0],
        )
        results.append(
            BenefitExtraction(
                "reward",
                amount,
                None,
                None,
                minimum_spending,
                maximum_benefit or amount,
                "Ödül veya hediye tutarı",
                evidence,
            )
        )

    installment_count = extract_installment_count(full_text)
    if installment_count:
        results.append(
            BenefitExtraction(
                "installment",
                None,
                None,
                None,
                minimum_spending,
                None,
                f"{installment_count} taksit",
                evidence_sentence(full_text, ("taksit",)),
            )
        )

    special_rate_evidence = evidence_sentence(
        full_text,
        (
            "özel kur",
            "avantajlı kur",
        ),
    )
    special_rate_key = search_key(
        special_rate_evidence or ""
    )
    if (
        special_rate_evidence
        and any(
            term in special_rate_key
            for term in (
                "kur",
                "doviz",
                "altin",
                "gumus",
                "kiymetli maden",
            )
        )
    ):
        results.append(
            BenefitExtraction(
                "special_rate",
                None,
                None,
                None,
                None,
                None,
                "Özel döviz veya kıymetli maden kuru",
                special_rate_evidence,
            )
        )

    pos_key = search_key(full_text)
    pos_evidence = evidence_sentence(
        full_text,
        (
            "sanal pos",
            "pos kampanyası",
            "pos çözümleri",
            "bloke",
            "komisyon",
            "ek taksit",
        ),
    )
    if (
        (
            "pos kampanyasi" in pos_key
            or "sanal pos" in pos_key
            or "kuveyt turk pos" in pos_key
            or "pos cozumleri" in pos_key
            or "pos'tan" in pos_key
        )
        and pos_evidence
    ):
        results.append(
            BenefitExtraction(
                "pos_advantage",
                None,
                None,
                None,
                minimum_spending,
                None,
                "POS komisyon, bloke veya ek taksit avantajı",
                pos_evidence,
            )
        )

    free_service_patterns = (
        (
            r"ücretsiz\s+HGS\s+etiketi",
            "Ücretsiz HGS etiketi",
            ("ücretsiz HGS etiketi",),
        ),
        (
            r"kart\s+ücreti\s+alınmamaktadır",
            "Kart ücreti alınmıyor",
            ("kart ücreti",),
        ),
        (
            r"ücretsiz\s+faydalan",
            "Ücretsiz ürün veya hizmet paketi",
            ("ücretsiz faydalan",),
        ),
    )
    for pattern, description, keywords in free_service_patterns:
        if re.search(
            pattern,
            full_text,
            flags=re.IGNORECASE,
        ):
            results.append(
                BenefitExtraction(
                    "free_service",
                    None,
                    None,
                    None,
                    None,
                    None,
                    description,
                    evidence_sentence(full_text, keywords),
                )
            )

    # Aynı tür ve açıklamadaki tekrarları temizle.
    # Nitel avantajlar yalnızca başlıktaki açık sinyallerle
    # eklenir. Böylece ilgili kampanya bağlantıları ve ortak
    # site metinleri yanlış avantaj üretmez.
    title_key = search_key(title)

    qualitative_title_rules = (
        (
            ("lounge",),
            "free_service",
            "Ücretsiz lounge hizmeti",
        ),
        (
            ("fast track",),
            "free_service",
            "Ücretsiz Fast Track hizmeti",
        ),
        (
            ("asistanlik hizmetleri",),
            "service",
            "Asistanlık hizmetleri",
        ),
        (
            ("gastroclub",),
            "membership",
            "GastroClub üyeliği",
        ),
        (
            ("statunuzu yukseltin",),
            "status_upgrade",
            "Statü yükseltme ayrıcalığı",
        ),
        (
            ("mil puanina donusuyor",),
            "miles",
            "Bonusların Mil Puanına dönüşümü",
        ),
        (
            ("sifir komisyon", "masrafsiz bankacilik"),
            "fee_exemption",
            "Komisyon veya masraf muafiyeti",
        ),
        (
            ("gunluk hesap", "katilim hesab"),
            "return_advantage",
            "Avantajlı getiri oranı",
        ),
        (
            ("masterkobi",),
            "privilege",
            "MasterKOBİ ayrıcalıkları",
        ),
    )

    for title_terms, benefit_type, description in (
        qualitative_title_rules
    ):
        if not any(
            term in title_key
            for term in title_terms
        ):
            continue

        results.append(
            BenefitExtraction(
                benefit_type,
                None,
                None,
                None,
                None,
                None,
                description,
                title,
            )
        )



    # NONFINANCE_GUARDRAILS_V5
    # Pasaport harcı kampanyasındaki "3 ay
    # taksitlendirilebilecektir" ifadesi, genel taksit
    # deseninin dışında kaldığı için başlık ve açık kanıtla
    # tamamlanır.
    targeted_title_key = search_key(title)

    if (
        "pasaport harci" in targeted_title_key
        and not any(
            item.benefit_type == "installment"
            for item in results
        )
    ):
        targeted_evidence = (
            evidence_sentence(
                full_text,
                (
                    "pasaport harcı",
                    "3 ay taksit",
                    "taksitlendirilebilecektir",
                ),
            )
            or title
        )

        results.append(
            BenefitExtraction(
                "installment",
                None,
                None,
                None,
                None,
                None,
                "3 taksit",
                targeted_evidence,
            )
        )

    unique_results: list[BenefitExtraction] = []
    seen: set[tuple[str, str]] = set()
    for item in results:
        key = (item.benefit_type, item.description)
        if key not in seen:
            seen.add(key)
            unique_results.append(item)

    return unique_results


AUDIENCE_RULES = (
    (
        (
            "yeni müşterilerimize özel",
            "yeni müşterilere özel",
            "yeni müşteri olan",
            "yeni müşterimiz olan",
            "ilk kez müşteri olan",
            "müşterimiz olun",
            "müşteri olun",
            "müşteri olup",
            "müşteri olduktan sonra",
            "müşteri olduktan",
            "müşterimiz olanlar",
            "müşterisi olun",
            "müşterisi olan",
            "hesap açın",
            "hesap açan müşteriler",
            "mobilden müşterimiz olan",
            "mobil'den müşterimiz olan",
            "mobil’den müşterimiz olan",
            "mobilden müşterimiz olarak",
            "mobil'den müşterimiz olarak",
            "mobil’den müşterimiz olarak",
            "xtm'den müşterimiz olan",
            "xtm’den müşterimiz olan",
        ),
        "new_customer",
        "Yeni Müşteriler",
    ),
    (
        (
            "mevcut müşteriler",
            "daha önce kurumumuzda hiç işlem gerçekleştirmemiş "
            "mevcut müşteriler",
        ),
        "existing_customer",
        "Mevcut Müşteriler",
    ),
    (
        (
            "dijital müşteriler",
            "mobil müşteriler",
            "mobil üzerinden müşteri",
            "kuveyt türk mobil'den müşteri",
            "kuveyt türk mobil’den müşteri",
            "kuveyt türk mobil üzerinden müşteri",
            "mobilden müşterimiz olan",
            "mobil'den müşterimiz olan",
            "mobil’den müşterimiz olan",
            "mobilden müşterimiz olarak",
            "mobil'den müşterimiz olarak",
            "mobil’den müşterimiz olarak",
        ),
        "digital_customer",
        "Dijital Müşteriler",
    ),
    (
        (
            "kart sahipleri",
            "worldcard sahipleri",
            "world kart sahipleri",
            "kredi kartları ile",
            "kredi kartlarınız ile",
            "kredi kartıyla",
            "kredi kartı ile",
            "kredi kartına özel",
            "kredi kartınıza özel",
            "kredi kartı olan",
            "kredi kartı başvuruları",
            "banka kartları ile",
            "sağlam kart",
            "miles&smiles kart",
            "business kredi kartları",
            "tüzel kredi kartları",
            "business kredi kartları",
            "sağlam business kart",
            "sağlam tohum kart",
            "business kredi kartları",
            "business kart",
            "miles&smiles kuveyt türk",
            "bu kartların sanal ve ek kartları",
            "bu kartların ek kartları",
        ),
        "card_holder",
        "Kart Sahipleri",
    ),
    (
        (
            "ticari müşteriler",
            "kobi müşteriler",
            "kobi’lere",
            "kobi'lere",
            "kobilere",
            "esnaf",
            "çiftçi",
            "şahıs firması",
            "şahıs firmaları",
            "tüzel şirket",
            "tüzel firma",
            "tüzel kredi kartları",
            "net ihracatçı",
            "e-ihracat yapan",
            "sağlam business kart",
            "sağlam tohum kart",
            "üye işyeri",
            "üye işyerinin",
            "sanal pos",
            "pos kampanyası",
            "pos çözümleri",
        ),
        "business_customer",
        "Ticari Müşteriler",
    ),
    (
        (
            "bireysel müşteriler",
            "bireysel kredi kartları",
            "bireysel kredi kartıyla",
            "bireysel kredi kartı olan",
            "bireysel kredi kartı başvuruları",
            "bireysel kredi kartı başvurularını",
            "bireysel kuveyt türk kredi kartları",
            "bireysel kartlar",
        ),
        "individual_customer",
        "Bireysel Müşteriler",
    ),
    (
        ("maaş müşterileri",),
        "salary_customer",
        "Maaş Müşterileri",
    ),
    (
        (
            "18-25 yaş",
            "18 - 25 yaş",
            "genç müşteriler",
        ),
        "young_customer",
        "Genç Müşteriler",
    ),
)


def extract_audiences(
    title: str,
    text: str,
    *,
    source_group: str = "",
    campaign_category: str = "",
) -> list[AudienceExtraction]:
    content_text = strip_extraction_boilerplate(
        clean_content_text(title, text)
    )
    folded = search_key(f"{title} {content_text}")
    title_key = search_key(title)
    source_key = search_key(source_group)
    category_key = search_key(campaign_category)

    results: list[AudienceExtraction] = []
    seen: set[str] = set()

    def add(
        audience_type: str,
        audience_label: str,
        details: str | None = None,
    ) -> None:
        if audience_type in seen:
            return
        seen.add(audience_type)
        results.append(
            AudienceExtraction(
                audience_type,
                audience_label,
                details,
            )
        )

    for terms, audience_type, label in AUDIENCE_RULES:
        if audience_type in {
            "new_customer",
            "business_customer",
        }:
            continue

        if any(
            search_key(term) in folded
            for term in terms
        ):
            add(audience_type, label)

    metadata_rules = (
        (
            "bireysel kart kampanyalari",
            (
                ("card_holder", "Kart Sahipleri"),
            ),
        ),
        (
            "ticari kart kampanyalari",
            (
                ("business_customer", "Ticari Müşteriler"),
                ("card_holder", "Kart Sahipleri"),
            ),
        ),
        (
            "ticari pos kampanyalari",
            (
                ("business_customer", "Ticari Müşteriler"),
            ),
        ),
        (
            "bireysel musteri ol kampanyalari",
            (
                ("individual_customer", "Bireysel Müşteriler"),
                ("new_customer", "Yeni Müşteriler"),
            ),
        ),
        (
            "ticari musteri ol kampanyalari",
            (
                ("business_customer", "Ticari Müşteriler"),
                ("new_customer", "Yeni Müşteriler"),
            ),
        ),
        (
            "ticari kobi kampanyalari",
            (
                ("business_customer", "Ticari Müşteriler"),
            ),
        ),
        (
            "bireysel tum kampanyalar",
            (
                ("individual_customer", "Bireysel Müşteriler"),
            ),
        ),
    )

    for source_phrase, audiences in metadata_rules:
        if source_phrase not in source_key:
            continue

        for audience_type, label in audiences:
            add(audience_type, label)

    if "happy kart kampanyalari" in source_key:
        add("card_holder", "Happy Kart Kullanıcıları")

    explicit_card_title_terms = (
        "ala kart",
        "ala kredi kart",
        "happy kart",
        "happy kredi kart",
        "mastercard business kart",
    )
    explicit_card_body_terms = (
        "kart sahipleri",
        "kartinizla",
        "kartiniz ile",
        "kredi kartinizla",
        "kredi kartiniz ile",
    )

    if (
        any(term in title_key for term in explicit_card_title_terms)
        or any(term in folded for term in explicit_card_body_terms)
    ):
        add("card_holder", "Kart Sahipleri")

    if category_key == "new_customer_campaign":
        add("new_customer", "Yeni Müşteriler")

    explicit_new_customer_title_terms = (
        "mobilden turkiye finansli ol",
        "mobilden musteri olan",
        "mobilden tanisin",
        "gunluk hesap",
    )

    if any(
        term in title_key
        for term in explicit_new_customer_title_terms
    ):
        add("new_customer", "Yeni Müşteriler")

    if (
        "ticari kampanyalar" in source_key
        or "ticari kart kampanyalari" in source_key
        or "kobi" in title_key
        or "business kart" in title_key
        or "masterkobi" in title_key
    ):
        add("business_customer", "Ticari Müşteriler")

    explicit_title_audiences = (
        (
            "banka calisanlarina ozel",
            "bank_employee",
            "Banka Çalışanları",
        ),
        (
            "kamu calisanlarina ozel",
            "public_employee",
            "Kamu Çalışanları",
        ),
        (
            "yeni yatirim hesabi",
            "investment_account_customer",
            "Yeni Yatırım Hesabı Açan Müşteriler",
        ),
        (
            "saglik meslek paketi",
            "profession_group",
            "Sağlık Meslek Mensupları",
        ),
        (
            "tushad uyeleri",
            "association_member",
            "TÜSHAD Üyeleri",
        ),
        (
            "pilvak",
            "profession_group",
            "Pilotlar",
        ),
        (
            "emeklinin bankasi",
            "retired_customer",
            "Emekliler",
        ),
    )

    for phrase, audience_type, label in (
        explicit_title_audiences
    ):
        if phrase in title_key:
            add(audience_type, label)

    if "gunluk hesap" in title_key:
        add("individual_customer", "Bireysel Müşteriler")

    if "yakinini mobil subeye davet et" in title_key:
        add(
            "individual_customer",
            "Mevcut Bireysel Müşteriler",
        )
        add("new_customer", "Yeni Müşteriler")

    # Son doğrulanan Türkiye Finans kampanyalarında başlık
    # doğrudan hedef kitleyi tanımlar. Bu kurallar gövde veya
    # footer anahtar kelimelerine dayanmaz.
    targeted_title_audience_rules = (
        (
            ("asistanlik hizmetleri",),
            "card_holder",
            "Âlâ Kart Sahipleri",
        ),
        (
            ("yolcu360",),
            "card_holder",
            "Bireysel Âlâ Kart Sahipleri",
        ),
        (
            ("hgs talimatina 700 tl bonus",),
            "card_holder",
            "Âlâ Kart Sahipleri",
        ),
        (
            (
                "ala musterilere ozel ala bes",
                "ala bes ile gelecege yatirim yapin",
            ),
            "premium_customer",
            "Âlâ Bankacılık Müşterileri",
        ),
    )

    for phrases, audience_type, label in (
        targeted_title_audience_rules
    ):
        if any(
            phrase in title_key
            for phrase in phrases
        ):
            add(audience_type, label)

    return results
