from __future__ import annotations

import math
import re

import pandas as pd
import streamlit as st

from src.finance_rule_engine import amount_matches
from src.postgres_repository import (
    get_standard_product_changes,
    get_standard_product_rule_sets,
    get_standard_products,
    postgres_health,
)
from src.ui_display import display_text, format_number_tr


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



def default_amount_for_family(
    family: str,
) -> int:
    key = str(family).casefold()

    if "araç" in key or "arac" in key:
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
    key = str(family).casefold()
    return "araç" in key or "arac" in key


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

    amount_token = (
        r"\d+(?:[.,]\d+)?"
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

if products.empty:
    st.info(
        "Henüz standart finansman ürünü bulunmuyor."
    )
    st.stop()


# ============================================================
# FİLTRELER
# ============================================================
financing_types = (
    products["product_family"]
    .dropna()
    .astype(str)
    .drop_duplicates()
    .sort_values(key=lambda s: s.str.casefold())
    .tolist()
)

top1, top2 = st.columns([1, 2])

with top1:
    selected_family = st.selectbox(
        "Finansman Türü",
        options=financing_types,
        help=(
            "Seçtiğiniz finansman türü bir ürün ailesidir. Seçili bankaların "
            "bu aile altında bulunan tüm standart finansman ürünleri, bankanın "
            "resmî ürün adıyla karşılaştırmaya dahil edilir."
        ),
    )

# Finansman Türü bir ürün ailesidir.
# Örn. İhtiyaç Finansmanı seçildiğinde Albaraka'nın Jet/Eğitim/BES/Pratik vb.,
# Kuveyt Türk'ün Eğitim/Hac-Umre/Seyahat/Kira vb. ve diğer seçili bankaların
# bu ailedeki tüm gerçek ürünleri bankanın resmî product_name değeriyle gelir.
comparison_products = products[
    products["product_family"] == selected_family
].copy()

banks = (
    comparison_products["bank_name"]
    .dropna()
    .astype(str)
    .drop_duplicates()
    .sort_values(key=lambda s: s.str.casefold())
    .tolist()
)

with top2:
    selected_banks = st.multiselect(
        "Bankalar",
        options=banks,
        default=banks,
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

rule_sets = get_standard_product_rule_sets(
    selected_ids
)
category_rules = rule_sets["category"]
amount_rules = rule_sets["amount_maturity"]
pricing_rules = rule_sets["pricing"]
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

# Ana kullanım: yalnız Finansman Türü + Bankalar yeterlidir.
# Seçili bankaların bu ailedeki TÜM ürünleri varsayılan olarak gösterilir.
# Tutar/vade/kategori/fiyatlama ancak kullanıcı özellikle isterse daraltma yapar.
st.caption(
    "Seçili bankaların bu finansman türündeki tüm ürünleri otomatik listelenir. "
    "Tutar, vade, kategori veya fiyatlama seçmek zorunlu değildir."
)
use_optional_filters = st.toggle(
    "İsteğe bağlı ek filtrelerle sonuçları daralt",
    value=False,
)

amount_filter_applicable = (
    amount_filter_available
    and use_optional_filters
)

maturity_filter_enabled = (
    maturity_filter_available
    and use_optional_filters
)

category_filter_enabled = (
    use_optional_filters
    and not is_vehicle_mode
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

filter_specs: list[str] = []

if category_filter_enabled:
    filter_specs.append("category")

if amount_filter_applicable:
    filter_specs.append("amount")

if maturity_filter_enabled:
    filter_specs.append("maturity")

if pricing_filter_enabled:
    filter_specs.append("pricing")

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
        amount_label = (
            "Araç / Kasko Değeri (TL)"
            if is_vehicle_mode
            else "Finansman Tutarı (TL)"
        )

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

        else:
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
            "value": 50000,
            "step": 1000,
        }

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
        selected_maturity_label = st.selectbox(
            "Tercih Edilen Vade",
            options=["Seçme"] + [
                f"{value} Ay"
                for value in maturity_values
            ],
        )

    selected_maturity = (
        None
        if selected_maturity_label == "Seçme"
        else int(selected_maturity_label.split()[0])
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
result_rows = []
result_context: dict[int, dict] = {}

for _, product in selected.iterrows():
    product_id = int(product["id"])

    vehicle_eval = None

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
    selected_category_limit_text = selected_category_limit_summary(
        category_matches
    )
    condition_text = offer_summary_without_general_maturity(
        product_id,
        offer_rules,
    )

    profit_text = profit_text_for_product(
        product,
        pricing_rules,
        selected_maturity,
        selected_pricing_variant,
    )

    fee_text = fee_summary_for_product(
        product_id,
        fee_rules,
        pricing_rules,
        selected_maturity,
        selected_pricing_variant,
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

        if (
            "financing_amount" in product_pricing_amounts.columns
            and not product_pricing_amounts.empty
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

    financing_ratio_text = "Belirtilmedi"
    if vehicle_eval is not None and vehicle_eval.get("ratio") is not None:
        financing_ratio_text = (
            "Azami %"
            + format_number_tr(vehicle_eval.get("ratio"))
        )
    elif has_value(product.get("maximum_financing_ratio")):
        financing_ratio_text = (
            "Azami %"
            + format_number_tr(
                product.get("maximum_financing_ratio")
            )
        )

    result_row = {
        "_product_id": product_id,
        "Banka": display_text(
            product.get("bank_name")
        ),
        "Ürün": display_product_name(
            product.get("product_name")
        ),
        "Kâr Payı": profit_text,
        "Genel Vade / Vade Bantları": general_maturity_text,
        "Seçili Kategori Taksit Sınırı": selected_category_limit_text,
        "Finansman Tutarı": financing_amount,
        "Finansman Oranı": financing_ratio_text,
        "Masraf": fee_text,
        "Özel Koşul": condition_text,
        "Resmî Kaynak": product.get(
            "source_url"
        ),
    }

    qualitative_values = feature_values_for_product(
        feature_rules,
        product_id,
    )

    result_row["Amaç"] = purpose_value(
        qualitative_values
    )

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
        "fee_text": fee_text,
        "financing_amount": financing_amount,
        "financing_ratio_text": financing_ratio_text,
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

st.subheader(f"{selected_family} — Seçili Bankaların Ürünleri")

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
    "Seçtiğiniz bankaların bu finansman türündeki tüm ürünleri tek tabloda karşılaştırılır."
)

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
    }

    if key in exact_placeholders:
        return True

    if key.startswith(
        "sayısal koşullar kaynakta yayımlanmamış"
    ):
        return True

    return False


def column_has_meaningful_data(
    frame: pd.DataFrame,
    column: str,
) -> bool:
    if column not in frame.columns:
        return False

    return any(
        not is_dashboard_placeholder(value)
        for value in frame[column].tolist()
    )


base_result_columns = [
    "Banka",
    "Ürün",
]

qualitative_columns = []

# İhtiyaç Finansmanı sonuç tablosunda amaç sütunu gösterilmez.
# Amaç bilgisi veri katmanında korunur ve ürün detayında kullanılabilir.
hide_purpose_in_results = "ihtiyaç" in _family_key(selected_family)

if (
    not hide_purpose_in_results
    and "Amaç" in results_df.columns
    and column_has_meaningful_data(
        results_df,
        "Amaç",
    )
):
    results_df["Amaç"] = results_df["Amaç"].apply(
        lambda value: (
            "Belirtilmedi"
            if is_dashboard_placeholder(value)
            else value
        )
    )
    qualitative_columns.append("Amaç")

# Ana karşılaştırma tablosunu karar odaklı tut.
# Yapı / Teminat / Maliyet bilgileri veri katmanında korunur;
# yalnız seçilen ürünün detay bölümünde gösterilir.
DETAIL_ONLY_QUALITATIVE_COLUMNS = {
    "Yapı",
    "Teminat",
    "Maliyet / Avantaj",
}

for _, table_label in QUALITATIVE_TABLE_COLUMNS:
    if table_label in DETAIL_ONLY_QUALITATIVE_COLUMNS:
        continue

    if table_label not in results_df.columns:
        continue

    if not column_has_meaningful_data(
        results_df,
        table_label,
    ):
        continue

    results_df[table_label] = (
        results_df[table_label].apply(
            lambda value: (
                "Belirtilmedi"
                if is_dashboard_placeholder(value)
                else value
            )
        )
    )

    qualitative_columns.append(
        table_label
    )

candidate_numeric_columns = [
    "Kâr Payı",
    "Genel Vade / Vade Bantları",
    "Seçili Kategori Taksit Sınırı",
    "Finansman Oranı",
]

# İhtiyaç Finansmanı sonuç tablosunu daha okunabilir tutmak için
# ürün limitini burada göstermiyoruz. Filtre ve ürün detayında korunur.
if "ihtiyaç" not in _family_key(selected_family):
    candidate_numeric_columns.insert(
        2,
        "Finansman Tutarı",
    )

numeric_result_columns = [
    column
    for column in candidate_numeric_columns
    if column_has_meaningful_data(
        results_df,
        column,
    )
]

# Resmî kaynak her zaman erişilebilir kalsın.
numeric_result_columns.append(
    "Resmî Kaynak"
)

display_columns = (
    base_result_columns
    + qualitative_columns
    + numeric_result_columns
)

if qualitative_columns:
    if len(numeric_result_columns) == 1:
        st.caption(
            "Bu ürün grubunda karşılaştırma, resmî kaynakta "
            "yayımlanan amaç ve nitel özellikler üzerinden "
            "yapılmaktadır. Verisi olmayan sütunlar gizlenmiştir."
        )
    else:
        if hide_purpose_in_results:
            st.caption(
                "Nitel özellikler ayrı sütunlarda gösterilir; "
                "mevcut sayısal koşullar ayrıca karşılaştırmaya "
                "dahil edilir."
            )
        else:
            st.caption(
                "Amaç ve nitel özellikler ayrı sütunlarda gösterilir; "
                "mevcut sayısal koşullar ayrıca karşılaştırmaya "
                "dahil edilir."
            )

column_config = {
    "Ürün": st.column_config.TextColumn(
        "Ürün Adı",
        width="large",
    ),
    "Genel Vade / Vade Bantları": st.column_config.TextColumn(
        "Genel Vade / Vade Bantları",
        width="large",
    ),
    "Seçili Kategori Taksit Sınırı": st.column_config.TextColumn(
        "Seçili Kategori Taksit Sınırı",
        width="medium",
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
# Finansman Türü + Bankalar seçildiğinde seçili bankaların bu ailedeki
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

    if meaningful_detail_value(
        context["profit_text"]
    ):
        detail_metrics.append(
            (
                "Kâr Payı",
                context["profit_text"],
            )
        )

    if meaningful_detail_value(
        context["general_maturity_text"]
    ):
        detail_metrics.append(
            (
                "Genel Vade / Vade Bantları",
                context["general_maturity_text"],
            )
        )

    if meaningful_detail_value(
        context["selected_category_limit_text"]
    ):
        detail_metrics.append(
            (
                "Seçili Kategori Taksit Sınırı",
                context["selected_category_limit_text"],
            )
        )

    if meaningful_detail_value(
        context["financing_amount"]
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
        context["fee_text"]
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
if (
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

        pricing_columns = [
            "Fiyatlama",
            "Vade",
            "Finansman Tutarı",
            "Kâr Payı",
            "Tahsis Ücreti",
            "Aylık Toplam Maliyet",
            "Yıllık Toplam Maliyet",
        ]

        pricing_columns = [
            column
            for column in pricing_columns
            if (
                column in {"Fiyatlama", "Vade"}
                or pricing_view[column]
                .astype(str)
                .ne("Belirtilmedi")
                .any()
            )
        ]

        st.dataframe(
            pricing_view[pricing_columns],
            use_container_width=True,
            hide_index=True,
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
