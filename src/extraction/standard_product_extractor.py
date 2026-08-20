from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from src.finance_rule_engine import dumps_finance_rules


@dataclass(frozen=True)
class StandardProductExtraction:
    product_name: str
    clean_text: str
    minimum_financing_amount: float | None
    maximum_financing_amount: float | None
    minimum_maturity_months: int | None
    maximum_maturity_months: int | None
    profit_share_rate: float | None
    profit_share_rate_text: str | None
    interest_free: bool
    interest_free_text: str | None
    maturity_rules_text: str | None
    maturity_reference_upper_amount: float | None
    financing_ratio_rules_text: str | None
    maximum_financing_ratio: float | None
    housing_first_home_rules_text: str | None
    housing_additional_home_rules_text: str | None
    housing_finance_rules_json: str | None
    vehicle_finance_rules_text: str | None
    vehicle_age_rules_text: str | None
    shopping_general_limit_amount: float | None
    shopping_general_max_maturity_months: int | None
    shopping_finance_rules_text: str | None
    shopping_phone_rule_text: str | None
    shopping_tablet_max_maturity_months: int | None
    shopping_computer_max_maturity_months: int | None
    fee_waiver_text: str | None
    insurance_fee_waived: bool
    allocation_fee_waived: bool
    commission_fee_waived: bool
    finance_rules_json: str | None


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = unicodedata.normalize(
        "NFKC",
        str(value),
    )
    text = (
        text.replace("\u00a0", " ")
        .replace("\u200b", " ")
        .replace("\ufeff", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


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


def clean_page_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    # ASP.NET / SharePoint sayfalarında tüm gerçek sayfa
    # içeriği tek bir <form> kapsayıcısının içinde olabilir.
    # Formu komple silmek başlık ve ürün metnini de yok eder.
    #
    # Bu yüzden formun kendisini kaldırıp içeriğini koruyoruz.
    for form in soup.find_all("form"):
        form.unwrap()

    # Hesaplama araçlarının kullanıcıya ürün şartı olmayan
    # varsayılan değerlerini extraction'a taşımamak için
    # interaktif elemanları yine tamamen kaldırıyoruz.
    for node in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
            "header",
            "footer",
            "nav",
            "input",
            "select",
            "option",
            "button",
        ]
    ):
        node.decompose()

    heading = soup.find("h1")
    product_name = normalize_text(
        heading.get_text(" ", strip=True)
        if heading
        else ""
    )

    # Bazı SharePoint/JS sayfalarında görünür ürün başlığı h1
    # olmayabilir. Bu durumda URL'den isim uydurmak yerine
    # sayfanın kendi metadata başlığını kullan.
    if not product_name:
        og_title = soup.find(
            "meta",
            attrs={"property": "og:title"},
        )

        if og_title is not None:
            product_name = normalize_text(
                og_title.get("content")
            )

    if not product_name and soup.title:
        product_name = normalize_text(
            soup.title.get_text(" ", strip=True)
        )

    # Site adını ürün adına taşımamak için yalnız yaygın
    # başlık ayraçlarından sonraki Türkiye Finans ekini temizle.
    product_name = re.sub(
        r"\s*(?:\||-|–|—)\s*Türkiye\s+Finans\s*$",
        "",
        product_name,
        flags=re.IGNORECASE,
    ).strip()

    # Bazı banka sayfalarında SSS/accordion alanı ilk <main>
    # etiketinin dışında render ediliyor. Sadece ilk <main>'i
    # okumak ürünün gerçek koşullarını kaybettirebilir.
    # Header/footer/nav/form vb. gürültüyü yukarıda temizledikten
    # sonra tüm body metnini kullanıyoruz.
    content_root = soup.body or soup
    clean_text = normalize_text(
        content_root.get_text(" ", strip=True)
    )

    return product_name, clean_text


def _money_value(raw: str | None) -> float | None:
    value = parse_tr_number(raw)
    if value is None or value <= 0:
        return None
    return value


def extract_amounts(
    text: str,
) -> tuple[float | None, float | None]:
    """
    Yalnızca açık ürün koşullarını kabul eder.

    Kabul:
      - minimum 500 TL, maksimum 16.500 TL
      - minimum finansman tutarı 500 TL
      - maksimum 250.000 TL finansman
      - 500 TL ile 16.500 TL arasında finansman

    Kabul edilmez:
      - Finansman Tutarı 1.000 TL 2.000.000 TL
      - slider / hesaplama aracı başlangıç-bitiş değerleri
    """
    normalized = normalize_text(text)

    minimum: float | None = None
    maximum: float | None = None

    money = r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?"

    range_patterns = (
        rf"(?:minimum|asgari|en\s+az)\s+{money}\s*(?:TL|₺)"
        rf"[^.!?]{{0,100}}?"
        rf"(?:maksimum|azami|en\s+fazla)\s+{money}\s*(?:TL|₺)",

        rf"{money}\s*(?:TL|₺)\s*(?:ile|[-–—])\s*"
        rf"{money}\s*(?:TL|₺)\s+aras[ıi](?:nda|ndaki)"
        rf"[^.!?]{{0,60}}(?:finansman|kulland[ıi]r)",

        rf"(?:finansman|kulland[ıi]r)[^.!?]{{0,80}}"
        rf"{money}\s*(?:TL|₺)\s*(?:ile|[-–—])\s*"
        rf"{money}\s*(?:TL|₺)\s+aras[ıi](?:nda|ndaki)",
    )

    for pattern in range_patterns:
        match = re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )
        if not match:
            continue

        lower = _money_value(match.group(1))
        upper = _money_value(match.group(2))

        if (
            lower is not None
            and upper is not None
            and lower <= upper
        ):
            return lower, upper

    min_patterns = (
        rf"(?:minimum|asgari|en\s+az)"
        rf"(?:\s+finansman)?(?:\s+tutar[ıi])?"
        rf"\s*[:\-]?\s*{money}\s*(?:TL|₺)",

        rf"(?:finansman|kulland[ıi]r)"
        rf"[^.!?]{{0,50}}"
        rf"(?:minimum|asgari|en\s+az)"
        rf"[^.!?]{{0,20}}{money}\s*(?:TL|₺)",

        # "Harcama yapabileceğiniz minimum tutar 500 TL'dir."
        rf"(?:harcama|alışveriş|alisveris)"
        rf"[^.!?]{{0,70}}"
        rf"(?:minimum|asgari|en\s+az)\s+tutar"
        rf"\s*[:\-]?\s*{money}\s*(?:TL|₺)",
    )

    max_patterns = (
        rf"(?:maksimum|azami|en\s+fazla)"
        rf"(?:\s+finansman)?(?:\s+tutar[ıi])?"
        rf"\s*[:\-]?\s*{money}\s*(?:TL|₺)",

        rf"(?:finansman|kulland[ıi]r)"
        rf"[^.!?]{{0,50}}"
        rf"(?:maksimum|azami|en\s+fazla)"
        rf"[^.!?]{{0,20}}{money}\s*(?:TL|₺)",

        rf"(?:maksimum|azami|en\s+fazla)"
        rf"[^.!?]{{0,15}}{money}\s*(?:TL|₺)"
        rf"[^.!?]{{0,40}}finansman",

        # "maksimum kredi (finansman) limiti 50.000 TL"
        rf"(?:maksimum|azami|en\s+fazla)"
        rf"[^.!?]{{0,40}}"
        rf"(?:kredi\s*)?"
        rf"(?:\(\s*finansman\s*\)\s*)?"
        rf"limit(?:i)?"
        rf"\s*[:\-]?\s*{money}\s*(?:TL|₺)",

        # "Eğitim finansmanı üst limiti 600.000 TL"
        rf"(?:finansman|kredi)"
        rf"[^.!?]{{0,50}}"
        rf"(?:üst|azami|maksimum)\s+limit(?:i)?"
        rf"\s*[:\-]?\s*{money}\s*(?:TL|₺)",
    )

    for pattern in min_patterns:
        match = re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )
        if match:
            minimum = _money_value(match.group(1))
            if minimum is not None:
                break

    for pattern in max_patterns:
        match = re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )
        if match:
            maximum = _money_value(match.group(1))
            if maximum is not None:
                break

    return minimum, maximum


def extract_maturity(
    text: str,
) -> tuple[int | None, int | None]:
    normalized = normalize_text(text)

    minimum_candidates: list[int] = []
    maximum_candidates: list[int] = []

    range_patterns = (
        r"(?:minimum|asgari|en\s+az)\s+(\d{1,3})\s*ay"
        r"[^.!?]{0,100}?"
        r"(?:maksimum|azami|en\s+fazla)\s+(\d{1,3})\s*ay",
        r"(\d{1,3})\s*[-–—]\s*(\d{1,3})\s*ay"
        r"(?:\s+aras[ıi])?",
    )

    for pattern in range_patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            lower = int(match.group(1))
            upper = int(match.group(2))
            if 1 <= lower <= upper <= 120:
                minimum_candidates.append(lower)
                maximum_candidates.append(upper)

    min_patterns = (
        r"(?:minimum|asgari|en\s+az)"
        r"(?:\s+vade)?\s*[:\-]?\s*(\d{1,3})\s*ay",
    )

    max_patterns = (
        r"(?:maksimum|azami|en\s+fazla)"
        r"(?:\s+vade)?\s*[:\-]?\s*(\d{1,3})\s*ay",
        r"\b(\d{1,3})\s*aya?\s+kadar\s+(?:(?:fark|farklı)\s+)?vade",
        r"\bmaksimum\s+(\d{1,3})\s*ay\s+vade",
        r"\b(\d{1,3})\s*aya?\s+varan\s+(?:taksit|vade)",

        # Örnek:
        # "maksimum 250.000 TL ve 36 ay vade ile sınırlıdır."
        #
        # "maksimum" kelimesi tutarı niteler; aynı cümlede
        # "36 ay vade" ürünün azami vadesidir.
        r"(?:maksimum|azami|en\s+fazla)"
        r"\s+"
        r"(?:\d{1,3}(?:[.\s]\d{3})*|\d+)"
        r"(?:,\d+)?\s*(?:TL|₺)"
        r"\s*(?:ve|,|/|ile)\s*"
        r"(\d{1,3})\s*ay\s+vade\b",
    )

    for pattern in min_patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            value = int(match.group(1))
            if 1 <= value <= 120:
                minimum_candidates.append(value)

    for pattern in max_patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            value = int(match.group(1))
            if 1 <= value <= 120:
                maximum_candidates.append(value)

    return (
        min(minimum_candidates) if minimum_candidates else None,
        max(maximum_candidates) if maximum_candidates else None,
    )


def extract_profit_share(
    text: str,
) -> tuple[float | None, str | None]:
    """
    Hesaplama aracındaki 'Kâr Oranı (%) 0' gibi çıplak
    varsayılan değerleri kabul etmez.

    Oranın gerçek ürün şartı olduğunu gösteren cümle yapıları
    aranır: "'dır", "uygulanır", "ile sunulur", "oranıyla" vb.
    """
    normalized = normalize_text(text)

    patterns = (
        r"k[aâ]r\s+(?:pay[ıi]\s+)?oran[ıi]"
        r"(?:\s+ayl[ıi]k)?\s*"
        r"%\s*(\d{1,3}(?:[.,]\d{1,4})?)"
        r"\s*(?:['’]?(?:d[ıi]r|dir|dur|dür)|"
        r"olarak|uygulan[ıi]r|ile)",

        r"%\s*(\d{1,3}(?:[.,]\d{1,4})?)"
        r"\s*(?:oran[ıi]nda\s+)?"
        r"k[aâ]r\s+(?:pay[ıi]\s+)?"
        r"(?:oran[ıi]yla|oran[ıi]\s+ile|pay[ıi]\s+ile)",

        r"(?:ayl[ıi]k\s+)?"
        r"%\s*(\d{1,3}(?:[.,]\d{1,4})?)"
        r"\s+k[aâ]r\s+pay[ıi]\s+"
        r"(?:ile|oran[ıi]yla)",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )
        if not match:
            continue

        value = parse_tr_number(match.group(1))
        if value is None or not (0 <= value <= 100):
            continue

        return (
            value,
            f"%{str(value).replace('.', ',')}",
        )

    return None, None


def extract_vehicle_maturity_rules(
    text: str,
) -> tuple[
    str | None,
    float | None,
    int | None,
    str | None,
    float | None,
]:
    """
    Araç değerine göre vade ve finansman oranı kademelerini
    hem SSS paragrafından hem de tablo metninden çıkarır.

    Kaynaktaki araç/fatura/kasko değeri hiçbir zaman doğrudan
    "finansman tutarı" olarak yazılmaz.
    """
    normalized = normalize_text(text)

    vehicle_context = bool(
        re.search(
            r"(?:"
            r"fatura\s*(?:/|\s+veya\s+)?\s*kasko\s+değer[ıi]"
            r"|fatura\s+bedeli"
            r"|kasko\s+değer[ıi]"
            r"|araç\s+değer[ıi]"
            r"|taşıt\s+finansman"
            r")",
            normalized,
            flags=re.IGNORECASE,
        )
    )
    if not vehicle_context:
        return None, None, None, None, None

    money = r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?"
    rules: list[
        tuple[
            float | None,
            float | None,
            float | None,
            int,
        ]
    ] = []

    def add_rule(
        lower: float | None,
        upper: float | None,
        ratio: float | None,
        months: int,
    ) -> None:
        if months < 1 or months > 120:
            return

        # "0 TL – 400.000 TL" ile "400.000 TL ve altında"
        # aynı ekonomik banttır. İlk bandın alt sınırını None
        # olarak normalize ederek SSS paragrafı ve tablo
        # kaynaklarından gelen aynı kuralın iki kez görünmesini
        # engelliyoruz.
        if lower is not None and abs(lower) < 1e-9:
            lower = None

        key = (lower, upper, ratio, months)
        if key not in rules:
            rules.append(key)

    # --------------------------------------------------------
    # 1) SSS paragraf biçimi
    # --------------------------------------------------------
    # "400.000 TL ve altında ... en uzun vade 48 ay"
    for match in re.finditer(
        rf"{money}\s*(?:TL|₺)\s+ve\s+alt[ıi]nda"
        rf"[^.!?]{{0,220}}?"
        rf"(?:en\s+uzun\s+vade|maksimum\s+vade|"
        rf"azami\s+vade|en\s+fazla)"
        rf"[^.!?\d]{{0,20}}(\d{{1,3}})\s*ay",
        normalized,
        flags=re.IGNORECASE,
    ):
        upper = parse_tr_number(match.group(1))
        months = int(match.group(2))
        if upper is not None:
            add_rule(None, upper, None, months)

    # "400.001 TL – 800.000 TL ... maksimum vade 36 ay"
    for match in re.finditer(
        rf"{money}\s*(?:TL|₺)\s*[-–—]\s*"
        rf"{money}\s*(?:TL|₺)"
        rf"[^.!?]{{0,220}}?"
        rf"(?:en\s+uzun\s+vade|maksimum\s+vade|"
        rf"azami\s+vade|en\s+fazla)"
        rf"[^.!?\d]{{0,20}}(\d{{1,3}})\s*ay",
        normalized,
        flags=re.IGNORECASE,
    ):
        lower = parse_tr_number(match.group(1))
        upper = parse_tr_number(match.group(2))
        months = int(match.group(3))
        if (
            lower is not None
            and upper is not None
            and lower <= upper
        ):
            add_rule(lower, upper, None, months)

    # --------------------------------------------------------
    # 1B) Türkiye Finans metin biçimi
    # --------------------------------------------------------
    # "400.000 TL'ye kadar ... maksimum vade süresi 48 ay"
    # veya "400.000 TL'ye kadar vade 48 ayı ..."
    for match in re.finditer(
        rf"{money}\s*(?:TL|₺)"
        rf"(?:['’`]?ye|['’`]?ya)?\s+kadar"
        rf"[^.!?]{{0,180}}?"
        rf"(?:maksimum\s+vade(?:\s+süresi)?"
        rf"|azami\s+vade"
        rf"|vade)"
        rf"[^.!?\d]{{0,20}}"
        rf"(\d{{1,3}})\s*ay",
        normalized,
        flags=re.IGNORECASE,
    ):
        upper = parse_tr_number(match.group(1))
        months = int(match.group(2))

        if upper is not None:
            add_rule(None, upper, None, months)

    # "400.000 - 800.000 TL arası ... maksimum vade 36 ay"
    # veya "400.000-800.000 TL arası vade 36 ayı ..."
    for match in re.finditer(
        rf"{money}\s*(?:TL|₺)?\s*[-–—]\s*"
        rf"{money}\s*(?:TL|₺)"
        rf"\s*(?:aras[ıi]|aral[ıi]ğ[ıi]nda|arasında)?"
        rf"[^.!?]{{0,180}}?"
        rf"(?:maksimum\s+vade(?:\s+süresi)?"
        rf"|azami\s+vade"
        rf"|vade)"
        rf"[^.!?\d]{{0,20}}"
        rf"(\d{{1,3}})\s*ay",
        normalized,
        flags=re.IGNORECASE,
    ):
        lower = parse_tr_number(match.group(1))
        upper = parse_tr_number(match.group(2))
        months = int(match.group(3))

        if (
            lower is not None
            and upper is not None
            and lower <= upper
        ):
            add_rule(lower, upper, None, months)

    # Finansman oranı metin biçimi:
    # "400.000 TL’ye kadar olan kısmının %70’i"
    # "400.000-800.000 TL arasında %50’si"
    explicit_ratios: dict[
        tuple[float | None, float | None],
        float,
    ] = {}

    for match in re.finditer(
        rf"{money}\s*(?:TL|₺)"
        rf"(?:['’`]?ye|['’`]?ya)?\s+kadar"
        rf"[^.!?]{{0,100}}?"
        rf"%\s*(\d{{1,3}}(?:[.,]\d+)?)",
        normalized,
        flags=re.IGNORECASE,
    ):
        upper = parse_tr_number(match.group(1))
        ratio = parse_tr_number(match.group(2))

        if (
            upper is not None
            and ratio is not None
            and 0 <= ratio <= 100
        ):
            explicit_ratios[(None, upper)] = ratio

    for match in re.finditer(
        rf"{money}\s*(?:TL|₺)?\s*[-–—]\s*"
        rf"{money}\s*(?:TL|₺)"
        rf"\s*(?:aras[ıi]nda|aral[ıi]ğ[ıi]nda)?"
        rf"[^.!?]{{0,100}}?"
        rf"%\s*(\d{{1,3}}(?:[.,]\d+)?)",
        normalized,
        flags=re.IGNORECASE,
    ):
        lower = parse_tr_number(match.group(1))
        upper = parse_tr_number(match.group(2))
        ratio = parse_tr_number(match.group(3))

        if (
            lower is not None
            and upper is not None
            and ratio is not None
            and lower <= upper
            and 0 <= ratio <= 100
        ):
            explicit_ratios[(lower, upper)] = ratio

    # --------------------------------------------------------
    # 2) FAQ tablo biçimi:
    # 0 TL – 400.000 TL 70% 48
    # 400.001 TL – 800.000 TL 50% 36
    # --------------------------------------------------------
    table_pattern = re.compile(
        rf"{money}\s*(?:TL|₺)\s*[-–—]\s*"
        rf"{money}\s*(?:TL|₺)"
        rf"\s*(\d{{1,3}}(?:[.,]\d+)?)\s*%"
        rf"\s*(\d{{1,3}})(?!\s*(?:TL|₺|%))",
        flags=re.IGNORECASE,
    )

    for match in table_pattern.finditer(normalized):
        lower = parse_tr_number(match.group(1))
        upper = parse_tr_number(match.group(2))
        ratio = parse_tr_number(match.group(3))
        months = int(match.group(4))

        if (
            lower is not None
            and upper is not None
            and ratio is not None
            and lower <= upper
            and 0 <= ratio <= 100
        ):
            add_rule(lower, upper, ratio, months)

    # "2.000.000 ve üzeri 0% 0" vade 0 olduğu için aktif
    # finansman kademesi değildir; üst eşik belirlemek için
    # ayrıca kullanılmaz. Son pozitif bandın üst sınırı kullanılır.

    if not rules:
        return None, None, None, None, None

    positive_rules = [
        item
        for item in rules
        if item[3] > 0
    ]

    upper_values = [
        item[1]
        for item in positive_rules
        if item[1] is not None
    ]
    reference_upper = (
        max(upper_values)
        if upper_values
        else None
    )

    max_maturity = max(
        item[3]
        for item in positive_rules
    )

    ratios = [
        item[2]
        for item in positive_rules
        if item[2] is not None
    ]
    max_ratio = max(ratios) if ratios else None

    # Birleştirilmiş vade kademeleri
    maturity_by_band: dict[
        tuple[float | None, float | None],
        int,
    ] = {}
    ratio_by_band: dict[
        tuple[float | None, float | None],
        float,
    ] = {}

    for lower, upper, ratio, months in positive_rules:
        band = (lower, upper)
        maturity_by_band[band] = max(
            months,
            maturity_by_band.get(band, 0),
        )
        effective_ratio = (
            ratio
            if ratio is not None
            else explicit_ratios.get(band)
        )

        if effective_ratio is not None:
            ratio_by_band[band] = effective_ratio

    def fmt_money(value: float) -> str:
        return f"{int(value):,}".replace(",", ".")

    ordered_bands = sorted(
        maturity_by_band,
        key=lambda band: (
            -1 if band[0] is None else band[0],
            float("inf") if band[1] is None else band[1],
        ),
    )

    maturity_parts: list[str] = []
    ratio_parts: list[str] = []

    for lower, upper in ordered_bands:
        if lower is None and upper is not None:
            band_text = f"≤ {fmt_money(upper)} TL"
        elif lower is not None and upper is not None:
            band_text = (
                f"{fmt_money(lower)}–"
                f"{fmt_money(upper)} TL"
            )
        else:
            continue

        maturity_parts.append(
            f"{band_text} → "
            f"{maturity_by_band[(lower, upper)]} ay"
        )

        ratio = ratio_by_band.get((lower, upper))
        if ratio is not None:
            ratio_text = (
                str(int(ratio))
                if float(ratio).is_integer()
                else str(ratio).replace(".", ",")
            )
            ratio_parts.append(
                f"{band_text} → %{ratio_text}"
            )

    return (
        " | ".join(maturity_parts)
        if maturity_parts
        else None,
        reference_upper,
        max_maturity,
        " | ".join(ratio_parts)
        if ratio_parts
        else None,
        max_ratio,
    )


def _search_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", normalize_text(value))
    without_marks = "".join(
        char for char in decomposed
        if not unicodedata.combining(char)
    )
    return without_marks.casefold().replace("ı", "i")


def _format_rate(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value).replace(".", ",")


def _short_housing_band(label: str) -> str:
    normalized = normalize_text(label)
    values = [
        parse_tr_number(raw)
        for raw in re.findall(r"\d{1,3}(?:\.\d{3})+|\d+", normalized)
    ]
    values = [v for v in values if v is not None]

    def million_number(value: float) -> str:
        n = value / 1_000_000
        if float(n).is_integer():
            return str(int(n))
        return str(round(n, 2)).replace(".", ",")

    if not values:
        return normalized

    key = _search_key(normalized)

    if len(values) == 1:
        value = values[0]
        label_m = million_number(value) + "M"
        if (
            "<" in normalized
            and "deger" in key
            and normalized.find("<") < key.find("deger")
        ):
            return f">{label_m}"
        if "<=" in normalized or "=<" in normalized:
            return f"≤{label_m}"
        return label_m

    low, high = min(values), max(values)
    return f"{million_number(low)}–{million_number(high)}M"


def _housing_band_bounds(label: str) -> tuple[float | None, float | None]:
    """Konut/ekspertiz değer bandını canonical (alt, üst) sınırlara çevirir.

    Alt sınır Streamlit değerlendirmesinde dışlayıcı (>), üst sınır dahil (<=)
    kabul edilir. Kaynakta 5.000.001 gibi başlayan aralıklar 5.000.000 dışlayıcı
    alt sınıra normalize edilir.
    """
    normalized = normalize_text(label)
    key = _search_key(normalized)

    values: list[float] = []

    # "5-7 milyon", "20 milyon üzeri" gibi yazımlar.
    million_matches = re.findall(
        r"(\d+(?:[.,]\d+)?)\s*milyon",
        key,
        flags=re.IGNORECASE,
    )
    if million_matches:
        for raw in million_matches:
            value = parse_tr_number(raw)
            if value is not None:
                values.append(float(value) * 1_000_000.0)
    else:
        for raw in re.findall(
            r"\d{1,3}(?:\.\d{3})+|\d{4,}",
            normalized,
        ):
            value = parse_tr_number(raw)
            if value is not None:
                values.append(float(value))

    # Aynı sayı farklı biçimlerde iki kez yakalanmışsa temizle.
    unique_values: list[float] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    values = unique_values

    if not values:
        return None, None

    # TF gibi "5.000.001 – 7.000.000" aralığı, önceki bandın
    # 5.000.000 TL'de bittiğini ifade eder. Canonical modelde alt sınır
    # dışlayıcı olduğu için 1 TL'yi geri alıyoruz.
    if len(values) >= 2:
        low, high = min(values), max(values)
        rounded_million = round(low / 1_000_000.0) * 1_000_000.0
        if abs(low - rounded_million - 1.0) < 0.01:
            low = rounded_million
        return low, high

    value = values[0]
    is_lower = bool(
        re.search(r"\b(?:uzeri|üzeri|ustunde|üstünde)\b", key)
        or re.search(r"deger\s*>\s*", key)
        or re.search(r"\b\d[^\n]{0,25}<\s*deger\b", key)
    )
    if is_lower:
        return value, None
    return None, value


def extract_housing_finance_rules(
    html: str,
    product_name: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Ekspertiz/enerji sınıfı tablolarını tek canonical şemaya çıkarır.

    Canonical JSON:
      {
        "standard_home": [{"min_value": ..., "max_value": ..., "ab": ...}],
        "additional_home": [...]
      }

    Böylece Dünya/Türkiye Finans/Kuveyt tabloları ile Albaraka override'ı
    aynı veri modelini kullanır.
    """
    soup = BeautifulSoup(html, "html.parser")
    canonical: dict[str, list[dict[str, Any]]] = {
        "standard_home": [],
        "additional_home": [],
    }
    product_key = _search_key(product_name or "")

    for table in soup.find_all("table"):
        # Header'ı yalnız ilk dört hücreyle sınırlama; bazı bankalarda iki
        # satırlı thead kullanılıyor.
        first_rows = table.find_all("tr")[:3]
        header_key = _search_key(
            " ".join(
                cell.get_text(" ", strip=True)
                for row in first_rows
                for cell in row.find_all(["th", "td"])
            )
        )

        has_value_header = any(
            token in header_key
            for token in (
                "konut degeri",
                "konut ekspertiz degeri",
                "ekspertiz degeri",
            )
        )
        has_energy_header = (
            "enerji" in header_key
            or all(token in header_key for token in ("a-b", "c"))
            or all(token in header_key for token in ("a - b", "c"))
        )
        if not (has_value_header and has_energy_header):
            continue

        heading = table.find_previous(
            ["h1", "h2", "h3", "h4", "h5", "h6"]
        )
        heading_key = _search_key(
            heading.get_text(" ", strip=True) if heading else ""
        )

        purchase_key: str | None = None
        if any(
            token in heading_key
            for token in (
                "ilk ev",
                "ilk konut",
                "standart konut",
            )
        ):
            purchase_key = "standard_home"
        elif any(
            token in heading_key
            for token in (
                "ikinci",
                "sonraki",
                "mevcut konut",
            )
        ):
            purchase_key = "additional_home"
        elif "ilk evim" in product_key:
            purchase_key = "standard_home"

        parsed_rows: list[dict[str, Any]] = []
        for row in table.find_all("tr"):
            cells = [
                normalize_text(cell.get_text(" ", strip=True))
                for cell in row.find_all(["th", "td"])
            ]
            if len(cells) < 4:
                continue

            rates: list[float] = []
            for raw in cells[1:4]:
                # Bankalar oranları hem "%90" hem "90%" biçiminde
                # yayımlayabiliyor. İki gösterimi de aynı canonical değere çek.
                match = re.search(
                    r"(?:%\s*(\d{1,3}(?:[.,]\d+)?)|"
                    r"(\d{1,3}(?:[.,]\d+)?)\s*%)",
                    raw,
                    flags=re.IGNORECASE,
                )
                if not match:
                    rates = []
                    break
                rate = parse_tr_number(
                    match.group(1) or match.group(2)
                )
                if rate is None:
                    rates = []
                    break
                rates.append(float(rate))

            if len(rates) != 3:
                continue

            lower, upper = _housing_band_bounds(cells[0])
            if lower is None and upper is None:
                continue

            parsed_rows.append(
                {
                    "min_value": lower,
                    "max_value": upper,
                    "ab": rates[0],
                    "c": rates[1],
                    "other": rates[2],
                    "source_band": cells[0],
                }
            )

        if not parsed_rows:
            continue

        # Kuveyt Türk'ün standart "Konut Finansmanı" tablosunda başlık
        # ek konut demiyor; oranların üst sınırı %22,5 olduğundan kaynak
        # açıkça ikinci/mevcut konut marjı setine karşılık geliyor.
        # Yüksek oranlı, başlıksız bir tabloyu ise (örn. Yeşil Konut)
        # tahmin ederek standard_home'a yazmıyoruz.
        if purchase_key is None:
            all_rates = [
                float(row[key])
                for row in parsed_rows
                for key in ("ab", "c", "other")
            ]
            if all_rates and max(all_rates) <= 25.0:
                purchase_key = "additional_home"

        if purchase_key is None:
            continue

        existing = canonical[purchase_key]
        seen = {
            (
                row.get("min_value"),
                row.get("max_value"),
                row.get("ab"),
                row.get("c"),
                row.get("other"),
            )
            for row in existing
        }
        for row in parsed_rows:
            dedupe = (
                row.get("min_value"),
                row.get("max_value"),
                row.get("ab"),
                row.get("c"),
                row.get("other"),
            )
            if dedupe not in seen:
                existing.append(row)
                seen.add(dedupe)

    if not canonical["standard_home"] and not canonical["additional_home"]:
        return None, None, None

    def compact(kind: str) -> str | None:
        rows = canonical[kind]
        if not rows:
            return None
        parts: list[str] = []
        for row in rows:
            band = _short_housing_band(str(row.get("source_band") or ""))
            parts.append(
                f"{band} "
                f"{_format_rate(float(row['ab']))}/"
                f"{_format_rate(float(row['c']))}/"
                f"{_format_rate(float(row['other']))}"
            )
        return " · ".join(parts)

    # source_band UI için zorunlu değil; JSON'u daha yalın/stabil tut.
    output: dict[str, list[dict[str, Any]]] = {
        "standard_home": [],
        "additional_home": [],
    }
    for kind in output:
        for row in canonical[kind]:
            clean_row = {
                key: row.get(key)
                for key in ("min_value", "max_value", "ab", "c", "other")
                if row.get(key) is not None
            }
            output[kind].append(clean_row)

    return (
        compact("standard_home"),
        compact("additional_home"),
        json.dumps(output, ensure_ascii=False, sort_keys=True),
    )


def extract_fixed_asset_financing_ratio(
    text: str,
    product_name: str | None = None,
) -> float | None:
    """Kaynakta doğrudan varlık/ekspertiz değerinin yüzdesi olarak verilen oranı çıkarır.

    Özellikle:
      - 2B: "Arazi değerinin %100'üne kadar finansman"
      - Gurbetten Sılaya: "Ekspertiz değerinin %50'si tutarında finansman"
    """
    product_key = _search_key(product_name or "")
    if not any(
        token in product_key
        for token in ("2b", "gurbetten", "konut", "gayrimenkul", "arsa", "is yeri")
    ):
        return None

    normalized = normalize_text(text)
    patterns = (
        r"(?:arazi|ekspertiz|gayrimenkul|konut)\s+değerinin\s*%\s*"
        r"(\d{1,3}(?:[.,]\d+)?)"
        r"[^.!?]{0,100}?finansman",
        r"(?:arazi|ekspertiz|gayrimenkul|konut)\s+degerinin\s*%\s*"
        r"(\d{1,3}(?:[.,]\d+)?)"
        r"[^.!?]{0,100}?finansman",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        value = parse_tr_number(match.group(1))
        if value is not None and 0 <= float(value) <= 100:
            return float(value)
    return None

def _short_vehicle_band(lower: float | None, upper: float | None) -> str:
    def compact(value: float) -> str:
        if value >= 1_000_000:
            number = value / 1_000_000
            if abs(number - round(number)) < 0.01:
                return f"{int(round(number))} mn"
            return str(round(number, 1)).replace(".", ",") + " mn"
        if value >= 1_000:
            number = value / 1_000
            if abs(number - round(number)) < 0.01:
                return f"{int(round(number))} bin"
            return str(round(number, 1)).replace(".", ",") + " bin"
        return str(int(value))
    if lower is None and upper is not None: return f"≤{compact(upper)}"
    if lower is not None and upper is not None: return f"{compact(lower)}–{compact(upper)}"
    if lower is not None: return f">{compact(lower)}"
    return "Belirtilmedi"


def extract_vehicle_finance_table_rules(html: str) -> str | None:
    soup=BeautifulSoup(html,'html.parser')
    for table in soup.find_all('table'):
        rows=table.find_all('tr')
        if not rows: continue
        header_cells=[normalize_text(c.get_text(' ',strip=True)) for c in rows[0].find_all(['th','td'])]
        header_key=_search_key(' '.join(header_cells))
        if not ((('kasko' in header_key) or ('satis degeri' in header_key) or ('arac degeri' in header_key)) and 'finansman' in header_key and 'vade' in header_key):
            continue
        parts=[]
        for row in rows[1:]:
            cells=[normalize_text(c.get_text(' ',strip=True)) for c in row.find_all(['th','td'])]
            if len(cells)<3: continue
            band_raw, ratio_raw, maturity_raw = cells[0], cells[1], cells[2]
            amounts=[parse_tr_number(x) for x in re.findall(r"\d{1,3}(?:\.\d{3})+|\d+",band_raw)]
            amounts=[x for x in amounts if x is not None]
            lower=upper=None; band_key=_search_key(band_raw)
            if len(amounts)>=2:
                lower=min(amounts); upper=max(amounts)
                if lower==0: lower=None
            elif len(amounts)==1:
                value=amounts[0]
                if 'uzeri' in band_key or 'ustu' in band_key or '>' in band_raw: lower=value
                else: upper=value
            ratio_match=re.search(r"%\s*(\d{1,3}(?:[.,]\d+)?)|(\d{1,3}(?:[.,]\d+)?)\s*%",ratio_raw,flags=re.I)
            ratio=parse_tr_number((ratio_match.group(1) or ratio_match.group(2))) if ratio_match else None
            mk=_search_key(maturity_raw)
            no_disbursement=('kullandirim yapilmayacak' in mk or 'kullandirim yapilmayacaktir' in mk)
            if ratio is not None and ratio==0 and not re.search(r"\b[1-9]\d*\b",maturity_raw): no_disbursement=True
            band=_short_vehicle_band(lower,upper)
            if no_disbursement:
                parts.append(f"{band}: Kullandırım yok"); continue
            mm=re.search(r"\b(\d{1,3})\b",maturity_raw); months=int(mm.group(1)) if mm else None
            if ratio is None or months is None or months<=0: continue
            ratio_text=str(int(ratio)) if float(ratio).is_integer() else str(ratio).replace('.',',')
            parts.append(f"{band}: %{ratio_text} / {months} ay")
        if parts: return ' · '.join(parts)
    return None


def extract_vehicle_age_rules(text: str) -> str | None:
    normalized=normalize_text(text); parts=[]; seen=set()
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", normalized):
        age_match=re.search(r"\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*yaş",sentence,flags=re.I)
        if not age_match: continue
        mm=next((m for m in re.finditer(r"\b(\d{1,3})\s*ay(?:d[ıi]r|dir|dur|dür)?\b",sentence,flags=re.I) if m.start()>age_match.end()),None)
        if mm is None: continue
        low,high,months=int(age_match.group(1)),int(age_match.group(2)),int(mm.group(1))
        if not (0<=low<=high<=50 and 1<=months<=120): continue
        key=(low,high,months)
        if key in seen: continue
        seen.add(key); parts.append(f"{low}–{high} yaş → {months} ay")
    return ' · '.join(parts) if parts else None


def combine_vehicle_rule_text(maturity_rules_text: str | None, financing_ratio_rules_text: str | None) -> str | None:
    if not maturity_rules_text: return None
    ratios={}
    if financing_ratio_rules_text:
        for part in financing_ratio_rules_text.split('|'):
            part=part.strip()
            if '→' in part:
                band,value=part.split('→',1); ratios[band.strip()]=value.strip()
    output=[]
    for part in maturity_rules_text.split('|'):
        part=part.strip()
        if '→' not in part: continue
        band,months=part.split('→',1); band=band.strip(); months=months.strip(); ratio=ratios.get(band)
        output.append(f"{band}: {ratio} / {months}" if ratio else f"{band}: {months}")
    return ' · '.join(output) if output else None


def _compact_tl(value: float) -> str:
    if value >= 1_000_000:
        number = value / 1_000_000
        if float(number).is_integer():
            return f"{int(number)} mn TL"
        return str(round(number, 1)).replace(".", ",") + " mn TL"
    if value >= 1_000:
        number = value / 1_000
        if float(number).is_integer():
            return f"{int(number)} bin TL"
        return str(round(number, 1)).replace(".", ",") + " bin TL"
    return f"{int(value)} TL"


def extract_shopping_finance_rules(
    text: str,
) -> tuple[
    float | None,
    int | None,
    str | None,
    str | None,
    int | None,
    int | None,
]:
    """
    Alışveriş finansmanındaki genel ve kategori bazlı koşulları
    ayrı alanlara çıkarır.

    Birim dönüşümü yapılmaz:
      - Kaynak "36 aya varan" diyorsa ay olarak kalır.
      - Kaynak "12 taksit" diyorsa taksit olarak kalır.
    """
    normalized = normalize_text(text)
    key = _search_key(normalized)

    if (
        "alisveris finansman" not in key
        and "alisverisleriniz" not in key
    ):
        return None, None, None, None, None, None

    money = r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?"

    general_limit = None
    general_months = None
    phone_rule = None
    tablet_months = None
    computer_months = None

    general_match = re.search(
        rf"{money}\s*(?:TL|₺)"
        rf"(?:['’`]?ye|['’`]?ya)?\s+kadar"
        rf"[^.!?]{{0,180}}?"
        rf"(\d{{1,3}})\s*aya?\s+varan\s+(?:taksit|vade)",
        normalized,
        flags=re.IGNORECASE,
    )

    if general_match:
        amount = parse_tr_number(general_match.group(1))
        months = int(general_match.group(2))
        if (
            amount is not None
            and amount > 0
            and 1 <= months <= 120
        ):
            general_limit = amount
            general_months = months

    phone_sentence = next(
        (
            sentence
            for sentence in re.split(
                r"(?<=[.!?])\s+|\n+",
                normalized,
            )
            if "cep telefonu" in _search_key(sentence)
        ),
        None,
    )

    if phone_sentence:
        phone_match = re.search(
            rf"{money}\s*(?:TL|₺)"
            rf"(?:['’`]?ye|['’`]?ya)?\s+kadar"
            rf"[^.!?]{{0,90}}?"
            rf"(?:en\s+fazla\s+)?(\d{{1,3}})\s*taksit"
            rf"[^.!?]{{0,160}}?"
            rf"{money}\s*(?:TL|₺)"
            rf"(?:['’`]?(?:nin|nın|nun|nün))?"
            rf"\s+(?:üzerinde|uzerinde)"
            rf"[^.!?]{{0,90}}?"
            rf"(?:en\s+fazla\s+)?(\d{{1,3}})\s*taksit",
            phone_sentence,
            flags=re.IGNORECASE,
        )

        if phone_match:
            threshold_1 = parse_tr_number(
                phone_match.group(1)
            )
            low_count = int(phone_match.group(2))
            threshold_2 = parse_tr_number(
                phone_match.group(3)
            )
            high_count = int(phone_match.group(4))
            threshold = threshold_1 or threshold_2

            if (
                threshold is not None
                and 1 <= low_count <= 120
                and 1 <= high_count <= 120
            ):
                compact = _compact_tl(threshold)
                phone_rule = (
                    f"≤{compact}: {low_count} taksit · "
                    f">{compact}: {high_count} taksit"
                )

    for token, target in (
        ("tablet", "tablet"),
        ("bilgisayar", "computer"),
    ):
        sentence = next(
            (
                sentence
                for sentence in re.split(
                    r"(?<=[.!?])\s+|\n+",
                    normalized,
                )
                if token in _search_key(sentence)
            ),
            None,
        )

        if not sentence:
            continue

        # Kaynak bu örneklerde "ay vadelendirilmektedir" diyor.
        # Önce ay aranır; taksit ifadesini aya çevirmeyiz.
        month_match = re.search(
            r"(?:en\s+fazla\s+)?"
            r"(\d{1,3})\s*ay"
            r"(?:\s+vade(?:lendiril\w*)?)?",
            sentence,
            flags=re.IGNORECASE,
        )

        if not month_match:
            continue

        value = int(month_match.group(1))
        if not 1 <= value <= 120:
            continue

        if target == "tablet":
            tablet_months = value
        else:
            computer_months = value

    summary_parts: list[str] = []

    if (
        general_limit is not None
        and general_months is not None
    ):
        summary_parts.append(
            f"Genel: ≤{_compact_tl(general_limit)} / "
            f"{general_months} ay"
        )

    if phone_rule:
        summary_parts.append(
            f"Cep telefonu: {phone_rule}"
        )

    if tablet_months is not None:
        summary_parts.append(
            f"Tablet: {tablet_months} ay"
        )

    if computer_months is not None:
        summary_parts.append(
            f"Bilgisayar: {computer_months} ay"
        )

    return (
        general_limit,
        general_months,
        (
            " · ".join(summary_parts)
            if summary_parts
            else None
        ),
        phone_rule,
        tablet_months,
        computer_months,
    )


def extract_fee_waivers(
    text: str,
) -> tuple[str | None, bool, bool, bool]:
    """
    Açık ücret muafiyetlerini çıkarır.
    "Masrafsız" gibi genel ifadelerden tek tek ücret uydurmaz.
    """
    key = _search_key(normalize_text(text))

    negative = (
        r"(?:yansitilmayacaktir|yansitilmaz|"
        r"alinmayacaktir|alinmaz|"
        r"tahsil edilmeyecektir|tahsil edilmez|"
        r"ucretsizdir|ucretsiz|ucret yoktur|ucret yok)"
    )

    insurance = False
    allocation = False
    commission = False

    if re.search(
        rf"sigorta[^.!?]{{0,50}}tahsis\s+ucreti"
        rf"[^.!?]{{0,80}}{negative}",
        key,
        flags=re.IGNORECASE,
    ):
        insurance = True
        allocation = True

    if re.search(
        rf"sigorta(?:\s+ucreti)?[^.!?]{{0,80}}{negative}",
        key,
        flags=re.IGNORECASE,
    ) or re.search(
        rf"{negative}[^.!?]{{0,80}}sigorta(?:\s+ucreti)?",
        key,
        flags=re.IGNORECASE,
    ):
        insurance = True

    if re.search(
        rf"tahsis(?:\s+ucreti)?[^.!?]{{0,80}}{negative}",
        key,
        flags=re.IGNORECASE,
    ) or re.search(
        rf"{negative}[^.!?]{{0,80}}tahsis(?:\s+ucreti)?",
        key,
        flags=re.IGNORECASE,
    ):
        allocation = True

    if re.search(
        rf"komisyon(?:\s+ucreti)?[^.!?]{{0,80}}{negative}",
        key,
        flags=re.IGNORECASE,
    ) or re.search(
        rf"{negative}[^.!?]{{0,80}}komisyon(?:\s+ucreti)?",
        key,
        flags=re.IGNORECASE,
    ):
        commission = True

    parts: list[str] = []
    if insurance:
        parts.append("Sigorta ücreti yok")
    if allocation:
        parts.append("Tahsis ücreti yok")
    if commission:
        parts.append("Komisyon yok")

    return (
        " · ".join(parts) if parts else None,
        insurance,
        allocation,
        commission,
    )


def has_tf_finansman_destegi_subsection_maturity(
    product_name: str,
    text: str,
) -> bool:
    """
    Türkiye Finans 'Finansman Desteği' sayfasındaki
    '18 aya varan taksit' ifadesi ana ürünün genel vadesi
    değildir; sayfadaki Döviz Kredileri alt bölümüne aittir.

    Bu nedenle 18 ay değeri ürün seviyesindeki
    maximum_maturity_months alanına taşınmaz.
    """
    name_key = normalize_text(
        product_name
    ).casefold().replace("i̇", "i")

    if name_key != "finansman desteği":
        return False

    normalized = normalize_text(text)

    has_fx_section = bool(
        re.search(
            r"döviz\s+kredileri"
            r"[^.!?]{0,500}?"
            r"18\s+aya?\s+varan\s+taksit",
            normalized,
            flags=re.IGNORECASE,
        )
    )

    has_general_18_limit = bool(
        re.search(
            r"(?:finansman desteğinin|finansman desteği)"
            r"[^.!?]{0,120}?"
            r"(?:maksimum|azami|en fazla)"
            r"[^.!?]{0,40}?"
            r"18\s*ay",
            normalized,
            flags=re.IGNORECASE,
        )
    )

    return (
        has_fx_section
        and not has_general_18_limit
    )


def has_variant_specific_maturity_without_global_limit(
    product_name: str,
    text: str,
) -> bool:
    """
    Bir ürün sayfasında farklı alt finansman yapıları için
    ayrı ayrı vade sınırları yayımlanmışsa, bunlardan en büyüğü
    ürünün genel azami vadesi gibi gösterilmemelidir.

    Şimdilik güçlü ve açık kaynak yapısı bulunan
    Savunma Sanayii Başkanlığı Finansman Destek Paketi
    için uygulanır:
      - Leasing: 60 aya kadar
      - İşletme Finansmanı: maksimum 12 ay
    """
    name_key = normalize_text(
        product_name
    ).casefold().replace("i̇", "i")

    if (
        "savunma sanayii başkanlığı" not in name_key
        or "finansman destek paketi" not in name_key
    ):
        return False

    normalized = normalize_text(text)

    leasing_limit = bool(
        re.search(
            r"leasing\s+finansman"
            r"[^.!?]{0,260}?"
            r"(?:toplamda\s+)?60\s*aya?\s+kadar",
            normalized,
            flags=re.IGNORECASE,
        )
    )

    business_limit = bool(
        re.search(
            r"işletme\s+finansman"
            r"[^.!?]{0,260}?"
            r"maksimum\s+12\s*ay",
            normalized,
            flags=re.IGNORECASE,
        )
    )

    return leasing_limit and business_limit


def extract_standard_product(
    html: str,
) -> StandardProductExtraction:
    product_name, clean_text = clean_page_text(html)

    min_amount, max_amount = extract_amounts(clean_text)
    min_maturity, max_maturity = extract_maturity(clean_text)

    # Açık bir "genel azami vade" cümlesi varsa, tutara
    # bağlı vade bantlarının içindeki daha büyük rakamların
    # ürün özetindeki max_vade alanını ezmesine izin verme.
    #
    # Örnek:
    #   Genel max vade: 18 ay
    #   Tutar bantları: 36 / 24 / 12 ay
    #
    # Tutar bantları finance_rules_json içinde ayrı kalır.
    explicit_global_maturity = None
    normalized_clean_text = normalize_text(clean_text)

    for pattern in (
        r"finansman(?:ın|in)?\s+maksimum\s+vadesi"
        r"\s*(\d{1,3})\s*ay",
        r"finansman(?:ın|in)?\s+azami\s+vadesi"
        r"\s*(\d{1,3})\s*ay",
    ):
        match = re.search(
            pattern,
            normalized_clean_text,
            flags=re.IGNORECASE,
        )
        if match:
            value = int(match.group(1))
            if 1 <= value <= 120:
                explicit_global_maturity = value
                break

    if explicit_global_maturity is not None:
        max_maturity = explicit_global_maturity

    # Birden fazla alt finansman yapısının farklı vade
    # limitlerini tek bir "genel max vade" alanına sıkıştırma.
    if (
        has_variant_specific_maturity_without_global_limit(
            product_name,
            clean_text,
        )
        or has_tf_finansman_destegi_subsection_maturity(
            product_name,
            clean_text,
        )
    ):
        min_maturity = None
        max_maturity = None

    rate, rate_text = extract_profit_share(clean_text)

    # Sabit bir oran kaynakta açıkça verilmemiş fakat sayfada
    # finansman hesaplama aracı / aylık kâr oranı alanı varsa,
    # "Belirtilmedi" yerine oranı dinamik olarak işaretle.
    #
    # Bu özellikle kullanıcı girdisine göre hesaplanan
    # araç/konut finansmanı hesaplama araçlarında önemlidir.
    # Buradan ASLA %0 veya başka bir "standart" oran uydurulmaz.
    if rate is None and not rate_text:
        raw_page_text = normalize_text(
            BeautifulSoup(
                html,
                "html.parser",
            ).get_text(" ", strip=True)
        )

        has_finance_calculator = bool(
            re.search(
                r"(?:finansman\s+hesaplama"
                r"|finansal\s+hesaplama"
                r"|ödeme\s+plan[ıi])",
                raw_page_text,
                flags=re.IGNORECASE,
            )
        )
        has_profit_rate_control = bool(
            re.search(
                r"(?:k[aâ]r\s+oran[ıi]\s+belirle"
                r"|k[aâ]r\s+oran[ıi]n[ıi]\s+kendim"
                r"|ayl[ıi]k\s+k[aâ]r\s+oran[ıi])",
                raw_page_text,
                flags=re.IGNORECASE,
            )
        )

        if has_finance_calculator and has_profit_rate_control:
            rate_text = "Hesaplama aracında dinamik"

    (
        maturity_rules_text,
        maturity_reference_upper_amount,
        rules_max_maturity,
        financing_ratio_rules_text,
        maximum_financing_ratio,
    ) = extract_vehicle_maturity_rules(clean_text)

    if rules_max_maturity is not None:
        max_maturity = (
            rules_max_maturity
            if max_maturity is None
            else max(max_maturity, rules_max_maturity)
        )

    (
        housing_first_home_rules_text,
        housing_additional_home_rules_text,
        housing_finance_rules_json,
    ) = extract_housing_finance_rules(html, product_name)

    fixed_asset_ratio = extract_fixed_asset_financing_ratio(
        clean_text,
        product_name,
    )
    if maximum_financing_ratio is None and fixed_asset_ratio is not None:
        maximum_financing_ratio = fixed_asset_ratio

    vehicle_finance_rules_text = (
        extract_vehicle_finance_table_rules(html)
    )

    combined_vehicle_rules_text = combine_vehicle_rule_text(
        maturity_rules_text,
        financing_ratio_rules_text,
    )

    def _rule_count(value: str | None) -> int:
        if not value:
            return 0
        return value.count("·") + value.count("|") + 1

    if (
        combined_vehicle_rules_text is not None
        and _rule_count(combined_vehicle_rules_text)
        > _rule_count(vehicle_finance_rules_text)
    ):
        vehicle_finance_rules_text = (
            combined_vehicle_rules_text
        )
    product_name_key = normalize_text(
        product_name
    ).casefold()

    is_vehicle_product = any(
        token in product_name_key
        for token in (
            "taşıt",
            "tasit",
            "araç",
            "arac",
            "motosiklet",
            "ticari plaka",
            "ticari hat",
        )
    )

    if not is_vehicle_product:
        # İhtiyaç finansmanının 125/250 bin TL tutar-vade
        # bantları "araç finansman kuralı" değildir.
        vehicle_finance_rules_text = None
        vehicle_age_rules_text = None
    else:
        vehicle_age_rules_text = (
            extract_vehicle_age_rules(clean_text)
        )

    (
        shopping_general_limit_amount,
        shopping_general_max_maturity_months,
        shopping_finance_rules_text,
        shopping_phone_rule_text,
        shopping_tablet_max_maturity_months,
        shopping_computer_max_maturity_months,
    ) = extract_shopping_finance_rules(clean_text)

    (
        fee_waiver_text,
        insurance_fee_waived,
        allocation_fee_waived,
        commission_fee_waived,
    ) = extract_fee_waivers(clean_text)

    finance_rules_json = dumps_finance_rules(
        html=html,
        clean_text=clean_text,
        insurance_fee_waived=insurance_fee_waived,
        allocation_fee_waived=allocation_fee_waived,
        commission_fee_waived=commission_fee_waived,
    )

    # Türkiye Finans / eXtra Limit kaynak koruması.
    #
    # Kaynakta “maksimum finansman limiti 120 bin TL” açıkça
    # yayımlanıyor. “Minimum taksitlendirme tutarı 100 TL” ise
    # minimum finansman tutarı DEĞİLDİR; bu nedenle min_amount
    # alanına yazılmaz, ürün koşulu olarak saklanır.
    if (
        normalize_text(product_name).casefold() == "extra limit"
        and "Türkiye Finans" in clean_text
    ):
        if re.search(
            r"maksimum\s+finansman\s+limiti\s+120\s*bin\s*TL",
            clean_text,
            flags=re.IGNORECASE,
        ):
            max_amount = 120_000.0

        try:
            extra_rules = json.loads(finance_rules_json or "{}")
        except Exception:
            extra_rules = {}

        for key in (
            "category_rules",
            "amount_maturity_rules",
            "pricing_tiers",
            "fee_rules",
            "offer_rules",
        ):
            extra_rules.setdefault(key, [])

        minimum_installment = bool(
            re.search(
                r"Minimum\s+taksitlendirme\s+tutar[ıi]\s+100\s*TL",
                clean_text,
                flags=re.IGNORECASE,
            )
        )
        below_minimum_cash = bool(
            re.search(
                r"(?:100\s*TL|Minimum\s+taksitlendirme\s+tutar[ıi])"
                r"[^.!?]{0,120}(?:alt[ıi]nda|altındaki)"
                r"[^.!?]{0,180}peşin",
                clean_text,
                flags=re.IGNORECASE,
            )
        )
        reusable_limit = bool(
            re.search(
                r"taksitlerinizi\s+ödedikçe[^.!?]{0,140}"
                r"limit\s+yeniden\s+kullan[ıi]ma\s+aç[ıi]l[ıi]r",
                clean_text,
                flags=re.IGNORECASE,
            )
        )

        if minimum_installment:
            condition_parts = ["Minimum taksitlendirme tutarı 100 TL"]
            if below_minimum_cash:
                condition_parts.append("100 TL altı harcamalar peşin yansıtılır")
            if reusable_limit:
                condition_parts.append("Ödedikçe limit yeniden kullanıma açılır")

            condition_text = " · ".join(condition_parts)
            source_match = re.search(
                r"Minimum\s+taksitlendirme\s+tutar[ıi]\s+100\s*TL"
                r"[^.!?]{0,420}",
                clean_text,
                flags=re.IGNORECASE,
            )
            source_text = (
                source_match.group(0).strip()
                if source_match
                else condition_text
            )

            # Aynı koşulu tekrar tekrar eklemeyelim.
            extra_rules["offer_rules"] = [
                rule
                for rule in extra_rules["offer_rules"]
                if "Minimum taksitlendirme tutarı"
                not in str(rule.get("condition_text") or "")
            ]
            extra_rules["offer_rules"].append(
                {
                    "rule_type": "product_offer",
                    "rule_label": "Ürüne Özel Finansman Koşulu",
                    "min_amount": None,
                    "max_amount": None,
                    "min_inclusive": False,
                    "max_inclusive": True,
                    "max_installments": None,
                    "max_maturity_months": None,
                    "interest_free": False,
                    "condition_text": condition_text,
                    "source_text": source_text,
                }
            )

        finance_rules_json = json.dumps(
            extra_rules,
            ensure_ascii=False,
            sort_keys=True,
        )

    if shopping_general_max_maturity_months is not None:
        max_maturity = (
            shopping_general_max_maturity_months
            if max_maturity is None
            else max(max_maturity, shopping_general_max_maturity_months)
        )

    interest_free = bool(
        re.search(
            r"\bvade\s+farks[ıi]z\b",
            clean_text,
            flags=re.IGNORECASE,
        )
    )

    return StandardProductExtraction(
        product_name=product_name,
        clean_text=clean_text,
        minimum_financing_amount=min_amount,
        maximum_financing_amount=max_amount,
        minimum_maturity_months=min_maturity,
        maximum_maturity_months=max_maturity,
        profit_share_rate=rate,
        profit_share_rate_text=rate_text,
        interest_free=interest_free,
        interest_free_text=(
            "Vade farksız"
            if interest_free
            else None
        ),
        maturity_rules_text=maturity_rules_text,
        maturity_reference_upper_amount=(
            maturity_reference_upper_amount
        ),
        financing_ratio_rules_text=(
            financing_ratio_rules_text
        ),
        maximum_financing_ratio=(
            maximum_financing_ratio
        ),
        housing_first_home_rules_text=housing_first_home_rules_text,
        housing_additional_home_rules_text=housing_additional_home_rules_text,
        housing_finance_rules_json=housing_finance_rules_json,
        vehicle_finance_rules_text=vehicle_finance_rules_text,
        vehicle_age_rules_text=vehicle_age_rules_text,
        shopping_general_limit_amount=shopping_general_limit_amount,
        shopping_general_max_maturity_months=(
            shopping_general_max_maturity_months
        ),
        shopping_finance_rules_text=shopping_finance_rules_text,
        shopping_phone_rule_text=shopping_phone_rule_text,
        shopping_tablet_max_maturity_months=(
            shopping_tablet_max_maturity_months
        ),
        shopping_computer_max_maturity_months=(
            shopping_computer_max_maturity_months
        ),
        fee_waiver_text=fee_waiver_text,
        insurance_fee_waived=insurance_fee_waived,
        allocation_fee_waived=allocation_fee_waived,
        commission_fee_waived=commission_fee_waived,
        finance_rules_json=finance_rules_json,
    )
