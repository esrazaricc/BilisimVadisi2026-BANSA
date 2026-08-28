from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.competition_fast_router import _products, _present, _structured_fee_value
from src.competition_natural_chat import _source_url
from src.qualitative_feature_extractor import extract_qualitative_features
from src.calculator_constraints import all_constraints
from src.source_link_resolver import resolve_product_detail_url
from src.ui_table_density import clean_cell, sanitize_frame, select_dense_columns


ROOT = Path(__file__).resolve().parents[1]


FAMILY_LABEL_OVERRIDES = {
    "arac_finansmani": "Taşıt Finansmanı",
    "konut_finansmani": "Konut Finansmanı",
    "ihtiyac_finansmani": "İhtiyaç Finansmanı",
    "alisveris_finansmani": "Alışveriş Finansmanı",
    "arsa_finansmani": "Arsa Finansmanı",
    "isyeri_finansmani": "İş Yeri Finansmanı",
    "ticari_finansman": "Ticari Finansman",
    "gayri_nakdi_finansman": "Gayri Nakdi Finansman",
    "tarim_finansmani": "Tarım Finansmanı",
    "leasing": "Leasing / Finansal Kiralama",
    "surdurulebilir_finansman": "Sürdürülebilir Finansman",
    "gayrimenkul_finansmani": "Gayrimenkul Finansmanı",
    "finansman": "Diğer Finansman",
}


def _missing(value: object) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    return str(value).strip().casefold() in {"", "none", "nan", "—", "-", "belirtilmedi"}


def _text(value: object, fallback: str = "") -> str:
    if _missing(value):
        return fallback
    return clean_cell(re.sub(r"\s+", " ", str(value)).strip()) or fallback


def _money(value: object) -> str:
    if _missing(value):
        return ""
    try:
        number = float(value)
    except Exception:
        return _text(value)
    if not math.isfinite(number):
        return ""
    return f"{number:,.2f} TL".replace(",", "X").replace(".", ",").replace("X", ".")


def _rate(value: object, text: object = None) -> str:
    if not _missing(value):
        try:
            n = float(value)
            return (f"%{n:g}").replace(".", ",")
        except Exception:
            return _text(value)
    return _text(text, "")


def _maturity(row: pd.Series) -> str:
    rule = _text(row.get("maturity_rules_text"), "")
    if rule:
        return rule
    min_m = row.get("minimum_maturity_months")
    max_m = row.get("maximum_maturity_months")
    if not _missing(min_m) and not _missing(max_m):
        return f"{int(float(min_m))}–{int(float(max_m))} ay"
    if not _missing(max_m):
        return f"{int(float(max_m))} aya kadar"
    if not _missing(min_m):
        return f"En az {int(float(min_m))} ay"
    return "—"


def _amount_limit(row: pd.Series) -> str:
    lo = row.get("minimum_financing_amount")
    hi = row.get("maximum_financing_amount")
    if not _missing(lo) and not _missing(hi):
        return f"{_money(lo)} – {_money(hi)}"
    if not _missing(hi):
        return f"≤ {_money(hi)}"
    if not _missing(lo):
        return f"≥ {_money(lo)}"
    return "—"


def _ratio_rule(row: pd.Series) -> str:
    bank = _text(row.get("bank_name"), "")
    family = _text(row.get("product_family_key"), "")
    # Current Dünya vehicle evidence establishes maturity bands only.
    if bank == "Dünya Katılım" and family == "arac_finansmani":
        return ""
    text = _text(row.get("financing_ratio_rules_text"), "")
    if text:
        return text
    ratio = row.get("maximum_financing_ratio")
    if not _missing(ratio):
        try:
            return (f"Azami %{float(ratio):g}").replace(".", ",")
        except Exception:
            pass
    return "—"


def _calculator_summary(bank: str, family_key: str) -> str:
    try:
        constraints = tuple(c for c in all_constraints() if c.bank_name == bank and c.family_key == family_key)
    except Exception:
        constraints = ()
    if not constraints:
        return ""
    parts: list[str] = []
    for item in constraints:
        item_parts = [str(getattr(item, "calculator_product", "Hesaplama aracı") or "Hesaplama aracı")]
        max_amount = getattr(item, "max_financing_amount", None)
        if max_amount is not None:
            item_parts.append(f"giriş üst sınırı {_money(max_amount)}")
        min_m = getattr(item, "min_maturity_months", None)
        max_m = getattr(item, "max_maturity_months", None)
        observed = getattr(item, "observed_maturity_months", None)
        if min_m is not None and max_m is not None:
            item_parts.append(f"{int(min_m)}–{int(max_m)} ay")
        elif observed is not None:
            item_parts.append(f"{int(observed)} ay gözleminde")
        age = getattr(item, "max_vehicle_age", None)
        if age is not None:
            item_parts.append(f"2.el yaş ≤ {int(age)}")
        if str(getattr(item, "amount_limit_mode", "") or "") == "term_scoped_observation":
            item_parts.append("diğer vadelere genellenmez")
        parts.append(" · ".join(item_parts))
    return " | ".join(parts)


@lru_cache(maxsize=2048)
def _qualitative_cached(product_name: str, family: str, scope: str, clean_text: str) -> tuple[tuple[str, str], ...]:
    try:
        features = extract_qualitative_features(
            product_name=product_name,
            product_family=family,
            scope=scope,
            clean_text=clean_text,
        )
    except Exception:
        return ()
    return tuple((str(x.feature_key), str(x.feature_value)) for x in features if str(x.feature_value).strip())


def _qualitative(row: pd.Series) -> dict[str, str]:
    pairs = _qualitative_cached(
        _text(row.get("product_name"), ""),
        _text(row.get("product_family"), ""),
        _text(row.get("scope"), ""),
        _text(row.get("clean_text"), ""),
    )
    return dict(pairs)


def finance_family_options() -> list[tuple[str, str]]:
    frame = _products()
    pairs: dict[str, str] = {}
    for _, row in frame[["product_family_key", "product_family"]].drop_duplicates().iterrows():
        key = _text(row.get("product_family_key"), "")
        if not key:
            continue
        label = FAMILY_LABEL_OVERRIDES.get(key, _text(row.get("product_family"), key))
        pairs[key] = label
    priority = [
        "konut_finansmani", "arac_finansmani", "ihtiyac_finansmani", "alisveris_finansmani",
        "arsa_finansmani", "isyeri_finansmani", "ticari_finansman", "gayri_nakdi_finansman",
        "tarim_finansmani", "leasing", "surdurulebilir_finansman", "gayrimenkul_finansmani", "finansman",
    ]
    order = {key: idx for idx, key in enumerate(priority)}
    return sorted(pairs.items(), key=lambda kv: (order.get(kv[0], 999), kv[1].casefold()))


def bank_options_for_family(family_key: str) -> list[str]:
    frame = _products()
    work = frame[frame["product_family_key"].fillna("").astype(str).eq(family_key)]
    return sorted(work["bank_name"].dropna().astype(str).unique().tolist(), key=str.casefold)




def _display_metadata(row: pd.Series) -> dict[str, object]:
    raw = row.get("finance_rules_json")
    if _missing(raw):
        return {}
    try:
        payload = json.loads(str(raw)) if isinstance(raw, str) else dict(raw)
    except Exception:
        return {}
    meta = payload.get("display_metadata") or {}
    return meta if isinstance(meta, dict) else {}


def _join_clean(*values: object, separator: str = " · ") -> str:
    parts: list[str] = []
    for value in values:
        text = clean_cell(value)
        if text and text not in parts:
            parts.append(text)
    return separator.join(parts)

def _catalog_row(row: pd.Series) -> dict[str, object]:
    q = _qualitative(row)
    meta = _display_metadata(row)
    allocation, _ = _structured_fee_value(row, "allocation_fee", requested_amount=None)
    appraisal, _ = _structured_fee_value(row, "appraisal_fee", requested_amount=None)
    mortgage, _ = _structured_fee_value(row, "mortgage_fee", requested_amount=None)
    special = _join_clean(
        row.get("vehicle_age_rules_text"),
        row.get("housing_first_home_rules_text"),
        row.get("shopping_finance_rules_text"),
        meta.get("eligibility_condition"),
        meta.get("state_support_note"),
        meta.get("state_support_display"),
        meta.get("pricing_condition"),
        meta.get("pricing_advantage"),
        meta.get("storage_duration_note"),
        meta.get("grace_period_note"),
        meta.get("comparison_note"),
    )

    amount_limit = _amount_limit(row)
    if not clean_cell(amount_limit):
        amount_limit = _join_clean(meta.get("product_specific_limit_text"), meta.get("product_limit_note"))

    maturity = _maturity(row)
    if not clean_cell(maturity):
        maturity = _join_clean(meta.get("product_specific_maturity_text"), meta.get("currency_maturity_note"))

    ratio_rule = _ratio_rule(row)
    if not clean_cell(ratio_rule):
        bank = _text(row.get("bank_name"), "")
        family = _text(row.get("product_family_key"), "")
        if not (bank == "Dünya Katılım" and family == "arac_finansmani"):
            ratio_rule = clean_cell(meta.get("financing_ratio_note"))

    usage_purpose = _join_clean(q.get("usage_purpose"), meta.get("verified_usage_purpose"))
    repayment = _join_clean(q.get("repayment_structure"), meta.get("verified_repayment_structure"))
    currency = _join_clean(q.get("currency"), meta.get("verified_currency"), meta.get("currency"))
    channel = _join_clean(q.get("application_channel"), meta.get("verified_channel"))

    return {
        "Banka": _text(row.get("bank_name")),
        "Ürün": _text(row.get("product_name")),
        "Kapsam": _text(row.get("scope")),
        "Kâr Payı / Fiyatlama": _rate(row.get("profit_share_rate"), row.get("profit_share_rate_text")),
        "Limit / Finansman Tutarı": clean_cell(amount_limit),
        "Vade / Ödeme": clean_cell(maturity),
        "Finansman Oranı / Kuralı": clean_cell(ratio_rule),
        "Hesaplama Aracı": _calculator_summary(_text(row.get("bank_name"), ""), _text(row.get("product_family_key"), "")),
        "Tahsis Ücreti": clean_cell(allocation),
        "Ekspertiz Ücreti": clean_cell(appraisal),
        "İpotek / Rehin": clean_cell(mortgage),
        "Kullanım Amacı": clean_cell(usage_purpose),
        "Hedef Kitle": clean_cell(q.get("target_segment", "")),
        "Finansman Yapısı": clean_cell(q.get("transaction_structure", "")),
        "Ödeme / Kullanım": clean_cell(repayment),
        "Para Birimi": clean_cell(currency),
        "Teminat / Güvence": clean_cell(q.get("security_type", "")),
        "Kullanım / Kanal": clean_cell(channel),
        "Dış Ticaret": clean_cell(q.get("foreign_trade", "")),
        "Özel Koşullar": clean_cell(special),
        "Ürün Kaynağı": resolve_product_detail_url(_text(row.get("bank_name"), ""), _text(row.get("product_name"), ""), _source_url(row)),
        "Son Kontrol": _text(row.get("last_checked_at")),
        "__family_key": _text(row.get("product_family_key"), ""),
        "__max_maturity": pd.to_numeric(pd.Series([row.get("maximum_maturity_months")]), errors="coerce").iloc[0],
        "__max_amount": pd.to_numeric(pd.Series([row.get("maximum_financing_amount")]), errors="coerce").iloc[0],
        "__ratio": (float(row.get("maximum_financing_ratio")) if not _missing(row.get("maximum_financing_ratio")) and not (_text(row.get("bank_name"), "") == "Dünya Katılım" and _text(row.get("product_family_key"), "") == "arac_finansmani") else float("nan")),
        "__rate": pd.to_numeric(pd.Series([row.get("profit_share_rate")]), errors="coerce").iloc[0],
        "__product_id": row.get("id"),
    }


def build_finance_catalog_table(family_key: str, banks: Iterable[str] = ()) -> pd.DataFrame:
    frame = _products().copy()
    work = frame[frame["product_family_key"].fillna("").astype(str).eq(str(family_key))].copy()
    bank_tuple = tuple(str(x) for x in banks if str(x).strip())
    if bank_tuple:
        work = work[work["bank_name"].astype(str).isin(bank_tuple)].copy()
    if work.empty:
        return pd.DataFrame()
    work = work.sort_values(["bank_name", "product_name", "id"], kind="stable")
    return pd.DataFrame([_catalog_row(row) for _, row in work.iterrows()])


def public_catalog_columns(frame: pd.DataFrame, family_key: str | None = None) -> list[str]:
    """Return a family-specific, high-fill public schema.

    Missing fields are not represented as a wall of ``Belirtilmedi`` values.
    Instead, each finance family gets a decision-oriented column profile and
    columns with weak verified coverage are hidden dynamically.
    """
    if frame is None or frame.empty:
        return []
    if not family_key and "__family_key" in frame.columns:
        keys = [clean_cell(x) for x in frame["__family_key"].tolist() if clean_cell(x)]
        family_key = keys[0] if keys else ""

    profiles: dict[str, tuple[str, ...]] = {
        "konut_finansmani": (
            "Kâr Payı / Fiyatlama", "Vade / Ödeme", "Finansman Oranı / Kuralı",
            "Tahsis Ücreti", "Ekspertiz Ücreti", "İpotek / Rehin", "Kullanım Amacı",
            "Özel Koşullar", "Hesaplama Aracı", "Limit / Finansman Tutarı",
        ),
        "arac_finansmani": (
            "Kâr Payı / Fiyatlama", "Vade / Ödeme", "Finansman Oranı / Kuralı",
            "Hesaplama Aracı", "Özel Koşullar", "Tahsis Ücreti", "Kullanım / Kanal",
            "Teminat / Güvence", "Limit / Finansman Tutarı",
        ),
        "ihtiyac_finansmani": (
            "Limit / Finansman Tutarı", "Vade / Ödeme", "Kâr Payı / Fiyatlama",
            "Tahsis Ücreti", "Kullanım Amacı", "Kullanım / Kanal", "Ödeme / Kullanım",
            "Teminat / Güvence",
        ),
        "alisveris_finansmani": (
            "Limit / Finansman Tutarı", "Vade / Ödeme", "Kâr Payı / Fiyatlama",
            "Tahsis Ücreti", "Kullanım / Kanal", "Özel Koşullar", "Kullanım Amacı",
        ),
        "arsa_finansmani": (
            "Vade / Ödeme", "Finansman Oranı / Kuralı", "Kâr Payı / Fiyatlama",
            "Tahsis Ücreti", "Ekspertiz Ücreti", "İpotek / Rehin", "Kullanım Amacı",
            "Kullanım / Kanal",
        ),
        "isyeri_finansmani": (
            "Vade / Ödeme", "Finansman Oranı / Kuralı", "Kâr Payı / Fiyatlama",
            "Tahsis Ücreti", "Ekspertiz Ücreti", "İpotek / Rehin", "Kullanım Amacı",
        ),
        "gayrimenkul_finansmani": (
            "Kullanım Amacı", "Vade / Ödeme", "Finansman Oranı / Kuralı",
            "Kâr Payı / Fiyatlama", "Tahsis Ücreti", "Ekspertiz Ücreti", "İpotek / Rehin",
        ),
        "ticari_finansman": (
            "Kullanım Amacı", "Finansman Yapısı", "Limit / Finansman Tutarı", "Vade / Ödeme",
            "Teminat / Güvence", "Para Birimi", "Kullanım / Kanal", "Ödeme / Kullanım",
            "Dış Ticaret",
        ),
        "gayri_nakdi_finansman": (
            "Finansman Yapısı", "Kullanım Amacı", "Para Birimi", "Dış Ticaret",
            "Kullanım / Kanal", "Teminat / Güvence", "Ödeme / Kullanım",
        ),
        "tarim_finansmani": (
            "Özel Koşullar", "Vade / Ödeme", "Kullanım Amacı", "Finansman Yapısı",
            "Finansman Oranı / Kuralı", "Ödeme / Kullanım", "Teminat / Güvence",
            "Kullanım / Kanal", "Limit / Finansman Tutarı",
        ),
        "leasing": (
            "Kullanım Amacı", "Finansman Oranı / Kuralı", "Vade / Ödeme", "Para Birimi",
            "Teminat / Güvence", "Kullanım / Kanal", "Dış Ticaret",
        ),
        "surdurulebilir_finansman": (
            "Kullanım Amacı", "Vade / Ödeme", "Finansman Oranı / Kuralı", "Kâr Payı / Fiyatlama",
            "Limit / Finansman Tutarı", "Kullanım / Kanal", "Özel Koşullar",
        ),
    }
    generic = (
        "Kullanım Amacı", "Vade / Ödeme", "Limit / Finansman Tutarı", "Kâr Payı / Fiyatlama",
        "Finansman Yapısı", "Teminat / Güvence", "Kullanım / Kanal", "Özel Koşullar",
    )
    preferred = profiles.get(str(family_key or ""), generic)
    threshold = {
        "konut_finansmani": 0.28,
        "arac_finansmani": 0.25,
        "ihtiyac_finansmani": 0.18,
        "alisveris_finansmani": 0.25,
        "ticari_finansman": 0.18,
        "gayri_nakdi_finansman": 0.20,
        "tarim_finansmani": 0.15,
        "leasing": 0.18,
    }.get(str(family_key or ""), 0.20)
    minimum_optional = {
        "konut_finansmani": 5,
        "arac_finansmani": 5,
        "ihtiyac_finansmani": 3,
        "alisveris_finansmani": 4,
        "ticari_finansman": 2,
        "gayri_nakdi_finansman": 4,
        "tarim_finansmani": 2,
        "leasing": 1,
    }.get(str(family_key or ""), 3)
    return select_dense_columns(
        sanitize_frame(frame),
        preferred=preferred,
        mandatory=("Banka", "Ürün"),
        trailing=("Ürün Kaynağı",),
        min_fill=threshold,
        min_optional=minimum_optional,
        max_optional=9,
    )


def finance_catalog_insights(frame: pd.DataFrame) -> list[tuple[str, str]]:
    if frame is None or frame.empty:
        return []
    insights: list[tuple[str, str]] = []

    counts = frame.groupby("Banka", dropna=True).size().sort_values(ascending=False)
    if not counts.empty:
        insights.append(("En fazla ürün seçeneği", f"{counts.index[0]} · {int(counts.iloc[0])} ürün"))

    maturity = frame.dropna(subset=["__max_maturity"]).copy() if "__max_maturity" in frame else pd.DataFrame()
    if not maturity.empty:
        best = maturity.sort_values("__max_maturity", ascending=False).iloc[0]
        insights.append(("En uzun yayımlanmış vade", f"{best['Banka']} · {best['Ürün']} · {int(best['__max_maturity'])} ay"))

    amounts = frame.dropna(subset=["__max_amount"]).copy() if "__max_amount" in frame else pd.DataFrame()
    if not amounts.empty:
        best = amounts.sort_values("__max_amount", ascending=False).iloc[0]
        insights.append(("En yüksek yayımlanmış ürün limiti", f"{best['Banka']} · {best['Ürün']} · {_money(best['__max_amount'])}"))

    ratios = frame.dropna(subset=["__ratio"]).copy() if "__ratio" in frame else pd.DataFrame()
    if not ratios.empty:
        best = ratios.sort_values("__ratio", ascending=False).iloc[0]
        insights.append(("En yüksek yayımlanmış finansman oranı", f"{best['Banka']} · {best['Ürün']} · %{float(best['__ratio']):g}".replace(".", ",")))

    return insights[:4]


def numeric_money_from_text(value: object) -> float | None:
    text = str(value or "")
    if any(marker in text.casefold() for marker in ("doğrulanmadı", "belirtilmedi", "—")):
        return None
    m = re.search(r"([0-9][0-9.]*,[0-9]{2})\s*TL", text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(".", "").replace(",", "."))
    except Exception:
        return None


def scenario_insights(frame: pd.DataFrame) -> list[tuple[str, str]]:
    if frame is None or frame.empty:
        return []
    insights: list[tuple[str, str]] = []
    for column, label in (("Toplam Geri Ödeme", "En düşük doğrulanmış toplam geri ödeme"), ("Aylık Taksit", "En düşük doğrulanmış aylık taksit")):
        if column not in frame.columns:
            continue
        work = frame.copy()
        work["__money"] = work[column].map(numeric_money_from_text)
        work = work.dropna(subset=["__money"])
        if work.empty:
            continue
        best = work.sort_values("__money", ascending=True).iloc[0]
        condition = str(best.get("Koşul") or "").strip()
        suffix = f" · {condition}" if condition and condition not in {"—", "Standart"} else ""
        insights.append((label, f"{best['Banka']}{suffix} · {_money(best['__money'])}"))
    return insights


def detailed_product_record(product_id: object) -> dict[str, str]:
    frame = _products()
    try:
        found = frame[frame["id"].astype(str).eq(str(product_id))]
    except Exception:
        return {}
    if found.empty:
        return {}
    row = found.iloc[0]
    public = _catalog_row(row)
    public.pop("__max_maturity", None)
    public.pop("__max_amount", None)
    public.pop("__ratio", None)
    public.pop("__rate", None)
    public.pop("__product_id", None)
    extra = {
        "Faizsiz / Kâr Paysız Notu": _text(row.get("interest_free_text")),
        "Araç Finansman Kuralları": _text(row.get("vehicle_finance_rules_text")),
        "Alışveriş Telefon Kuralı": _text(row.get("shopping_phone_rule_text")),
        "Ücret Muafiyeti": _text(row.get("fee_waiver_text")),
        "İlk Konut Kuralları": _text(row.get("housing_first_home_rules_text")),
        "Ek Konut Kuralları": _text(row.get("housing_additional_home_rules_text")),
    }
    for key, value in extra.items():
        if clean_cell(value):
            public[key] = clean_cell(value)
    return public
