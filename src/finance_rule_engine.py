from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from bs4 import BeautifulSoup


RULE_ENGINE_VERSION = "2026-08-15-pricing-evidence-guard-v2"


CATEGORY_ALIASES = {
    "cep telefonu": "Cep Telefonu",
    "telefon": "Cep Telefonu",
    "bilgisayar": "Bilgisayar",
    "tablet": "Tablet",
    "mobilya": "Mobilya",
    "havayolu ve konaklama": "Havayolu ve Konaklama",
    "havayolu": "Havayolu ve Konaklama",
    "beyaz esya": "Beyaz Eşya",
    "elektronik": "Elektronik",
    "egitim": "Eğitim",
    "saglik": "Sağlık",
    "giyim": "Giyim",
    "kozmetik": "Kozmetik",
    "gida": "Gıda",
    "akaryakit": "Akaryakıt",
    "market": "Market",
    "restoran": "Restoran",
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    value = unicodedata.normalize("NFKC", str(value))
    value = (
        value.replace("\u00a0", " ")
        .replace("\u200b", " ")
        .replace("\ufeff", " ")
    )
    return re.sub(r"\s+", " ", value).strip()


def search_key(value: Any) -> str:
    text = unicodedata.normalize(
        "NFKD",
        normalize_text(value),
    )
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )
    return text.casefold().replace("ı", "i")


def parse_number(value: Any) -> float | None:
    if value is None:
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


def category_key(label: Any) -> str:
    key = search_key(label)
    for alias in sorted(
        CATEGORY_ALIASES,
        key=len,
        reverse=True,
    ):
        if alias in key:
            return alias.replace(" ", "_")
    return re.sub(r"[^a-z0-9]+", "_", key).strip("_")


def category_label(label: Any) -> str:
    key = search_key(label)
    for alias, display in CATEGORY_ALIASES.items():
        if alias in key:
            return display
    return normalize_text(label)


def _money_pattern() -> str:
    return r"(\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?"


def extract_category_rules(
    text: str,
) -> list[dict[str, Any]]:
    """
    Kategori bazlı taksit / ay kısıtlarını çıkarır.

    Önemli:
    - Kaynak "taksit" diyorsa max_installments.
    - Kaynak "ay" diyorsa max_maturity_months.
    - Taksit -> ay dönüşümü yapılmaz.
    """
    normalized = normalize_text(text)
    key = search_key(normalized)
    rules: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    def add(
        label: str,
        *,
        min_amount: float | None = None,
        max_amount: float | None = None,
        min_inclusive: bool = False,
        max_inclusive: bool = True,
        max_installments: int | None = None,
        max_maturity_months: int | None = None,
        condition_text: str | None = None,
        source_text: str | None = None,
    ) -> None:
        if (
            max_installments is None
            and max_maturity_months is None
        ):
            return

        row = {
            "category_key": category_key(label),
            "category_label": category_label(label),
            "min_amount": min_amount,
            "max_amount": max_amount,
            "min_inclusive": bool(min_inclusive),
            "max_inclusive": bool(max_inclusive),
            "max_installments": max_installments,
            "max_maturity_months": max_maturity_months,
            "condition_text": condition_text,
            "source_text": source_text,
        }
        dedupe = (
            row["category_key"],
            min_amount,
            max_amount,
            min_inclusive,
            max_inclusive,
            max_installments,
            max_maturity_months,
        )
        if dedupe in seen:
            return
        seen.add(dedupe)
        rules.append(row)

    money = _money_pattern()

    # Cep telefonu: tutar eşikli iki kural.
    phone_patterns = (
        rf"{money}\s*(?:TL|₺)"
        rf"(?:['’`]?ye|['’`]?ya)?\s+kadar"
        rf"[^.!?]{{0,80}}?cep\s+telefonu"
        rf"[^.!?]{{0,80}}?(\d{{1,3}})"
        rf"(?:\s*taksit)?"
        rf"[^.!?]{{0,160}}?"
        rf"{money}\s*(?:TL|₺)"
        rf"(?:['’`]?(?:nin|nın|nun|nün|den|dan))?"
        rf"\s*(?:üzeri|üzerinde|fazla)"
        rf"[^.!?]{{0,80}}?cep\s+telefonu"
        rf"[^.!?]{{0,80}}?(\d{{1,3}})"
        rf"(?:\s*taksit)?",

        rf"cep\s+telefonu"
        rf"[^.!?]{{0,100}}?"
        rf"{money}\s*(?:TL|₺)"
        rf"(?:['’`]?ye|['’`]?ya)?\s+kadar"
        rf"[^.!?]{{0,80}}?(\d{{1,3}})\s*taksit"
        rf"[^.!?]{{0,160}}?"
        rf"{money}\s*(?:TL|₺)"
        rf"[^.!?]{{0,60}}?"
        rf"(?:üzeri|üzerinde)"
        rf"[^.!?]{{0,80}}?(\d{{1,3}})\s*taksit",
    )

    for pattern in phone_patterns:
        match = re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )
        if not match:
            continue

        threshold1 = parse_number(match.group(1))
        low_count = int(match.group(2))
        threshold2 = parse_number(match.group(3))
        high_count = int(match.group(4))
        threshold = threshold1 or threshold2

        if threshold is not None:
            add(
                "Cep Telefonu",
                max_amount=threshold,
                max_inclusive=True,
                max_installments=low_count,
                condition_text=(
                    f"≤ {int(threshold):,} TL"
                    .replace(",", ".")
                ),
                source_text=match.group(0),
            )
            add(
                "Cep Telefonu",
                min_amount=threshold,
                min_inclusive=False,
                max_installments=high_count,
                condition_text=(
                    f"> {int(threshold):,} TL"
                    .replace(",", ".")
                ),
                source_text=match.group(0),
            )
        break

    # Cümle bazlı kategori kuralları.
    sentences = re.split(
        r"(?<=[.!?])\s+|\n+",
        normalized,
    )

    known_labels = sorted(
        set(CATEGORY_ALIASES.values()),
        key=len,
        reverse=True,
    )

    for sentence in sentences:
        sentence_key = search_key(sentence)

        for display in known_labels:
            if display == "Cep Telefonu":
                continue

            aliases = [
                alias
                for alias, label in CATEGORY_ALIASES.items()
                if label == display
            ]

            if not any(
                alias in sentence_key
                for alias in aliases
            ):
                continue

            escaped = "|".join(
                re.escape(alias)
                for alias in aliases
            )

            # "Tablet alışverişleriniz en fazla 6 ay"
            #
            # Aynı flattened metinde daha sonra geçen
            # "Finansmanın maksimum vadesi 18 aydır"
            # ifadesini kategori kuralı sanmamak için aradaki
            # metni ayrıca kontrol ediyoruz.
            month_match = re.search(
                rf"(?:{escaped})"
                rf"(?P<middle>[^,.;:]{{0,45}}?)"
                rf"(?:en\s+fazla\s+)?"
                rf"(?P<months>\d{{1,3}})"
                rf"\s*ay(?:a|lık)?\b",
                sentence_key,
                flags=re.IGNORECASE,
            )
            if month_match:
                middle = month_match.group("middle")

                global_maturity_context = bool(
                    re.search(
                        r"(?:finansman(?:in|ın)?"
                        r"|maksimum\s+vade"
                        r"|azami\s+vade)",
                        middle,
                        flags=re.IGNORECASE,
                    )
                )

                # Kategori ay kuralı için kategoriye özgü bir
                # bağlam da bulunmalı.
                category_maturity_context = bool(
                    re.search(
                        r"(?:alisveris|alışveriş"
                        r"|alim|alım|vadelendir"
                        r"|en\s+fazla)",
                        middle,
                        flags=re.IGNORECASE,
                    )
                )

                if (
                    not global_maturity_context
                    and category_maturity_context
                ):
                    add(
                        display,
                        max_maturity_months=int(
                            month_match.group("months")
                        ),
                        condition_text="Tüm tutarlar",
                        source_text=sentence,
                    )
                    continue

            # "Bilgisayar alımları 12 ... taksit ile sınırlandırılmıştır"
            installment_match = re.search(
                rf"(?:{escaped})"
                rf"[^,.;:]{{0,80}}?"
                rf"(?:en\s+fazla\s+)?"
                rf"(\d{{1,3}})\s*taksit\b",
                sentence_key,
                flags=re.IGNORECASE,
            )

            if installment_match:
                count = int(
                    installment_match.group(1)
                )
                if 1 <= count <= 120:
                    add(
                        display,
                        max_installments=count,
                        condition_text="Tüm tutarlar",
                        source_text=sentence,
                    )

    # Flatten edilmiş kategori tabloları:
    # "Bilgisayar12 Tablet6 Mobilya18 ..." gibi HTML/CSS
    # nedeniyle tek satıra dönüşmüş gerçek kategori tabloları.
    #
    # Güvenlik:
    # - Sayı kategori adının hemen ardından gelmeli.
    # - Sayı TL, %, ay/yıl gibi başka bir birime ait olmamalı.
    # - En az 3 farklı kategori-sayı çifti birbirine yakın olmalı.
    # Böylece sayfadaki dağınık "Gıda ... 10.000 TL" gibi
    # ifadeler tablo sanılmaz.
    dense_candidates: list[
        tuple[int, int, str, int, str]
    ] = []

    for display in known_labels:
        if display == "Cep Telefonu":
            continue

        aliases = [
            alias
            for alias, label in CATEGORY_ALIASES.items()
            if label == display
        ]
        escaped = "|".join(
            re.escape(alias)
            for alias in aliases
        )

        for match in re.finditer(
            rf"(?:{escaped})"
            rf"(?:\s*\([^)]{{0,80}}\))?"
            rf"\s*[:\-–—]?\s*"
            rf"(\d{{1,3}})"
            rf"(?![\d.,])"
            rf"(?!\s*(?:tl|₺|%|ay\b|aya\b|aylik\b|"
            rf"yil\b|yila\b|yillik\b))",
            key,
            flags=re.IGNORECASE,
        ):
            value = int(match.group(1))
            if 1 <= value <= 120:
                dense_candidates.append(
                    (
                        match.start(),
                        match.end(),
                        display,
                        value,
                        match.group(0),
                    )
                )

    dense_candidates.sort(
        key=lambda item: item[0]
    )

    best_cluster: list[
        tuple[int, int, str, int, str]
    ] = []

    for i, candidate in enumerate(
        dense_candidates
    ):
        cluster = [
            row
            for row in dense_candidates[i:]
            if row[0] - candidate[0] <= 450
        ]

        distinct = {
            row[2]
            for row in cluster
        }

        if (
            len(distinct) >= 3
            and len(cluster) > len(best_cluster)
        ):
            best_cluster = cluster

    if best_cluster:
        added_labels: set[str] = set()

        for _, _, display, value, raw in best_cluster:
            if display in added_labels:
                continue

            added_labels.add(display)
            add(
                display,
                max_installments=value,
                condition_text="Tüm tutarlar",
                source_text=(
                    "Kategori bazlı taksit tablosu: "
                    + raw
                ),
            )


    return rules


def extract_amount_maturity_rules(
    text: str,
) -> list[dict[str, Any]]:
    """
    Finansman tutarına göre azami vade kademelerini çıkarır.
    """
    normalized = normalize_text(text)
    money = _money_pattern()
    rules: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    def add(
        *,
        min_amount=None,
        max_amount=None,
        min_inclusive=False,
        max_inclusive=True,
        months: int,
        source_text: str,
    ):
        key = (
            min_amount,
            max_amount,
            min_inclusive,
            max_inclusive,
            months,
        )
        if key in seen:
            return
        seen.add(key)
        rules.append(
            {
                "min_amount": min_amount,
                "max_amount": max_amount,
                "min_inclusive": bool(min_inclusive),
                "max_inclusive": bool(max_inclusive),
                "max_maturity_months": months,
                "source_text": source_text,
            }
        )

    upper_patterns = (
        rf"{money}\s*(?:TL|₺)"
        rf"(?:\s*['’`]?\s*(?:ye|ya))?\s+kadar"
        rf"[^.!?]{{0,120}}?"
        rf"(?:en\s+fazla|maksimum|azami)"
        rf"[^.!?\d]{{0,25}}(\d{{1,3}})\s*ay",
    )
    for pattern in upper_patterns:
        for match in re.finditer(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        ):
            upper = parse_number(match.group(1))
            months = int(match.group(2))
            if upper is not None and 1 <= months <= 120:
                add(
                    max_amount=upper,
                    max_inclusive=True,
                    months=months,
                    source_text=match.group(0),
                )

    range_patterns = (
        rf"{money}\s*(?:TL|₺)?\s*[-–—]\s*"
        rf"{money}\s*(?:TL|₺)"
        rf"[^.!?]{{0,80}}?(?:arası|arasında)"
        rf"[^.!?]{{0,100}}?"
        rf"(?:en\s+fazla|maksimum|azami)"
        rf"[^.!?\d]{{0,25}}(\d{{1,3}})\s*ay",

        # "125.000 - 250.000 TL' ye kadar olması
        #  durumunda maksimum vade 24 ay"
        rf"{money}\s*(?:TL|₺)?\s*[-–—]\s*"
        rf"{money}\s*(?:TL|₺)"
        rf"(?:\s*['’`]?\s*(?:ye|ya))?\s+kadar"
        rf"[^.!?]{{0,120}}?"
        rf"(?:en\s+fazla|maksimum|azami)"
        rf"[^.!?\d]{{0,25}}(\d{{1,3}})\s*ay",
    )
    for pattern in range_patterns:
        for match in re.finditer(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        ):
            low = parse_number(match.group(1))
            high = parse_number(match.group(2))
            months = int(match.group(3))
            if (
                low is not None
                and high is not None
                and low <= high
                and 1 <= months <= 120
            ):
                add(
                    min_amount=low,
                    max_amount=high,
                    min_inclusive=False,
                    max_inclusive=True,
                    months=months,
                    source_text=match.group(0),
                )

    lower_patterns = (
        rf"(?<![\d.]){money}\s*(?:TL|₺)"
        rf"(?:['’`]?(?:den|dan|ten|tan))?\s+fazla"
        rf"[^.!?]{{0,100}}?"
        rf"(?:en\s+fazla|maksimum|azami)"
        rf"[^.!?\d]{{0,25}}(\d{{1,3}})\s*ay",
    )
    for pattern in lower_patterns:
        for match in re.finditer(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        ):
            low = parse_number(match.group(1))
            months = int(match.group(2))
            if low is not None and 1 <= months <= 120:
                add(
                    min_amount=low,
                    min_inclusive=False,
                    months=months,
                    source_text=match.group(0),
                )

    # Bazı sayfalarda hem "250.000 TL'ye kadar 24 ay" şeklinde genel bir
    # cümle hem de "125.000-250.000 TL ... 24 ay" şeklinde gerçek bant
    # bulunabiliyor. Alt bant da yayımlanmışsa genel üst-kuralı tekrar
    # göstermek karşılaştırmada yanıltıcıdır. Aynı üst sınır/vade için daha
    # spesifik bir aralık ve onun altında ayrı bir kural varsa geniş kuralı
    # kaldırıyoruz.
    cleaned: list[dict[str, Any]] = []
    for row in rules:
        if row.get("min_amount") is None and row.get("max_amount") is not None:
            high = row.get("max_amount")
            months = row.get("max_maturity_months")
            ranges = [
                other for other in rules
                if other.get("min_amount") is not None
                and other.get("max_amount") == high
                and other.get("max_maturity_months") == months
            ]
            if ranges:
                low = min(float(other["min_amount"]) for other in ranges)
                has_lower_band = any(
                    other.get("max_amount") is not None
                    and float(other.get("max_amount")) <= low
                    and other.get("max_maturity_months") != months
                    for other in rules
                )
                if has_lower_band:
                    continue
        cleaned.append(row)

    # En spesifikten genele sıralama.
    return sorted(
        cleaned,
        key=lambda row: (
            float("-inf")
            if row["min_amount"] is None
            else row["min_amount"],
            float("inf")
            if row["max_amount"] is None
            else row["max_amount"],
        ),
    )


def _pricing_variant_parts_from_title(
    title: str,
) -> list[str]:
    key = search_key(title)
    parts: list[str] = []

    if (
        "ilk konut" in key
        or "ilk konutunu alan" in key
    ):
        parts.append("İlk Konut")
    elif (
        "mevcut konut" in key
        or "mevcut konutu olan" in key
        or "ikinci konut" in key
    ):
        parts.append("Mevcut Konut")

    if "sigortasiz" in key:
        parts.append("Sigortasız")
    elif "sigortali" in key:
        parts.append("Sigortalı")

    if re.search(r"\b0\s*km\b", key):
        parts.append("0 km")
    elif (
        "2. el" in key
        or "2 el" in key
        or "ikinci el" in key
    ):
        parts.append("2. El")

    return parts


def _pricing_variant_for_table(
    table,
) -> str:
    heading = table.find_previous(
        ["h2", "h3", "h4", "h5"]
    )

    if heading is None:
        return "Standart"

    title = normalize_text(
        heading.get_text(" ", strip=True)
    )
    key = search_key(title)

    parts = _pricing_variant_parts_from_title(
        title
    )

    if parts:
        return " · ".join(parts)

    if (
        "maliyet" in key
        or "kar payi" in key
        or "kar orani" in key
    ):
        return title[:120]

    return "Standart"



def _pricing_variant_from_title(
    title: str,
) -> str:
    parts = _pricing_variant_parts_from_title(
        title
    )

    if parts:
        return " · ".join(parts)

    return "Standart"


def _extract_pricing_tiers_from_text(
    clean_text: str,
) -> list[dict[str, Any]]:
    """
    HTML tablosu yapısal olarak kaçırılmışsa, kaynak sayfanın
    düz metnindeki açık "Maliyet Tablosu" bölümlerini okur.

    Yalnız 5 kolonun da yüzde biçiminde bulunduğu satırlar kabul
    edilir:
      Vade | Kâr Payı | Tahsis | Aylık Toplam | Yıllık Toplam
    """
    text = normalize_text(clean_text)
    if not text:
        return []

    heading_pattern = re.compile(
        r"(?P<title>"
        r"(?:Sigortalı|Sigortasız)"
        r"[^.!?]{0,220}?"
        r"Maliyet\s+Tablosu"
        r")",
        flags=re.IGNORECASE,
    )

    headings = list(heading_pattern.finditer(text))
    if not headings:
        return []

    row_pattern = re.compile(
        r"(?<![\d.,])"
        r"(?P<maturity>\d{1,3})"
        r"\s+(?:ay\s+)?"
        r"(?P<profit>\d{1,3}(?:[.,]\d+)?)\s*%"
        r"\s+"
        r"(?P<allocation>\d{1,3}(?:[.,]\d+)?)\s*%"
        r"\s+"
        r"(?P<monthly>\d{1,3}(?:[.,]\d+)?)\s*%"
        r"\s+"
        r"(?P<annual>\d{1,3}(?:[.,]\d+)?)\s*%",
        flags=re.IGNORECASE,
    )

    result: list[dict[str, Any]] = []

    for i, heading in enumerate(headings):
        start = heading.end()
        end = (
            headings[i + 1].start()
            if i + 1 < len(headings)
            else min(len(text), start + 3500)
        )

        segment = text[start:end]
        variant = _pricing_variant_from_title(
            heading.group("title")
        )

        for match in row_pattern.finditer(segment):
            maturity = int(match.group("maturity"))
            if not 1 <= maturity <= 120:
                continue

            record = {
                "pricing_variant": variant,
                "maturity_months": maturity,
                "profit_share_rate": parse_number(
                    match.group("profit")
                ),
                "allocation_fee_rate": parse_number(
                    match.group("allocation")
                ),
                "monthly_total_cost_rate": parse_number(
                    match.group("monthly")
                ),
                "annual_total_cost_rate": parse_number(
                    match.group("annual")
                ),
                "source_text": (
                    f"{maturity} | "
                    f"%{match.group('profit')} | "
                    f"%{match.group('allocation')} | "
                    f"%{match.group('monthly')} | "
                    f"%{match.group('annual')}"
                ),
            }

            result.append(record)

    return result


def _pricing_signature(
    row: dict[str, Any],
) -> tuple:
    return (
        row.get("maturity_months"),
        row.get("profit_share_rate"),
        row.get("allocation_fee_rate"),
        row.get("monthly_total_cost_rate"),
        row.get("annual_total_cost_rate"),
    )


def extract_pricing_tiers(
    html: str,
    clean_text: str = "",
) -> list[dict[str, Any]]:
    """
    Vade / kâr oranı / tahsis / aylık-yıllık maliyet
    tablolarını çıkarır.

    Aynı üründe birden fazla tablo varsa (örn. Sigortalı /
    Sigortasız, 0 km / 2. El) hepsini pricing_variant ile
    birlikte korur.
    """
    soup = BeautifulSoup(html, "html.parser")
    tiers: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        headers = [
            normalize_text(
                cell.get_text(" ", strip=True)
            )
            for cell in rows[0].find_all(["th", "td"])
        ]
        header_keys = [
            search_key(header)
            for header in headers
        ]

        def idx(*tokens: str) -> int | None:
            for i, key in enumerate(header_keys):
                if all(token in key for token in tokens):
                    return i
            return None

        maturity_i = idx("vade")
        profit_i = (
            idx("kar", "oran")
            if idx("kar", "oran") is not None
            else idx("kar", "payi")
        )
        allocation_i = idx("tahsis", "ucreti")
        monthly_i = (
            idx("aylik", "maliyet")
            if idx("aylik", "maliyet") is not None
            else idx("aylik", "toplam")
        )
        annual_i = (
            idx("yillik", "maliyet")
            if idx("yillik", "maliyet") is not None
            else idx("yillik", "toplam")
        )

        if monthly_i is None:
            monthly_candidates = [
                i
                for i, key in enumerate(header_keys)
                if (
                    "aylik" in key
                    and "kar" not in key
                    and "oran" not in key
                )
            ]
            if len(monthly_candidates) == 1:
                monthly_i = monthly_candidates[0]

        if annual_i is None:
            annual_candidates = [
                i
                for i, key in enumerate(header_keys)
                if "yillik" in key
            ]
            if len(annual_candidates) == 1:
                annual_i = annual_candidates[0]

        if (
            monthly_i is None
            and annual_i is not None
            and allocation_i is not None
            and annual_i - allocation_i == 2
        ):
            candidate = annual_i - 1
            if candidate not in {
                maturity_i,
                profit_i,
                allocation_i,
            }:
                monthly_i = candidate

        if profit_i is None:
            generic_rate_i = None
            for i, key in enumerate(header_keys):
                if key.strip() == "oran":
                    generic_rate_i = i
                    break

            has_cost_context = any(
                value is not None
                for value in (
                    allocation_i,
                    monthly_i,
                    annual_i,
                )
            )
            if has_cost_context:
                profit_i = generic_rate_i

        if maturity_i is None or profit_i is None:
            continue

        variant = _pricing_variant_for_table(table)

        for row in rows[1:]:
            cells = [
                normalize_text(
                    cell.get_text(" ", strip=True)
                )
                for cell in row.find_all(["th", "td"])
            ]
            if len(cells) <= max(maturity_i, profit_i):
                continue

            maturity = parse_number(cells[maturity_i])
            profit = parse_number(cells[profit_i])

            if (
                maturity is None
                or profit is None
                or not 1 <= maturity <= 120
            ):
                continue

            def val(index: int | None):
                if index is None or index >= len(cells):
                    return None
                return parse_number(cells[index])

            record = {
                "pricing_variant": variant,
                "maturity_months": int(maturity),
                "profit_share_rate": profit,
                "allocation_fee_rate": val(allocation_i),
                "monthly_total_cost_rate": val(monthly_i),
                "annual_total_cost_rate": val(annual_i),
                "source_text": " | ".join(cells),
            }

            # ALLOCATION_FEE_RATE_SEMANTIC_GUARD
            # Tahsis ucreti yuzde semantigindedir.
            # Ornek 500 TL gibi parasal degerler rate alanina sizamaz.
            _allocation_value = record.get("allocation_fee_rate")

            if _allocation_value is not None:
                try:
                    _allocation_value = float(_allocation_value)
                except (TypeError, ValueError):
                    _allocation_value = None

                if (
                    _allocation_value is None
                    or not 0 <= _allocation_value <= 100
                ):
                    record["allocation_fee_rate"] = None

            key = (
                record["pricing_variant"],
                record["maturity_months"],
                record["profit_share_rate"],
                record["allocation_fee_rate"],
                record["monthly_total_cost_rate"],
                record["annual_total_cost_rate"],
            )
            if key in seen:
                continue

            seen.add(key)
            tiers.append(record)

    text_tiers = _extract_pricing_tiers_from_text(
        clean_text
    )

    if text_tiers:
        # HTML'de aynı ekonomik satır "Standart" etiketiyle
        # yakalanmışsa, metindeki açık Sigortalı/Sigortasız
        # başlığını tercih et.
        by_signature = {
            _pricing_signature(row): row
            for row in text_tiers
        }

        merged: list[dict[str, Any]] = []

        for row in tiers:
            signature = _pricing_signature(row)
            fallback = by_signature.get(signature)

            if (
                fallback is not None
                and row.get("pricing_variant")
                not in {
                    "Sigortalı",
                    "Sigortasız",
                    "Sigortalı · 0 km",
                    "Sigortalı · 2. El",
                    "Sigortasız · 0 km",
                    "Sigortasız · 2. El",
                }
            ):
                row = dict(row)
                row["pricing_variant"] = fallback[
                    "pricing_variant"
                ]

            merged.append(row)

        existing = {
            (
                row.get("pricing_variant"),
                _pricing_signature(row),
            )
            for row in merged
        }

        for row in text_tiers:
            key = (
                row.get("pricing_variant"),
                _pricing_signature(row),
            )
            if key not in existing:
                merged.append(row)
                existing.add(key)

        tiers = merged

    return tiers


def extract_offer_rules(
    text: str,
) -> list[dict[str, Any]]:
    """
    Ürünün kendisine ait tutar / taksit / vade / vade-farksız
    koşullarını çıkarır.

    Örnek:
      "5.000 TL'ye kadar vade farksız 3 ay taksit imkanı"

    Not:
    "vade farksız" ifadesinden kâr payı %0 üretilmez.
    """
    normalized = normalize_text(text)
    key = search_key(normalized)
    money = _money_pattern()

    rules: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    def add(
        *,
        min_amount: float | None = None,
        max_amount: float | None = None,
        min_inclusive: bool = False,
        max_inclusive: bool = True,
        max_installments: int | None = None,
        max_maturity_months: int | None = None,
        interest_free: bool = False,
        condition_text: str | None = None,
        source_text: str | None = None,
    ) -> None:
        if (
            max_installments is None
            and max_maturity_months is None
            and not interest_free
        ):
            return

        dedupe = (
            min_amount,
            max_amount,
            min_inclusive,
            max_inclusive,
            max_installments,
            max_maturity_months,
            interest_free,
        )
        if dedupe in seen:
            return
        seen.add(dedupe)

        rules.append(
            {
                "rule_type": "product_offer",
                "rule_label": "Ürüne Özel Finansman Koşulu",
                "min_amount": min_amount,
                "max_amount": max_amount,
                "min_inclusive": bool(min_inclusive),
                "max_inclusive": bool(max_inclusive),
                "max_installments": max_installments,
                "max_maturity_months": max_maturity_months,
                "interest_free": bool(interest_free),
                "condition_text": condition_text,
                "source_text": source_text,
            }
        )

    sentences = re.split(
        r"(?<=[.!?])\s+|\n+",
        normalized,
    )

    # "5.000 TL'ye kadar vade farksız 3 ay taksit"
    pattern = (
        rf"{money}\s*(?:TL|₺)"
        rf"(?:['’`]?ye|['’`]?ya)?\s+kadar"
        rf"[^.!?]{{0,180}}?"
        rf"vade\s+farks[iı]z"
        rf"[^.!?]{{0,100}}?"
        rf"(\d{{1,3}})\s*"
        rf"(ay(?:l[iı]k)?\s*)?"
        rf"taksit\b"
    )

    # "5.000 TL'ye kadar 3 ay vade farksız taksit"
    reverse_pattern = (
        rf"{money}\s*(?:TL|₺)"
        rf"(?:['’`]?ye|['’`]?ya)?\s+kadar"
        rf"[^.!?]{{0,120}}?"
        rf"(\d{{1,3}})\s*ay"
        rf"[^.!?]{{0,80}}?"
        rf"vade\s+farks[iı]z"
        rf"[^.!?]{{0,60}}?"
        rf"taksit\b"
    )

    for sentence in sentences:
        match = re.search(
            pattern,
            sentence,
            flags=re.IGNORECASE,
        )

        if match:
            upper = parse_number(match.group(1))
            count = int(match.group(2))
            has_month = bool(match.group(3))

            if (
                upper is not None
                and upper > 0
                and 1 <= count <= 120
            ):
                parts = [
                    (
                        f"≤ {int(upper):,} TL"
                        .replace(",", ".")
                    ),
                    "Vade farksız",
                    f"{count} taksit",
                ]
                if has_month:
                    parts.append(f"{count} ay")

                add(
                    max_amount=upper,
                    max_inclusive=True,
                    max_installments=count,
                    max_maturity_months=(
                        count if has_month else None
                    ),
                    interest_free=True,
                    condition_text=" · ".join(parts),
                    source_text=sentence,
                )
            continue

        match = re.search(
            reverse_pattern,
            sentence,
            flags=re.IGNORECASE,
        )
        if match:
            upper = parse_number(match.group(1))
            months = int(match.group(2))

            if (
                upper is not None
                and upper > 0
                and 1 <= months <= 120
            ):
                add(
                    max_amount=upper,
                    max_inclusive=True,
                    max_installments=months,
                    max_maturity_months=months,
                    interest_free=True,
                    condition_text=(
                        f"≤ {int(upper):,} TL"
                        .replace(",", ".")
                        + f" · Vade farksız · "
                        + f"{months} taksit · {months} ay"
                    ),
                    source_text=sentence,
                )

    # Ürünün genel azami vadesi.
    # Örn: "Finansmanın maksimum vadesi 18 aydır."
    global_patterns = (
        r"finansman(?:ın|in)?\s+maksimum\s+vadesi"
        r"\s*(\d{1,3})\s*ay",
        r"(\d{1,3})\s*aya?\s+varan\s+vadeler",
        r"(\d{1,3})\s*aya?\s+kadar\s+vadeler",
    )

    for pattern in global_patterns:
        match = re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        )
        if not match:
            continue

        months = int(match.group(1))
        if 1 <= months <= 120:
            add(
                max_maturity_months=months,
                condition_text=(
                    f"Genel azami vade: {months} ay"
                ),
                source_text=match.group(0),
            )
            break

    # Tutar/taksit belirtilmese de açık vade-farksız ürün koşulu.
    if not any(
        row.get("interest_free")
        for row in rules
    ):
        free_match = re.search(
            r"(?:vade\s+farks[ıi]z"
            r"|vade\s+fark[ıi]\s+al[ıi]nmamaktad[ıi]r"
            r"|vade\s+fark[ıi]\s+al[ıi]nmaz)",
            normalized,
            flags=re.IGNORECASE,
        )
        if free_match:
            add(
                interest_free=True,
                condition_text="Vade farksız",
                source_text=free_match.group(0),
            )

    return rules


def build_finance_rules(
    *,
    html: str,
    clean_text: str,
    insurance_fee_waived: bool = False,
    allocation_fee_waived: bool = False,
    commission_fee_waived: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    fee_rules: list[dict[str, Any]] = []

    # Fiyatlama satırlarını burada silmeyiz. Örnek/temsili tablolar da kanıt
    # olarak saklanır; ana karşılaştırmada kullanılıp kullanılamayacağı
    # ``value_type`` metadata'sı ve pricing guardrail katmanında belirlenir.
    pricing_tiers = extract_pricing_tiers(
        html,
        clean_text,
    )

    fee_key = search_key(clean_text)

    # Daha geniş ama yine açık negatif ifadeler:
    # "sigorta ... alınmamaktadır", "masraf ... alınmamaktadır".
    if re.search(
        r"sigorta[^.!?]{0,100}"
        r"(?:alinmamaktadir|alinmaz|alinmayacaktir)",
        fee_key,
    ):
        insurance_fee_waived = True

    general_expense_waived = bool(
        re.search(
            r"(?:masraf|ucret)[^.!?]{0,100}"
            r"(?:alinmamaktadir|alinmaz|alinmayacaktir)",
            fee_key,
        )
    )

    if insurance_fee_waived:
        fee_rules.append(
            {
                "fee_type": "insurance",
                "fee_label": "Sigorta Ücreti",
                "waived": True,
                "amount": None,
                "rate": None,
                "note": "Kaynakta alınmayacağı açıkça belirtiliyor.",
            }
        )

    if allocation_fee_waived:
        fee_rules.append(
            {
                "fee_type": "allocation",
                "fee_label": "Tahsis Ücreti",
                "waived": True,
                "amount": None,
                "rate": None,
                "note": "Kaynakta alınmayacağı açıkça belirtiliyor.",
            }
        )

    # Tahsis ücreti için önce gerçek maliyet tablosunu
    # kullan. Böylece flattened metindeki %4,20 kâr oranı,
    # yanlışlıkla tahsis ücreti olarak alınmaz.
    if not allocation_fee_waived:
        allocation_rate = None
        allocation_is_maximum = False

        tier_rates = sorted(
            {
                float(row["allocation_fee_rate"])
                for row in pricing_tiers
                if row.get("allocation_fee_rate")
                is not None
                and 0 <= float(row["allocation_fee_rate"]) <= 100
            }
        )

        if len(tier_rates) == 1:
            allocation_rate = tier_rates[0]
        else:
            normalized_fee_text = normalize_text(
                clean_text
            )

            explicit_patterns = (
                r"(?:finansman\s+)?tahsis\s+ücreti"
                r"[^.!?]{0,160}?"
                r"finansman\s+tutar[ıi]n[ıi]n"
                r"[^.!?]{0,60}?"
                r"%\s*(\d{1,3}(?:[.,]\d{1,4})?)",

                r"(?:finansman\s+)?tahsis\s+ücreti"
                r"[^.!?]{0,160}?"
                r"finansman\s+tutar[ıi]n[ıi]n"
                r"[^.!?]{0,60}?"
                r"(\d{1,3}(?:[.,]\d{1,4})?)\s*%",

                # Kuveyt Türk ticari gayrimenkul/2B/arsa örneği:
                # "finansman tutarı üzerinden maksimum %1.10"
                r"(?:finansman\s+)?tahsis\s+ücreti"
                r"[^.!?]{0,180}?"
                r"finansman\s+tutar[ıi]\s+üzerinden"
                r"[^.!?]{0,80}?"
                r"%\s*(\d{1,3}(?:[.,]\d{1,4})?)",

                r"(?:finansman\s+)?tahsis\s+ücreti"
                r"[^.!?]{0,180}?"
                r"finansman\s+tutar[ıi]\s+üzerinden"
                r"[^.!?]{0,80}?"
                r"(\d{1,3}(?:[.,]\d{1,4})?)\s*%",
            )

            for pattern in explicit_patterns:
                match = re.search(
                    pattern,
                    normalized_fee_text,
                    flags=re.IGNORECASE,
                )
                if not match:
                    continue

                value = parse_number(
                    match.group(1)
                )
                if (
                    value is not None
                    and 0 <= value <= 100
                ):
                    allocation_rate = value
                    allocation_is_maximum = bool(
                        re.search(
                            r"\b(?:maksimum|azami)\b",
                            match.group(0),
                            flags=re.IGNORECASE,
                        )
                    )
                    break

            if allocation_rate is None:
                binde_match = re.search(
                    r"(?:finansman\s+)?tahsis\s+ücreti"
                    r"[^.!?]{0,180}?"
                    r"binde\s*(\d{1,3}(?:[.,]\d+)?)",
                    normalized_fee_text,
                    flags=re.IGNORECASE,
                )

                if binde_match:
                    value = parse_number(
                        binde_match.group(1)
                    )
                    if value is not None:
                        allocation_rate = (
                            float(value) / 10.0
                        )

        if allocation_rate is not None:
            fee_rules.append(
                {
                    "fee_type": "allocation",
                    "fee_label": (
                        "Azami Tahsis Ücreti"
                        if allocation_is_maximum
                        else "Tahsis Ücreti"
                    ),
                    "waived": False,
                    "amount": None,
                    "rate": allocation_rate,
                    "note": (
                        "Kaynakta azami/maksimum oran olarak yayımlanıyor."
                        if allocation_is_maximum
                        else (
                            "Kaynak maliyet tablosu veya açık "
                            "tahsis ücreti ifadesinden çıkarıldı."
                        )
                    ),
                }
            )

    if commission_fee_waived:
        fee_rules.append(
            {
                "fee_type": "commission",
                "fee_label": "Komisyon",
                "waived": True,
                "amount": None,
                "rate": None,
                "note": "Kaynakta alınmayacağı açıkça belirtiliyor.",
            }
        )

    if general_expense_waived:
        fee_rules.append(
            {
                "fee_type": "general_expense",
                "fee_label": "Masraf",
                "waived": True,
                "amount": None,
                "rate": None,
                "note": "Kaynakta masraf alınmadığı açıkça belirtiliyor.",
            }
        )

    return {
        "category_rules": extract_category_rules(clean_text),
        "amount_maturity_rules": extract_amount_maturity_rules(
            clean_text
        ),
        "pricing_tiers": pricing_tiers,
        "fee_rules": fee_rules,
        "offer_rules": extract_offer_rules(clean_text),
    }


def dumps_finance_rules(
    **kwargs,
) -> str:
    return json.dumps(
        build_finance_rules(**kwargs),
        ensure_ascii=False,
        sort_keys=True,
    )


def amount_matches(
    *,
    amount: float,
    min_amount: float | None,
    max_amount: float | None,
    min_inclusive: bool,
    max_inclusive: bool,
) -> bool:
    if min_amount is not None:
        if min_inclusive:
            if amount < min_amount:
                return False
        elif amount <= min_amount:
            return False

    if max_amount is not None:
        if max_inclusive:
            if amount > max_amount:
                return False
        elif amount >= max_amount:
            return False

    return True
