from __future__ import annotations

import json
import math
import re
import unicodedata

import pandas as pd
import streamlit as st

from src.finance_rule_engine import amount_matches
from src.finance_common_scenario import (
    evaluate_product_eligibility,
    filter_exact_verified_scenarios,
)
from src.postgres_repository import (
    get_latest_finance_scenarios,
    get_standard_product_changes,
    get_standard_product_rule_sets,
    get_standard_products,
    postgres_health,
)
from src.ui_display import display_text, format_number_tr
from src.pricing_guardrails import filter_authoritative_pricing_frame
from src.finance_taxonomy import (
    category_label as bansa_category_label,
    category_order as bansa_category_order,
    classify_finance_category,
    normalize_scope,
    scope_label as bansa_scope_label,
    scope_order as bansa_scope_order,
)
from src.finance_column_profiles import (
    get_profile as get_finance_column_profile,
    join_verified_values,
    select_main_table_columns,
)


st.set_page_config(
    page_title="Finansman Karşılaştırması",
    page_icon="🏦",
    layout="wide",
)

st.title("Finansman Karşılaştırması")
st.caption(
    "Finansman türünü, bankaları ve ihtiyacınızı seçin; "
    "uygun ürünleri tek tabloda karşılaştırın."
)

try:
    _pg_health = postgres_health()
except Exception as exc:
    st.error(
        "PostgreSQL bağlantısı kurulamadı. Bu sayfa SQLite'a geri dönmez. "
        f"Hata: {exc}"
    )
    st.stop()

st.caption(
    "🟢 Veri kaynağı: PostgreSQL · "
    f"{_pg_health.get('database_name', 'bansa_db')} / "
    f"{_pg_health.get('schema_name', 'bansa')} · "
    f"Güncel standart ürün: {_pg_health.get('current_products', 0)}"
)


def has_value(value: object) -> bool:
    return (
        value is not None
        and not pd.isna(value)
        and str(value).strip() != ""
    )


def tr_money(value: object) -> str:
    if not has_value(value):
        return "Belirtilmedi"
    return f"{format_number_tr(value)} TL"


def rate_text(value: object) -> str:
    if not has_value(value):
        return "Belirtilmedi"
    return f"%{format_number_tr(value)}"



def parse_user_tl_input(value: object) -> float | None:
    """
    Streamlit text_input üzerinden girilen tam TL değerini parse eder.

    Kabul edilen örnekler:
      2000000
      2.000.000
      2,000,000
      2 000 000
      2.000.000 TL

    Ondalıklı tutarlar bu ekranda gerekli olmadığı için bilinçli
    olarak kabul edilmez.
    """
    raw = str(value or "").strip()
    if not raw:
        return None

    cleaned = (
        raw.upper()
        .replace("₺", "")
        .replace("TL", "")
        .replace(" ", "")
        .strip()
    )

    if re.fullmatch(r"\d+", cleaned):
        return float(cleaned)

    if re.fullmatch(
        r"\d{1,3}(?:[.,]\d{3})+",
        cleaned,
    ):
        return float(
            cleaned.replace(".", "").replace(",", "")
        )

    return None


def default_amount_for_family(
    family: str,
) -> int:
    key = str(family).casefold()

    if any(token in key for token in ("araç", "arac", "taşıt", "tasit")):
        return 500_000
    if "konut" in key:
        return 2_000_000
    if "alışveriş" in key or "alisveris" in key:
        return 50_000
    if "ihtiyaç" in key or "ihtiyac" in key:
        return 50_000
    if "ticari" in key:
        return 250_000

    return 50_000


def display_product_name(value: object) -> str:
    text = display_text(value)

    text = re.sub(
        r"(?:\\?\*)+\s*$",
        "",
        text,
    ).rstrip()

    return text


def vehicle_family(family: str) -> bool:
    key = str(family).casefold().replace("i̇", "i")
    return any(token in key for token in ("araç", "arac", "taşıt", "tasit"))


def housing_family(family: str) -> bool:
    key = (
        str(family)
        .casefold()
        .replace("i̇", "i")
    )
    return "konut" in key


def _legacy_housing_band_bounds(
    label: object,
) -> tuple[float | None, float | None]:
    """Eski list-schema housing JSON kayıtlarını canonical yapıya taşır."""
    raw = str(label or "").strip()
    if not raw:
        return None, None

    key = (
        unicodedata.normalize("NFKD", raw)
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
    )

    million_values: list[float] = []
    for match in re.findall(
        r"(\d+(?:[.,]\d+)?)\s*milyon",
        key,
    ):
        try:
            million_values.append(
                float(match.replace(",", ".")) * 1_000_000
            )
        except ValueError:
            pass

    values = million_values
    if not values:
        values = []
        for match in re.findall(
            r"\d{1,3}(?:\.\d{3})+|\d{4,}",
            raw,
        ):
            parsed = parse_scaled_amount(match)
            if parsed is not None:
                values.append(float(parsed))

    if not values:
        return None, None

    values = list(dict.fromkeys(values))
    if len(values) >= 2:
        low, high = min(values), max(values)
        rounded_million = round(low / 1_000_000) * 1_000_000
        if abs(low - rounded_million - 1) < 0.01:
            low = rounded_million
        return low, high

    value = values[0]
    is_lower = bool(
        re.search(r"\b(?:uzeri|ustunde)\b", key)
        or "deger >" in key
        or re.search(r"\d[^\n]{0,25}<\s*deger", key)
    )
    return (value, None) if is_lower else (None, value)


def parse_housing_rules_json(
    value: object,
) -> dict:
    """Konut kurallarını canonical dict şemasında döndürür.

    Yeni şema:
      {"standard_home": [...], "additional_home": [...]}

    Eski Dünya Katılım kayıtlarında kullanılan list şeması da geriye
    dönük olarak desteklenir; böylece veri göçü bitmeden UI bozulmaz.
    """
    if not has_value(value):
        return {}

    if isinstance(value, (dict, list)):
        parsed = value
    else:
        try:
            parsed = json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}

    if isinstance(parsed, dict):
        result = {
            "standard_home": list(parsed.get("standard_home") or []),
            "additional_home": list(parsed.get("additional_home") or []),
        }
        return result if any(result.values()) else {}

    if not isinstance(parsed, list):
        return {}

    result: dict[str, list[dict]] = {
        "standard_home": [],
        "additional_home": [],
    }

    for row in parsed:
        if not isinstance(row, dict):
            continue

        kind_raw = str(row.get("purchase_type") or "").casefold()
        if kind_raw in {"first_home", "standard_home"}:
            kind = "standard_home"
        elif kind_raw in {"additional_home", "second_home"}:
            kind = "additional_home"
        else:
            continue

        low, high = _legacy_housing_band_bounds(
            row.get("value_band_source")
            or row.get("value_band_short")
        )

        canonical = {
            "min_value": low,
            "max_value": high,
            "ab": row.get("rate_ab"),
            "c": row.get("rate_c"),
            "other": row.get("rate_other"),
        }
        if any(
            canonical.get(key) is not None
            for key in ("ab", "c", "other")
        ):
            result[kind].append(canonical)

    return result if any(result.values()) else {}

def housing_value_band_text(
    rule: dict,
) -> str:
    low = rule.get("min_value")
    high = rule.get("max_value")

    if low is None and high is not None:
        return f"Değer ≤ {tr_money(high)}"

    if low is not None and high is not None:
        return (
            f"{tr_money(low)} < Değer ≤ "
            f"{tr_money(high)}"
        )

    if low is not None:
        return f"Değer > {tr_money(low)}"

    return "Tüm değerler"


def evaluate_housing_rule(
    product: pd.Series,
    property_value: float,
    purchase_type: str,
    energy_class: str,
) -> dict | None:
    """
    Konut ekspertiz değerine, konut alım tipine ve enerji
    sınıfına göre resmî finansman oranını bulur.
    """
    rules = parse_housing_rules_json(
        product.get("housing_finance_rules_json")
    )
    if not rules:
        return None

    rule_key = (
        "additional_home"
        if purchase_type == "2. ve Sonraki Konut Alımı"
        else "standard_home"
    )

    energy_key = {
        "A-B": "ab",
        "C": "c",
        "Diğer": "other",
    }.get(energy_class)

    if not energy_key:
        return None

    for rule in rules.get(rule_key, []):
        low = rule.get("min_value")
        high = rule.get("max_value")

        matches = True

        if low is not None and float(property_value) <= float(low):
            matches = False

        if high is not None and float(property_value) > float(high):
            matches = False

        if not matches:
            continue

        ratio = rule.get(energy_key)
        if ratio is None:
            return None

        ratio = float(ratio)

        return {
            "purchase_type": purchase_type,
            "energy_class": energy_class,
            "min_value": low,
            "max_value": high,
            "ratio": ratio,
            "max_financing_amount": (
                float(property_value)
                * ratio
                / 100.0
            ),
        }

    return None


def housing_rule_table(
    product: pd.Series,
    purchase_type: str,
) -> pd.DataFrame:
    rules = parse_housing_rules_json(
        product.get("housing_finance_rules_json")
    )

    rule_key = (
        "additional_home"
        if purchase_type == "2. ve Sonraki Konut Alımı"
        else "standard_home"
    )

    rows = []

    for rule in rules.get(rule_key, []):
        rows.append(
            {
                "Konut / Ekspertiz Değeri": housing_value_band_text(rule),
                "A-B Enerji Sınıfı": (
                    rate_text(rule.get("ab"))
                    if rule.get("ab") is not None
                    else "—"
                ),
                "C Enerji Sınıfı": (
                    rate_text(rule.get("c"))
                    if rule.get("c") is not None
                    else "—"
                ),
                "Diğer": (
                    rate_text(rule.get("other"))
                    if rule.get("other") is not None
                    else "—"
                ),
            }
        )

    return pd.DataFrame(rows)


def _vehicle_text_key(value: object) -> str:
    """Araç durum/sigorta ifadelerini Türkçe karakterlerden bağımsız eşleştir."""
    if not has_value(value):
        return ""

    return (
        str(value)
        .casefold()
        .replace("ı", "i")
        .replace("İ", "i")
    )


def vehicle_variant_profile(
    product: pd.Series,
    product_id: int,
    pricing_rules: pd.DataFrame,
    selected_pricing_variant: str | None = None,
) -> tuple[str, str]:
    """
    Resmî ürün verisinde açıkça bulunan araç durumunu ve sigorta
    fiyatlama ayrımını özetler.

    Öncelik:
      1) pricing_variant (örn. "Sigortalı · 0 km")
      2) scope / vehicle_age_rules_text / product_name /
         vehicle_finance_rules_text

    Kaynakta açık kanıt yoksa tahmin yapılmaz.
    """
    evidence: list[str] = []

    if not pricing_rules.empty:
        subset = pricing_rules[
            pricing_rules["product_id"] == product_id
        ].copy()

        if (
            selected_pricing_variant is not None
            and "pricing_variant" in subset.columns
        ):
            selected_rows = subset[
                subset["pricing_variant"]
                == selected_pricing_variant
            ]
            if not selected_rows.empty:
                subset = selected_rows

        if "pricing_variant" in subset.columns:
            evidence.extend(
                subset["pricing_variant"]
                .dropna()
                .astype(str)
                .loc[lambda s: s.str.strip().ne("")]
                .drop_duplicates()
                .tolist()
            )

    for field in (
        "scope",
        "vehicle_age_rules_text",
        "product_name",
        "vehicle_finance_rules_text",
    ):
        value = product.get(field)
        if has_value(value):
            evidence.append(str(value))

    vehicle_states: list[str] = []
    insurance_states: list[str] = []

    for item in evidence:
        key = _vehicle_text_key(item)

        if re.search(
            r"\b0\s*(?:km|kilometre)\b"
            r"|\bsifir\s*(?:km|kilometre|arac|tasit)?\b",
            key,
        ):
            if "0 km" not in vehicle_states:
                vehicle_states.append("0 km")

        if re.search(
            r"\b2\s*\.?\s*el\b"
            r"|\bikinci\s+el\b",
            key,
        ):
            if "2. El" not in vehicle_states:
                vehicle_states.append("2. El")

        if re.search(r"\bsigortasiz\b", key):
            if "Sigortasız" not in insurance_states:
                insurance_states.append("Sigortasız")

        cleaned_for_insured = re.sub(
            r"\bsigortasiz\b",
            "",
            key,
        )
        if re.search(r"\bsigortali\b", cleaned_for_insured):
            if "Sigortalı" not in insurance_states:
                insurance_states.append("Sigortalı")

    vehicle_order = ["0 km", "2. El"]
    insurance_order = ["Sigortalı", "Sigortasız"]

    vehicle_states.sort(
        key=lambda value: (
            vehicle_order.index(value)
            if value in vehicle_order
            else len(vehicle_order)
        )
    )
    insurance_states.sort(
        key=lambda value: (
            insurance_order.index(value)
            if value in insurance_order
            else len(insurance_order)
        )
    )

    vehicle_text = (
        " · ".join(vehicle_states)
        if vehicle_states
        else "—"
    )
    insurance_text = (
        " · ".join(insurance_states)
        if insurance_states
        else "—"
    )

    return vehicle_text, insurance_text


def vehicle_fields_from_pricing_variant(
    value: object,
) -> tuple[str, str]:
    """
    Tek bir pricing_variant değerinden araç durumu ve
    sigorta durumunu çıkarır.
    Örn:
      "Sigortalı · 0 km" -> ("0 km", "Sigortalı")
      "Sigortasız · 2. El" -> ("2. El", "Sigortasız")
    """
    key = _vehicle_text_key(value)

    vehicle_status = "—"
    insurance_status = "—"

    if re.search(
        r"\b0\s*(?:km|kilometre)\b"
        r"|\bsifir\s*(?:km|kilometre|arac|tasit)?\b",
        key,
    ):
        vehicle_status = "0 km"
    elif re.search(
        r"\b2\s*\.?\s*el\b"
        r"|\bikinci\s+el\b",
        key,
    ):
        vehicle_status = "2. El"

    if re.search(r"\bsigortasiz\b", key):
        insurance_status = "Sigortasız"
    else:
        cleaned = re.sub(
            r"\bsigortasiz\b",
            "",
            key,
        )
        if re.search(r"\bsigortali\b", cleaned):
            insurance_status = "Sigortalı"

    return vehicle_status, insurance_status


def _family_key(family: str) -> str:
    return (
        str(family)
        .casefold()
        .replace("i̇", "i")
    )


def is_gayri_nakdi_family(
    family: str,
) -> bool:
    key = _family_key(family)

    return (
        "gayri nakdi" in key
        or "gayrinakdi" in key
    )


def meaningful_detail_value(
    value,
) -> bool:
    """
    Ürün detayında yalnız gerçek bilgi taşıyan alanları göster.
    Kaynakta veri bulunmadığını söyleyen placeholder metinleri
    ayrı bir metrik olarak ekranda tutma.
    """
    if value is None:
        return False

    text_value = str(value).strip()

    if not text_value:
        return False

    placeholders = {
        "Belirtilmedi",
        "—",
        "-",
        "Kaynakta yayımlanmamış",
        "Kaynakta sayısal değer yayımlanmamış",
        "Kaynakta sayısal değer yok",
        "Uygulanamaz",
    }

    return text_value not in placeholders


def _frame_has_any_value(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
) -> bool:
    if frame is None or frame.empty:
        return False

    for column in columns:
        if column not in frame.columns:
            continue

        if frame[column].apply(has_value).any():
            return True

    return False


def financing_amount_applicable(
    family: str,
    selected_products: pd.DataFrame | None = None,
    category_rules: pd.DataFrame | None = None,
    amount_rules: pd.DataFrame | None = None,
    offer_rules: pd.DataFrame | None = None,
) -> bool:
    """
    Finansman tutarı filtresini yalnız gerçekten kullanılabilir
    sayısal tutar kanıtı varsa göster.

    Araç ailesinde giriş finansman tutarı değil araç/kasko
    değeridir ve her zaman kendi değerlendirme akışını kullanır.
    Gayri Nakdi ürünlerde tutar filtresi uygulanmaz.
    """
    if is_gayri_nakdi_family(family):
        return False

    if vehicle_family(family):
        return True

    # Konut finansmanındaki ekspertiz değeri / enerji sınıfı / ilk-ikinci
    # ev gibi bankaya özgü hesaplar ana karşılaştırma filtresi değildir.
    # Konut ailesinde üstte yalnız gerçekten genel finansman tutarı verisi
    # varsa normal tutar filtresi gösterilir.
    if selected_products is None:
        return True

    if _frame_has_any_value(
        selected_products,
        (
            "minimum_financing_amount",
            "maximum_financing_amount",
            "shopping_general_limit_amount",
        ),
    ):
        return True

    if _frame_has_any_value(
        amount_rules,
        (
            "min_amount",
            "max_amount",
        ),
    ):
        return True

    if _frame_has_any_value(
        category_rules,
        (
            "min_amount",
            "max_amount",
        ),
    ):
        return True

    if _frame_has_any_value(
        offer_rules,
        (
            "min_amount",
            "max_amount",
        ),
    ):
        return True

    return False


def maturity_filter_applicable(
    family: str,
    selected_products: pd.DataFrame | None = None,
    category_rules: pd.DataFrame | None = None,
    amount_rules: pd.DataFrame | None = None,
    pricing_rules: pd.DataFrame | None = None,
    offer_rules: pd.DataFrame | None = None,
) -> bool:
    """
    Tercih Edilen Vade filtresini yalnız seçili ürün grubunda
    kullanıcı tarafından gerçekten filtrelenebilecek yapılandırılmış
    bir vade/taksit kuralı varsa göster.
    """
    if is_gayri_nakdi_family(family):
        return False

    if vehicle_family(family):
        return True

    if selected_products is None:
        return True

    if _frame_has_any_value(
        selected_products,
        (
            "minimum_maturity_months",
            "maximum_maturity_months",
        ),
    ):
        return True

    if _frame_has_any_value(
        amount_rules,
        (
            "min_maturity_months",
            "max_maturity_months",
        ),
    ):
        return True

    if _frame_has_any_value(
        category_rules,
        (
            "min_maturity_months",
            "max_maturity_months",
            "max_installments",
        ),
    ):
        return True

    if _frame_has_any_value(
        pricing_rules,
        (
            "maturity_months",
        ),
    ):
        return True

    if _frame_has_any_value(
        offer_rules,
        (
            "max_maturity_months",
            "max_installments",
        ),
    ):
        return True

    return False



def parse_scaled_amount(
    raw: str,
) -> float | None:
    token = str(raw).strip().casefold()
    token = token.replace("₺", "").replace("tl", "")
    token = re.sub(r"\s+", " ", token).strip()

    multiplier = 1.0

    if re.search(r"\b(?:mn|milyon)\b", token):
        multiplier = 1_000_000.0
        token = re.sub(
            r"\b(?:mn|milyon)\b",
            "",
            token,
        )
    elif re.search(r"\bbin\b", token):
        multiplier = 1_000.0
        token = re.sub(r"\bbin\b", "", token)

    token = token.strip()

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
        return float(token) * multiplier
    except ValueError:
        return None


def parse_vehicle_rules_text(
    value: object,
) -> list[dict]:
    if not has_value(value):
        return []

    text = str(value)
    parts = [
        item.strip()
        for item in re.split(r"\s*[·•]\s*", text)
        if item.strip()
    ]

    parsed = []

    # Türkçe binlik ayraçlı tutarların (örn. 1.200.000 / 2.000.000)
    # yalnız ilk iki grubunu yakalayıp 1.200 / 2.000'e düşürmesini engelle.
    amount_token = (
        r"(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"
        r"(?:\s*(?:bin|mn|milyon))?"
        r"(?:\s*(?:TL|₺))?"
    )

    for part in parts:
        if ":" not in part:
            continue

        range_text, outcome = [
            item.strip()
            for item in part.split(":", 1)
        ]

        low = None
        high = None
        low_inclusive = False
        high_inclusive = True

        upper_match = re.search(
            rf"[≤<]=?\s*({amount_token})",
            range_text,
            flags=re.IGNORECASE,
        )

        lower_match = re.search(
            rf">\s*({amount_token})",
            range_text,
            flags=re.IGNORECASE,
        )

        range_match = re.search(
            rf"({amount_token})\s*[-–—]\s*"
            rf"({amount_token})",
            range_text,
            flags=re.IGNORECASE,
        )

        if range_match:
            low = parse_scaled_amount(
                range_match.group(1)
            )
            high = parse_scaled_amount(
                range_match.group(2)
            )
            # Özet metinlerde "400 bin–800 bin"
            # şeklindeki ikinci bant 400.000'in üstünden başlar.
            low_inclusive = False
            high_inclusive = True
        elif upper_match:
            high = parse_scaled_amount(
                upper_match.group(1)
            )
            high_inclusive = "≤" in range_text
        elif lower_match:
            low = parse_scaled_amount(
                lower_match.group(1)
            )
            low_inclusive = False
            high = None

        blocked = bool(
            re.search(
                r"kulland[ıi]r[ıi]m\s+(?:yok|yap[ıi]lma)"
                r"|kulland[ıi]r[ıi]m\s+yap[ıi]lmayacakt[ıi]r"
                r"|%0\b",
                outcome,
                flags=re.IGNORECASE,
            )
        )

        ratio_match = re.search(
            r"%\s*(\d{1,3}(?:[.,]\d+)?)",
            outcome,
        )
        maturity_match = re.search(
            r"(\d{1,3})\s*ay",
            outcome,
            flags=re.IGNORECASE,
        )

        ratio = (
            float(
                ratio_match.group(1).replace(",", ".")
            )
            if ratio_match
            else None
        )
        months = (
            int(maturity_match.group(1))
            if maturity_match
            else None
        )

        if (
            low is None
            and high is None
            and ratio is None
            and months is None
            and not blocked
        ):
            continue

        parsed.append(
            {
                "min_amount": low,
                "max_amount": high,
                "min_inclusive": low_inclusive,
                "max_inclusive": high_inclusive,
                "ratio": ratio,
                "max_maturity_months": months,
                "blocked": blocked,
                "source_part": part,
            }
        )

    return parsed


def evaluate_vehicle_rule(
    rule_text: object,
    asset_value: float,
) -> dict | None:
    for rule in parse_vehicle_rules_text(rule_text):
        if amount_matches(
            amount=float(asset_value),
            min_amount=rule["min_amount"],
            max_amount=rule["max_amount"],
            min_inclusive=rule["min_inclusive"],
            max_inclusive=rule["max_inclusive"],
        ):
            result = dict(rule)

            ratio = result.get("ratio")
            result["max_financing_amount"] = (
                float(asset_value) * float(ratio) / 100.0
                if ratio is not None
                and not result.get("blocked")
                else None
            )
            return result

    return None


def vehicle_band_text(rule: dict) -> str:
    low = rule.get("min_amount")
    high = rule.get("max_amount")

    if low is None and high is not None:
        return f"Değer ≤ {tr_money(high)}"

    if low is not None and high is not None:
        return (
            f"{tr_money(low)} < Değer ≤ "
            f"{tr_money(high)}"
        )

    if low is not None:
        return f"Değer > {tr_money(low)}"

    return "Belirtilmedi"


def amount_band(row: pd.Series) -> str:
    low = row.get("min_amount")
    high = row.get("max_amount")
    low_inc = bool(row.get("min_inclusive"))
    high_inc = bool(row.get("max_inclusive"))

    if has_value(low) and has_value(high):
        left = "≤" if low_inc else "<"
        right = "≤" if high_inc else "<"
        return (
            f"{tr_money(low)} {left} Tutar "
            f"{right} {tr_money(high)}"
        )

    if has_value(high):
        sign = "≤" if high_inc else "<"
        return f"Tutar {sign} {tr_money(high)}"

    if has_value(low):
        sign = "≥" if low_inc else ">"
        return f"Tutar {sign} {tr_money(low)}"

    return "Tüm tutarlar"


def amount_maturity_summary_for_product(
    product_id: int,
    amount_rules: pd.DataFrame,
) -> str:
    """Ürünün TÜM resmî tutar-vade bantlarını tek metinde gösterir."""
    if amount_rules.empty:
        return ""

    subset = amount_rules[
        amount_rules["product_id"] == product_id
    ].copy()
    if subset.empty:
        return ""

    def sort_value(value, fallback):
        return float(value) if has_value(value) else fallback

    subset = subset.sort_values(
        by=["min_amount", "max_amount"],
        key=lambda col: col.map(
            lambda value: sort_value(
                value,
                float("-inf") if col.name == "min_amount" else float("inf"),
            )
        ),
        na_position="first",
    )

    parts: list[str] = []
    for _, rule in subset.iterrows():
        months = rule.get("max_maturity_months")
        if not has_value(months):
            continue

        low = rule.get("min_amount")
        high = rule.get("max_amount")
        low_inc = bool(rule.get("min_inclusive"))
        high_inc = bool(rule.get("max_inclusive"))

        if has_value(low) and has_value(high):
            left = "≤" if low_inc else "<"
            right = "≤" if high_inc else "<"
            band = f"{tr_money(low)} {left} Tutar {right} {tr_money(high)}"
        elif has_value(high):
            sign = "≤" if high_inc else "<"
            band = f"Tutar {sign} {tr_money(high)}"
        elif has_value(low):
            sign = "≥" if low_inc else ">"
            band = f"Tutar {sign} {tr_money(low)}"
        else:
            band = "Tüm tutarlar"

        item = f"{band} → {int(months)} ay"
        if item not in parts:
            parts.append(item)

    return " · ".join(parts)


def general_maturity_summary_for_product(
    product: pd.Series,
    product_id: int,
    amount_rules: pd.DataFrame,
) -> str:
    """Genel ürün vadesini kategori taksit sınırından ayrı gösterir."""
    bands = amount_maturity_summary_for_product(
        product_id,
        amount_rules,
    )
    if bands:
        return bands

    if has_value(product.get("maximum_maturity_months")):
        return f"{int(product.get('maximum_maturity_months'))} aya kadar"

    return "Kaynakta sayısal değer yayımlanmamış"




def pricing_amount_summary_for_product(
    product_id: int,
    pricing_rules: pd.DataFrame,
) -> str:
    """
    Fiyatlama tablosunda finansman tutarı + vade + kâr payı birlikte
    tutuluyorsa tüm satırları görünür bir özet halinde döndürür.

    Örn:
      100.000 TL → 12 ay · %4,49
      250.000 TL → 24 ay · %4,29
    """
    if pricing_rules.empty:
        return ""

    subset = pricing_rules[
        pricing_rules["product_id"] == product_id
    ].copy()

    if subset.empty:
        return ""

    required = {
        "maturity_months",
        "profit_share_rate",
    }
    if not required.issubset(subset.columns):
        return ""

    has_financing_amount = (
        "financing_amount" in subset.columns
        and subset["financing_amount"].notna().any()
    )

    if not has_financing_amount:
        return ""

    sort_cols = [
        col
        for col in (
            "financing_amount",
            "maturity_months",
            "pricing_variant",
        )
        if col in subset.columns
    ]
    if sort_cols:
        subset = subset.sort_values(
            sort_cols,
            kind="stable",
        )

    parts: list[str] = []

    for _, row in subset.iterrows():
        amount = row.get("financing_amount")
        maturity = row.get("maturity_months")
        rate = row.get("profit_share_rate")

        if not has_value(amount):
            continue

        details: list[str] = []

        if has_value(maturity):
            details.append(
                f"{int(maturity)} ay"
            )

        if has_value(rate):
            details.append(
                rate_text(rate)
            )

        variant = (
            str(row.get("pricing_variant") or "")
            .strip()
            if "pricing_variant" in subset.columns
            else ""
        )

        if variant:
            details.append(variant)

        item = tr_money(amount)

        if details:
            item += " → " + " · ".join(details)

        if item not in parts:
            parts.append(item)

    return " · ".join(parts)


def amount_dependent_summary_for_product(
    product: pd.Series,
    product_id: int,
    amount_rules: pd.DataFrame,
    pricing_rules: pd.DataFrame,
) -> str:
    """
    Tüm finansman ailelerinde tutara/değere göre değişen yapılandırılmış
    koşulları görünür tutar.

    Öncelik:
      1) product_amount_maturity_rules -> tutar/değer bandı + azami vade
      2) product_pricing_tiers.financing_amount -> tutar + vade + kâr payı
      3) araç ürünlerinde vehicle_finance_rules_text -> değer + oran + vade
    """
    parts: list[str] = []

    # 1) Normalize edilmiş tutar-vade bantları
    amount_summary = amount_maturity_summary_for_product(
        product_id,
        amount_rules,
    )
    if amount_summary:
        parts.append(amount_summary)

    # 2) Fiyatlama tablosunda tutara bağlı fiyatlama
    pricing_summary = pricing_amount_summary_for_product(
        product_id,
        pricing_rules,
    )
    if (
        pricing_summary
        and pricing_summary not in parts
    ):
        parts.append(pricing_summary)

    # 3) Araç için kaynak metnindeki değer-oran-vade bantları
    if vehicle_family(
        product.get("product_family")
    ):
        vehicle_rule_text = product.get(
            "vehicle_finance_rules_text"
        )

        if has_value(vehicle_rule_text):
            vehicle_parts: list[str] = []

            for rule in parse_vehicle_rules_text(
                vehicle_rule_text
            ):
                if rule.get("blocked"):
                    continue

                band = vehicle_band_text(rule)

                details: list[str] = []

                ratio = rule.get("ratio")
                months = rule.get(
                    "max_maturity_months"
                )

                if ratio is not None:
                    details.append(
                        "Azami %"
                        + format_number_tr(ratio)
                    )

                if months is not None:
                    details.append(
                        f"{int(months)} ay"
                    )

                if details:
                    item = (
                        band
                        + " → "
                        + " · ".join(details)
                    )

                    if item not in vehicle_parts:
                        vehicle_parts.append(item)

            vehicle_summary = " · ".join(
                vehicle_parts
            )

            if (
                vehicle_summary
                and vehicle_summary not in parts
            ):
                parts.append(vehicle_summary)

    return " · ".join(parts)


def product_has_amount_dependent_terms(
    product: pd.Series,
    product_id: int,
    amount_rules: pd.DataFrame,
    pricing_rules: pd.DataFrame,
) -> bool:
    return bool(
        amount_dependent_summary_for_product(
            product,
            product_id,
            amount_rules,
            pricing_rules,
        )
    )


def selected_category_limit_summary(
    category_matches: list[pd.Series],
) -> str:
    """Seçilen ürün kategorisinin yasal/ürün bazlı taksit-vade sınırını özetler."""
    if not category_matches:
        return "Belirtilmedi"

    parts: list[str] = []
    for row in category_matches:
        label = display_text(row.get("category_label"))
        installments = row.get("max_installments")
        months = row.get("max_maturity_months")

        limits: list[str] = []
        if has_value(installments):
            limits.append(f"maksimum {int(installments)} taksit")
        if has_value(months):
            limits.append(f"maksimum {int(months)} ay")

        if not limits:
            continue

        item = f"{label}: {' · '.join(limits)}"
        if item not in parts:
            parts.append(item)

    return " · ".join(parts) if parts else "Belirtilmedi"


def offer_summary_without_general_maturity(
    product_id: int,
    offer_rules: pd.DataFrame,
) -> str:
    """Kategori ve genel vade bilgisinden bağımsız gerçek özel koşulları gösterir."""
    if offer_rules.empty:
        return "Belirtilmedi"

    subset = offer_rules[offer_rules["product_id"] == product_id]
    parts: list[str] = []
    for _, row in subset.iterrows():
        text = display_text(row.get("condition_text"))
        if text == "Belirtilmedi":
            continue
        key = text.casefold()
        if key.startswith("genel azami vade"):
            continue
        if text not in parts:
            parts.append(text)

    return " · ".join(parts) if parts else "Belirtilmedi"


def product_financing_amount_eligible(
    product: pd.Series,
    amount: float,
) -> bool:
    minimum = product.get(
        "minimum_financing_amount"
    )
    maximum = product.get(
        "maximum_financing_amount"
    )

    if has_value(minimum):
        if float(amount) < float(minimum):
            return False

    if has_value(maximum):
        if float(amount) > float(maximum):
            return False

    return True


def product_amount_text(
    product: pd.Series,
    matching_offer: list[pd.Series] | None = None,
) -> str:
    # Önce ürünün genel finansman limiti.
    #
    # Offer/özel kampanya tutarı ürünün genel limiti değildir.
    # Örn. "5.000 TL'ye kadar vade farksız 3 taksit"
    # Finansman Tutarı sütununu 5.000 TL yapmamalıdır.
    shopping_limit = product.get(
        "shopping_general_limit_amount"
    )
    if has_value(shopping_limit):
        return f"≤ {tr_money(shopping_limit)}"

    low = product.get("minimum_financing_amount")
    high = product.get("maximum_financing_amount")

    if has_value(low) and has_value(high):
        return f"{tr_money(low)} – {tr_money(high)}"
    if has_value(high):
        return f"≤ {tr_money(high)}"
    if has_value(low):
        return f"≥ {tr_money(low)}"

    # Ürünün genel tutarı kaynakta yoksa ancak o zaman
    # offer bandını fallback olarak göster.
    if matching_offer:
        bands = []

        for rule in matching_offer:
            band = amount_band(rule)

            if (
                band != "Tüm tutarlar"
                and band not in bands
            ):
                bands.append(band)

        if bands:
            return " / ".join(bands)

    return "Kaynakta sayısal değer yayımlanmamış"



def housing_financing_amount_summary(
    product: pd.Series,
) -> str:
    """
    Konut/gayrimenkul ana tablosunda kullanıcı girdisini değil,
    bankanın resmî olarak yayımladığı finansman tutarı/oran yapısını gösterir.
    """
    explicit = product_amount_text(product)

    if (
        explicit
        and explicit
        not in {
            "Belirtilmedi",
            "Kaynakta sayısal değer yayımlanmamış",
        }
    ):
        return explicit

    ratio = product.get("maximum_financing_ratio")
    if has_value(ratio):
        return (
            "Gayrimenkul/ekspertiz değerinin azami "
            + rate_text(ratio)
        )

    housing_rules = parse_housing_rules_json(
        product.get("housing_finance_rules_json")
    )
    if housing_rules:
        return (
            "Ekspertiz değeri ve konut koşullarına göre"
        )

    ratio_text_value = str(
        product.get("financing_ratio_rules_text") or ""
    ).strip()

    if ratio_text_value:
        key = (
            ratio_text_value
            .casefold()
            .replace("i̇", "i")
        )

        if "ekspertiz" in key and "değiş" in key:
            return "Ekspertiz değeri ve koşullara göre"

        if "arazi" in key and "%" in ratio_text_value:
            return ratio_text_value

        if "ekspertiz" in key and "%" in ratio_text_value:
            return ratio_text_value

    return "Kaynakta sayısal tutar/oran yayımlanmamış"


def housing_installment_summary(
    product: pd.Series,
    product_id: int,
    category_rules: pd.DataFrame,
    offer_rules: pd.DataFrame,
    pricing_rules: pd.DataFrame,
) -> str:
    """
    Taksit sayısını yalnız kaynakta desteklenen yapıdan üretir.

    Öncelik:
      1) Açık max_installments
      2) Resmî fiyatlama tablosundaki aylık vade planları
      3) Yalnız vade varsa 'Vade süresine göre' ifadesi
    """
    explicit: set[int] = set()

    for frame in (category_rules, offer_rules):
        if frame.empty:
            continue

        subset = frame[
            frame["product_id"] == product_id
        ]

        if "max_installments" not in subset.columns:
            continue

        explicit.update(
            int(value)
            for value in subset["max_installments"].dropna()
            if float(value) > 0
        )

    if explicit:
        values = sorted(explicit)
        if len(values) == 1:
            return f"Azami {values[0]} taksit"
        return " / ".join(
            f"{value} taksit"
            for value in values
        )

    if not pricing_rules.empty:
        subset = pricing_rules[
            pricing_rules["product_id"] == product_id
        ]

        if (
            not subset.empty
            and "maturity_months" in subset.columns
        ):
            maturities = sorted(
                {
                    int(value)
                    for value in subset[
                        "maturity_months"
                    ].dropna()
                    if float(value) > 0
                }
            )

            if maturities:
                # pricing_tiers satırları aylık vade planlarıdır.
                if len(maturities) <= 6:
                    return " / ".join(
                        str(value)
                        for value in maturities
                    ) + " taksit"

                return (
                    f"{min(maturities)}–{max(maturities)} "
                    "taksit (plana göre)"
                )

    if has_value(
        product.get("maximum_maturity_months")
    ):
        return "Vade süresine göre"

    return "Kaynakta taksit sayısı yayımlanmamış"


def non_allocation_fee_summary_for_product(
    product_id: int,
    fee_rules: pd.DataFrame,
) -> str:
    """
    Tahsis ücretini tekrar etmeden diğer resmî masrafları özetler.
    """
    if fee_rules.empty:
        return "—"

    subset = fee_rules[
        fee_rules["product_id"] == product_id
    ].copy()

    if subset.empty:
        return "—"

    if "fee_type" in subset.columns:
        fee_type_key = (
            subset["fee_type"]
            .fillna("")
            .astype(str)
            .str.casefold()
        )
    else:
        fee_type_key = pd.Series(
            [""] * len(subset),
            index=subset.index,
        )

    if "fee_label" in subset.columns:
        fee_label_key = (
            subset["fee_label"]
            .fillna("")
            .astype(str)
            .str.casefold()
        )
    else:
        fee_label_key = pd.Series(
            [""] * len(subset),
            index=subset.index,
        )

    subset = subset[
        ~(
            fee_type_key.eq("allocation")
            | fee_label_key.str.contains(
                "tahsis",
                regex=False,
            )
        )
    ]

    if subset.empty:
        return "—"

    parts: list[str] = []

    for _, row in subset.iterrows():
        label = display_text(
            row.get("fee_label")
        )

        if label == "Belirtilmedi":
            label = "Masraf"

        waived = (
            int(row.get("waived") or 0) == 1
        )

        if waived:
            status = "Alınmıyor"
        elif has_value(row.get("rate")):
            status = rate_text(row.get("rate"))
        elif has_value(row.get("amount")):
            status = tr_money(row.get("amount"))
        else:
            note = str(row.get("note") or "").strip()
            status = note if note else "Var"

        item = f"{label}: {status}"
        if item not in parts:
            parts.append(item)

    return " · ".join(parts) if parts else "—"


def allocation_fee_text_for_product(
    product_id: int,
    fee_rules: pd.DataFrame,
    pricing_rules: pd.DataFrame,
    selected_maturity: int | None,
    selected_pricing_variant: str | None,
) -> str:
    """
    Ana karşılaştırma tablosu için yalnız tahsis ücretini döndürür.

    Öncelik:
      1) product_pricing_tiers.allocation_fee_rate
      2) product_fee_rules içindeki allocation/tahsis kaydı
    """
    pricing_subset = (
        pricing_rules[
            pricing_rules["product_id"] == product_id
        ].copy()
        if not pricing_rules.empty
        else pd.DataFrame()
    )

    if not pricing_subset.empty:
        if (
            selected_pricing_variant is not None
            and "pricing_variant" in pricing_subset.columns
        ):
            variant_rows = pricing_subset[
                pricing_subset["pricing_variant"]
                == selected_pricing_variant
            ]
            if not variant_rows.empty:
                pricing_subset = variant_rows

        if (
            selected_maturity is not None
            and "maturity_months" in pricing_subset.columns
        ):
            maturity_rows = pricing_subset[
                pricing_subset["maturity_months"]
                == selected_maturity
            ]
            if not maturity_rows.empty:
                pricing_subset = maturity_rows

        if "allocation_fee_rate" in pricing_subset.columns:
            rates = sorted(
                {
                    float(value)
                    for value in pricing_subset[
                        "allocation_fee_rate"
                    ].dropna()
                }
            )

            if len(rates) == 1:
                if math.isclose(rates[0], 0.0, abs_tol=1e-12):
                    return "Alınmıyor"
                return rate_text(rates[0])

            if len(rates) > 1:
                low = min(rates)
                high = max(rates)
                if math.isclose(low, high):
                    return rate_text(low)
                return (
                    f"%{format_number_tr(low)}–"
                    f"%{format_number_tr(high)}"
                )

    if not fee_rules.empty:
        subset = fee_rules[
            fee_rules["product_id"] == product_id
        ].copy()

        if not subset.empty:
            allocation_rows = pd.DataFrame()

            if "fee_type" in subset.columns:
                allocation_rows = subset[
                    subset["fee_type"]
                    .fillna("")
                    .astype(str)
                    .str.casefold()
                    == "allocation"
                ]

            if (
                allocation_rows.empty
                and "fee_label" in subset.columns
            ):
                allocation_rows = subset[
                    subset["fee_label"]
                    .fillna("")
                    .astype(str)
                    .str.casefold()
                    .str.contains("tahsis", regex=False)
                ]

            if not allocation_rows.empty:
                maximum_fee_evidence = " ".join(
                    allocation_rows.get(
                        "fee_label",
                        pd.Series(dtype=str),
                    ).fillna("").astype(str).tolist()
                    + allocation_rows.get(
                        "note",
                        pd.Series(dtype=str),
                    ).fillna("").astype(str).tolist()
                ).casefold()
                is_maximum_fee = (
                    "azami" in maximum_fee_evidence
                    or "maksimum" in maximum_fee_evidence
                )

                if (
                    "waived" in allocation_rows.columns
                    and allocation_rows["waived"]
                    .fillna(0)
                    .astype(int)
                    .eq(1)
                    .any()
                ):
                    return "Alınmıyor"

                if "rate" in allocation_rows.columns:
                    rates = sorted(
                        {
                            float(value)
                            for value in allocation_rows[
                                "rate"
                            ].dropna()
                        }
                    )
                    if len(rates) == 1:
                        if math.isclose(
                            rates[0],
                            0.0,
                            abs_tol=1e-12,
                        ):
                            return "Alınmıyor"
                        rendered = rate_text(rates[0])
                        return (
                            "Azami " + rendered
                            if is_maximum_fee
                            else rendered
                        )
                    if len(rates) > 1:
                        rendered = (
                            f"%{format_number_tr(min(rates))}–"
                            f"%{format_number_tr(max(rates))}"
                        )
                        return (
                            "Azami " + rendered
                            if is_maximum_fee
                            else rendered
                        )

                if "amount" in allocation_rows.columns:
                    amounts = sorted(
                        {
                            float(value)
                            for value in allocation_rows[
                                "amount"
                            ].dropna()
                        }
                    )
                    if len(amounts) == 1:
                        if math.isclose(
                            amounts[0],
                            0.0,
                            abs_tol=1e-12,
                        ):
                            return "Alınmıyor"
                        return tr_money(amounts[0])
                    if len(amounts) > 1:
                        return (
                            f"{tr_money(min(amounts))}–"
                            f"{tr_money(max(amounts))}"
                        )

    return "—"


def fee_summary_for_product(
    product_id: int,
    fee_rules: pd.DataFrame,
    pricing_rules: pd.DataFrame,
    selected_maturity: int | None,
    selected_pricing_variant: str | None,
) -> str:
    labels: list[str] = []

    pricing_subset = (
        pricing_rules[
            pricing_rules["product_id"] == product_id
        ].copy()
        if not pricing_rules.empty
        else pd.DataFrame()
    )

    if not pricing_subset.empty:
        if (
            selected_pricing_variant is not None
            and "pricing_variant"
            in pricing_subset.columns
        ):
            variant_rows = pricing_subset[
                pricing_subset["pricing_variant"]
                == selected_pricing_variant
            ]

            if not variant_rows.empty:
                pricing_subset = variant_rows

        if selected_maturity is not None:
            exact = pricing_subset[
                pricing_subset["maturity_months"]
                == selected_maturity
            ]

            if not exact.empty:
                pricing_subset = exact

        allocation_rates = sorted(
            {
                float(value)
                for value in pricing_subset[
                    "allocation_fee_rate"
                ].dropna()
            }
        )

        if len(allocation_rates) == 1:
            labels.append(
                "Tahsis Ücreti: "
                + rate_text(allocation_rates[0])
            )
        elif len(allocation_rates) > 1:
            labels.append(
                "Tahsis Ücreti: "
                f"%{format_number_tr(min(allocation_rates))}"
                "–"
                f"%{format_number_tr(max(allocation_rates))}"
            )

    if not fee_rules.empty:
        subset = fee_rules[
            fee_rules["product_id"] == product_id
        ]

        for _, row in subset.iterrows():
            fee_type = str(
                row.get("fee_type") or ""
            ).strip()

            if (
                fee_type == "allocation"
                and any(
                    item.startswith(
                        "Tahsis Ücreti:"
                    )
                    for item in labels
                )
            ):
                continue

            label = display_text(
                row.get("fee_label")
            )

            if int(row.get("waived", 0)) == 1:
                status = "Alınmıyor"
            elif has_value(row.get("rate")):
                status = rate_text(
                    row.get("rate")
                )
            elif has_value(row.get("amount")):
                status = tr_money(
                    row.get("amount")
                )
            else:
                status = "Var"

            item = f"{label}: {status}"

            if item not in labels:
                labels.append(item)

    return (
        " · ".join(labels)
        if labels
        else "Kaynakta yayımlanmamış"
    )



def pricing_rows_for_product(
    product_id: int,
    pricing_rules: pd.DataFrame,
    selected_pricing_variant: str | None = None,
) -> pd.DataFrame:
    if pricing_rules.empty:
        return pd.DataFrame()

    subset = pricing_rules[
        pricing_rules["product_id"] == product_id
    ].copy()

    if (
        selected_pricing_variant is not None
        and not subset.empty
        and "pricing_variant" in subset.columns
    ):
        selected_rows = subset[
            subset["pricing_variant"]
            == selected_pricing_variant
        ]
        if not selected_rows.empty:
            subset = selected_rows

    return subset


def vehicle_value_rule_summary_text(product: pd.Series) -> str:
    """Araç değer → oran → azami vade kurallarını doğrudan doğrulanmış
    vehicle_finance_rules_text üzerinden üretir. Varsayılan araç değeri veya
    generic amount rule bu ana özeti değiştiremez.
    """
    rules = parse_vehicle_rules_text(product.get("vehicle_finance_rules_text"))
    if not rules:
        return ""
    parts: list[str] = []
    for rule in rules:
        band = vehicle_band_text(rule)
        if rule.get("blocked"):
            item = f"{band} → kullandırım yok"
        else:
            outcomes: list[str] = []
            if rule.get("ratio") is not None:
                outcomes.append(f"Azami %{format_number_tr(rule.get('ratio'))}")
            if rule.get("max_maturity_months") is not None:
                outcomes.append(f"{int(rule.get('max_maturity_months'))} ay")
            if not outcomes:
                continue
            item = f"{band} → " + " · ".join(outcomes)
        if item not in parts:
            parts.append(item)
    return " · ".join(parts)


def vehicle_financing_ratio_summary_text(product: pd.Series) -> str:
    rules = [r for r in parse_vehicle_rules_text(product.get("vehicle_finance_rules_text")) if not r.get("blocked") and r.get("ratio") is not None]
    if rules:
        rates = sorted({float(r["ratio"]) for r in rules})
        if len(rates) == 1:
            return f"Azami %{format_number_tr(rates[0])}"
        return f"Değer bandına göre %{format_number_tr(min(rates))}–%{format_number_tr(max(rates))}"
    if has_value(product.get("maximum_financing_ratio")):
        return "Azami %" + format_number_tr(product.get("maximum_financing_ratio"))
    return "Belirtilmedi"


def vehicle_pricing_maturity_text(
    product: pd.Series,
    pricing_rules: pd.DataFrame,
    selected_pricing_variant: str | None = None,
) -> str:
    """Araç ana tablosunda azami vade, fiyatlama örneğinden değil
    öncelikle araç değer/yaş kuralından gelir. Fiyatlama tablosu yalnız araç
    değer bandı yayımlanmamışsa fallback olabilir.
    """
    vehicle_rule_text = product.get("vehicle_finance_rules_text")
    if has_value(vehicle_rule_text):
        vehicle_maturities = sorted(
            {
                int(rule["max_maturity_months"])
                for rule in parse_vehicle_rules_text(vehicle_rule_text)
                if rule.get("max_maturity_months") is not None and not rule.get("blocked")
            },
            reverse=True,
        )
        if vehicle_maturities:
            return " · ".join(str(value) for value in vehicle_maturities) + " ay"

    product_id = int(product["id"])
    subset = pricing_rows_for_product(product_id, pricing_rules, selected_pricing_variant)
    if not subset.empty and "maturity_months" in subset.columns:
        maturities = sorted({int(value) for value in subset["maturity_months"].dropna()}, reverse=True)
        if maturities:
            return " · ".join(str(value) for value in maturities) + " ay"

    if has_value(product.get("maximum_maturity_months")):
        return f"Azami {int(product.get('maximum_maturity_months'))} ay"
    return "Kaynakta sayısal değer yayımlanmamış"

def vehicle_profit_summary_text(
    product: pd.Series,
    pricing_rules: pd.DataFrame,
    selected_maturity: int | None,
    selected_pricing_variant: str | None,
) -> str:
    """
    Araç finansmanında çok boyutlu fiyatlama varsa yüzdeleri
    tek bir min-max aralığına sıkıştırmaz.

    Örn. Sigortalı/Sigortasız + 0 km/2.El + vade kombinasyonları.
    """
    product_id = int(product["id"])
    subset = pricing_rows_for_product(
        product_id,
        pricing_rules,
        selected_pricing_variant,
    )

    if selected_maturity is not None and not subset.empty:
        exact = subset[
            subset["maturity_months"]
            == selected_maturity
        ]
        if not exact.empty:
            subset = exact

    if not subset.empty and "value_type" in subset.columns:
        bank_name = str(product.get("bank_name") or "").strip()
        product_name = str(product.get("product_name") or "").strip().casefold()
        if (
            bank_name == "Türkiye Finans"
            and subset["value_type"].dropna().astype(str).eq("conditional_pricing").all()
        ):
            return "Koşullu fiyatlama tablosu · tutar/vade/ürün koşullarına göre"
        if bank_name == "Albaraka Türk" and "togg" in product_name:
            return "Model/tutar/vadeye göre fiyatlama"

    if not subset.empty:
        rates = sorted(
            {
                float(value)
                for value in subset[
                    "profit_share_rate"
                ].dropna()
            }
        )

        variants = []
        if "pricing_variant" in subset.columns:
            variants = (
                subset["pricing_variant"]
                .dropna()
                .astype(str)
                .loc[
                    lambda s: s.str.strip().ne("")
                ]
                .drop_duplicates()
                .tolist()
            )

        # Tek bir açık oran varsa doğrudan göster.
        if len(rates) == 1:
            return rate_text(rates[0])

        # Birden fazla fiyatlama varyantı/rate varsa bunun tek bir
        # "oran aralığı" olmadığını açıkça ifade et.
        if len(rates) > 1:
            variant_key = " ".join(
                _vehicle_text_key(value)
                for value in variants
            )

            has_vehicle_or_insurance_dimension = bool(
                re.search(
                    r"\b0\s*km\b"
                    r"|\b2\s*\.?\s*el\b"
                    r"|\bikinci\s+el\b"
                    r"|\bsigortali\b"
                    r"|\bsigortasiz\b",
                    variant_key,
                )
            )

            if has_vehicle_or_insurance_dimension:
                return (
                    "Vade/araç/sigorta seçeneğine "
                    "göre değişir"
                )

            return (
                "Vade/fiyatlama seçeneğine göre değişir"
            )

    # Pricing tier yoksa mevcut genel ürün mantığına dön.
    return profit_text_for_product(
        product,
        pricing_rules,
        selected_maturity,
        selected_pricing_variant,
    )


def housing_profit_summary_text(
    product: pd.Series,
    pricing_rules: pd.DataFrame,
    selected_maturity: int | None,
    selected_pricing_variant: str | None,
) -> str:
    """Konut ana tablosunda fiyatlama matrisini tek yüzde/aralığa ezmez."""
    product_id = int(product["id"])
    subset = (
        pricing_rules[
            pricing_rules["product_id"] == product_id
        ].copy()
        if not pricing_rules.empty
        else pd.DataFrame()
    )

    if not subset.empty:
        if (
            selected_pricing_variant is not None
            and "pricing_variant" in subset.columns
        ):
            exact_variant = subset[
                subset["pricing_variant"] == selected_pricing_variant
            ]
            if not exact_variant.empty:
                subset = exact_variant

        if selected_maturity is not None and "maturity_months" in subset.columns:
            exact_maturity = subset[
                subset["maturity_months"] == selected_maturity
            ]
            if not exact_maturity.empty:
                rates = sorted(
                    {
                        float(value)
                        for value in exact_maturity[
                            "profit_share_rate"
                        ].dropna()
                    }
                )
                if len(rates) == 1:
                    return rate_text(rates[0])
                if len(rates) > 1:
                    return "Konut/sigorta seçeneğine göre değişir"

        rates = sorted(
            {
                float(value)
                for value in subset["profit_share_rate"].dropna()
            }
        ) if "profit_share_rate" in subset.columns else []

        variants = []
        if "pricing_variant" in subset.columns:
            variants = (
                subset["pricing_variant"]
                .dropna()
                .astype(str)
                .loc[lambda s: s.str.strip().ne("")]
                .drop_duplicates()
                .tolist()
            )

        variant_key = " ".join(
            str(value).casefold()
            for value in variants
        )
        if len(variants) > 1 or any(
            token in variant_key
            for token in (
                "ilk konut",
                "mevcut konut",
                "sigortalı",
                "sigortasız",
                "sigortali",
                "sigortasiz",
            )
        ):
            return "Vade/sigorta/konut durumuna göre değişir"

        has_amount_specific_pricing = (
            "financing_amount" in subset.columns
            and subset["financing_amount"].notna().any()
        )
        if has_amount_specific_pricing and len(rates) == 1:
            return f"Örnek fiyatlama: {rate_text(rates[0])}"

        maturities = (
            subset["maturity_months"].dropna().nunique()
            if "maturity_months" in subset.columns
            else 0
        )
        if len(rates) > 1 and maturities > 1:
            return "Vadeye göre değişir"
        if len(rates) == 1:
            return rate_text(rates[0])

    return profit_text_for_product(
        product,
        pricing_rules,
        selected_maturity,
        selected_pricing_variant,
    )



def _housing_pricing_subset(
    product_id: int,
    pricing_rules: pd.DataFrame,
) -> pd.DataFrame:
    if pricing_rules.empty:
        return pd.DataFrame()
    subset = pricing_rules[
        pricing_rules["product_id"] == product_id
    ].copy()
    return subset


def is_dashboard_placeholder(value: object) -> bool:
    if value is None:
        return True

    try:
        if pd.isna(value):
            return True
    except Exception:
        pass

    text = str(value).strip()

    if not text:
        return True

    key = text.casefold()

    exact_placeholders = {
        "none",
        "nan",
        "belirtilmedi",
        "kaynakta yayımlanmamış",
        "kaynakta sayısal değer yayımlanmamış",
        "—",
        "-",
    }

    if key in exact_placeholders:
        return True

    if key.startswith(
        "sayısal koşullar kaynakta yayımlanmamış"
    ):
        return True

    return False


def housing_comparison_profit_text(
    product: pd.Series,
    pricing_rules: pd.DataFrame,
) -> str:
    """
    Konut ana karşılaştırma tablosu için kısa ve karşılaştırılabilir
    fiyatlama özeti.

    - Çoklu fiyatlama satırları tek bir "dinamik" metnine ezilmez.
    - Örnek maliyet tablosu genel ürün oranı gibi sunulmaz.
    - Sayısal fiyatlama yoksa uydurma oran üretilmez.
    """
    product_id = int(product["id"])
    subset = _housing_pricing_subset(
        product_id,
        pricing_rules,
    )

    if not subset.empty and "profit_share_rate" in subset.columns:
        rates = sorted(
            {
                float(value)
                for value in subset[
                    "profit_share_rate"
                ].dropna()
            }
        )

        variants: list[str] = []
        if "pricing_variant" in subset.columns:
            variants = (
                subset["pricing_variant"]
                .dropna()
                .astype(str)
                .loc[lambda s: s.str.strip().ne("")]
                .drop_duplicates()
                .tolist()
            )

        variant_key = " ".join(
            value.casefold()
            for value in variants
        )

        # Türkiye Finans güncel resmî konut tablosunda fiyatlama sigorta
        # durumuna ve vadeye göre ayrı yayımlanır. Tek bir geniş aralık
        # kullanıcıya koşulları gizlediği için sigortalı/sigortasız
        # aralıkları ana tabloda ayrı gösterilir.
        bank_name = str(product.get("bank_name") or "").strip()
        product_name = str(product.get("product_name") or "").strip().rstrip("*").strip()
        if (
            bank_name == "Türkiye Finans"
            and product_name == "Konut Finansmanı (Konut Kredisi)"
            and "pricing_variant" in subset.columns
        ):
            variant_series = (
                subset["pricing_variant"]
                .fillna("")
                .astype(str)
                .str.casefold()
            )

            def _variant_rate_range(marker: str) -> str | None:
                values = sorted(
                    {
                        float(value)
                        for value in subset.loc[
                            variant_series.str.contains(marker, regex=False),
                            "profit_share_rate",
                        ].dropna()
                    }
                )
                if not values:
                    return None
                if len(values) == 1:
                    return rate_text(values[0])
                return rate_text(min(values)) + "–" + rate_text(max(values))

            insured = _variant_rate_range("sigortalı")
            uninsured = _variant_rate_range("sigortasız")
            if insured and uninsured:
                return "Koşullu fiyatlama tablosu · Sigortalı/Sigortasız ve vadeye göre"

        sample_only = bool(variants) and all(
            any(
                token in value.casefold()
                for token in (
                    "örnek",
                    "ornek",
                    "sample",
                )
            )
            for value in variants
        )

        if len(rates) == 1:
            value = rate_text(rates[0])
            if sample_only:
                amount_label = ""
                if (
                    "financing_amount" in subset.columns
                    and subset["financing_amount"].notna().any()
                ):
                    amounts = sorted(
                        {
                            float(v)
                            for v in subset[
                                "financing_amount"
                            ].dropna()
                        }
                    )
                    if len(amounts) == 1:
                        amount_label = (
                            " · "
                            + tr_money(amounts[0])
                            + " örnek"
                        )
                return value + amount_label
            return value

        if len(rates) > 1:
            rate_range = (
                rate_text(min(rates))
                + "–"
                + rate_text(max(rates))
            )
            dimensions: list[str] = []
            if (
                "sigortalı" in variant_key
                or "sigortali" in variant_key
                or "sigortasız" in variant_key
                or "sigortasiz" in variant_key
            ):
                dimensions.append("sigorta")
            if (
                "ilk konut" in variant_key
                or "mevcut konut" in variant_key
            ):
                dimensions.append("konut")
            if (
                "maturity_months" in subset.columns
                and subset["maturity_months"].dropna().nunique() > 1
            ):
                dimensions.insert(0, "vade")

            if dimensions:
                return (
                    rate_range
                    + " · "
                    + "/".join(dimensions)
                )
            return rate_range

    # Ürün kolonunda açık tek oran varsa göster.
    if has_value(product.get("profit_share_rate")):
        return rate_text(
            product.get("profit_share_rate")
        )

    rate_text_value = str(
        product.get("profit_share_rate_text") or ""
    ).strip()

    if (
        rate_text_value
        and not is_dashboard_placeholder(
            rate_text_value
        )
    ):
        rate_key = (
            rate_text_value.casefold()
            .replace("\u0131", "i")
            .replace("\u0130", "i")
        )

        # Resmi kaynaktan dogrulanmis urune ozgu
        # fiyatlama/indirim bilgisi uzun oldugu icin
        # generic placeholder'a ezilmemeli.
        verified_qualitative = (
            "2 puan indirim" in rate_key
            or (
                "sifir" in rate_key
                and "guncel piyasa" in rate_key
            )
            or (
                "daha uygun" in rate_key
                and "guncel piyasa" in rate_key
            )
        )

        if verified_qualitative:
            return rate_text_value

        if len(rate_text_value) <= 45:
            return rate_text_value

    return "Hesaplama arac\u0131nda belirlenir"


def _housing_ratio_values(
    rules: dict,
) -> tuple[list[float], bool, bool]:
    values: list[float] = []

    standard = list(
        rules.get("standard_home") or []
    )
    additional = list(
        rules.get("additional_home") or []
    )

    for row in standard + additional:
        for key in ("ab", "c", "other"):
            value = row.get(key)
            if value is not None:
                values.append(float(value))

    return values, bool(standard), bool(additional)


def housing_comparison_ratio_text(
    product: pd.Series,
) -> str:
    """
    Finansman oranını tek bir yüzdeye indirgemeden kısa özetler.
    """
    if has_value(
        product.get("maximum_financing_ratio")
    ):
        ratio = float(
            product.get("maximum_financing_ratio")
        )
        rules_text = (
            str(
                product.get(
                    "financing_ratio_rules_text"
                )
                or ""
            )
            .casefold()
            .replace("i̇", "i")
        )
        if "ekspertiz" in rules_text:
            return (
                rate_text(ratio)
                + " · ekspertiz"
            )
        if "arazi" in rules_text:
            return (
                rate_text(ratio)
                + " · arazi değeri"
            )
        return rate_text(ratio)

    rules = parse_housing_rules_json(
        product.get(
            "housing_finance_rules_json"
        )
    )
    values, has_standard, has_additional = (
        _housing_ratio_values(rules)
    )

    if values:
        low = min(values)
        high = max(values)
        range_text = (
            rate_text(low)
            if math.isclose(
                low,
                high,
                abs_tol=1e-12,
            )
            else (
                rate_text(low)
                + "–"
                + rate_text(high)
            )
        )

        if has_standard and has_additional:
            return (
                range_text
                + " · ekspertiz/enerji/konut"
            )
        if has_standard:
            return (
                range_text
                + " · ilk konut"
            )
        if has_additional:
            return (
                range_text
                + " · mevcut konut"
            )
        return range_text

    rule_text = str(
        product.get(
            "financing_ratio_rules_text"
        )
        or ""
    ).strip()
    if rule_text:
        key = (
            rule_text.casefold()
            .replace("i̇", "i")
        )
        if (
            "ekspertiz" in key
            or "enerji" in key
            or "konut" in key
        ):
            return "Koşullara göre · detayda"

    return "Kaynakta doğrulanmadı"


def housing_comparison_maturity_text(
    product: pd.Series,
) -> str:
    max_maturity = product.get(
        "maximum_maturity_months"
    )

    rules_text = str(
        product.get("maturity_rules_text") or ""
    ).strip()

    if (
        rules_text
        and not is_dashboard_placeholder(
            rules_text
        )
    ):
        rules_key = (
            rules_text.casefold()
            .replace("\u0131", "i")
            .replace("\u0130", "i")
        )

        # Para birimine gore farkli vadeler varsa tek
        # bir azami deger eksik bilgi verebilir.
        if (
            "usd" in rules_key
            or "eur" in rules_key
            or not has_value(max_maturity)
        ):
            return rules_text

    if has_value(max_maturity):
        return (
            f"{int(max_maturity)} ay"
        )

    return "Kaynakta do\u011frulanmad\u0131"


def _fee_rows_for_type(
    product_id: int,
    fee_rules: pd.DataFrame,
    fee_type: str,
) -> pd.DataFrame:
    if fee_rules.empty:
        return pd.DataFrame()

    subset = fee_rules[
        fee_rules["product_id"] == product_id
    ].copy()
    if subset.empty or "fee_type" not in subset.columns:
        return pd.DataFrame()

    return subset[
        subset["fee_type"]
        .fillna("")
        .astype(str)
        .str.casefold()
        == fee_type.casefold()
    ].copy()


def fee_source_url_for_product(
    product_id: int,
    fee_rules: pd.DataFrame,
) -> str | None:
    """
    Konut masraflarının geldiği ayrı resmî ücret kaynağını bulur.

    Ürün sayfası ile ücret tarifesi aynı şey değildir. Notlarda birden
    fazla URL varsa ücret tablosu/PDF olanı tercih edilir.
    """
    if fee_rules.empty:
        return None

    subset = fee_rules[
        fee_rules["product_id"] == product_id
    ].copy()
    if subset.empty or "note" not in subset.columns:
        return None

    urls: list[str] = []
    for raw_note in subset["note"].fillna("").astype(str):
        for url in re.findall(r"https?://[^\s|]+", raw_note):
            cleaned = url.rstrip(".,);]")
            if cleaned not in urls:
                urls.append(cleaned)

    if not urls:
        return None

    for url in urls:
        key = url.casefold()
        if (
            ".pdf" in key
            or "ucret" in key
            or "ücret" in key
            or "urun-ve-hizmet" in key
            or "urun_hizmet" in key
        ):
            return url

    return urls[0]


def first_rule_source_url(
    rules: pd.DataFrame | None,
    product_id: int,
) -> str | None:
    """
    Bir ürün için ilk doğrulanmış kural kaynağını güvenli biçimde döndürür.

    Eski/karışık şemalarda aynı isimli ``source_url`` sütunu birden fazla kez
    bulunabilir. Bu yardımcı Series varsayımı yapmaz; tüm eşleşen kaynak
    sütunlarını tarar ve AttributeError üretmez.
    """
    if rules is None or rules.empty or "product_id" not in rules.columns:
        return None

    subset = rules.loc[rules["product_id"] == product_id]
    if subset.empty:
        return None

    for column_name in ("source_url", "product_source_url"):
        matching_positions = [
            index
            for index, name in enumerate(subset.columns)
            if name == column_name
        ]
        for position in matching_positions:
            series = subset.iloc[:, position]
            for raw in series.tolist():
                if pd.isna(raw):
                    continue
                value = str(raw).strip()
                if value:
                    return value

    return None


def housing_fee_comparison_text(
    product_id: int,
    fee_rules: pd.DataFrame,
    fee_type: str,
) -> str:
    """
    Belirli bir masraf kalemini gösterir.

    Kritik kural:
    "Alınmıyor" yalnız o MASRAF KALEMİNİN resmî kaydında waived=True
    ise yazılır. Genel/generic bir expense kaydı başka masrafı sıfırlamaz.
    """
    subset = _fee_rows_for_type(
        product_id,
        fee_rules,
        fee_type,
    )
    if subset.empty:
        return "Kaynakta doğrulanmadı"

    row = subset.iloc[0]
    waived = bool(row.get("waived") or False)
    if waived:
        return "Alınmıyor"

    note = str(row.get("note") or "").strip()
    note_key = (
        note.casefold()
        .replace("i̇", "i")
    )

    if has_value(row.get("rate")):
        value = rate_text(
            row.get("rate")
        )
        if "azami" in note_key or "maksimum" in note_key:
            return "Azami " + value
        return value

    if has_value(row.get("amount")):
        value = tr_money(
            row.get("amount")
        )

        # Kuveyt Türk'te 2026-08 itibarıyla iki resmî kaynak farklı
        # ekspertiz tutarı yayımlıyor: ürün sayfaları 23.203 TL, ayrı
        # ücret tarifesi 23.645 TL. Tek birini kesin ürün ücreti gibi
        # göstermek yerine kaynak farkını müşteriye açıkça göster.
        if (
            fee_type.casefold() == "appraisal"
            and "23.203" in note
            and "23.645" in note
            and "resmî kaynaklar birbiriyle farklı" in note_key
        ):
            return (
                "Ürün sayfası: asgari 23.203 TL · "
                "Ücret tarifesi: asgari 23.645 TL"
            )

        # Kuveyt Türk ürün sayfası ipotek için sayısal tutar vermiyor;
        # genel ücret tarifesi ise 4.500 TL asgari tutar yayımlıyor.
        # 4.500 TL'yi ürün sayfasının sabit ücreti gibi sunma.
        if (
            fee_type.casefold() == "mortgage_establishment"
            and "4.500" in note
            and "sayısal bir ipotek tesis tutarı yayımlamaz" in note_key
        ):
            return (
                "Ürün sayfası: maliyet kadar · "
                "Ücret tarifesi: asgari 4.500 TL"
            )

        if "örnek" in note_key or "ornek" in note_key:
            value = "Örnek " + value
        elif "asgari" in note_key or "minimum" in note_key:
            value = "Asgari " + value

        if (
            "değiş" in note_key
            or "degis" in note_key
            or "lokasyon" in note_key
            or "brüt alan" in note_key
            or "brut alan" in note_key
        ):
            value += " · değişken"
        elif (
            "hesaplama aracı" in note_key
            or "hesaplama araci" in note_key
        ):
            value += " · hesaplama örneği"

        # Dünya Katılım gibi ücretin ürün sayfasında değil ayrı resmî
        # ücret tarifesinde yayımlandığı durumlarda kaynak türünü hücrede
        # de belirt; kullanıcı Ürün Kaynağı'na tıklayınca rakamı aramasın.
        if "ürün sayfasında bu sayısal ücret yayımlanmıyor" in note_key:
            value += " · ücret tarifesi"

        return value

    if (
        "gerçek maliyet" in note_key
        or "gercek maliyet" in note_key
        or "3. kişilere ödenen" in note_key
        or "3. kisilere odenen" in note_key
        or "maliyet kadar" in note_key
    ):
        return "Gerçek maliyet"

    return "Detayda belirtilmiş"


def housing_fee_detail_rows(
    product_id: int,
    fee_rules: pd.DataFrame,
) -> list[dict[str, str]]:
    if fee_rules.empty:
        return []

    subset = fee_rules[
        fee_rules["product_id"] == product_id
    ].copy()
    if subset.empty:
        return []

    preferred_order = {
        "allocation": 0,
        "appraisal": 1,
        "mortgage_establishment": 2,
        "mortgage_release": 3,
    }

    rows: list[dict[str, str]] = []
    for _, row in subset.iterrows():
        fee_type = str(
            row.get("fee_type") or ""
        )
        label = str(
            row.get("fee_label") or fee_type
        ).strip()

        value = housing_fee_comparison_text(
            product_id,
            fee_rules,
            fee_type,
        )

        note = str(
            row.get("note") or ""
        ).strip()

        rows.append(
            {
                "_order": preferred_order.get(
                    fee_type,
                    99,
                ),
                "Masraf Kalemi": label,
                "Değer": value,
                "Açıklama": note if note else "—",
            }
        )

    rows.sort(
        key=lambda item: (
            item["_order"],
            item["Masraf Kalemi"],
        )
    )
    for row in rows:
        row.pop("_order", None)
    return rows


def housing_offer_detail_rows(
    product_id: int,
    offer_rules: pd.DataFrame,
) -> list[dict[str, str]]:
    if offer_rules.empty:
        return []

    subset = offer_rules[
        offer_rules["product_id"] == product_id
    ].copy()

    rows: list[dict[str, str]] = []
    for _, row in subset.iterrows():
        label = str(
            row.get("rule_label") or ""
        ).strip()
        condition = str(
            row.get("condition_text") or ""
        ).strip()
        if not label or not condition:
            continue
        rows.append(
            {
                "Koşul": label,
                "Açıklama": condition,
            }
        )
    return rows



def profit_text_for_product(
    product: pd.Series,
    pricing_rules: pd.DataFrame,
    selected_maturity: int | None,
    selected_pricing_variant: str | None,
) -> str:
    product_id = int(product["id"])

    subset = (
        pricing_rules[
            pricing_rules["product_id"] == product_id
        ]
        if not pricing_rules.empty
        else pd.DataFrame()
    )

    # Türkiye Finans'ın birçok ürününde yayımlanan oranlar tek bir
    # "güncel genel oran" değil; tutar/vade/sigorta/ek ürün koşullu resmi
    # fiyatlama tablolarıdır. Ana tabloda çıplak yüzde aralığına ezmeyiz.
    if (
        str(product.get("bank_name") or "").strip() == "Türkiye Finans"
        and not subset.empty
        and "value_type" in subset.columns
        and subset["value_type"].dropna().astype(str).eq("conditional_pricing").all()
    ):
        condition_values = []
        if "conditions" in subset.columns:
            condition_values = (
                subset["conditions"].dropna().astype(str)
                .loc[lambda x: x.str.strip().ne("")]
                .drop_duplicates().tolist()
            )
        product_name_key = str(product.get("product_name") or "").casefold()
        if "dijital ihtiyaç" in product_name_key:
            return "Koşullu fiyatlama tablosu · vade/KKB skoruna göre"
        if "ihtiyaç finansmanı" in product_name_key:
            variant_parts = []
            if "pricing_variant" in subset.columns:
                for label in ("Sigortalı", "Sigortasız"):
                    group = subset[subset["pricing_variant"].astype(str).str.casefold() == label.casefold()]
                    rates = sorted({float(v) for v in group["profit_share_rate"].dropna()}) if not group.empty else []
                    if rates:
                        if math.isclose(min(rates), max(rates)):
                            variant_parts.append(f"{label} {rate_text(min(rates))}")
                        else:
                            variant_parts.append(f"{label} %{format_number_tr(min(rates))}–%{format_number_tr(max(rates))}")
            if variant_parts:
                return " · ".join(variant_parts) + " · vade/KKB'ye göre"
            return "Koşullu fiyatlama tablosu · Sigortalı/Sigortasız ve vade/KKB'ye göre"
        if "trendyol" in product_name_key:
            return "Koşullu fiyatlama tablosu · limit/sigorta koşuluna göre"
        return "Koşullu fiyatlama tablosu · sigorta/ürün/vade koşullarına göre"

    if (
        selected_pricing_variant is not None
        and not subset.empty
        and "pricing_variant" in subset.columns
    ):
        variant_subset = subset[
            subset["pricing_variant"]
            == selected_pricing_variant
        ]
        if not variant_subset.empty:
            subset = variant_subset
        elif subset["pricing_variant"].nunique() > 1:
            return "Kaynakta sayısal değer yayımlanmamış"

    if selected_maturity is not None and not subset.empty:
        exact = subset[
            subset["maturity_months"]
            == selected_maturity
        ]
        if not exact.empty:
            value = exact.iloc[0].get(
                "profit_share_rate"
            )
            if has_value(value):
                return rate_text(value)

    # Tek bir fiyatlama varyantında vade bazlı oran tablosu varsa
    # aralığa sıkıştırmak yerine tüm resmî satırları görünür tut.
    # Örn. eXtra Limit: 3 ay %4,29 · 12 ay %4,19 · 24 ay %4,14 · 36 ay %4,09.
    if selected_maturity is None and not subset.empty:
        variant_count = (
            subset["pricing_variant"].dropna().nunique()
            if "pricing_variant" in subset.columns
            else 0
        )
        if variant_count <= 1 and "maturity_months" in subset.columns:
            schedule_rows = subset.dropna(
                subset=["maturity_months", "profit_share_rate"]
            ).copy()
            if not schedule_rows.empty:
                schedule_rows = schedule_rows.sort_values("maturity_months")
                per_maturity = []
                valid = True
                for maturity, group in schedule_rows.groupby("maturity_months"):
                    unique_rates = sorted(
                        {float(v) for v in group["profit_share_rate"].dropna()}
                    )
                    if len(unique_rates) != 1:
                        valid = False
                        break
                    per_maturity.append(
                        f"{int(maturity)} ay: {rate_text(unique_rates[0])}"
                    )
                if valid and len(per_maturity) > 1:
                    return " · ".join(per_maturity)

    rates = (
        subset["profit_share_rate"]
        .dropna()
        .astype(float)
        .tolist()
        if not subset.empty
        else []
    )

    if rates:
        low = min(rates)
        high = max(rates)
        if math.isclose(low, high):
            return rate_text(low)
        return (
            f"%{format_number_tr(low)}–"
            f"%{format_number_tr(high)}"
        )

    if has_value(product.get("profit_share_rate_text")):
        return display_text(
            product.get("profit_share_rate_text")
        )

    if has_value(product.get("profit_share_rate")):
        return rate_text(
            product.get("profit_share_rate")
        )

    if (
        product.get("interest_free") is True
        or product.get("interest_free") == 1
    ):
        return "Vade farksız"

    return "Kaynakta sayısal değer yayımlanmamış"


def matching_rows_by_amount(
    frame: pd.DataFrame,
    product_id: int,
    amount: float,
) -> list[pd.Series]:
    if frame.empty:
        return []

    subset = frame[
        frame["product_id"] == product_id
    ]

    matches: list[pd.Series] = []

    for _, row in subset.iterrows():
        if amount_matches(
            amount=amount,
            min_amount=(
                None
                if pd.isna(row.get("min_amount"))
                else float(row.get("min_amount"))
            ),
            max_amount=(
                None
                if pd.isna(row.get("max_amount"))
                else float(row.get("max_amount"))
            ),
            min_inclusive=bool(
                row.get("min_inclusive")
            ),
            max_inclusive=bool(
                row.get("max_inclusive")
            ),
        ):
            matches.append(row)

    return matches


def rule_result_text(
    product: pd.Series,
    category_matches: list[pd.Series],
    offer_matches: list[pd.Series],
    amount_matches_rows: list[pd.Series],
) -> tuple[str, str]:
    installment_caps: list[int] = []
    month_caps: list[int] = []

    # Aynı kuralın açıkça hem taksit hem ay verdiği durumları
    # ayrıca izliyoruz. Örn. "3 ay / 3 taksit".
    paired_month_caps: list[int] = []

    condition_parts: list[str] = []

    for row in category_matches:
        has_installment = has_value(
            row.get("max_installments")
        )
        has_month = has_value(
            row.get("max_maturity_months")
        )

        if has_installment:
            installment_caps.append(
                int(row.get("max_installments"))
            )

        if has_month:
            value = int(
                row.get("max_maturity_months")
            )
            month_caps.append(value)

            if has_installment:
                paired_month_caps.append(value)

        label = display_text(
            row.get("category_label")
        )
        condition = display_text(
            row.get("condition_text")
        )

        if condition != "Belirtilmedi":
            condition_parts.append(
                f"{label}: {condition}"
            )

    for row in offer_matches:
        has_installment = has_value(
            row.get("max_installments")
        )
        has_month = has_value(
            row.get("max_maturity_months")
        )

        if has_installment:
            installment_caps.append(
                int(row.get("max_installments"))
            )

        if has_month:
            value = int(
                row.get("max_maturity_months")
            )
            month_caps.append(value)

            if has_installment:
                paired_month_caps.append(value)

        condition = display_text(
            row.get("condition_text")
        )

        if condition != "Belirtilmedi":
            condition_parts.append(condition)

    for row in amount_matches_rows:
        if has_value(
            row.get("max_maturity_months")
        ):
            month_caps.append(
                int(row.get("max_maturity_months"))
            )

            condition_parts.append(
                f"{amount_band(row)} → "
                f"azami "
                f"{int(row.get('max_maturity_months'))} ay"
            )

    # Genel ürün vadesi yalnız seçime özgü hiçbir
    # taksit/vade sınırı yoksa fallback olarak kullanılır.
    #
    # Örn. Cep Telefonu >20.000 TL → 3 taksit
    # için ürünün genel "36 ay" vadesi eklenmez.
    if (
        not month_caps
        and not installment_caps
        and has_value(
            product.get("maximum_maturity_months")
        )
    ):
        month_caps.append(
            int(
                product.get(
                    "maximum_maturity_months"
                )
            )
        )

    installment = (
        min(installment_caps)
        if installment_caps
        else None
    )

    if installment is not None:
        # Taksit sınırı varsa yalnız AYNI kuralda açıkça
        # belirtilen vade bilgisini yanında göster.
        months = (
            min(paired_month_caps)
            if paired_month_caps
            else None
        )
    else:
        months = (
            min(month_caps)
            if month_caps
            else None
        )

    limits = []

    if installment is not None:
        limits.append(
            f"{installment} taksit"
        )

    if months is not None:
        limits.append(
            f"{months} ay"
        )

    limit_text = (
        " · ".join(limits)
        if limits
        else "Kaynakta sayısal değer yayımlanmamış"
    )

    unique_conditions = []

    for item in condition_parts:
        if item not in unique_conditions:
            unique_conditions.append(item)

    condition_text = (
        " · ".join(unique_conditions)
        if unique_conditions
        else "Belirtilmedi"
    )

    return limit_text, condition_text


def detail_category_lines(
    frame: pd.DataFrame,
) -> list[str]:
    lines = []
    if frame.empty:
        return lines

    for _, row in frame.iterrows():
        label = display_text(row.get("category_label"))
        band = amount_band(row)

        result = []
        if has_value(row.get("max_installments")):
            result.append(
                f"{int(row.get('max_installments'))} taksit"
            )
        if has_value(row.get("max_maturity_months")):
            result.append(
                f"{int(row.get('max_maturity_months'))} ay"
            )

        if result:
            lines.append(
                f"**{label}** — {band}: "
                + " · ".join(result)
            )

    return lines


def detail_amount_lines(
    frame: pd.DataFrame,
) -> list[str]:
    lines = []
    if frame.empty:
        return lines

    for _, row in frame.iterrows():
        if has_value(row.get("max_maturity_months")):
            lines.append(
                f"**{amount_band(row)}** → "
                f"azami {int(row.get('max_maturity_months'))} ay"
            )

    return lines


def offer_condition_summary(
    product_id: int,
    offer_rules: pd.DataFrame,
    selected_amount: float,
) -> str:
    """
    Ürünün kaynakta bulunan tüm özel tekliflerini gösterir.

    Seçilen tutara uymayan bir teklif kaybolmaz; bunun yerine
    "(seçili tutara uygulanmıyor)" notu eklenir.
    """
    if offer_rules.empty:
        return "Belirtilmedi"

    subset = offer_rules[
        offer_rules["product_id"] == product_id
    ]

    if subset.empty:
        return "Belirtilmedi"

    parts: list[str] = []

    for _, row in subset.iterrows():
        band = amount_band(row)
        details: list[str] = []

        if int(row.get("interest_free") or 0) == 1:
            details.append("Vade farksız")

        if has_value(row.get("max_installments")):
            details.append(
                f"{int(row.get('max_installments'))} taksit"
            )

        if has_value(row.get("max_maturity_months")):
            maturity_text = (
                f"{int(row.get('max_maturity_months'))} ay"
            )

            # 3 taksit + 3 ay gibi iki alan kaynakta açıkça
            # birlikte tutuluyorsa ikisini de göstermek doğrudur.
            if maturity_text not in details:
                details.append(maturity_text)

        label = display_text(
            row.get("rule_label")
        )

        if (
            label != "Belirtilmedi"
            and label not in details
        ):
            # Çok uzun/generic etiketleri ana tabloya taşımıyoruz.
            if len(label) <= 60:
                details.append(label)

        item = band

        if details:
            item += ": " + " · ".join(details)

        applicable = amount_matches(
            amount=float(selected_amount),
            min_amount=(
                None
                if pd.isna(row.get("min_amount"))
                else float(row.get("min_amount"))
            ),
            max_amount=(
                None
                if pd.isna(row.get("max_amount"))
                else float(row.get("max_amount"))
            ),
            min_inclusive=bool(
                row.get("min_inclusive")
            ),
            max_inclusive=bool(
                row.get("max_inclusive")
            ),
        )

        if not applicable:
            item += " (seçili tutara uygulanmıyor)"

        if item not in parts:
            parts.append(item)

    return (
        " · ".join(parts)
        if parts
        else "Belirtilmedi"
    )


def detail_offer_lines(
    frame: pd.DataFrame,
) -> list[str]:
    lines = []
    if frame.empty:
        return lines

    for _, row in frame.iterrows():
        condition = display_text(
            row.get("condition_text")
        )
        if condition != "Belirtilmedi":
            lines.append(f"**Özel koşul:** {condition}")

    return lines


def detail_fee_lines(
    frame: pd.DataFrame,
) -> list[str]:
    lines = []
    if frame.empty:
        return lines

    for _, row in frame.iterrows():
        label = display_text(row.get("fee_label"))
        if int(row.get("waived", 0)) == 1:
            status = "Alınmıyor"
        elif has_value(row.get("rate")):
            status = rate_text(row.get("rate"))
        elif has_value(row.get("amount")):
            status = tr_money(row.get("amount"))
        else:
            status = "Var"

        lines.append(f"**{label}:** {status}")

    return lines


def detail_fee_lines_from_summary(
    summary: str,
) -> list[str]:
    """
    Detay kartında ham fee_rules yerine sonuç tablosunda
    kullanılan, fiyatlama matrisiyle doğrulanmış masraf
    özetini gösterir.

    Böylece örneğin:
      Kâr oranı %4,25
      Tahsis ücreti %0
    olan tabloda eski/yanlış bir fee_rule "%6" ise bile
    kullanıcıya maliyet tablosundaki doğru %0 gösterilir.
    """
    if (
        not summary
        or summary == "Belirtilmedi"
    ):
        return []

    lines: list[str] = []

    for item in summary.split(" · "):
        item = item.strip()
        if not item:
            continue

        if ":" in item:
            label, status = item.split(":", 1)
            lines.append(
                f"**{label.strip()}:** "
                f"{status.strip()}"
            )
        else:
            lines.append(item)

    return lines



QUALITATIVE_FEATURE_ORDER = [
    ("usage_purpose", "Kullanım Amacı"),
    ("target_segment", "Hedef Kitle"),
    ("currency", "Para Birimi"),
    ("transaction_structure", "İşlem / Finansman Yapısı"),
    ("digital_process", "Dijital İşlem"),
    ("foreign_trade", "Dış Ticaret"),
    ("application_channel", "Başvuru / Kanal"),
    ("security_type", "Teminat / Güvence"),
    ("repayment_structure", "Ödeme / Kullanım Yapısı"),
    ("transaction_limit", "İşlem / Limit"),
    ("cost_advantage", "Maliyet / Avantaj"),
    ("comparison_subtype", "Alt Tür"),
]


def feature_values_for_product(
    feature_rules: pd.DataFrame,
    product_id: int,
) -> dict[str, str]:
    if feature_rules.empty:
        return {}

    subset = feature_rules[
        feature_rules["product_id"] == product_id
    ]

    if subset.empty:
        return {}

    result = {}

    for key, label in QUALITATIVE_FEATURE_ORDER:
        rows = subset[
            subset["feature_key"] == key
        ]

        values = (
            rows["feature_value"]
            .dropna()
            .astype(str)
            .loc[lambda s: s.str.strip().ne("")]
            .drop_duplicates()
            .tolist()
        )

        if values:
            result[label] = " · ".join(values)

    return result


QUALITATIVE_TABLE_COLUMNS = [
    ("Hedef Kitle", "Hedef Kitle"),
    ("Para Birimi", "Para Birimi"),
    ("İşlem / Finansman Yapısı", "Yapı"),
    ("Dijital İşlem", "Dijital"),
    ("Dış Ticaret", "Dış Ticaret"),
    ("Başvuru / Kanal", "Kanal"),
    ("Teminat / Güvence", "Teminat"),
    ("Ödeme / Kullanım Yapısı", "Ödeme / Kullanım"),
    ("İşlem / Limit", "İşlem / Limit"),
    ("Maliyet / Avantaj", "Maliyet / Avantaj"),
    ("Alt Tür", "Alt Tür"),
]


def purpose_value(
    values: dict[str, str],
) -> str:
    purpose = str(
        values.get("Kullanım Amacı", "")
        or ""
    ).strip()

    if not purpose:
        return "Belirtilmedi"

    return purpose


def product_has_numeric_core(
    product: pd.Series,
) -> bool:
    return any(
        has_value(product.get(key))
        for key in (
            "minimum_financing_amount",
            "maximum_financing_amount",
            "minimum_maturity_months",
            "maximum_maturity_months",
            "profit_share_rate",
            "profit_share_rate_text",
            "shopping_general_limit_amount",
            "maximum_financing_ratio",
        )
    )


def use_qualitative_comparison(
    selected_family: str,
    selected_products: pd.DataFrame,
    feature_rules: pd.DataFrame,
) -> bool:
    if feature_rules.empty or selected_products.empty:
        return False

    family_key = str(selected_family).casefold()

    explicit_family = any(
        token in family_key
        for token in (
            "gayri nakdi",
            "nakdi",
            "ticari",
            "leasing",
            "tarım",
        )
    )

    numeric_sparse = (
        selected_products.apply(
            lambda row: not product_has_numeric_core(row),
            axis=1,
        ).mean()
        >= 0.5
    )

    return explicit_family or numeric_sparse

products = get_standard_products()

# EMLAK_HOUSING_UI_CLEANUP_V1
# Yalnizca gorunen urun etiketi temizlenir.
# PostgreSQL urun kimligi ve kaynak veri degistirilmez.
if "product_name" in products.columns:
    products["product_name"] = products[
        "product_name"
    ].replace(
        {
            "Tamamlay\u0131c\u0131 Konut Finansman\u0131 | T\u00fcrkiye Emlak Kat\u0131l\u0131m Bankas\u0131":
                "Tamamlay\u0131c\u0131 Konut Finansman\u0131",
        }
    )

if products.empty:
    st.info(
        "Henüz standart finansman ürünü bulunmuyor."
    )
    st.stop()

# ============================================================
# BANSA FİNANSMAN TAKSONOMİSİ
# ============================================================
# Karşılaştırma iki seviyelidir:
#   1) Finansman Alanı: Bireysel / İş-Ticari
#   2) Finansman Türü: seçilen alandaki normalize kategori
#
# Bankanın resmî ürün adı, product_family değeri ve scope bilgisi veri
# katmanında aynen korunur. Ürün adında "ticari" geçmesi tek başına ürünü
# İş/Ticari alana taşımaz; ayrım yalnız doğrulanmış scope üzerinden yapılır.
products = products.copy()
products["_normalized_scope"] = products.get(
    "scope",
    pd.Series(index=products.index, dtype=object),
).apply(normalize_scope)
products["_bansa_scope"] = products["_normalized_scope"].apply(bansa_scope_label)
products["_bansa_scope_order"] = products["_normalized_scope"].apply(bansa_scope_order)
products["_bansa_category_key"] = products.apply(
    lambda row: classify_finance_category(
        row.get("product_family"),
        row.get("product_name"),
        row.get("scope"),
    ),
    axis=1,
)
products["_bansa_category"] = products["_bansa_category_key"].apply(bansa_category_label)
products["_bansa_category_order"] = products["_bansa_category_key"].apply(bansa_category_order)

# Yalnız açıkça Bireysel veya Ticari olarak doğrulanmış scope'lar müşteriye
# sunulur. Belirsiz scope kayıtları yanlış karşılaştırmaya sızmasın.
comparison_scope_products = products[
    products["_normalized_scope"].isin(["bireysel", "ticari"])
].copy()
if comparison_scope_products.empty:
    st.info("PostgreSQL'de karşılaştırılabilir finansman ürünü bulunmuyor.")
    st.stop()

# ============================================================
# FİLTRELER
# ============================================================
scope_frame = (
    comparison_scope_products[[
        "_normalized_scope",
        "_bansa_scope",
        "_bansa_scope_order",
    ]]
    .drop_duplicates()
    .sort_values(["_bansa_scope_order", "_bansa_scope"], kind="stable")
)
finance_scopes = scope_frame["_normalized_scope"].tolist()

st.caption(
    "Önce finansman alanını seçin. Finansman türleri ve banka listesi, "
    "yalnız seçtiğiniz alanda resmî olarak kayıtlı ürünlerden oluşturulur."
)

scope_col, family_col, bank_col = st.columns([1, 1.25, 2])

with scope_col:
    selected_scope = st.selectbox(
        "Finansman Alanı",
        options=finance_scopes,
        format_func=bansa_scope_label,
        help=(
            "Bireysel Finansman yalnız bireysel ürünleri; İş / Ticari "
            "Finansman yalnız bankanın ticari/KOBİ/kurumsal kapsamda "
            "yayımladığı ürünleri gösterir."
        ),
    )

scoped_products = comparison_scope_products[
    comparison_scope_products["_normalized_scope"] == selected_scope
].copy()

category_frame = (
    scoped_products[["_bansa_category", "_bansa_category_order"]]
    .drop_duplicates()
    .sort_values(["_bansa_category_order", "_bansa_category"], kind="stable")
)
financing_types = category_frame["_bansa_category"].tolist()

if not financing_types:
    st.info("Seçilen finansman alanında karşılaştırılabilir ürün türü bulunmuyor.")
    st.stop()

with family_col:
    selected_family = st.selectbox(
        "Finansman Türü",
        options=financing_types,
        help=(
            "Seçenekler Finansman Alanı'na göre otomatik değişir. "
            "Bankanın resmî ürün adı ve kendi ürün ailesi değiştirilmez."
        ),
    )

comparison_products = scoped_products[
    scoped_products["_bansa_category"] == selected_family
].copy()

# Eski discovery config'inde Kuveyt Türk'ün 2B / Arsa / İş Yeri ürünleri
# aynı URL klasöründe bulundukları için yanlışlıkla "Konut Finansmanı"
# ailesine düşebiliyordu. Repair scripti veri tabanını kalıcı olarak
# düzeltir; bu koruma ise repair henüz çalışmamış olsa bile yanlış
# ürünlerin konut karşılaştırmasına girmesini engeller.
if selected_scope == "bireysel" and housing_family(selected_family):
    _misclassified_non_home_products = {
        ("Kuveyt Türk", "2B Finansmanı"),
        ("Kuveyt Türk", "Arsa Finansmanı"),
        ("Kuveyt Türk", "İş Yeri Finansmanı"),
    }
    comparison_products = comparison_products[
        ~comparison_products.apply(
            lambda row: (
                str(row.get("bank_name") or "").strip(),
                str(row.get("product_name") or "").strip().rstrip("*").strip(),
            )
            in _misclassified_non_home_products,
            axis=1,
        )
    ].copy()

banks = (
    comparison_products["bank_name"]
    .dropna()
    .astype(str)
    .drop_duplicates()
    .sort_values(key=lambda s: s.str.casefold())
    .tolist()
)

with bank_col:
    selected_banks = st.multiselect(
        "Bankalar",
        options=banks,
        default=banks,
        help=(
            "Yalnız seçilen Finansman Alanı + Finansman Türü kombinasyonunda "
            "ürünü bulunan bankalar listelenir."
        ),
    )

if not selected_banks:
    st.info("En az bir banka seçin.")
    st.stop()

selected = comparison_products[
    comparison_products["bank_name"].isin(
        selected_banks
    )
].copy()

if selected.empty:
    st.info(
        "Seçili bankalarda bu finansman türü ailesinde kayıtlı ürün bulunmuyor."
    )
    st.stop()

selected_ids = selected["id"].astype(int).tolist()

# FINANCE_SCENARIO_UI_V1
# Scenario verisi canonical urun verisinden ayri okunur.
finance_scenarios = get_latest_finance_scenarios(
    selected_ids
)

rule_sets = get_standard_product_rule_sets(
    selected_ids
)
category_rules = rule_sets["category"]
amount_rules = rule_sets["amount_maturity"]
pricing_all_rules = rule_sets.get("pricing_all", rule_sets["pricing"])
pricing_rules = filter_authoritative_pricing_frame(rule_sets["pricing"])
fee_rules = rule_sets["fee"]
offer_rules = rule_sets["offer"]
feature_rules = rule_sets.get(
    "feature",
    pd.DataFrame(),
)

qualitative_mode = use_qualitative_comparison(
    selected_family,
    selected,
    feature_rules,
)

pricing_variant_options: list[str] = []

if (
    not pricing_rules.empty
    and "pricing_variant" in pricing_rules.columns
):
    pricing_variant_options = (
        pricing_rules["pricing_variant"]
        .dropna()
        .astype(str)
        .loc[
            lambda s: s.str.strip().ne("")
        ]
        .drop_duplicates()
        .tolist()
    )

    preferred_order = [
        "Sigortalı",
        "Sigortalı · 0 km",
        "Sigortalı · 2. El",
        "Sigortasız",
        "Sigortasız · 0 km",
        "Sigortasız · 2. El",
        "Standart",
    ]

    pricing_variant_options.sort(
        key=lambda value: (
            preferred_order.index(value)
            if value in preferred_order
            else len(preferred_order),
            value.casefold(),
        )
    )


available_categories = (
    category_rules[
        ["category_key", "category_label"]
    ]
    .drop_duplicates()
    .sort_values(
        "category_label",
        key=lambda s: s.str.casefold(),
    )
    if not category_rules.empty
    else pd.DataFrame()
)

category_options = {"Tümü": None}

if not available_categories.empty:
    for _, row in available_categories.iterrows():
        category_options[
            row["category_label"]
        ] = row["category_key"]

is_vehicle_mode = vehicle_family(
    selected_family
)
is_housing_mode = housing_family(
    selected_family
)

amount_filter_available = financing_amount_applicable(
    selected_family,
    selected,
    category_rules,
    amount_rules,
    offer_rules,
)

maturity_filter_available = maturity_filter_applicable(
    selected_family,
    selected,
    category_rules,
    amount_rules,
    pricing_rules,
    offer_rules,
)

is_gayri_nakdi_mode = is_gayri_nakdi_family(
    selected_family
)

# Ana kullanım: Finansman Alanı + Finansman Türü + Bankalar yeterlidir.
# Seçili bankaların bu ailedeki TÜM ürünleri varsayılan olarak gösterilir.
# Tutar/vade/kategori/fiyatlama ancak kullanıcı özellikle isterse daraltma yapar.
if is_vehicle_mode:
    st.caption(
        "Araç Finansmanı'nda Araç / Kasko Değeri hesaplama için kullanılır. "
        "Resmî finansman oranı bulunan ürünlerde orana göre finansman tutarı "
        "otomatik hesaplanır. Diğer ek filtreler isteğe bağlıdır."
    )
elif is_housing_mode:
    st.caption(
        "Konut Finansmanı ana tablosunda bankalar ortak kriterlerle "
        "karşılaştırılır. Enerji sınıfı, ilk/ikinci konut ve ekspertiz "
        "değerine bağlı bankaya özgü kurallar Ürün Detayı bölümünde gösterilir."
    )
else:
    st.caption(
        "Seçili bankaların bu finansman türündeki ürünleri karşılaştırılır. "
        "Sayısal finansmanlarda ortak tutar ve ortak vade kullanılır; "
        "nitel ürünlerde doğrulanmış ürün özellikleri esas alınır."
    )
# FINANCE_COMMON_SCENARIO_UI_V1
#
# Numeric individual financing comparison rule:
# same financing amount + same maturity.
#
# Vehicle, housing and qualitative commercial flows remain
# outside this strict common-scenario mode for now.
strict_common_scenario_mode = (
    not qualitative_mode
    and not is_vehicle_mode
    and not is_housing_mode
    and not is_gayri_nakdi_mode
)

if strict_common_scenario_mode:
    use_optional_filters = True

    st.info(
        "Bu finansman t\u00fcr\u00fcnde bankalar ayn\u0131 tutar ve "
        "ayn\u0131 vade \u00fczerinden kar\u015f\u0131la\u015ft\u0131r\u0131l\u0131r. "
        "Talep edilen ko\u015fullar\u0131 kar\u015f\u0131lamayan \u00fcr\u00fcnler "
        "kar\u015f\u0131la\u015ft\u0131rma sonucuna al\u0131nmaz."
    )
else:
    use_optional_filters = st.toggle(
        "\u0130ste\u011fe ba\u011fl\u0131 ek filtrelerle sonu\u00e7lar\u0131 daralt",
        value=False,
    )

amount_filter_applicable = (
    (
        amount_filter_available
        or strict_common_scenario_mode
    )
    and (
        use_optional_filters
        or is_vehicle_mode
        or strict_common_scenario_mode
    )
)

maturity_filter_enabled = (
    (
        maturity_filter_available
        or strict_common_scenario_mode
    )
    and (
        use_optional_filters
        or strict_common_scenario_mode
    )
)

category_filter_enabled = (
    use_optional_filters
    and not is_vehicle_mode
    and not is_housing_mode
    and not is_gayri_nakdi_mode
    and len(category_options) > 1
)

# Tek bir fiyatlama etiketi kullanıcıya seçim hakkı vermez.
# Bu nedenle ancak gerçek bir alternatif varsa ve kullanıcı ek filtreleri açtıysa gösterilir.
pricing_filter_enabled = (
    use_optional_filters
    and not is_gayri_nakdi_mode
    and len(pricing_variant_options) > 1
)

maturity_candidates = set()

if not pricing_rules.empty:
    maturity_candidates.update(
        pricing_rules["maturity_months"]
        .dropna()
        .astype(int)
        .tolist()
    )

if "maximum_maturity_months" in selected.columns:
    maturity_candidates.update(
        selected["maximum_maturity_months"]
        .dropna()
        .astype(int)
        .tolist()
    )

if is_vehicle_mode:
    for _, product_row in selected.iterrows():
        for rule in parse_vehicle_rules_text(
            product_row.get("vehicle_finance_rules_text")
        ):
            months = rule.get("max_maturity_months")
            if months:
                maturity_candidates.add(int(months))

maturity_values = sorted(maturity_candidates)

# Filtreler artık sabit kolon sayısına göre değil,
# seçili ürün grubunda gerçekten kullanılabilir veri olup
# olmamasına göre oluşturulur.

selected_category_label = "Genel"
selected_category_key = None
simulator_amount = None
selected_maturity_label = "Seçme"
selected_maturity = None
selected_pricing_variant = None
selected_housing_purchase_type = "Standart Konut Alımı"
selected_housing_energy_class = "A-B"
housing_comparison_value = None

filter_specs: list[str] = []

if category_filter_enabled:
    filter_specs.append("category")

if amount_filter_applicable:
    filter_specs.append("amount")

if maturity_filter_enabled:
    filter_specs.append("maturity")

if pricing_filter_enabled:
    filter_specs.append("pricing")

# Konut ekspertiz değeri ana karşılaştırma tablosunun girdisi değildir.
# Bankaya özgü hesap yalnız Ürün Detayı bölümünde yapılır.

filter_columns = (
    st.columns(len(filter_specs))
    if filter_specs
    else []
)

column_by_filter = {
    name: filter_columns[index]
    for index, name in enumerate(filter_specs)
}

if is_gayri_nakdi_mode:
    st.caption(
        "Gayri Nakdi Finansman ürünleri, resmî kaynakta "
        "yayımlanan amaç ve nitel özellikler üzerinden "
        "karşılaştırılır."
    )

category_filter_title = (
    "Alışveriş / Ürün Kategorisi"
    if "ihtiyaç" in _family_key(selected_family)
    else "Kategori"
)

if category_filter_enabled:
    with column_by_filter["category"]:
        selected_category_label = st.selectbox(
            category_filter_title,
            options=list(category_options.keys()),
        )
        selected_category_key = category_options[
            selected_category_label
        ]

if amount_filter_applicable:
    with column_by_filter["amount"]:
        if is_vehicle_mode:
            amount_label = "Araç / Kasko Değeri (TL)"
        else:
            amount_label = "Finansman Tutarı (TL)"

        input_max_value = None

        if is_vehicle_mode:
            known_vehicle_max_values = []
            vehicle_rule_unknown_exists = False

            for _, product_row in selected.iterrows():
                parsed_rules = parse_vehicle_rules_text(
                    product_row.get(
                        "vehicle_finance_rules_text"
                    )
                )

                if not parsed_rules:
                    vehicle_rule_unknown_exists = True
                    continue

                allowed_rules = [
                    rule
                    for rule in parsed_rules
                    if not rule.get("blocked")
                ]

                finite_highs = [
                    float(rule["max_amount"])
                    for rule in allowed_rules
                    if rule.get("max_amount") is not None
                ]

                if finite_highs:
                    known_vehicle_max_values.append(
                        max(finite_highs)
                    )
                else:
                    vehicle_rule_unknown_exists = True

            # Bir araç ürününde kaynakta yapılandırılmış değer bandı
            # yoksa başka bir ürünün bandını tüm aileye üst sınır
            # olarak dayatma. Örn. Togg/Deniz Taşıtları görünür kalır.
            if (
                known_vehicle_max_values
                and not vehicle_rule_unknown_exists
            ):
                input_max_value = int(
                    max(known_vehicle_max_values)
                )

        elif not is_housing_mode:
            known_general_max_values = []
            unknown_general_max_exists = False

            for _, product_row in selected.iterrows():
                product_max = product_row.get(
                    "maximum_financing_amount"
                )

                if has_value(product_max):
                    known_general_max_values.append(
                        float(product_max)
                    )
                else:
                    unknown_general_max_exists = True

            if (
                known_general_max_values
                and not unknown_general_max_exists
            ):
                input_max_value = int(
                    max(known_general_max_values)
                )

        amount_kwargs = {
            "label": amount_label,
            "min_value": 0,
            "value": default_amount_for_family(
                selected_family
            ),
            "step": 1000,
        }

        # FINANCE_COMMON_SCENARIO_DEFAULT_V1
        if (
            strict_common_scenario_mode
            and "ihtiyac"
            in _family_key(
                selected_family
            )
        ):
            amount_kwargs["value"] = 100_000

        if input_max_value is not None:
            amount_kwargs["max_value"] = max(
                1000,
                input_max_value,
            )
            amount_kwargs["value"] = min(
                amount_kwargs["value"],
                amount_kwargs["max_value"],
            )

        simulator_amount = st.number_input(
            **amount_kwargs
        )

        if input_max_value is not None:
            if is_vehicle_mode:
                st.caption(
                    "Seçili bankaların doğrulanmış araç "
                    "kurallarına göre azami araç/kasko değeri: "
                    f"{format_number_tr(input_max_value)} TL"
                )
            else:
                st.caption(
                    "Seçili ürünlerin kaynakta belirtilen "
                    "azami finansman limitlerine göre üst sınır: "
                    f"{format_number_tr(input_max_value)} TL"
                )

if maturity_filter_enabled:
    with column_by_filter["maturity"]:

        _maturity_labels = [
            f"{value} Ay"
            for value in maturity_values
        ]

        if strict_common_scenario_mode:

            if not _maturity_labels:
                st.error(
                    "Se\u00e7ili finansman t\u00fcr\u00fc i\u00e7in "
                    "do\u011frulanm\u0131\u015f vade bilgisi bulunamad\u0131."
                )
                st.stop()

            _preferred_maturity_label = "36 Ay"

            _default_maturity_index = (
                _maturity_labels.index(
                    _preferred_maturity_label
                )
                if (
                    _preferred_maturity_label
                    in _maturity_labels
                )
                else 0
            )

            selected_maturity_label = st.selectbox(
                "Ortak Vade",
                options=_maturity_labels,
                index=_default_maturity_index,
                help=(
                    "T\u00fcm uygun bankalar girilen finansman "
                    "tutar\u0131 ve ayn\u0131 vade \u00fczerinden "
                    "kar\u015f\u0131la\u015ft\u0131r\u0131l\u0131r."
                ),
            )

        else:

            selected_maturity_label = st.selectbox(
                "Tercih Edilen Vade",
                options=[
                    "Se\u00e7me"
                ]
                + _maturity_labels,
            )

    selected_maturity = (
        None
        if (
            not strict_common_scenario_mode
            and selected_maturity_label
            == "Se\u00e7me"
        )
        else int(
            selected_maturity_label
            .split()[0]
        )
    )


if pricing_filter_enabled:
    with column_by_filter["pricing"]:
        selected_pricing_variant = st.selectbox(
            "Fiyatlama Seçeneği",
            options=pricing_variant_options,
        )


# ============================================================
# TEK KARŞILAŞTIRMA TABLOSU
# ============================================================
# FINANCE_COMMON_SCENARIO_MAIN_TABLE_V2
#
# Strict comparison:
# only an exact verified scenario with the SAME
# amount and SAME maturity can enter the main table.
_strict_exact_scenarios = pd.DataFrame()

_strict_exact_by_product: dict[
    int,
    pd.DataFrame,
] = {}


if strict_common_scenario_mode:

    if (
        simulator_amount is None
        or selected_maturity is None
    ):
        raise RuntimeError(
            "Strict common scenario inputs are missing."
        )

    _strict_exact_scenarios = (
        filter_exact_verified_scenarios(
            finance_scenarios,
            amount=float(
                simulator_amount
            ),
            maturity=int(
                selected_maturity
            ),
        )
    )

    if not _strict_exact_scenarios.empty:

        for (
            _strict_product_id,
            _strict_group,
        ) in _strict_exact_scenarios.groupby(
            "product_id",
            sort=False,
        ):

            _strict_exact_by_product[
                int(_strict_product_id)
            ] = _strict_group.copy()


def _strict_exact_rate_summary(
    group: pd.DataFrame | None,
) -> str:

    if group is None or group.empty:
        return (
            "Bu tutar/vade i\u00e7in "
            "canl\u0131 sonu\u00e7 do\u011frulanmad\u0131"
        )

    working = group.copy()

    if (
        "input_variant"
        in working.columns
    ):

        working[
            "_exact_variant_order"
        ] = (
            working[
                "input_variant"
            ]
            .fillna("")
            .astype(str)
            .str.casefold()
            .map(
                {
                    "sigortali": 0,
                    "sigortasiz": 1,
                    "standard": 2,
                    "standart": 2,
                }
            )
            .fillna(9)
        )

        working = working.sort_values(
            [
                "_exact_variant_order",
                "input_variant",
            ],
            kind="stable",
        )


    parts = []


    for _, scenario in working.iterrows():

        rate = scenario.get(
            "profit_share_rate"
        )

        if not has_value(rate):
            continue


        variant = (
            str(
                scenario.get(
                    "input_variant"
                )
                or ""
            )
            .strip()
            .casefold()
        )


        label = {
            "sigortali":
                "Sigortal\u0131",

            "sigortasiz":
                "Sigortas\u0131z",

            "standard":
                "",

            "standart":
                "",
        }.get(
            variant,
            str(
                scenario.get(
                    "input_variant"
                )
                or ""
            ).strip(),
        )


        rate_value = rate_text(
            rate
        )


        value = (
            f"{label} {rate_value}"
            if label
            else rate_value
        )


        if value not in parts:
            parts.append(
                value
            )


    if not parts:

        return (
            "Bu tutar/vade i\u00e7in "
            "canl\u0131 oran do\u011frulanmad\u0131"
        )


    return " \u00b7 ".join(
        parts
    )


result_rows = []
result_context: dict[int, dict] = {}

for _, product in selected.iterrows():
    product_id = int(product["id"])

    # FINANCE_COMMON_SCENARIO_ELIGIBILITY_V1
    if strict_common_scenario_mode:

        if (
            simulator_amount is None
            or selected_maturity is None
        ):
            raise RuntimeError(
                "Strict common scenario inputs are missing."
            )

        common_eligibility = (
            evaluate_product_eligibility(
                product,
                amount=float(
                    simulator_amount
                ),
                maturity=int(
                    selected_maturity
                ),
                amount_rules=amount_rules,
            )
        )

        if not common_eligibility.eligible:
            continue

        # FINANCE_COMMON_SCENARIO_EXACT_PRODUCT_V2
        #
        # Canonical eligibility alone is not enough for
        # the main numeric comparison. There must also
        # be an exact verified calculator scenario.
        _product_exact_scenarios = (
            _strict_exact_by_product.get(
                product_id
            )
        )

        if (
            _product_exact_scenarios is None
            or _product_exact_scenarios.empty
        ):
            continue

    vehicle_eval = None
    housing_eval = None

    if is_vehicle_mode and amount_filter_applicable:
        vehicle_rule_text = product.get(
            "vehicle_finance_rules_text"
        )

        if has_value(vehicle_rule_text):
            vehicle_eval = evaluate_vehicle_rule(
                vehicle_rule_text,
                float(simulator_amount),
            )

            if vehicle_eval is not None:
                # Kaynak açıkça kullandırım yapılmayacağını söylüyorsa
                # yalnız bu ürünü uygun sonuçlardan çıkar.
                if vehicle_eval.get("blocked"):
                    continue

                vehicle_max_months = vehicle_eval.get(
                    "max_maturity_months"
                )
                if (
                    maturity_filter_enabled
                    and selected_maturity is not None
                    and vehicle_max_months is not None
                    and selected_maturity > vehicle_max_months
                ):
                    continue
        else:
            # Band kuralı yayımlanmamış olması ürünün olmadığı anlamına
            # gelmez. Genel ürün vadesi varsa vade filtresinde onu kullan.
            general_vehicle_maturity = product.get(
                "maximum_maturity_months"
            )
            if (
                maturity_filter_enabled
                and selected_maturity is not None
                and has_value(general_vehicle_maturity)
                and selected_maturity > int(general_vehicle_maturity)
            ):
                continue

    category_matches: list[pd.Series] = []

    if (
        not is_vehicle_mode
        and amount_filter_applicable
    ):
        if not product_financing_amount_eligible(
            product,
            float(simulator_amount),
        ):
            continue

    if selected_category_key is not None:
        if category_rules.empty:
            continue

        product_category = category_rules[
            (
                category_rules["product_id"]
                == product_id
            )
            & (
                category_rules["category_key"]
                == selected_category_key
            )
        ]

        for _, row in product_category.iterrows():
            if not amount_filter_applicable:
                category_matches.append(row)
                continue

            if amount_matches(
                amount=float(simulator_amount),
                min_amount=(
                    None
                    if pd.isna(row.get("min_amount"))
                    else float(row.get("min_amount"))
                ),
                max_amount=(
                    None
                    if pd.isna(row.get("max_amount"))
                    else float(row.get("max_amount"))
                ),
                min_inclusive=bool(
                    row.get("min_inclusive")
                ),
                max_inclusive=bool(
                    row.get("max_inclusive")
                ),
            ):
                category_matches.append(row)

        # Kategori seçildiyse ve ürün bu kategori+tutar
        # için açık bir kurala sahip değilse hiç gösterme.
        if not category_matches:
            continue

    if (
        is_vehicle_mode
        or is_housing_mode
        or not amount_filter_applicable
    ):
        # Araç modunda giriş araç/kasko değeridir.
        # Diğer ailelerde de seçili ürün grubunda doğrulanmış
        # tutar kuralı yoksa finansman tutarı filtresi uygulanmaz.
        offer_matches = []
        amount_matches_rows = []
    else:
        offer_matches = matching_rows_by_amount(
            offer_rules,
            product_id,
            float(simulator_amount),
        )

        amount_matches_rows = matching_rows_by_amount(
            amount_rules,
            product_id,
            float(simulator_amount),
        )

    # rule_result_text uygunluk/legacy hesaplaması için korunur; fakat
    # genel ürün vadesi ile seçili kategori taksit sınırı artık aynı
    # sütunda birleştirilmez.
    limit_text, _legacy_condition_text = rule_result_text(
        product,
        category_matches,
        offer_matches,
        amount_matches_rows,
    )

    general_maturity_text = general_maturity_summary_for_product(
        product,
        product_id,
        amount_rules,
    )

    amount_dependent_terms_text = (
        amount_dependent_summary_for_product(
            product,
            product_id,
            amount_rules,
            pricing_rules,
        )
    )
    selected_category_limit_text = selected_category_limit_summary(
        category_matches
    )
    condition_text = offer_summary_without_general_maturity(
        product_id,
        offer_rules,
    )

    if is_vehicle_mode:
        profit_text = vehicle_profit_summary_text(
            product,
            pricing_rules,
            selected_maturity,
            selected_pricing_variant,
        )
        vehicle_pricing_maturities = (
            vehicle_pricing_maturity_text(
                product,
                pricing_rules,
                selected_pricing_variant,
            )
        )
    elif is_housing_mode:
        profit_text = housing_profit_summary_text(
            product,
            pricing_rules,
            selected_maturity,
            selected_pricing_variant,
        )
        vehicle_pricing_maturities = (
            "Kaynakta sayısal değer yayımlanmamış"
        )
    else:
        profit_text = profit_text_for_product(
            product,
            pricing_rules,
            selected_maturity,
            selected_pricing_variant,
        )
        vehicle_pricing_maturities = (
            "Kaynakta sayısal değer yayımlanmamış"
        )

    fee_text = fee_summary_for_product(
        product_id,
        fee_rules,
        pricing_rules,
        selected_maturity,
        selected_pricing_variant,
    )

    allocation_fee_text = (
        allocation_fee_text_for_product(
            product_id,
            fee_rules,
            pricing_rules,
            selected_maturity,
            selected_pricing_variant,
        )
    )

    housing_main_profit_text = (
        housing_comparison_profit_text(
            product,
            pricing_rules,
        )
        if is_housing_mode
        else "—"
    )
    housing_main_maturity_text = (
        housing_comparison_maturity_text(
            product
        )
        if is_housing_mode
        else "—"
    )
    housing_main_ratio_text = (
        housing_comparison_ratio_text(
            product
        )
        if is_housing_mode
        else "—"
    )
    housing_allocation_fee_text = (
        housing_fee_comparison_text(
            product_id,
            fee_rules,
            "allocation",
        )
        if is_housing_mode
        else "—"
    )
    housing_appraisal_fee_text = housing_fee_comparison_text(
        product_id, fee_rules, "appraisal"
    )
    housing_mortgage_fee_text = housing_fee_comparison_text(
        product_id, fee_rules, "mortgage_establishment"
    )

    housing_installment_text = (
        housing_installment_summary(
            product,
            product_id,
            category_rules,
            offer_rules,
            pricing_rules,
        )
        if is_housing_mode
        else "—"
    )

    housing_other_fee_text = (
        non_allocation_fee_summary_for_product(
            product_id,
            fee_rules,
        )
        if is_housing_mode
        else "—"
    )

    # "Finansman Tutarı" ürünün kaynakta belirtilen
    # finansman limitini/range'ini göstermelidir.
    #
    # simulator_amount yalnız kullanıcı filtresidir;
    # ürün özelliğinin üstüne yazılmaz.
    financing_amount = product_amount_text(
        product,
        (
            offer_matches
            if amount_filter_applicable
            else None
        ),
    )

    # Fiyatlama tablosunda plan/model bazlı finansman tutarı yayımlanmışsa
    # genel ürün limiti yokken karşılaştırma satırında görünür tut.
    if not has_value(financing_amount) and not pricing_rules.empty:
        product_pricing_amounts = pricing_rules[
            pricing_rules["product_id"] == product_id
        ].copy()
        if (
            selected_pricing_variant is not None
            and not product_pricing_amounts.empty
            and "pricing_variant" in product_pricing_amounts.columns
        ):
            selected_plan_amounts = product_pricing_amounts[
                product_pricing_amounts["pricing_variant"]
                == selected_pricing_variant
            ]
            if not selected_plan_amounts.empty:
                product_pricing_amounts = selected_plan_amounts

        sample_pricing_only = False
        if (
            "pricing_variant" in product_pricing_amounts.columns
            and not product_pricing_amounts.empty
        ):
            variant_key = " ".join(
                product_pricing_amounts[
                    "pricing_variant"
                ]
                .fillna("")
                .astype(str)
                .str.casefold()
                .tolist()
            )
            sample_pricing_only = any(
                token in variant_key
                for token in (
                    "örnek",
                    "ornek",
                    "maliyet örneği",
                    "maliyet ornegi",
                    "sample",
                )
            )

        if (
            "financing_amount" in product_pricing_amounts.columns
            and not product_pricing_amounts.empty
            and not sample_pricing_only
        ):
            plan_amounts = sorted(
                {
                    float(value)
                    for value in product_pricing_amounts[
                        "financing_amount"
                    ].dropna()
                }
            )
            if len(plan_amounts) == 1:
                financing_amount = tr_money(plan_amounts[0])
            elif len(plan_amounts) > 1:
                financing_amount = (
                    "Plan bazlı "
                    + tr_money(plan_amounts[0])
                    + " – "
                    + tr_money(plan_amounts[-1])
                )

    if is_housing_mode:
        financing_amount = (
            housing_financing_amount_summary(
                product
            )
        )

    if vehicle_eval is not None:
        ratio = vehicle_eval.get("ratio")
        max_months = vehicle_eval.get(
            "max_maturity_months"
        )
        max_financing = vehicle_eval.get(
            "max_financing_amount"
        )

        if max_months is not None:
            general_maturity_text = f"{int(max_months)} ay"

        if max_financing is not None:
            ratio_part = (
                f" (%{format_number_tr(ratio)})"
                if ratio is not None
                else ""
            )
            financing_amount = (
                f"Azami {tr_money(max_financing)}"
                f"{ratio_part}"
            )

        vehicle_parts = [
            "Araç/Kasko: "
            + vehicle_band_text(vehicle_eval)
        ]
        if ratio is not None:
            vehicle_parts.append(
                "Azami finansman oranı "
                f"%{format_number_tr(ratio)}"
            )
        if max_months is not None:
            vehicle_parts.append(
                f"Azami vade {int(max_months)} ay"
            )

        condition_text = " · ".join(vehicle_parts)

    if housing_eval is not None:
        housing_ratio = housing_eval.get("ratio")
        housing_max_financing = housing_eval.get(
            "max_financing_amount"
        )

        if housing_max_financing is not None:
            financing_amount = (
                "Azami "
                + tr_money(housing_max_financing)
            )

        housing_parts = [
            selected_housing_purchase_type,
            f"Enerji sınıfı {selected_housing_energy_class}",
            housing_value_band_text(housing_eval),
        ]

        if housing_ratio is not None:
            housing_parts.append(
                "Azami finansman oranı "
                f"%{format_number_tr(housing_ratio)}"
            )

        condition_text = " · ".join(
            housing_parts
        )

    has_numeric_eligibility_evidence = any(
        (
            category_matches,
            offer_matches,
            amount_matches_rows,
        )
    ) or any(
        has_value(product.get(key))
        for key in (
            "minimum_financing_amount",
            "maximum_financing_amount",
            "minimum_maturity_months",
            "maximum_maturity_months",
            "profit_share_rate",
            "profit_share_rate_text",
        )
    )

    if (
        not is_vehicle_mode
        and not is_housing_mode
        and amount_filter_applicable
        and not has_numeric_eligibility_evidence
    ):
        numeric_note = (
            "Sayısal koşullar kaynakta yayımlanmamış; "
            "seçilen tutar için uygunluk doğrulanamadı."
        )

        if condition_text == "Belirtilmedi":
            condition_text = numeric_note
        elif numeric_note not in condition_text:
            condition_text = (
                condition_text
                + " · "
                + numeric_note
            )

    # TARIM_RATIO_DEFAULT_DISPLAY_V4
    financing_ratio_text = (
        "\u2014"
        if (
            is_housing_mode
            or str(
                product.get("product_family_key") or ""
            ) == "tarim_finansmani"
        )
        else "Belirtilmedi"
    )
    housing_comparison_financing_text = "—"

    housing_rules_for_product = (
        parse_housing_rules_json(
            product.get("housing_finance_rules_json")
        )
        if is_housing_mode
        else {}
    )

    if is_housing_mode and housing_rules_for_product:
        # Enerji sınıfı / standart-ek konut gibi birden fazla boyut
        # varsa ana tabloda tek bir oran seçmek doğru değildir.
        financing_ratio_text = "Detayda hesaplanır"
        housing_comparison_financing_text = "Detayda hesaplanır"

    elif (
        is_housing_mode
        and has_value(
            product.get("maximum_financing_ratio")
        )
    ):
        ratio_value = float(
            product.get("maximum_financing_ratio")
        )
        financing_ratio_text = (
            "Azami %"
            + format_number_tr(ratio_value)
        )

        if housing_comparison_value is not None:
            housing_comparison_financing_text = tr_money(
                float(housing_comparison_value)
                * ratio_value
                / 100.0
            )

    elif (
        is_housing_mode
        and has_value(product.get("financing_ratio_rules_text"))
    ):
        financing_ratio_text = "Koşula göre değişir"
        housing_comparison_financing_text = "Detayda açıklanır"

    elif is_vehicle_mode:
        financing_ratio_text = vehicle_financing_ratio_summary_text(product)
    elif has_value(product.get("maximum_financing_ratio")):
        financing_ratio_text = (
            "Azami %"
            + format_number_tr(product.get("maximum_financing_ratio"))
        )

    # Araç finansmanında kullanıcı Araç / Kasko Değeri girdiğinde,
    # resmî finansman oranı varsa o değere göre karşılaştırılabilir
    # finansman tutarını ayrı bir sütunda göster.
    #
    # Bu hesap Kâr Payı oranını DEĞİL, finansman oranını kullanır:
    #   araç/kasko değeri × finansman oranı / 100
    ratio_financing_text = "—"

    if (
        is_housing_mode
        and housing_eval is not None
        and housing_eval.get("max_financing_amount") is not None
    ):
        ratio_financing_text = tr_money(
            housing_eval.get("max_financing_amount")
        )

    elif (
        is_vehicle_mode
        and amount_filter_applicable
        and simulator_amount is not None
    ):
        ratio_for_calculation = None

        # En doğru kaynak, girilen araç değerine denk gelen resmî
        # araç değer bandının finansman oranıdır.
        if (
            vehicle_eval is not None
            and not vehicle_eval.get("blocked")
            and vehicle_eval.get("ratio") is not None
        ):
            ratio_for_calculation = float(
                vehicle_eval.get("ratio")
            )

        # Üründe değer-bandı kuralı yayımlanmamış fakat genel
        # azami finansman oranı yayımlanmışsa onu fallback kullan.
        elif (
            not has_value(
                product.get("vehicle_finance_rules_text")
            )
            and has_value(
                product.get("maximum_financing_ratio")
            )
        ):
            ratio_for_calculation = float(
                product.get("maximum_financing_ratio")
            )

        if ratio_for_calculation is not None:
            ratio_based_amount = (
                float(simulator_amount)
                * ratio_for_calculation
                / 100.0
            )
            ratio_financing_text = tr_money(
                ratio_based_amount
            )

    vehicle_status_text = "—"
    vehicle_insurance_text = "—"

    if is_vehicle_mode:
        (
            vehicle_status_text,
            vehicle_insurance_text,
        ) = vehicle_variant_profile(
            product,
            product_id,
            pricing_rules,
            selected_pricing_variant,
        )

    result_row = {
        "_product_id": product_id,
        "Banka": display_text(
            product.get("bank_name")
        ),
        "Ürün": display_product_name(
            product.get("product_name")
        ),
        "Araç Durumu": vehicle_status_text,
        "Sigorta Durumu": vehicle_insurance_text,
        "Kâr Payı": profit_text,
        "Kâr Payı Oranı": profit_text,
        "Kâr Payı / Fiyatlama": housing_main_profit_text,
        "Vade / Vade Bantları": (
            vehicle_pricing_maturities
            if is_vehicle_mode
            else general_maturity_text
        ),
        "Vade Süresi": general_maturity_text,
        "Azami Vade": housing_main_maturity_text,
        "Taksit Sayısı": housing_installment_text,
        "Tutar / Değer Bazlı Koşullar": (
            vehicle_value_rule_summary_text(product)
            if is_vehicle_mode and vehicle_value_rule_summary_text(product)
            else (amount_dependent_terms_text if amount_dependent_terms_text else "—")
        ),
        "Genel Vade / Vade Bantları": general_maturity_text,
        "Seçili Kategori Taksit Sınırı": selected_category_limit_text,
        "Finansman Tutarı": financing_amount,
        "Gayrimenkul / Ekspertiz Değeri": (
            tr_money(housing_comparison_value)
            if (
                is_housing_mode
                and housing_comparison_value is not None
            )
            else "—"
        ),
        "Finansman Oranı": (
            housing_main_ratio_text
            if is_housing_mode
            else financing_ratio_text
        ),
        "Orana Göre Finansman Tutarı": (
            housing_comparison_financing_text
            if is_housing_mode
            else ratio_financing_text
        ),
        "Tahsis Ücreti": (
            housing_allocation_fee_text
            if is_housing_mode
            else allocation_fee_text
        ),
        "Ekspertiz Ücreti": housing_appraisal_fee_text,
        "İpotek Tesis Ücreti": housing_mortgage_fee_text,
        "Masraf": fee_text,
        "Masraf Bilgisi": housing_other_fee_text,
        "Özel Koşul": condition_text,
        "Resmî Kaynak": product.get(
            "source_url"
        ),
        "Ürün Kaynağı": product.get(
            "source_url"
        ),
        "Ücret Kaynağı": (
            fee_source_url_for_product(
                product_id,
                fee_rules,
            )
        ),
        "Fiyatlama Kaynağı": first_rule_source_url(
            pricing_all_rules,
            product_id,
        ),
    }

    qualitative_values = feature_values_for_product(
        feature_rules,
        product_id,
    )

    result_row["Amaç"] = purpose_value(
        qualitative_values
    )

    # Ürün-özel doğrulanmış semantik düzeltmeler finance_rules/display_metadata
    # içinde tutulur; yanlış çıkarılmış nitel alan ana tabloya sızmaz.
    _display_meta = {}
    try:
        # SQLite: finance_rules_json
        # PostgreSQL: finance_rules
        _finance_rules_raw = product.get("finance_rules_json")

        if _finance_rules_raw is None:
            _finance_rules_raw = product.get("finance_rules")

        if isinstance(_finance_rules_raw, dict):
            _finance_rules_obj = _finance_rules_raw
        elif isinstance(_finance_rules_raw, str):
            _finance_rules_obj = json.loads(
                _finance_rules_raw or "{}"
            )
        else:
            _finance_rules_obj = {}

        if (
            isinstance(_finance_rules_obj, dict)
            and isinstance(
                _finance_rules_obj.get("display_metadata"),
                dict,
            )
        ):
            _display_meta = (
                _finance_rules_obj.get("display_metadata")
                or {}
            )
    except Exception:
        _display_meta = {}

    # STATE_SUPPORT_DISPLAY_PRIORITY
    _state_support_display = str(
        _display_meta.get("state_support_display") or ""
    ).strip()

    _state_support_note = str(
        _display_meta.get("state_support_note") or ""
    ).strip()

    if _state_support_display:
        result_row["Devlet Deste?i / S?bvansiyon"] = (
            _state_support_display
        )

    elif _state_support_note:
        _state_support_match = re.search(
            r"%(\d{1,3})",
            _state_support_note,
        )

        if _state_support_match:
            result_row["Devlet Desteği / Sübvansiyon"] = (
                f"%{_state_support_match.group(1)}'e kadar"
            )
        else:
            result_row["Devlet Desteği / Sübvansiyon"] = "Sübvansiyonlu"
    else:
        result_row["Devlet Desteği / Sübvansiyon"] = "—"

    result_row["Ürün Koşulu"] = join_verified_values(
        _display_meta.get("eligibility_condition")
    )

    if _display_meta.get("verified_usage_purpose"):
        qualitative_values["Kullanım Amacı"] = _display_meta["verified_usage_purpose"]
        qualitative_values["usage_purpose"] = _display_meta["verified_usage_purpose"]
        result_row["Amaç"] = _display_meta["verified_usage_purpose"]
    if _display_meta.get("verified_repayment_structure"):
        qualitative_values["Ödeme / Kullanım Yapısı"] = _display_meta["verified_repayment_structure"]
        qualitative_values["repayment_structure"] = _display_meta["verified_repayment_structure"]
    if _display_meta.get("verified_currency"):
        qualitative_values["Para Birimi"] = _display_meta["verified_currency"]
        qualitative_values["currency"] = _display_meta["verified_currency"]
    if _display_meta.get("verified_channel"):
        qualitative_values["Başvuru / Kanal"] = _display_meta["verified_channel"]
        qualitative_values["application_channel"] = _display_meta["verified_channel"]
    if _display_meta.get("remove_security_type"):
        qualitative_values.pop("Teminat / Güvence", None)
        qualitative_values.pop("security_type", None)

    for source_label, table_label in (
        QUALITATIVE_TABLE_COLUMNS
    ):
        value = str(
            qualitative_values.get(
                source_label,
                "",
            )
            or ""
        ).strip()

        result_row[table_label] = (
            value
            if value
            else "Belirtilmedi"
        )

    # --------------------------------------------------------
    # KATEGORİYE ÖZEL ANA TABLO ALANLARI
    # --------------------------------------------------------
    # Generic sütunları her finansman türüne zorlamak yerine, mevcut
    # doğrulanmış verilerden karar vermeye yarayan ortak alanlar üret.
    # join_verified_values eksik/placeholder alanları atlar; herhangi bir
    # sayısal veya nitel bilgi tahmin edilmez.
    result_row["Kullanım Amacı"] = join_verified_values(
        result_row.get("Amaç")
    )
    result_row["Finansman Yapısı"] = join_verified_values(
        result_row.get("Yapı")
    )
    # Finansman üst limiti ile işlem/kanal limitini birbirine karıştırma.
    # Örn. Albaraka Bayide Finansman'daki 60.000 TL, ürünün azami finansman
    # limiti değil; şubeye gitmeden bayide tamamlanabilen işlem eşiğidir.
    # Jet Ticari Finansman'daki 2.000.000 TL ise gerçek ürün üst limitidir.
    result_row["Finansman Limiti"] = join_verified_values(
        result_row.get("Finansman Tutarı"),
    )
    result_row["İşlem / Kanal Limiti"] = join_verified_values(
        result_row.get("İşlem / Limit"),
    )

    # Bireysel ekranlarla geriye dönük uyumluluk için birleşik alan korunur.
    # Ticari sütun profilleri bu alanı kullanmaz.
    result_row["Limit / Finansman Tutarı"] = join_verified_values(
        result_row.get("Finansman Tutarı"),
        result_row.get("İşlem / Limit"),
    )
    result_row["Vade / Ödeme"] = join_verified_values(
        result_row.get("Vade / Vade Bantları"),
        result_row.get("Ödeme / Kullanım"),
    )
    result_row["Teminat / Güvence"] = join_verified_values(
        result_row.get("Teminat")
    )
    result_row["Enstrüman Türü"] = join_verified_values(result_row.get("Yapı"))
    result_row["Kullanım Alanı"] = join_verified_values(result_row.get("Amaç"))
    result_row["Komisyon / Ücret"] = join_verified_values(result_row.get("Masraf"))
    result_row["Ödeme / Hasat Yapısı"] = join_verified_values(
        result_row.get("Vade / Vade Bantları"), result_row.get("Ödeme / Kullanım")
    )
    result_row["Varlık / Yatırım Türü"] = join_verified_values(result_row.get("Amaç"))
    result_row["Vade / Kira Planı"] = join_verified_values(
        result_row.get("Vade / Vade Bantları"), result_row.get("Ödeme / Kullanım")
    )
    result_row["Maliyet / KDV Yapısı"] = join_verified_values(result_row.get("Maliyet / Avantaj"))

    _digital_value = result_row.get("Dijital")
    _digital_hint = (
        ""
        if is_dashboard_placeholder(_digital_value)
        else f"Dijital: {_digital_value}"
    )
    result_row["Kullanım / Kanal"] = join_verified_values(
        result_row.get("Kanal"),
        _digital_hint,
    )

    result_row["Masraf / Ücretler"] = join_verified_values(
        result_row.get("Masraf")
    )
    result_row["Ürün Koşulları"] = join_verified_values(
        result_row.get("Özel Koşul"),
        result_row.get("Seçili Kategori Taksit Sınırı"),
    )

    if not is_housing_mode:
        # Aynı başlık bütün kategorilerde kullanılır; pricing_guardrails
        # nedeniyle örnek/temsili oranlar güncel fiyatlama gibi gösterilmez.
        # FINANCE_COMMON_SCENARIO_EXACT_RATE_V2
        if strict_common_scenario_mode:

            _exact_group_for_row = (
                _strict_exact_by_product.get(
                    product_id
                )
            )

            result_row[
                "K\u00e2r Pay\u0131 / Fiyatlama"
            ] = _strict_exact_rate_summary(
                _exact_group_for_row
            )

        else:

            result_row[
                "K\u00e2r Pay\u0131 / Fiyatlama"
            ] = join_verified_values(
                result_row.get(
                    "K\u00e2r Pay\u0131"
                )
            )

    _vehicle_age_text = product.get("vehicle_age_rules_text")
    result_row["Araç / Yaş Kapsamı"] = join_verified_values(
        result_row.get("Araç Durumu"),
        _vehicle_age_text,
    )

    result_rows.append(result_row)

    result_context[product_id] = {
        "product": product,
        "category_matches": category_matches,
        "offer_matches": offer_matches,
        "amount_matches": amount_matches_rows,
        "limit_text": limit_text,
        "general_maturity_text": general_maturity_text,
        "selected_category_limit_text": selected_category_limit_text,
        "profit_text": profit_text,
        "vehicle_pricing_maturities": vehicle_pricing_maturities,
        "amount_dependent_terms_text": amount_dependent_terms_text,
        "fee_text": fee_text,
        "allocation_fee_text": allocation_fee_text,
        "housing_main_profit_text": housing_main_profit_text,
        "housing_main_maturity_text": housing_main_maturity_text,
        "housing_main_ratio_text": housing_main_ratio_text,
        "housing_appraisal_fee_text": housing_appraisal_fee_text,
        "housing_mortgage_fee_text": housing_mortgage_fee_text,
        "housing_installment_text": housing_installment_text,
        "housing_other_fee_text": housing_other_fee_text,
        "financing_amount": financing_amount,
        "financing_ratio_text": financing_ratio_text,
        "vehicle_ratio_financing_text": ratio_financing_text,
        "housing_comparison_value": housing_comparison_value,
        "housing_comparison_financing_text": housing_comparison_financing_text,
        "housing_eval": housing_eval,
        "vehicle_status_text": vehicle_status_text,
        "vehicle_insurance_text": vehicle_insurance_text,
        "condition_text": condition_text,
        "vehicle_eval": vehicle_eval,
        "qualitative_values": qualitative_values,
    }


if (
    not qualitative_mode
    and amount_filter_applicable
):
    st.caption(
        "Finansman Tutarı filtresi uygun ürünleri bulmak için kullanılır. "
        "Sonuç tablosundaki ‘Finansman Tutarı’ ise ürünün resmî kaynakta "
        "belirtilen finansman limitini gösterir."
    )

# FINANCE_MAIN_TABLE_POLISH_V2
# Yalnizca ana karsilastirma sunumunu iyilestirir.
# PostgreSQL, product family ve kaynak veri degistirilmez.

_result_product_names = {
    str(row.get("\u00dcr\u00fcn") or "").strip()
    for row in result_rows
}

_result_product_keys = {
    name.casefold()
    .replace("\u0131", "i")
    .replace("\u015f", "s")
    .replace("\u00e7", "c")
    .replace("\u00fc", "u")
    .replace("\u00f6", "o")
    .replace("\u011f", "g")
    for name in _result_product_names
}

_has_elus = any(
    "elus" in name
    for name in _result_product_keys
)

_has_ges = any(
    "cati ges" in name
    for name in _result_product_keys
)

_has_energy_efficiency = any(
    "enerji verimliligi" in name
    for name in _result_product_keys
)

_is_special_mixed_group = (
    len(result_rows) == 4
    and _has_elus
    and _has_ges
    and _has_energy_efficiency
)

_is_single_ges_summary = (
    len(result_rows) == 1
    and _has_ges
)

if _is_single_ges_summary:
    st.subheader(
        "\u00c7at\u0131 GES Finansman\u0131 \u2014 \u00dcr\u00fcn \u00d6zeti"
    )

elif _is_special_mixed_group:
    st.subheader(
        "Di\u011fer / \u00d6zel Ama\u00e7l\u0131 Finansmanlar"
    )
    st.caption(
        "Bu gruptaki \u00fcr\u00fcnler farkl\u0131 kullan\u0131m ama\u00e7lar\u0131na "
        "y\u00f6neliktir. Birebir e\u015fde\u011fer finansman \u00fcr\u00fcnleri "
        "olarak de\u011ferlendirilmemelidir."
    )

else:
    st.subheader(
        f"{selected_family} \u2014 Se\u00e7ili Bankalar\u0131n \u00dcr\u00fcnleri"
    )

if not result_rows:
    if is_vehicle_mode:
        st.warning(
            f"{format_number_tr(simulator_amount)} TL "
            "araç/kasko değeri için seçili bankalarda "
            "doğrulanmış kullandırım kuralına uyan bir "
            "finansman ürünü bulunamadı."
        )
    elif selected_category_key is not None:
        if amount_filter_applicable:
            st.info(
                f"{selected_category_label} kategorisi ve "
                f"{format_number_tr(simulator_amount)} TL için "
                "seçili bankalarda uygulanabilir bir finansman "
                "kuralı bulunamadı."
            )
        else:
            st.info(
                f"{selected_category_label} kategorisi için "
                "seçili bankalarda uygulanabilir bir ürün "
                "bulunamadı."
            )
    else:
        st.info(
            "Seçili filtreler için gösterilecek finansman "
            "ürünü bulunamadı."
        )
    st.stop()

results_df = pd.DataFrame(result_rows)

st.caption(
    f"Toplam {len(results_df)} ürün gösteriliyor. "
    "Seçtiğiniz bankaların bu finansman türündeki tüm ürünleri tek tabloda karşılaştırılır. "
    + (
        "Konut Finansmanı ana tablosu yalnız karşılaştırılabilir finansal kriterleri "
        "gösterir. Bankaya özgü oran matrisi, fiyatlama koşulları ve ayrıntılı masraflar "
        "aşağıdaki Ürün Detayı bölümündedir."
        if is_housing_mode
        else (
            "Resmî kaynakta tutara/değere göre değişen vade, oran veya "
            "fiyatlama varsa tek bir azami değere indirgenmeden bantlarıyla gösterilir."
        )
    )
)

# ============================================================
# KATEGORİYE ÖZEL ANA KARŞILAŞTIRMA SÜTUNLARI
# ============================================================
# Her finansman türüne aynı generic şablonu uygulamak, özellikle ticari
# ürünlerde çok sayıda "Belirtilmedi" sütunu üretip gerçek karar verisini
# görünmez hale getiriyordu. Artık sütunlar finansman alanı + kategoriye göre
# src/finance_column_profiles.py içinden belirlenir.
#
# Kritik güvenlik kuralı:
#   * doğrulanmış veri yoksa sütun gizlenir;
#   * eksik değer için sayı/metin tahmini yapılmaz;
#   * Konut'ta kullanıcı tarafından sabitlenen temel ücret alanları korunur.
_column_profile = get_finance_column_profile(
    selected_scope,
    selected_family,
)

display_columns = select_main_table_columns(
    results_df,
    selected_scope,
    selected_family,
    include_fee_source=True,
)

# Eski generic qualitative listesi artık ana tablo seçiminde kullanılmaz.
# Veriler Ürün Detayı bölümünde korunmaya devam eder.
qualitative_columns: list[str] = []

st.caption(
    "Bu tabloda yalnız seçilen finansman türü için karar vermeye yarayan "
    "ve en az bir üründe resmî kaynaktan doğrulanabilen alanlar gösterilir. "
    "Doğrulanmayan limit, vade, oran veya ücret için tahmin yapılmaz; tamamen "
    "boş kalan sütunlar ana karşılaştırmadan çıkarılır."
)
if _column_profile.description:
    st.caption(f"Karşılaştırma odağı: {_column_profile.description}")

column_config = {
    "Ürün": st.column_config.TextColumn(
        "Ürün Adı",
        width="large",
    ),
    "Kullanım Amacı": st.column_config.TextColumn(
        "Finansman Amacı",
        width="large",
        help="Resmî ürün sayfasında açıkça belirtilen kullanım/finansman amacıdır.",
    ),
    "Finansman Yapısı": st.column_config.TextColumn(
        "Finansman Yapısı",
        width="medium",
        help="Taksitli, limitli, teminatlı veya benzeri yapı yalnız resmî kaynakta doğrulanmışsa gösterilir.",
    ),
    "Ürün Koşulu": st.column_config.TextColumn(
        "Ürün Koşulu",
        width="medium",
        help="Finansmana konu urun veya islem icin resmi kaynakta belirtilen uygunluk kosuludur.",
    ),
    "Devlet Desteği / Sübvansiyon": st.column_config.TextColumn(
        "Devlet Desteği / Sübvansiyon",
        width="large",
        help="Resmî ürün sayfasında belirtilen devlet destekli veya sübvansiyonlu finansman bilgisidir; kâr payı oranı değildir.",
    ),
    "Finansman Limiti": st.column_config.TextColumn(
        "Finansman Limiti",
        width="medium",
        help="Ürünün resmî kaynakta yayımlanan azami/üst finansman tutarıdır. İşlem veya kanal eşiği bu alana taşınmaz.",
    ),
    "İşlem / Kanal Limiti": st.column_config.TextColumn(
        "İşlem / Kanal Limiti",
        width="large",
        help="Şubesiz işlem eşiği, kanal limiti veya benzeri işlem sınırıdır; ürünün azami finansman limiti anlamına gelmez.",
    ),
    "Limit / Finansman Tutarı": st.column_config.TextColumn(
        "Limit / Finansman Tutarı",
        width="large",
        help="Bireysel ürünlerde kullanılan doğrulanmış ürün/finansman limitidir. Ticari ürünlerde finansman ve işlem limitleri ayrı sütunlarda gösterilir.",
    ),
    "Vade / Ödeme": st.column_config.TextColumn(
        "Vade / Ödeme",
        width="large",
        help="Doğrulanmış azami vade, vade bantları ve/veya resmî ödeme yapısını birlikte gösterir.",
    ),
    "Teminat / Güvence": st.column_config.TextColumn(
        "Teminat / Güvence",
        width="medium",
        help="ELÜS, kefalet, kira sertifikası, banka garantisi gibi yalnız resmî kaynakta belirtilen güvence/teminat bilgisidir.",
    ),
    "Kullanım / Kanal": st.column_config.TextColumn(
        "Başvuru / Kullanım Kanalı",
        width="large",
        help="Şube, mobil, internet şubesi, POS vb. doğrulanmış başvuru veya kullanım kanallarıdır.",
    ),
    "Masraf / Ücretler": st.column_config.TextColumn(
        "Masraf / Ücretler",
        width="large",
        help="Yalnız resmî ücret/fiyatlama kaynağında doğrulanan masraf bilgisidir.",
    ),
    "Araç / Yaş Kapsamı": st.column_config.TextColumn(
        "Araç / Yaş Kapsamı",
        width="large",
        help="0 km / 2. el kapsamı ile varsa resmî araç yaşı sınırını gösterir.",
    ),
    "İşlem / Limit": st.column_config.TextColumn(
        "İşlem / Limit",
        width="large",
        help="Gayri nakdi veya özel işlem ürünlerinde resmî işlem/limit bilgisidir.",
    ),
    "Enstrüman Türü": st.column_config.TextColumn("Enstrüman Türü", width="medium"),
    "Kullanım Alanı": st.column_config.TextColumn("Kullanım Alanı", width="large"),
    "Komisyon / Ücret": st.column_config.TextColumn("Komisyon / Ücret", width="medium"),
    "Ödeme / Hasat Yapısı": st.column_config.TextColumn("Vade / Ödeme / Hasat Yapısı", width="large"),
    "Varlık / Yatırım Türü": st.column_config.TextColumn("Varlık / Yatırım Türü", width="large"),
    "Vade / Kira Planı": st.column_config.TextColumn("Vade / Kira Planı", width="large"),
    "Maliyet / KDV Yapısı": st.column_config.TextColumn("Maliyet / KDV Yapısı", width="large"),
    "Para Birimi": st.column_config.TextColumn(
        "Para Birimi",
        width="small",
        help="Yalnız ürün sayfasında açıkça doğrulanan para birimleri gösterilir.",
    ),
    "Dış Ticaret": st.column_config.TextColumn(
        "Dış Ticaret",
        width="small",
        help="Ürün dış ticaret / ihracat / ithalat amacıyla açıkça ilişkilendirilmişse gösterilir.",
    ),
    "Maliyet / Avantaj": st.column_config.TextColumn(
        "Maliyet / Avantaj",
        width="medium",
        help="Vade farksız kullanım, KDV avantajı gibi resmî kaynakta yayımlanan ürün avantajıdır.",
    ),
    "Ödeme / Kullanım": st.column_config.TextColumn(
        "Ödeme / Kullanım",
        width="large",
        help="Erteleme, esnek ödeme veya kullanım yapısı yalnız resmî kaynakta doğrulanmışsa gösterilir.",
    ),
    "Araç Durumu": st.column_config.TextColumn(
        "Araç Durumu",
        width="small",
        help=(
            "Resmî ürün/fiyatlama verisinde açıkça belirtilen "
            "0 km ve/veya 2. El kapsamını gösterir."
        ),
    ),
    "Sigorta Durumu": st.column_config.TextColumn(
        "Sigorta Durumu",
        width="small",
        help=(
            "Kâr payı/fiyatlama resmî olarak Sigortalı ve "
            "Sigortasız seçeneklere ayrılıyorsa gösterilir."
        ),
    ),
    "Kâr Payı / Fiyatlama": st.column_config.TextColumn(
        "Kâr Payı / Fiyatlama",
        width="large",
        help=(
            "Resmî fiyatlama tablosundaki oranı veya oran aralığını gösterir. "
            "Örnek maliyet tablosu genel oran gibi sunulmaz."
        ),
    ),
    "Azami Vade": st.column_config.TextColumn(
        "Azami Vade",
        width="small",
        help=(
            "Resmî ürün sayfasında doğrulanan azami vadeyi gösterir."
        ),
    ),
    "Ekspertiz Ücreti": st.column_config.TextColumn(
        "Ekspertiz Ücreti",
        width="large",
        help=(
            "Ekspertiz/değerleme için resmî kaynakta doğrulanan ücret veya "
            "maliyet esasını gösterir."
        ),
    ),
    "İpotek Tesis Ücreti": st.column_config.TextColumn(
        "İpotek Tesis Ücreti",
        width="large",
        help=(
            "İpotek tesisine ilişkin resmî ücret veya maliyet esasını gösterir."
        ),
    ),
    "Kâr Payı Oranı": st.column_config.TextColumn(
        "Kâr Payı Oranı",
        width="medium",
        help=(
            "Resmî fiyatlama verisindeki kâr payı oranını veya "
            "oranın hangi koşullara göre değiştiğini gösterir."
        ),
    ),
    "Vade Süresi": st.column_config.TextColumn(
        "Vade Süresi",
        width="medium",
        help=(
            "Resmî kaynakta yayımlanan azami vade veya vade bantlarını gösterir."
        ),
    ),
    "Taksit Sayısı": st.column_config.TextColumn(
        "Taksit Sayısı",
        width="medium",
        help=(
            "Kaynakta açık taksit sayısı varsa onu; fiyatlama planları varsa "
            "planlardaki ödeme dönemlerini gösterir."
        ),
    ),
    "Finansman Tutarı": st.column_config.TextColumn(
        "Finansman Tutarı",
        width="large",
        help=(
            "Bankanın yayımladığı finansman limiti veya ekspertiz/değer "
            "oranına bağlı finansman yapısını gösterir. Kullanıcı girdisi değildir."
        ),
    ),
    "Finansman Oranı": st.column_config.TextColumn(
        "Finansman Oranı",
        width="medium",
        help=(
            "Gayrimenkul/ekspertiz değerinin ne kadarının finanse edilebildiğini gösterir. "
            "Enerji sınıfı veya konut sahipliği gibi ek koşullar varsa detaya yönlendirir."
        ),
    ),
    "Masraf Bilgisi": st.column_config.TextColumn(
        "Masraf Bilgisi",
        width="large",
        help=(
            "Tahsis ücreti dışındaki resmî ekspertiz, ipotek veya diğer "
            "ücret/masraf kayıtlarını gösterir."
        ),
    ),
    "Vade / Vade Bantları": st.column_config.TextColumn(
        "Vade / Vade Bantları",
        width="medium",
        help=(
            "Resmî kaynakta yayımlanan gerçek vade seçeneklerini "
            "veya tutara/değere göre vade bantlarını gösterir."
        ),
    ),
    "Tutar / Değer Bazlı Koşullar": st.column_config.TextColumn(
        "Değer → Oran → Azami Vade",
        width="large",
        help=(
            "Resmî kaynakta tutara veya varlık değerine göre vade, "
            "finansman oranı ya da kâr payı değişiyorsa tüm bantları gösterir."
        ),
    ),
    "Genel Vade / Vade Bantları": st.column_config.TextColumn(
        "Genel Vade / Vade Bantları",
        width="large",
    ),
    "Seçili Kategori Taksit Sınırı": st.column_config.TextColumn(
        "Seçili Kategori Taksit Sınırı",
        width="medium",
    ),
    "Orana Göre Finansman Tutarı": st.column_config.TextColumn(
        "Orana Göre Finansman Tutarı",
        width="medium",
        help=(
            "Girilen araç/kasko veya gayrimenkul/ekspertiz değeri ile "
            "uygulanabilir resmî finansman oranından hesaplanır. "
            "Kâr payı hesabı değildir."
        ),
    ),
    "Gayrimenkul / Ekspertiz Değeri": st.column_config.TextColumn(
        "Gayrimenkul / Ekspertiz Değeri",
        width="medium",
        help=(
            "Kullanıcının karşılaştırma için girdiği gayrimenkul/ekspertiz değeridir; banka limiti değildir."
        ),
    ),
    "Tahsis Ücreti": st.column_config.TextColumn(
        "Tahsis Ücreti",
        width="small",
        help=(
            "Resmî fiyatlama veya ücret tablosunda yayımlanan "
            "finansman tahsis ücretini gösterir."
        ),
    ),
    "Ürün Kaynağı": st.column_config.LinkColumn(
        "Ürün Kaynağı",
        display_text="Aç",
        help="Finansman ürününün resmî ürün sayfası.",
    ),
    "Ücret Kaynağı": st.column_config.LinkColumn(
        "Ücret Kaynağı",
        display_text="Aç",
        help=(
            "Tahsis/ekspertiz/ipotek gibi masraflar ayrı bir resmî ücret "
            "tarifesinden geliyorsa doğrudan o kaynağı açar."
        ),
    ),
    "Resmî Kaynak": st.column_config.LinkColumn(
        "Resmî Kaynak",
        display_text="Aç",
    ),
}

for label in qualitative_columns:
    if label == "Amaç":
        width = "large"
    elif label in (
        "Hedef Kitle",
        "Yapı",
        "Teminat",
        "Ödeme / Kullanım",
    ):
        width = "medium"
    else:
        width = "small"

    column_config[label] = (
        st.column_config.TextColumn(
            label,
            width=width,
        )
    )

# KARŞILAŞTIRMA TEK TABLODA gösterilir.
# Finansman Alanı + Finansman Türü + Bankalar seçildiğinde seçili bankaların bu ailedeki
# tüm gerçek ürünleri, banka ve resmî ürün adı korunarak aynı tabloda yer alır.
# Böylece ürünler bankalar arasında doğrudan karşılaştırılabilir.
results_display = results_df.copy()

# Kullanıcının banka seçim sırasını koru; aynı banka içinde ürün adını sırala.
bank_order = {
    str(bank_name): index
    for index, bank_name in enumerate(selected_banks)
}
results_display["_bank_order"] = (
    results_display["Banka"]
    .astype(str)
    .map(bank_order)
    .fillna(len(bank_order))
)
results_display["_product_sort"] = (
    results_display["Ürün"]
    .astype(str)
    .str.casefold()
)
results_display = (
    results_display
    .sort_values(["_bank_order", "_product_sort"], kind="stable")
    .drop(columns=["_bank_order", "_product_sort"])
)

# FINANCE_MAIN_TABLE_POLISH_V1
# ------------------------------------------------------------
# Yalnizca ana karsilastirma tablosunun sunum katmanini temizler.
# PostgreSQL, source-of-truth veri ve urun kimlikleri degistirilmez.
# ------------------------------------------------------------

def _main_table_clean_text(value):
    if value is None:
        return "\u2014"

    try:
        if pd.isna(value):
            return "\u2014"
    except Exception:
        pass

    if not isinstance(value, str):
        return value

    text = value.strip()

    if text in {
        "",
        "Belirtilmedi",
        "None",
        "nan",
    }:
        return "\u2014"

    # "12 aya kadar \u00b7 12 aya kadar" gibi serializer tekrarlarini
    # semantigi bozmadan temizle.
    if " \u00b7 " in text:
        pieces = [
            part.strip()
            for part in text.split(" \u00b7 ")
            if part.strip()
        ]

        unique = []
        seen = set()

        for part in pieces:
            key = (
                part.casefold()
                .replace("\u0131", "i")
                .replace("\u0130", "i")
                .strip(" .;,")
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(part)

        text = " \u00b7 ".join(unique)

    return text if text else "\u2014"


# Sadece kullaniciya gosterilecek kopyayi temizle.
results_display = results_display.copy()

for _column in results_display.columns:
    if (
        results_display[_column].dtype == object
        or pd.api.types.is_string_dtype(
            results_display[_column]
        )
    ):
        results_display[_column] = (
            results_display[_column]
            .map(_main_table_clean_text)
        )


# ------------------------------------------------------------
# VERIFIED STANDARD SCENARIO DISPLAY
# ------------------------------------------------------------
# Yalnizca ayni benchmark'a ait dogrulanmis scenario snapshotlari
# ana karsilastirma tablosuna eklenir.
#
# Scenario orani urunun genel profit_share_rate degeri DEGILDIR.
# ------------------------------------------------------------

_SCENARIO_COLUMN = "\u00d6rnek Hesaplama"

# EMLAK_SCENARIO_BENCHMARK_KEY_V1
# Genel dogrulanmis benchmark 100.000 TL / 36 ay.
# Turkiye Emlak Katilim icin resmi sayfadaki
# 50.000 TL uzeri vade kisiti nedeniyle 100.000 TL / 24 ay.
_SCENARIO_DEFAULT_KEY = "benchmark_100000_36"
_EMLAK_SCENARIO_KEY = "benchmark_100000_24"


def _scenario_number_tr(
    value,
    digits=2,
):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    text = f"{number:,.{digits}f}"

    return (
        text
        .replace(",", "\u0000")
        .replace(".", ",")
        .replace("\u0000", ".")
    )


def _scenario_variant_label(value):
    key = (
        str(value or "")
        .strip()
        .casefold()
    )

    # FINANCE_SCENARIO_DISPLAY_LABELS_V2
    labels = {
        "sigortali": "Sigortal\u0131",
        "sigortasiz": "Sigortas\u0131z",

        "0km_sigortali":
            "0 km \u00b7 Sigortal\u0131",

        "0km_sigortasiz":
            "0 km \u00b7 Sigortas\u0131z",

        "2el_sigortali":
            "2. El \u00b7 Sigortal\u0131",

        "2el_sigortasiz":
            "2. El \u00b7 Sigortas\u0131z",

        "ilk_konut_sigortali":
            "\u0130lk Konut \u00b7 Sigortal\u0131",

        "ilk_konut_sigortasiz":
            "\u0130lk Konut \u00b7 Sigortas\u0131z",

        "mevcut_konut_sigortali":
            "Mevcut Konut \u00b7 Sigortal\u0131",

        "mevcut_konut_sigortasiz":
            "Mevcut Konut \u00b7 Sigortas\u0131z",

        # KUVEYT_SCENARIO_DISPLAY_LABELS_V1
        "binek_dijital":
            "Binek \u00b7 Dijital",

        "yeni_binek":
            "Yeni \u00b7 Binek",

        "2el_binek":
            "2. El \u00b7 Binek",

        # ALBARAKA_SCENARIO_DISPLAY_LABELS_V1
        "0km":
            "S\u0131f\u0131r KM",

        "2el":
            "2. El",

        "ilk_ev":
            "\u0130lk Ev",

        "mevcut_konut":
            "2. ve Sonraki Konut",

        # VAKIF_SCENARIO_DISPLAY_LABELS_V1
        "sifir_konut":
            "S\u0131f\u0131r Konut",

        "2el_konut":
            "2. El Konut",

        # EMLAK_SCENARIO_DISPLAY_LABELS_V1
        "yeni_konut":
            "Yeni Konut",

        "standard": "Standart",
        "standart": "Standart",
    }

    return labels.get(
        key,
        str(value or "Standart").strip()
        or "Standart",
    )


def _scenario_row_text(row):
    label = _scenario_variant_label(
        row.get("input_variant")
    )

    # ALBARAKA_SCENARIO_STANDARD_LABEL_HIDE_V1
    # VAKIF_SCENARIO_STANDARD_LABEL_HIDE_V1
    # Albaraka ve Vakif Katilim'da tek "standard"
    # senaryo bir varyant secenegi degildir.
    # Kullaniciya teknik "Standart" etiketi
    # gostermeyelim.
    _scenario_variant_key = (
        str(
            row.get(
                "input_variant"
            )
            or ""
        )
        .strip()
        .casefold()
    )

    _scenario_source_url_key = (
        str(
            row.get(
                "source_url"
            )
            or ""
        )
        .strip()
        .casefold()
    )

    # EMLAK_SCENARIO_SOURCE_LABELS_V1
    if (
        "emlakkatilim.com.tr"
        in _scenario_source_url_key
    ):
        if _scenario_variant_key == "0km":
            label = "0 Km"
        elif _scenario_variant_key == "2el":
            label = "2. El"
        elif _scenario_variant_key == "yeni_konut":
            label = "Yeni Konut"

    if (
        _scenario_variant_key
        in {
            "standard",
            "standart",
        }
        and any(
            domain
            in _scenario_source_url_key
            for domain in (
                "albaraka.com.tr",
                "vakifkatilim.com.tr",
                # ZIRAAT_SCENARIO_STANDARD_LABEL_HIDE_V1
                "ziraatkatilim.com.tr",
                # EMLAK_SCENARIO_STANDARD_LABEL_HIDE_V1
                "emlakkatilim.com.tr",
            )
        )
    ):
        label = ""

    rate = _scenario_number_tr(
        row.get("profit_share_rate"),
        2,
    )

    monthly = _scenario_number_tr(
        row.get("monthly_installment"),
        2,
    )

    total = _scenario_number_tr(
        row.get("total_repayment"),
        2,
    )

    parts = (
        [label]
        if label
        else []
    )

    # EMLAK_SCENARIO_BENCHMARK_DISPLAY_V1
    if (
        "emlakkatilim.com.tr"
        in _scenario_source_url_key
        and str(
            row.get(
                "scenario_key"
            )
            or ""
        ).strip()
        == _EMLAK_SCENARIO_KEY
    ):
        _scenario_amount = (
            _scenario_number_tr(
                row.get(
                    "input_amount"
                ),
                0,
            )
        )

        try:
            _scenario_months = int(
                float(
                    row.get(
                        "input_maturity_months"
                    )
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            _scenario_months = None

        if (
            _scenario_amount
            and _scenario_months
        ):
            parts.append(
                f"{_scenario_amount} TL / "
                f"{_scenario_months} ay"
            )

    if rate:
        parts.append(
            f"%{rate}"
        )

    if monthly:
        parts.append(
            f"{monthly} TL/ay"
        )

    if total:
        parts.append(
            f"{total} TL taksit toplam\u0131"
        )

    # VAKIF_SCENARIO_FEE_DISPLAY_V1
    # Bu masraflar canonical urun ucreti degildir.
    # Yalnizca resmi canli calculator scenario
    # response'unda donen degerlerdir.
    if (
        "vakifkatilim.com.tr"
        in _scenario_source_url_key
    ):
        _scenario_appraisal = (
            _scenario_number_tr(
                row.get(
                    "appraisal_fee"
                ),
                2,
            )
        )

        _scenario_mortgage = (
            _scenario_number_tr(
                row.get(
                    "mortgage_fee"
                ),
                2,
            )
        )

        try:
            _scenario_appraisal_positive = (
                float(
                    row.get(
                        "appraisal_fee"
                    )
                    or 0
                )
                > 0
            )
        except (
            TypeError,
            ValueError,
        ):
            _scenario_appraisal_positive = False

        try:
            _scenario_mortgage_positive = (
                float(
                    row.get(
                        "mortgage_fee"
                    )
                    or 0
                )
                > 0
            )
        except (
            TypeError,
            ValueError,
        ):
            _scenario_mortgage_positive = False

        if (
            _scenario_appraisal_positive
            and _scenario_appraisal
        ):
            parts.append(
                "Ekspertiz: "
                f"{_scenario_appraisal} TL"
            )

        if (
            _scenario_mortgage_positive
            and _scenario_mortgage
        ):
            parts.append(
                "\u0130potek: "
                f"{_scenario_mortgage} TL"
            )

    # EMLAK_SCENARIO_FEE_DISPLAY_V1
    # Turkiye Emlak Katilim resmi calculator snapshot
    # masraflari. TotalExpense banka tarafindan donen
    # deger olarak aynen gosterilir; yeniden hesaplanmaz.
    if (
        "emlakkatilim.com.tr"
        in _scenario_source_url_key
    ):
        _emlak_fee_fields = (
            (
                "Tahsis",
                "allocation_fee",
            ),
            (
                "Ekspertiz (hesaplama arac?)",
                "appraisal_fee",
            ),
            (
                "\u0130potek",
                "mortgage_fee",
            ),
            (
                "Toplam Masraf",
                "total_fees",
            ),
        )

        for (
            _emlak_fee_label,
            _emlak_fee_field,
        ) in _emlak_fee_fields:

            _emlak_fee_raw = row.get(
                _emlak_fee_field
            )

            try:
                _emlak_fee_positive = (
                    float(
                        _emlak_fee_raw
                        or 0
                    )
                    > 0
                )
            except (
                TypeError,
                ValueError,
            ):
                _emlak_fee_positive = False

            if not _emlak_fee_positive:
                continue

            _emlak_fee_text = (
                _scenario_number_tr(
                    _emlak_fee_raw,
                    2,
                )
            )

            if _emlak_fee_text:
                parts.append(
                    f"{_emlak_fee_label}: "
                    f"{_emlak_fee_text} TL"
                )

    return " \u00b7 ".join(parts)


_benchmark_scenarios = pd.DataFrame()

if (
    isinstance(
        finance_scenarios,
        pd.DataFrame,
    )
    and not finance_scenarios.empty
    and "scenario_key"
        in finance_scenarios.columns
):
    # EMLAK_SCENARIO_FILTER_V1
    _scenario_key_series = (
        finance_scenarios[
            "scenario_key"
        ]
        .fillna("")
        .astype(str)
    )

    if "source_url" in finance_scenarios.columns:
        _scenario_source_series = (
            finance_scenarios[
                "source_url"
            ]
            .fillna("")
            .astype(str)
            .str.casefold()
        )
    else:
        _scenario_source_series = pd.Series(
            "",
            index=finance_scenarios.index,
            dtype="object",
        )

    # FINANCE_COMMON_SCENARIO_EXACT_MATCH_V1
    #
    # In strict comparison mode a verified snapshot is usable
    # only when amount AND maturity exactly match user inputs.
    if (
        strict_common_scenario_mode
        and simulator_amount is not None
        and selected_maturity is not None
    ):

        _benchmark_scenarios = (
            filter_exact_verified_scenarios(
                finance_scenarios,
                amount=float(
                    simulator_amount
                ),
                maturity=int(
                    selected_maturity
                ),
            )
        )

    else:

        _scenario_default_mask = (
            _scenario_key_series
            == _SCENARIO_DEFAULT_KEY
        )

        _scenario_emlak_mask = (
            (
                _scenario_key_series
                == _EMLAK_SCENARIO_KEY
            )
            &
            _scenario_source_series.str.contains(
                "emlakkatilim.com.tr",
                regex=False,
            )
        )

        _benchmark_scenarios = (
            finance_scenarios[
                _scenario_default_mask
                |
                _scenario_emlak_mask
            ]
            .copy()
        )


if not _benchmark_scenarios.empty:

    _scenario_by_product_id = {}

    for (
        _scenario_product_id,
        _scenario_group,
    ) in _benchmark_scenarios.groupby(
        "product_id",
        sort=False,
    ):

        _scenario_group = (
            _scenario_group
            .copy()
        )

        _scenario_group[
            "_variant_order"
        ] = (
            _scenario_group[
                "input_variant"
            ]
            .astype(str)
            .str.casefold()
            .map(
                {
                    "sigortali": 0,
                    "sigortasiz": 1,

                    "0km_sigortali": 0,
                    "0km_sigortasiz": 1,
                    "2el_sigortali": 2,
                    "2el_sigortasiz": 3,

                    "ilk_konut_sigortali": 0,
                    "ilk_konut_sigortasiz": 1,
                    "mevcut_konut_sigortali": 2,
                    "mevcut_konut_sigortasiz": 3,

                    "binek_dijital": 0,
                    "yeni_binek": 0,
                    "2el_binek": 1,

                    # ALBARAKA_SCENARIO_ORDER_V1
                    "0km": 0,
                    "2el": 1,
                    "ilk_ev": 0,
                    "mevcut_konut": 1,

                    # VAKIF_SCENARIO_ORDER_V1
                    "sifir_konut": 0,
                    "2el_konut": 1,

                    # EMLAK_SCENARIO_ORDER_V1
                    "yeni_konut": 0,
                }
            )
            .fillna(9)
        )

        _scenario_group = (
            _scenario_group
            .sort_values(
                [
                    "_variant_order",
                    "input_variant",
                ],
                kind="stable",
            )
        )

        _scenario_texts = [
            _scenario_row_text(
                _scenario_row
            )
            for _, _scenario_row
            in _scenario_group.iterrows()
        ]

        _scenario_texts = [
            value
            for value in _scenario_texts
            if value
        ]

        if _scenario_texts:
            _scenario_by_product_id[
                int(_scenario_product_id)
            ] = " | ".join(
                _scenario_texts
            )


    # FINANCE_SCENARIO_IDENTITY_FIX_V2
    # UI katmani urun adlarindaki dipnot isaretlerini veya
    # belirli gorunur etiketleri temizleyebilir.
    # Scenario-product baglantisi bu sunum farkindan etkilenmemeli.
    def _scenario_identity_key(
        bank_name,
        product_name,
    ):
        _bank = (
            str(bank_name or "")
            .strip()
            .casefold()
        )

        _product = str(
            product_name or ""
        ).strip()

        # Dipnot / yildiz isaretlerini temizle.
        _product = re.sub(
            r"\s*[\*\u2020\u2021#]+\s*$",
            "",
            _product,
        )

        # Emlak UI temizliginde kullanilan gorunur suffix.
        _product = re.sub(
            r"\s*\|\s*T\u00fcrkiye Emlak "
            r"Kat\u0131l\u0131m Bankas\u0131\s*$",
            "",
            _product,
            flags=re.IGNORECASE,
        )

        _product = re.sub(
            r"\s+",
            " ",
            _product,
        ).strip().casefold()

        return (
            _bank,
            _product,
        )


    _product_id_by_display_key = {}

    for _, _selected_row in selected.iterrows():

        try:
            _selected_product_id = int(
                _selected_row.get("id")
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        _key = _scenario_identity_key(
            _selected_row.get(
                "bank_name"
            ),
            _selected_row.get(
                "product_name"
            ),
        )

        _product_id_by_display_key[
            _key
        ] = _selected_product_id


    def _scenario_for_display_row(row):
        _key = _scenario_identity_key(
            row.get("Banka"),
            row.get("\u00dcr\u00fcn"),
        )

        _product_id = (
            _product_id_by_display_key
            .get(_key)
        )

        if _product_id is None:
            return (
                "Hen\u00fcz do\u011frulanmad\u0131"
            )

        return (
            _scenario_by_product_id.get(
                int(_product_id)
            )
            or (
                "Hen\u00fcz do\u011frulanmad\u0131"
            )
        )


    results_display[
        _SCENARIO_COLUMN
    ] = results_display.apply(
        _scenario_for_display_row,
        axis=1,
    )

    # VAKIF_VEHICLE_SCOPE_DISPLAY_V1
    # ID=286 Tasit Finansmani resmi calculator'da
    # hem 0 km hem 2. El olarak hesaplanabiliyor.
    # Canonical DB verisi degistirilmeden yalnizca
    # gorunur tablo kapsami duzeltilir.
    _vakif_vehicle_scope_column = (
        "Ara\u00e7 / Ya\u015f Kapsam\u0131"
    )

    if (
        _vakif_vehicle_scope_column
        in results_display.columns
    ):

        def _vakif_vehicle_scope_for_display_row(
            row,
        ):
            _key = _scenario_identity_key(
                row.get("Banka"),
                row.get("\u00dcr\u00fcn"),
            )

            _product_id = (
                _product_id_by_display_key
                .get(_key)
            )

            if _product_id == 286:
                return (
                    "0 km \u00b7 2. El"
                )

            return row.get(
                _vakif_vehicle_scope_column
            )

        results_display[
            _vakif_vehicle_scope_column
        ] = results_display.apply(
            _vakif_vehicle_scope_for_display_row,
            axis=1,
        )

    if (
        _SCENARIO_COLUMN
        not in display_columns
    ):
        if (
            "\u00dcr\u00fcn Kayna\u011f\u0131"
            in display_columns
        ):
            _scenario_insert_index = (
                display_columns.index(
                    "\u00dcr\u00fcn Kayna\u011f\u0131"
                )
            )

            display_columns.insert(
                _scenario_insert_index,
                _SCENARIO_COLUMN,
            )

        else:
            display_columns.append(
                _SCENARIO_COLUMN
            )

    column_config[
        _SCENARIO_COLUMN
    ] = st.column_config.TextColumn(
        _SCENARIO_COLUMN,
        width="large",
        help=(
            "100.000 TL / 36 ay standart senaryosu. "
            "Buradaki oran ve taksitler urunun genel "
            "fiyatlamasi degil, dogrulanmis ornek "
            "hesaplama snapshotidir."
        ),
    )


def _main_table_meaningful_ratio(column_name):
    if column_name not in results_display.columns:
        return 0.0

    series = (
        results_display[column_name]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    placeholders = {
        "",
        "\u2014",
        "-",
        "Belirtilmedi",
        "None",
        "nan",
        "Kaynakta do\u011frulanmad\u0131",
        "Kaynakta yay\u0131mlanmam\u0131\u015f",
        "Kaynakta say\u0131sal de\u011fer yay\u0131mlanmam\u0131\u015f",
        "Kaynakta say\u0131sal de\u011fer yok",
    }

    meaningful = ~series.isin(placeholders)

    if len(series) == 0:
        return 0.0

    return float(
        meaningful.sum()
    ) / float(len(series))


# Ana tabloda sadece karar verisine donusen kolonlari tut.
# Bir-iki urunde dolu olup geri kalan tum tabloda bos kalan
# kolonlar Urun Detayi bolumunde korunmaya devam eder.
#
# Konut masraf kolonlari kullanici icin kritik oldugundan
# housing modunda bu yogunluk filtresine sokulmaz.
_sparse_candidates = {
    "Finansman Yap\u0131s\u0131",
    "Finansman Limiti",
    "\u0130\u015flem / Kanal Limiti",
    "\u0130\u015flem / Limit",
    "Para Birimi",
    "Teminat / G\u00fcvence",
    "Kullan\u0131m / Kanal",
    "Vade / \u00d6deme",
    "Ekspertiz \u00dccreti",
    "\u0130potek Tesis \u00dccreti",
}

if (
    not is_housing_mode
    and len(results_display) >= 4
):
    _clean_display_columns = []

    for _column in display_columns:
        if _column not in _sparse_candidates:
            _clean_display_columns.append(
                _column
            )
            continue

        _ratio = _main_table_meaningful_ratio(
            _column
        )

        # En az dort urunlu bir tabloda verinin dortte birinden
        # azinda dolu olan karar kolonu ana tabloda gizlenir.
        # Veri kaybolmaz; Urun Detayi bolumunde korunur.
        if _ratio >= 0.25:
            _clean_display_columns.append(
                _column
            )

    display_columns = _clean_display_columns


# ------------------------------------------------------------
# TABLO BAZLI SON YO?UNLUK TEMIZLIGI
# ------------------------------------------------------------

_v2_sparse_candidates = {
    # Ihtiyac / bireysel
    "Limit / Finansman Tutar\u0131",
    "Tahsis \u00dccreti",
    "\u00d6deme / Kullan\u0131m",

    # Gayrimenkul
    "Ekspertiz \u00dccreti",
    "\u0130potek Tesis \u00dccreti",
    "Masraf / \u00dccretler",

    # Alisveris / dijital
    "\u00dcr\u00fcn Ko\u015fullar\u0131",
    "Maliyet / Avantaj",

    # Ticari / gayri nakdi
    "Finansman Yap\u0131s\u0131",
    "Finansman Limiti",
    "\u0130\u015flem / Kanal Limiti",
    "\u0130\u015flem / Limit",
    "Para Birimi",
    "Teminat / G\u00fcvence",
    "Kullan\u0131m / Kanal",
    "Vade / \u00d6deme",

    # Tarim
    "\u00dcr\u00fcn Ko\u015fulu",
    "Finansman Oran\u0131",
    "\u00d6deme / Hasat Yap\u0131s\u0131",

    # Leasing
    "Varl\u0131k / Yat\u0131r\u0131m T\u00fcr\u00fc",
    "Vade / Kira Plan\u0131",
    "Maliyet / KDV Yap\u0131s\u0131",
}

_family_key_v2 = (
    str(selected_family or "")
    .casefold()
    .replace("\u0131", "i")
    .replace("\u015f", "s")
    .replace("\u00e7", "c")
    .replace("\u00fc", "u")
    .replace("\u00f6", "o")
    .replace("\u011f", "g")
)

if (
    not is_housing_mode
    and len(results_display) >= 4
):
    _v2_threshold = 0.25

    # Leasing tablosu 11 urunde cok asimetrik oldugu icin
    # ana tabloda daha yuksek kapsama esigi kullan.
    if "leasing" in _family_key_v2:
        _v2_threshold = 0.40

    # D?rt urunluk heterojen grupta tek bir urunde bulunan
    # alan karsilastirma kolonu sayilmaz.
    if _is_special_mixed_group:
        _v2_threshold = 0.50

    _v2_columns = []

    for _column in display_columns:

        if _column not in _v2_sparse_candidates:
            _v2_columns.append(
                _column
            )
            continue

        _ratio = _main_table_meaningful_ratio(
            _column
        )

        if _ratio >= _v2_threshold:
            _v2_columns.append(
                _column
            )

    display_columns = _v2_columns


# FINANCE_MAIN_TABLE_POLISH_V3
# ------------------------------------------------------------
# Gercek exportlardan sonra kalan son sunum tekrarlarini temizler.
# Veri ve PostgreSQL degistirilmez.
# ------------------------------------------------------------

_family_v3 = (
    str(selected_family or "")
    .casefold()
    .replace("\u0131", "i")
    .replace("\u015f", "s")
    .replace("\u00e7", "c")
    .replace("\u00fc", "u")
    .replace("\u00f6", "o")
    .replace("\u011f", "g")
)

# Ihtiyac:
# 50 urunun yalniz 13'unde dolu ve siklikla Vade/Odeme
# bilgisini tekrar eden kolon ana tablodan kaldirilir.
if (
    "ihtiyac" in _family_v3
    and "\u00d6deme / Kullan\u0131m" in display_columns
):
    display_columns.remove(
        "\u00d6deme / Kullan\u0131m"
    )

# Gayrimenkul:
# Ekspertiz/ipotek gibi seyrek masraf ayrintilari Urun
# Detayi'nda zaten korunuyor. Ana tabloyu genisletmesin.
if (
    "gayrimenkul" in _family_v3
    and not is_housing_mode
    and "Masraf / \u00dccretler" in display_columns
):
    display_columns.remove(
        "Masraf / \u00dccretler"
    )

# Arac:
# Masraf/Ucretler mevcut exportta esas olarak Tahsis
# Ucreti kolonunu tekrar ediyor.
if (
    is_vehicle_mode
    and "Masraf / \u00dccretler" in display_columns
):
    display_columns.remove(
        "Masraf / \u00dccretler"
    )

# 4 urunluk heterojen ozel-amacli grupta yalniz bir
# urunde dolu olan alanlar karsilastirma degeri uretmiyor.
if _is_special_mixed_group:
    for _column in (
        "Alt T\u00fcr",
        "Kullan\u0131m Amac\u0131",
    ):
        if (
            _column in display_columns
            and _main_table_meaningful_ratio(
                _column
            ) < 0.50
        ):
            display_columns.remove(
                _column
            )


# FINANCE_MAIN_TABLE_POLISH_V4
# ------------------------------------------------------------
# Gercek V3 exportlarindan sonra kalan son seyrek kolonlar.
# Yalnizca ana tablo sunumu degisir.
# PostgreSQL ve urun verisi degistirilmez.
# ------------------------------------------------------------

# TARIM
# Hedef Kitle / Finansman Yapisi / Devlet Destegi korunur.
# Odeme-Hasat yalniz 7/25 urunde dolu oldugu icin ana tablodan
# kaldirilir; Urun Detayi'ndaki veri korunur.
if (
    "Hedef Kitle" in results_display.columns
    and "Devlet Deste\u011fi / S\u00fcbvansiyon"
        in results_display.columns
):
    if "\u00d6deme / Hasat Yap\u0131s\u0131" in display_columns:
        display_columns.remove(
            "\u00d6deme / Hasat Yap\u0131s\u0131"
        )


# GAYRI NAKDI
# Enstruman ve kullanim alani ana karar kolonlaridir.
# Para Birimi yalniz 10/32 urunde dolu oldugu icin detayda kalir.
if (
    "Enstr\u00fcman T\u00fcr\u00fc" in results_display.columns
    and "Kullan\u0131m Alan\u0131" in results_display.columns
):
    if "Para Birimi" in display_columns:
        display_columns.remove(
            "Para Birimi"
        )


# TICARI
# 76 urunluk genel ticari tabloda Vade/Odeme ve
# Kullanim/Kanal yalniz 20'ser urunde dolu.
# Kullan?m Amaci ise anlamli kapsama sahip oldugu icin korunur.
_is_general_commercial_v4 = (
    len(results_display) >= 50
    and "Kullan\u0131m Amac\u0131"
        in results_display.columns
    and "Vade / \u00d6deme"
        in results_display.columns
    and "Enstr\u00fcman T\u00fcr\u00fc"
        not in results_display.columns
    and "Hedef Kitle"
        not in results_display.columns
)

if _is_general_commercial_v4:
    for _column in (
        "Vade / \u00d6deme",
        "Kullan\u0131m / Kanal",
    ):
        if _column in display_columns:
            display_columns.remove(
                _column
            )


# ------------------------------------------------------------
# TEK URUNLU GES -> KARSILASTIRMA TABLOSU YERINE URUN OZETI
# ------------------------------------------------------------

if _is_single_ges_summary:

    _single_row = results_display.iloc[0]

    with st.container(border=True):

        st.markdown(
            "**Banka:** "
            + str(
                _single_row.get("Banka")
                or "\u2014"
            )
        )

        st.markdown(
            "**\u00dcr\u00fcn:** "
            + str(
                _single_row.get("\u00dcr\u00fcn")
                or "\u2014"
            )
        )

        for _column in display_columns:

            if _column in {
                "Banka",
                "\u00dcr\u00fcn",
                "\u00dcr\u00fcn Kayna\u011f\u0131",
            }:
                continue

            _value = _single_row.get(
                _column
            )

            _text = str(
                _value
                if _value is not None
                else ""
            ).strip()

            if _text in {
                "",
                "\u2014",
                "Belirtilmedi",
                "None",
                "nan",
                "Kaynakta do\u011frulanmad\u0131",
                "Kaynakta yay\u0131mlanmam\u0131\u015f",
            }:
                continue

            st.markdown(
                f"**{_column}:** {_text}"
            )

        _source = str(
            _single_row.get(
                "\u00dcr\u00fcn Kayna\u011f\u0131"
            )
            or ""
        ).strip()

        if _source.startswith(
            ("http://", "https://")
        ):
            st.markdown(
                f"[\u00dcr\u00fcn Kayna\u011f\u0131]({_source})"
            )

    st.caption(
        "Bu ba\u015fl\u0131kta tek bir \u00fcr\u00fcn bulundu\u011fu i\u00e7in "
        "kar\u015f\u0131la\u015ft\u0131rma tablosu yerine \u00fcr\u00fcn \u00f6zeti g\u00f6steriliyor."
    )

else:
    st.dataframe(
        results_display[display_columns],
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
    )


# ============================================================
# SEÇİLEN ÜRÜN DETAYI — AYNI DASHBOARD
# ============================================================
st.subheader("Ürün Detayı")

# Detay seçimini banka -> ürün olarak iki aşamaya ayır.
# Böylece çok bankalı karşılaştırmada ürün detayına ulaşmak daha kolaydır.
detail_bank_options = list(
    dict.fromkeys(
        str(row["Banka"])
        for row in result_rows
    )
)

detail_select_bank_col, detail_select_product_col = st.columns(2)

with detail_select_bank_col:
    detail_bank = st.selectbox(
        "Detay Bankası",
        options=detail_bank_options,
    )

detail_rows_for_bank = [
    row
    for row in result_rows
    if str(row["Banka"]) == str(detail_bank)
]

detail_product_name_by_id = {
    int(row["_product_id"]): str(row["Ürün"])
    for row in detail_rows_for_bank
}

with detail_select_product_col:
    detail_id = st.selectbox(
        "İncelenecek Ürün",
        options=list(detail_product_name_by_id.keys()),
        format_func=lambda product_id: detail_product_name_by_id.get(
            int(product_id),
            str(product_id),
        ),
    )

context = result_context[int(detail_id)]
detail_product = context["product"]

with st.container(border=True):
    st.markdown(
        f"### {display_text(detail_product.get('bank_name'))}"
    )
    st.markdown(
        f"**{display_product_name(detail_product.get('product_name'))}**"
    )

    # Ürün detayında yalnız gerçekten anlamlı/verili alanları
    # göster. Filtrede görünmeyen veya kaynakta yayımlanmayan
    # sayısal alanları placeholder metriklerle doldurma.
    detail_metrics: list[tuple[str, str]] = []

    if is_housing_mode:
        detail_metrics.extend(
            [
                (
                    "Kâr Payı / Fiyatlama",
                    context.get("housing_main_profit_text")
                    or "—",
                ),
                (
                    "Azami Vade",
                    context.get("housing_main_maturity_text")
                    or "—",
                ),
                (
                    "Finansman Oranı",
                    context.get("housing_main_ratio_text")
                    or "—",
                ),
                (
                    "Tahsis Ücreti",
                    context.get("housing_allocation_fee_text")
                    or "—",
                ),
                (
                    "Ekspertiz Ücreti",
                    context.get("housing_appraisal_fee_text")
                    or "—",
                ),
                (
                    "İpotek Tesis Ücreti",
                    context.get("housing_mortgage_fee_text")
                    or "—",
                ),
            ]
        )

    if (
        not is_housing_mode
        and meaningful_detail_value(
            context["profit_text"]
        )
    ):
        detail_metrics.append(
            (
                "Kâr Payı",
                context["profit_text"],
            )
        )

    if (
        is_vehicle_mode
        and meaningful_detail_value(
            context.get("vehicle_pricing_maturities")
        )
    ):
        detail_metrics.append(
            (
                "Vade / Vade Bantları",
                context["vehicle_pricing_maturities"],
            )
        )
    elif (
        not is_housing_mode
        and meaningful_detail_value(
            context["general_maturity_text"]
        )
    ):
        detail_metrics.append(
            (
                "Vade / Vade Bantları",
                context["general_maturity_text"],
            )
        )

    if meaningful_detail_value(
        context.get("amount_dependent_terms_text")
    ):
        # Uzun bant metnini metrik kutusuna sıkıştırmıyoruz;
        # aşağıdaki detay tablosunda tam hali gösterilecek.
        pass

    if meaningful_detail_value(
        context["selected_category_limit_text"]
    ):
        detail_metrics.append(
            (
                "Seçili Kategori Taksit Sınırı",
                context["selected_category_limit_text"],
            )
        )

    if (
        not is_housing_mode
        and meaningful_detail_value(
            context.get("allocation_fee_text")
        )
    ):
        detail_metrics.append(
            (
                "Tahsis Ücreti",
                context["allocation_fee_text"],
            )
        )

    if (
        not is_housing_mode
        and meaningful_detail_value(
            context["financing_amount"]
        )
    ):
        detail_metric_label = (
            "Finansman Limiti"
            if "ihtiyaç" in _family_key(
                detail_product.get("product_family")
            ) or "ihtiyac" in _family_key(
                detail_product.get("product_family")
            )
            else "Finansman Tutarı"
        )
        detail_metrics.append(
            (
                detail_metric_label,
                context["financing_amount"],
            )
        )

    if meaningful_detail_value(
        context.get("financing_ratio_text")
    ):
        detail_metrics.append(
            (
                "Finansman Oranı",
                context["financing_ratio_text"],
            )
        )

    if (
        is_vehicle_mode
        and meaningful_detail_value(
            context.get("vehicle_ratio_financing_text")
        )
    ):
        detail_metrics.append(
            (
                "Orana Göre Finansman Tutarı",
                context["vehicle_ratio_financing_text"],
            )
        )

    if (
        is_vehicle_mode
        and meaningful_detail_value(
            context.get("vehicle_status_text")
        )
    ):
        detail_metrics.append(
            (
                "Araç Durumu",
                context["vehicle_status_text"],
            )
        )

    if (
        is_vehicle_mode
        and meaningful_detail_value(
            context.get("vehicle_insurance_text")
        )
    ):
        detail_metrics.append(
            (
                "Sigorta Durumu",
                context["vehicle_insurance_text"],
            )
        )

    if (
        is_vehicle_mode
        and amount_filter_applicable
        and simulator_amount is not None
    ):
        detail_metrics.append(
            (
                "Araç / Kasko Değeri",
                tr_money(simulator_amount),
            )
        )
    elif (
        category_filter_enabled
        and selected_category_key is not None
    ):
        detail_metrics.append(
            (
                (
                    "Seçili Ürün Kategorisi"
                    if "ihtiyaç" in _family_key(
                        detail_product.get("product_family")
                    )
                    else "Seçili Kategori"
                ),
                selected_category_label,
            )
        )

    if detail_metrics:
        if is_housing_mode:
            for start in range(
                0,
                len(detail_metrics),
                3,
            ):
                metric_group = detail_metrics[
                    start:start + 3
                ]
                metric_columns = st.columns(
                    len(metric_group)
                )

                for metric_column, (
                    metric_label,
                    metric_value,
                ) in zip(
                    metric_columns,
                    metric_group,
                ):
                    with metric_column:
                        st.metric(
                            metric_label,
                            metric_value,
                        )
        else:
            metric_columns = st.columns(
                len(detail_metrics)
            )

            for metric_column, (
                metric_label,
                metric_value,
            ) in zip(
                metric_columns,
                detail_metrics,
            ):
                with metric_column:
                    st.metric(
                        metric_label,
                        metric_value,
                    )

    if (
        not is_vehicle_mode
        and amount_filter_applicable
        and simulator_amount is not None
    ):
        st.caption(
            "Seçilen karşılaştırma tutarı: "
            f"{tr_money(simulator_amount)}"
        )

    # Ana sonuç tablosundan kaldırılan detaylar burada, yalnızca
    # seçilen banka + ürün için ve yalnız kaynakta anlamlı veri varsa gösterilir.
    # Başvuru / Kanal bilinçli olarak burada da gösterilmez; veri katmanında
    # korunur ancak karşılaştırma/karar kriteri olarak kullanılmaz.
    qualitative_values = context.get(
        "qualitative_values",
        {},
    )

    product_detail_rows: list[dict[str, str]] = []

    for source_label, detail_label_name in (
        ("İşlem / Finansman Yapısı", "Yapı"),
        ("Teminat / Güvence", "Teminat"),
        ("Maliyet / Avantaj", "Maliyet / Avantaj"),
    ):
        detail_value = str(
            qualitative_values.get(source_label, "")
            or ""
        ).strip()

        if meaningful_detail_value(detail_value):
            product_detail_rows.append(
                {
                    "Detay": detail_label_name,
                    "Bilgi": detail_value,
                }
            )

    if meaningful_detail_value(
        context.get("amount_dependent_terms_text")
    ):
        product_detail_rows.append(
            {
                "Detay": "Tutar / Değer Bazlı Koşullar",
                "Bilgi": context[
                    "amount_dependent_terms_text"
                ],
            }
        )

    if (
        not is_housing_mode
        and meaningful_detail_value(
            context["fee_text"]
        )
    ):
        product_detail_rows.append(
            {
                "Detay": "Masraf / Maliyet",
                "Bilgi": context["fee_text"],
            }
        )

    if meaningful_detail_value(
        context["condition_text"]
    ):
        product_detail_rows.append(
            {
                "Detay": "Özel Koşul",
                "Bilgi": context["condition_text"],
            }
        )

    if product_detail_rows:
        st.markdown("#### Ürün Bazlı Koşullar ve Detaylar")
        st.dataframe(
            pd.DataFrame(product_detail_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Detay": st.column_config.TextColumn(
                    "Detay",
                    width="medium",
                ),
                "Bilgi": st.column_config.TextColumn(
                    "Bilgi",
                    width="large",
                ),
            },
        )

    # Yukarıdaki ürün-koşulu bölümünde gösterilen nitel alanları
    # ikinci kez tekrar etme. Geri kalan anlamlı nitel özellikleri göster.
    detail_only_source_labels = {
        "İşlem / Finansman Yapısı",
        "Teminat / Güvence",
        "Maliyet / Avantaj",
        "Başvuru / Kanal",
    }

    feature_detail_rows = [
        {
            "Özellik": label,
            "Değer": value,
        }
        for label, value in qualitative_values.items()
        if label not in detail_only_source_labels
        and meaningful_detail_value(value)
    ]

    if feature_detail_rows:
        st.markdown("#### Diğer Nitel Ürün Özellikleri")
        st.dataframe(
            pd.DataFrame(feature_detail_rows),
            use_container_width=True,
            hide_index=True,
        )

        detail_feature_evidence = (
            feature_rules[
                feature_rules["product_id"]
                == detail_id
            ].copy()
            if not feature_rules.empty
            else pd.DataFrame()
        )

        if not detail_feature_evidence.empty:
            with st.expander(
                "Nitel özelliklerin kaynak dayanakları"
            ):
                evidence_frame = (
                    detail_feature_evidence[
                        [
                            "feature_label",
                            "feature_value",
                            "source_text",
                        ]
                    ]
                    .rename(
                        columns={
                            "feature_label": "Özellik",
                            "feature_value": "Değer",
                            "source_text": "Kaynak Dayanağı",
                        }
                    )
                )

                st.dataframe(
                    evidence_frame,
                    use_container_width=True,
                    hide_index=True,
                )


detail_category = pd.DataFrame(
    context["category_matches"]
)

detail_amount = pd.DataFrame(
    context["amount_matches"]
)

detail_offer = (
    offer_rules[
        offer_rules["product_id"] == detail_id
    ].copy()
    if not offer_rules.empty
    else pd.DataFrame()
)

detail_fee = (
    fee_rules[
        fee_rules["product_id"]
        == detail_id
    ]
    if not fee_rules.empty
    else pd.DataFrame()
)

detail_pricing = (
    pricing_rules[
        pricing_rules["product_id"]
        == detail_id
    ]
    if not pricing_rules.empty
    else pd.DataFrame()
)

detail_pricing_all = (
    pricing_all_rules[
        pricing_all_rules["product_id"] == detail_id
    ].copy()
    if pricing_all_rules is not None and not pricing_all_rules.empty
    else pd.DataFrame()
)

if (
    selected_pricing_variant is not None
    and not detail_pricing.empty
    and "pricing_variant" in detail_pricing.columns
):
    selected_variant_rows = detail_pricing[
        detail_pricing["pricing_variant"]
        == selected_pricing_variant
    ]
    if not selected_variant_rows.empty:
        detail_pricing = selected_variant_rows

detail_all_amount = (
    amount_rules[
        amount_rules["product_id"] == detail_id
    ].copy()
    if not amount_rules.empty
    else pd.DataFrame()
)

if not detail_pricing_all.empty and "value_type" in detail_pricing_all.columns:
    evidence_rows = []
    for _, _row in detail_pricing_all.iterrows():
        _kind = str(_row.get("value_type") or "exact")
        _kind_label = {
            "example": "Örnek / temsili",
            "conditional_pricing": "Koşullu fiyatlama",
            "exact": "Doğrudan fiyatlama",
            "dynamic": "Dinamik",
        }.get(_kind, _kind)
        _rate = _row.get("profit_share_rate")
        _maturity = _row.get("maturity_months")
        evidence_rows.append({
            "Kanıt Türü": _kind_label,
            "Fiyatlama Varyantı": str(_row.get("pricing_variant") or "Standart"),
            "Vade": (f"{int(_maturity)} ay" if has_value(_maturity) else "—"),
            "Kâr Payı": (rate_text(_rate) if has_value(_rate) else "—"),
            "Koşullar": str(_row.get("conditions") or "—"),
        })
    if evidence_rows:
        with st.container(border=True):
            st.markdown("#### Fiyatlama Kanıtı ve Koşulları")
            st.caption(
                "Örnek/temsili satırlar bilgi amaçlı saklanır; ana karşılaştırmada güncel genel oran olarak kullanılmaz."
            )
            st.dataframe(pd.DataFrame(evidence_rows), use_container_width=True, hide_index=True)

if is_housing_mode:
    _housing_fee_rows = housing_fee_detail_rows(
        int(detail_id),
        fee_rules,
    )
    if _housing_fee_rows:
        with st.container(border=True):
            st.markdown("#### Masraf ve Maliyet Detayı")
            st.dataframe(
                pd.DataFrame(_housing_fee_rows),
                use_container_width=True,
                hide_index=True,
            )

    _housing_offer_rows = housing_offer_detail_rows(
        int(detail_id),
        offer_rules,
    )
    if _housing_offer_rows:
        with st.container(border=True):
            st.markdown("#### Fiyatlama ve Önemli Koşullar")
            st.dataframe(
                pd.DataFrame(_housing_offer_rows),
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# KONUT / GAYRİMENKUL — BANKAYA ÖZGÜ DETAY / HESAPLAMA
# ============================================================
detail_housing_rules = parse_housing_rules_json(
    detail_product.get("housing_finance_rules_json")
)

detail_fixed_ratio = (
    float(detail_product.get("maximum_financing_ratio"))
    if has_value(detail_product.get("maximum_financing_ratio"))
    else None
)

if is_housing_mode and detail_housing_rules:
    with st.container(border=True):
        st.markdown("#### Bankaya Özgü Konut Finansmanı Hesabı")
        st.caption(
            "Bu hesap yalnız seçilen bankanın resmî ekspertiz değeri / "
            "enerji sınıfı kurallarını kullanır. Ana karşılaştırma tablosundaki "
            "değer alanı banka limiti değildir."
        )

        available_purchase_types: list[str] = []
        if detail_housing_rules.get("standard_home"):
            available_purchase_types.append("Standart / İlk Konut Alımı")
        if detail_housing_rules.get("additional_home"):
            available_purchase_types.append("2. ve Sonraki Konut Alımı")

        # Tek bir alım türü yayımlayan üründe kullanıcıya anlamsız bir
        # dropdown göstermeyelim (örn. Kuveyt İlk Evim / normal Konut).
        if len(available_purchase_types) == 1:
            detail_purchase_type_ui = available_purchase_types[0]
            st.caption(f"Konut alım türü: **{detail_purchase_type_ui}**")
            calc_columns = st.columns(2)
        else:
            calc_columns = st.columns(3)

        with calc_columns[0]:
            detail_property_value_raw = st.text_input(
                "Konut / Ekspertiz Değeri (TL)",
                value="",
                placeholder="Örn. 2.000.000",
                help=(
                    "Bu değer banka limiti değildir; seçtiğiniz konutun "
                    "ekspertiz değeridir. 2000000 veya 2.000.000 yazabilirsiniz."
                ),
                key=f"housing_property_value_{int(detail_id)}",
            )
            detail_property_value = parse_user_tl_input(
                detail_property_value_raw
            )

            if (
                str(detail_property_value_raw).strip()
                and detail_property_value is None
            ):
                st.error(
                    "Ekspertiz değerini yalnız rakamla girin. "
                    "Örnek: 2000000 veya 2.000.000"
                )

        if len(available_purchase_types) > 1:
            with calc_columns[1]:
                detail_purchase_type_ui = st.selectbox(
                    "Konut Alım Türü",
                    options=available_purchase_types,
                    key=f"housing_purchase_type_{int(detail_id)}",
                )
            energy_column = calc_columns[2]
        else:
            energy_column = calc_columns[1]

        with energy_column:
            detail_energy_class = st.selectbox(
                "Enerji Sınıfı",
                options=["A-B", "C", "Diğer"],
                key=f"housing_energy_{int(detail_id)}",
            )

        detail_purchase_type = (
            "2. ve Sonraki Konut Alımı"
            if detail_purchase_type_ui == "2. ve Sonraki Konut Alımı"
            else "Standart Konut Alımı"
        )

        detail_housing_eval = None
        if detail_property_value is not None:
            detail_housing_eval = evaluate_housing_rule(
                detail_product,
                float(detail_property_value),
                detail_purchase_type,
                detail_energy_class,
            )

        if detail_property_value is None:
            st.info(
                "Finansman oranı ve orana göre finansman tutarını görmek "
                "için konut ekspertiz değerini girin."
            )
        elif detail_housing_eval is not None:
            ratio = detail_housing_eval.get("ratio")
            max_amount = detail_housing_eval.get("max_financing_amount")

            calc_metric1, calc_metric2, calc_metric3 = st.columns(3)
            with calc_metric1:
                st.metric(
                    "Finansman Oranı",
                    rate_text(ratio) if ratio is not None else "—",
                )
            with calc_metric2:
                st.metric(
                    "Orana Göre Finansman Tutarı",
                    tr_money(max_amount) if max_amount is not None else "—",
                )
            with calc_metric3:
                st.metric(
                    "Uygulanan Değer Bandı",
                    housing_value_band_text(detail_housing_eval),
                )
        else:
            st.info(
                "Seçilen ekspertiz değeri / konut türü / enerji sınıfı "
                "için yapılandırılmış bir oran bulunamadı."
            )

elif is_housing_mode and detail_fixed_ratio is not None:
    # 2B ve Gurbetten Sılaya gibi kaynağın doğrudan varlık/ekspertiz
    # değerinin sabit bir yüzdesini verdiği ürünler.
    with st.container(border=True):
        st.markdown("#### Bankaya Özgü Finansman Oranı Hesabı")
        st.caption(
            "Kaynakta gayrimenkul/arazi/ekspertiz değerinin doğrudan bir "
            "yüzdesi yayımlanmıştır. Aşağıdaki değer banka limiti değildir."
        )

        fixed_value_raw = st.text_input(
            "Gayrimenkul / Ekspertiz Değeri (TL)",
            value="",
            placeholder="Örn. 2.000.000",
            help=(
                "2000000 veya 2.000.000 biçiminde girebilirsiniz."
            ),
            key=f"housing_fixed_ratio_value_{int(detail_id)}",
        )
        fixed_value = parse_user_tl_input(
            fixed_value_raw
        )

        if (
            str(fixed_value_raw).strip()
            and fixed_value is None
        ):
            st.error(
                "Değeri yalnız rakamla girin. "
                "Örnek: 2000000 veya 2.000.000"
            )

        fixed_col1, fixed_col2 = st.columns(2)
        with fixed_col1:
            st.metric(
                "Finansman Oranı",
                "Azami " + rate_text(detail_fixed_ratio),
            )
        with fixed_col2:
            st.metric(
                "Orana Göre Finansman Tutarı",
                (
                    tr_money(float(fixed_value) * detail_fixed_ratio / 100.0)
                    if fixed_value is not None
                    else "—"
                ),
            )

if not detail_all_amount.empty:
    amount_band_rows = []
    for _, rule in detail_all_amount.iterrows():
        months = rule.get("max_maturity_months")
        if not has_value(months):
            continue
        amount_band_rows.append(
            {
                "Finansman Tutarı Bandı": amount_band(rule),
                "Azami Vade": f"{int(months)} Ay",
            }
        )

    if amount_band_rows:
        with st.container(border=True):
            st.markdown("#### Tutar / Vade Bantları")
            st.dataframe(
                pd.DataFrame(amount_band_rows),
                use_container_width=True,
                hide_index=True,
            )


condition_lines = []

if is_housing_mode:
    detail_offer_summary = (
        offer_summary_without_general_maturity(
            detail_id,
            offer_rules,
        )
    )

    if detail_offer_summary != "Belirtilmedi":
        condition_lines.append(
            "**Ürüne özel koşul:** "
            + detail_offer_summary
        )

elif (
    not is_vehicle_mode
    and amount_filter_applicable
):
    detail_offer_summary = offer_condition_summary(
        detail_id,
        offer_rules,
        float(simulator_amount),
    )

    if detail_offer_summary != "Belirtilmedi":
        condition_lines.append(
            "**Ürüne özel koşul:** "
            + detail_offer_summary
        )
condition_lines.extend(
    detail_category_lines(detail_category)
)
condition_lines.extend(
    detail_amount_lines(detail_amount)
)
condition_lines.extend(
    detail_fee_lines_from_summary(
        context["fee_text"]
    )
)

vehicle_rule = detail_product.get(
    "vehicle_finance_rules_text"
)
if (
    vehicle_family(
        detail_product.get("product_family")
    )
    and has_value(vehicle_rule)
):
    condition_lines.append(
        "**Araç finansman kuralı:** "
        + display_text(vehicle_rule)
    )

vehicle_age = detail_product.get(
    "vehicle_age_rules_text"
)
if (
    vehicle_family(
        detail_product.get("product_family")
    )
    and has_value(vehicle_age)
):
    condition_lines.append(
        "**Araç yaşı kuralı:** "
        + display_text(vehicle_age)
    )

first_home = detail_product.get(
    "housing_first_home_rules_text"
)
if has_value(first_home):
    condition_lines.append(
        "**İlk ev finansman oranları:** "
        + display_text(first_home)
    )

additional_home = detail_product.get(
    "housing_additional_home_rules_text"
)
if has_value(additional_home):
    condition_lines.append(
        "**İkinci ve sonraki ev finansman oranları:** "
        + display_text(additional_home)
    )

# Tekrarları kaldır.
unique_lines = []
for line in condition_lines:
    if line not in unique_lines:
        unique_lines.append(line)

standard_housing_table = (
    housing_rule_table(
        detail_product,
        "Standart Konut Alımı",
    )
    if is_housing_mode
    else pd.DataFrame()
)
additional_housing_table = (
    housing_rule_table(
        detail_product,
        "2. ve Sonraki Konut Alımı",
    )
    if is_housing_mode
    else pd.DataFrame()
)

if (
    is_housing_mode
    and (
        not standard_housing_table.empty
        or not additional_housing_table.empty
    )
):
    with st.container(border=True):
        st.markdown("#### Bankanın Ekspertiz Değerine Göre Finansman Oranları")

        if not standard_housing_table.empty:
            st.markdown("**Standart / İlk Konut Alımı**")
            st.dataframe(
                standard_housing_table,
                use_container_width=True,
                hide_index=True,
            )

        if not additional_housing_table.empty:
            st.markdown("**2. ve Sonraki Konut Alımı**")
            st.dataframe(
                additional_housing_table,
                use_container_width=True,
                hide_index=True,
            )


with st.container(border=True):
    st.markdown("#### Finansman Koşulları")

    if unique_lines:
        for line in unique_lines:
            st.markdown(f"- {line}")
    else:
        st.caption(
            "Resmî kaynakta ek yapılandırılmış finansman "
            "koşulu bulunamadı."
        )

    source_url = detail_product.get("source_url")
    if has_value(source_url):
        st.markdown(
            f"[Resmî Ürün Sayfasını Aç]({source_url})"
        )


# Fiyatlama matrisi gerçekten varsa tek küçük tablo göster.
if not detail_pricing.empty:
    with st.container(border=True):
        st.markdown("#### Vadeye Göre Fiyatlama")

        pricing_view = detail_pricing.copy()

        # Araç ürünlerinde fiyatlama varyantını iki anlamlı boyuta ayır:
        # 0 km / 2. El ve Sigortalı / Sigortasız.
        if (
            is_vehicle_mode
            and "pricing_variant" in pricing_view.columns
        ):
            vehicle_variant_pairs = pricing_view[
                "pricing_variant"
            ].apply(
                vehicle_fields_from_pricing_variant
            )

            pricing_view["Araç Durumu"] = (
                vehicle_variant_pairs.apply(
                    lambda pair: pair[0]
                )
            )
            pricing_view["Sigorta Durumu"] = (
                vehicle_variant_pairs.apply(
                    lambda pair: pair[1]
                )
            )

            vehicle_status_options = [
                value
                for value in (
                    "0 km",
                    "2. El",
                )
                if value
                in set(
                    pricing_view[
                        "Araç Durumu"
                    ].astype(str)
                )
            ]

            insurance_status_options = [
                value
                for value in (
                    "Sigortalı",
                    "Sigortasız",
                )
                if value
                in set(
                    pricing_view[
                        "Sigorta Durumu"
                    ].astype(str)
                )
            ]

            selector_specs = []
            if len(vehicle_status_options) > 1:
                selector_specs.append("vehicle")
            if len(insurance_status_options) > 1:
                selector_specs.append("insurance")

            selector_columns = (
                st.columns(len(selector_specs))
                if selector_specs
                else []
            )
            selector_map = {
                name: selector_columns[index]
                for index, name
                in enumerate(selector_specs)
            }

            selected_detail_vehicle_status = "Tümü"
            selected_detail_insurance_status = "Tümü"

            if "vehicle" in selector_map:
                with selector_map["vehicle"]:
                    selected_detail_vehicle_status = (
                        st.selectbox(
                            "Araç Durumu",
                            options=[
                                "Tümü"
                            ]
                            + vehicle_status_options,
                            key=(
                                "vehicle_pricing_status_"
                                f"{int(detail_id)}"
                            ),
                        )
                    )
            elif len(vehicle_status_options) == 1:
                selected_detail_vehicle_status = (
                    vehicle_status_options[0]
                )

            if "insurance" in selector_map:
                with selector_map["insurance"]:
                    selected_detail_insurance_status = (
                        st.selectbox(
                            "Sigorta Durumu",
                            options=[
                                "Tümü"
                            ]
                            + insurance_status_options,
                            key=(
                                "vehicle_pricing_insurance_"
                                f"{int(detail_id)}"
                            ),
                        )
                    )
            elif len(insurance_status_options) == 1:
                selected_detail_insurance_status = (
                    insurance_status_options[0]
                )

            if selected_detail_vehicle_status != "Tümü":
                pricing_view = pricing_view[
                    pricing_view["Araç Durumu"]
                    == selected_detail_vehicle_status
                ].copy()

            if selected_detail_insurance_status != "Tümü":
                pricing_view = pricing_view[
                    pricing_view["Sigorta Durumu"]
                    == selected_detail_insurance_status
                ].copy()

            if (
                selected_detail_vehicle_status != "Tümü"
                or selected_detail_insurance_status != "Tümü"
            ):
                selected_parts = []
                if selected_detail_vehicle_status != "Tümü":
                    selected_parts.append(
                        selected_detail_vehicle_status
                    )
                if selected_detail_insurance_status != "Tümü":
                    selected_parts.append(
                        selected_detail_insurance_status
                    )

                st.caption(
                    "Gösterilen fiyatlama: "
                    + " · ".join(selected_parts)
                )

        pricing_view["Vade"] = pricing_view[
            "maturity_months"
        ].apply(
            lambda value: f"{int(value)} Ay"
        )
        if "financing_amount" in pricing_view.columns:
            pricing_view["Finansman Tutarı"] = pricing_view[
                "financing_amount"
            ].apply(
                lambda value: (
                    tr_money(value)
                    if has_value(value)
                    else "Belirtilmedi"
                )
            )

        pricing_view["Kâr Payı"] = pricing_view[
            "profit_share_rate"
        ].apply(rate_text)
        pricing_view["Tahsis Ücreti"] = pricing_view[
            "allocation_fee_rate"
        ].apply(rate_text)
        pricing_view["Aylık Toplam Maliyet"] = pricing_view[
            "monthly_total_cost_rate"
        ].apply(rate_text)
        pricing_view["Yıllık Toplam Maliyet"] = pricing_view[
            "annual_total_cost_rate"
        ].apply(rate_text)

        if "pricing_variant" in pricing_view.columns:
            pricing_view["Fiyatlama"] = pricing_view[
                "pricing_variant"
            ].map(display_text)

            if (
                is_vehicle_mode
                and "Araç Durumu" not in pricing_view.columns
            ):
                vehicle_variant_pairs = pricing_view[
                    "pricing_variant"
                ].apply(
                    vehicle_fields_from_pricing_variant
                )

                pricing_view["Araç Durumu"] = (
                    vehicle_variant_pairs.apply(
                        lambda pair: pair[0]
                    )
                )
                pricing_view["Sigorta Durumu"] = (
                    vehicle_variant_pairs.apply(
                        lambda pair: pair[1]
                    )
                )

        if is_vehicle_mode:
            pricing_columns = [
                "Araç Durumu",
                "Sigorta Durumu",
                "Vade",
                "Finansman Tutarı",
                "Kâr Payı",
                "Tahsis Ücreti",
                "Aylık Toplam Maliyet",
                "Yıllık Toplam Maliyet",
            ]

            # Pricing variant yalnız 0 km/2.El ve sigorta bilgisinden
            # ibaret değilse ek açıklama olarak Fiyatlama sütununu da koru.
            if (
                "Fiyatlama" in pricing_view.columns
                and pricing_view["Fiyatlama"]
                .astype(str)
                .str.strip()
                .ne("")
                .any()
                and not (
                    "Araç Durumu" in pricing_view.columns
                    and "Sigorta Durumu" in pricing_view.columns
                    and pricing_view["Araç Durumu"]
                    .astype(str)
                    .ne("—")
                    .any()
                    and pricing_view["Sigorta Durumu"]
                    .astype(str)
                    .ne("—")
                    .any()
                )
            ):
                pricing_columns.insert(
                    0,
                    "Fiyatlama",
                )
        else:
            pricing_columns = [
                "Fiyatlama",
                "Vade",
                "Finansman Tutarı",
                "Kâr Payı",
                "Tahsis Ücreti",
                "Aylık Toplam Maliyet",
                "Yıllık Toplam Maliyet",
            ]

        # Bazı ürünlerin pricing tier kayıtlarında financing_amount
        # alanı bulunmadığı için "Finansman Tutarı" adlı görünüm sütunu
        # hiç oluşturulmayabilir. Önce sütunun gerçekten varlığını
        # kontrol ederek KeyError oluşmasını engelle.
        always_keep_columns = {
            "Fiyatlama",
            "Vade",
        }

        pricing_columns = [
            column
            for column in pricing_columns
            if (
                column in pricing_view.columns
                and (
                    column in always_keep_columns
                    or pricing_view[column]
                    .astype(str)
                    .str.strip()
                    .replace(
                        {
                            "Belirtilmedi": "",
                            "—": "",
                            "-": "",
                            "nan": "",
                            "None": "",
                        }
                    )
                    .ne("")
                    .any()
                )
            )
        ]

        if (
            "maturity_months" in pricing_view.columns
            and not pricing_view.empty
        ):
            pricing_view = pricing_view.sort_values(
                "maturity_months",
                kind="stable",
            )

        st.dataframe(
            pricing_view[pricing_columns],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Araç Durumu": st.column_config.TextColumn(
                    "Araç Durumu",
                    width="small",
                ),
                "Sigorta Durumu": st.column_config.TextColumn(
                    "Sigorta Durumu",
                    width="small",
                ),
                "Vade": st.column_config.TextColumn(
                    "Vade",
                    width="small",
                ),
                "Kâr Payı": st.column_config.TextColumn(
                    "Kâr Payı",
                    width="small",
                ),
            },
        )


# ============================================================
# DEĞİŞİKLİK GEÇMİŞİ
# ============================================================
changes = get_standard_product_changes(
    limit=50
)

with st.expander(
    "Son Ürün Değişiklikleri",
    expanded=False,
):
    if changes.empty:
        st.caption(
            "Henüz kayıtlı bir standart ürün değişikliği yok."
        )
    else:
        view = changes.copy()
        labels = {
            "new_product": "Yeni Ürün",
            "terms_changed": "Koşullar Güncellendi",
            "content_changed": "İçerik Güncellendi",
            "reactivated": "Yeniden Göründü",
            "possible_removed": "Kaynakta Görünmüyor",
        }

        view["Değişiklik"] = (
            view["change_type"]
            .map(labels)
            .fillna(view["change_type"])
        )

        view["Tespit Tarihi"] = pd.to_datetime(
            view["detected_at"],
            errors="coerce",
        ).dt.strftime("%d.%m.%Y %H:%M")

        view = view.rename(
            columns={
                "bank_name": "Banka",
                "product_name": "Ürün",
            }
        )

        st.dataframe(
            view[
                [
                    "Tespit Tarihi",
                    "Değişiklik",
                    "Banka",
                    "Ürün",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
