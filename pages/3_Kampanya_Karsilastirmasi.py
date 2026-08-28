from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

from src.ui_campaign_dashboard import public_campaign_columns
from src.ui_table_density import clean_cell
from src.ui_theme import (
    apply_bansa_theme,
    render_insight_card,
    render_page_header,
    render_recommendation_box,
    render_section_lead,
    render_sidebar_navigation,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "curated_dashboard"

st.set_page_config(
    page_title="BANSA · Kampanya Karşılaştırması",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_bansa_theme()
render_sidebar_navigation("campaign")
render_page_header(
    "Kampanya Karşılaştırması",
    "Kategori, harcama tutarı, kullanım tipi ve önceliğe göre aktif kampanyaları sadeleştirir. "
    "Önce BANSA önerisi ve özet kartları gösterilir; detaylı tablo kullanıcı isterse açılır.",
    eyebrow="BANSA · Akıllı Kampanya Paneli",
)

rows = pd.read_csv(DATA / "campaign_dashboard_static.csv", dtype=str, keep_default_na=False)
profiles = json.loads((DATA / "campaign_profiles.json").read_text(encoding="utf-8"))

TODAY = date(2026, 8, 27)
USER_FRIENDLY_MISSING = "Detay için kampanya sayfasını inceleyin"
VALUE_DEPENDS_ON_TERMS = "Kampanya koşuluna göre değişir"

COMMON_DETAIL_COLUMNS = [
    "Banka",
    "Kampanya Adı",
    "Kampanya Kategorisi",
    "Başlangıç Tarihi",
    "Bitiş Tarihi",
    "Katılım Kanalı",
    "Kart / Müşteri Tipi",
    "Resmî Kaynak Linki",
]

USAGE_KEYWORDS = {
    "Tümü": (),
    "Online / e-ticaret": (
        "online",
        "e-ticaret",
        "internet",
        "mobil",
        "uygulama",
        "hepsiburada",
        "amazon",
        "trendyol",
        "n11",
        "pazarama",
        "pttavm",
        "web",
    ),
    "Mağaza / POS": (
        "mağaza",
        "pos",
        "üye işyeri",
        "alışveriş",
        "market",
        "akaryakıt",
        "restoran",
        "giyim",
    ),
    "Kartlı alışveriş": (
        "kart",
        "kredi kartı",
        "sağlam kart",
        "world",
        "bankkart",
        "paraf",
        "taksit",
    ),
    "Mobil bankacılık": (
        "mobil",
        "mobil bankacılık",
        "internet şube",
        "dijital",
        "görüntülü görüşme",
    ),
    "Finansman başvurusu": (
        "finansman",
        "kâr payı",
        "vade",
        "tahsis",
        "başvuru",
    ),
}

PRIORITY_LABELS = [
    "BANSA önerisi",
    "En yüksek avantaj",
    "Katılımı kolay",
    "Son günü yaklaşan",
    "Online kullanıma uygun",
]

BENEFIT_COLUMNS = [
    "Maksimum Kazanılabilir İndirim (TL)",
    "Maksimum Puan Limiti",
    "Maksimum Kazanım Limiti",
    "Sabit İndirim Tutarı (TL)",
    "Hediye Puan / İade Tutarı (TL)",
    "Ödül Tutarı / Türü",
    "Kazanılacak Puan / TL Karşılığı",
    "İndirim Oranı (%)",
    "İlave / Ücretsiz Taksit Sayısı",
    "Vade Farksız Taksit Sayısı (Ay)",
    "Peşin Fiyatına Taksit Sayısı",
    "Sonradan Ücretsiz / Kampanyalı Taksit Sayısı",
    "Kampanyalı Finansman Tutarı (TL)",
    "Sıfır Kâr Paylı / Masrafsız Finansman Üst Limiti (TL)",
    "Ana Fayda",
]

CONDITION_COLUMNS = [
    "Katılım Şartı (SMS / Mobil Onay)",
    "Kampanya Kod Şartı",
    "Ek Ürün Koşulu",
    "Belge / Kayıt Şartı",
    "Fatura / Kurum Sözleşme Zorunluluğu",
    "Paket Şartları",
    "Doğrudan Kuruma Transfer Şartı",
    "Kazanım Şartı",
    "Kart / Müşteri Tipi",
]


# -----------------------------------------------------------------------------
# Presentation-only helpers. These functions do not invent bank facts; they only
# choose how verified/static rows are summarized in the campaign dashboard.
# -----------------------------------------------------------------------------


def _date_value(value: object) -> date | None:
    text = clean_cell(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except Exception:
            continue
    return None


def _days_left(value: object) -> int | None:
    dt = _date_value(value)
    if dt is None:
        return None
    return (dt - TODAY).days


def _normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _first_meaningful(row: pd.Series, columns: Iterable[str]) -> str:
    for column in columns:
        if column in row.index:
            value = clean_cell(row.get(column, ""))
            if value:
                return value
    return ""


def _first_combined(row: pd.Series, columns: Iterable[str], *, limit: int = 2) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for column in columns:
        if column not in row.index:
            continue
        value = clean_cell(row.get(column, ""))
        if value and value.casefold() not in seen:
            values.append(value)
            seen.add(value.casefold())
        if len(values) >= limit:
            break
    return " · ".join(values)


def _campaign_text(row: pd.Series) -> str:
    return " ".join(_normalize_text(v) for v in row.values).casefold()


def _contains_any(row: pd.Series, keywords: Iterable[str]) -> bool:
    text = _campaign_text(row)
    return any(keyword.casefold() in text for keyword in keywords)


def _extract_numbers(text: object) -> list[float]:
    raw = _normalize_text(text)
    numbers: list[float] = []
    for hit in re.findall(r"\d+(?:[\.,]\d+)?", raw):
        try:
            numbers.append(float(hit.replace(".", "").replace(",", ".")))
        except Exception:
            continue
    return numbers


def _benefit_score(row: pd.Series) -> float:
    score = 0.0
    haystack = _campaign_text(row)

    # Open numeric reward/discount/taksit information increases usefulness.
    for column in BENEFIT_COLUMNS:
        if column not in row.index:
            continue
        value = clean_cell(row.get(column, ""))
        if not value:
            continue
        score += 8.0
        nums = _extract_numbers(value)
        if nums:
            score += min(max(nums), 50_000.0) / 2_500.0

    # Familiar high-intent terms make the campaign easier to explain in demo.
    keyword_boosts = {
        "taksit": 7.0,
        "indirim": 7.0,
        "puan": 6.5,
        "nakit iade": 8.0,
        "masrafsız": 6.0,
        "ücretsiz": 5.0,
        "sıfır kâr": 8.0,
        "vade farksız": 8.0,
        "online": 3.5,
        "mobil": 3.0,
    }
    for keyword, boost in keyword_boosts.items():
        if keyword in haystack:
            score += boost

    if str(row.get("Resmî Kaynak Linki", "")).startswith("http"):
        score += 8.0

    days = _days_left(row.get("Bitiş Tarihi", ""))
    if days is not None:
        if 0 <= days <= 30:
            score += 12.0
        elif 31 <= days <= 90:
            score += 7.0
        elif days > 90:
            score += 3.0

    return round(score, 2)


def _ease_score(row: pd.Series) -> float:
    text = _campaign_text(row)
    score = 0.0
    for keyword, boost in (
        ("otomatik", 12.0),
        ("mobil", 10.0),
        ("internet", 7.0),
        ("sms", 6.0),
        ("kod", -5.0),
        ("belge", -7.0),
        ("ek ürün", -6.0),
        ("üye işyeri", -2.0),
    ):
        if keyword in text:
            score += boost
    if str(row.get("Resmî Kaynak Linki", "")).startswith("http"):
        score += 4.0
    return round(score, 2)


def _scenario_fit_score(row: pd.Series, spending_amount: int, usage_type: str, card_user: bool, new_customer: bool) -> float:
    score = _benefit_score(row) + (_ease_score(row) * 0.65)
    text = _campaign_text(row)

    if usage_type != "Tümü" and _contains_any(row, USAGE_KEYWORDS[usage_type]):
        score += 16.0

    if card_user and any(token in text for token in ("kart", "kredi kartı", "world", "bankkart", "sağlam kart", "paraf")):
        score += 11.0
    if not card_user and "kart" in text:
        score -= 5.0

    if new_customer and any(token in text for token in ("yeni müşteri", "ilk kez", "müşteri ol", "hoş geldin")):
        score += 14.0
    if not new_customer and any(token in text for token in ("yeni müşteri", "ilk kez müşteri")):
        score -= 3.0

    min_amount = _first_meaningful(row, ["Asgari Harcama Tutarı (TL)", "Asgari Sepet Tutarı (TL)", "İşlem Başına Asgari Tutar (TL)", "Asgari Prim Tutarı"])
    nums = _extract_numbers(min_amount)
    if nums:
        threshold = min(nums)
        if spending_amount >= threshold:
            score += 7.0
        else:
            score -= 9.0

    days = _days_left(row.get("Bitiş Tarihi", ""))
    if days is not None and days < 0:
        score -= 100.0

    return round(score, 2)


def _main_benefit(row: pd.Series) -> str:
    return _first_meaningful(
        row,
        [
            "Örnek Senaryo",
            "Ödül Tutarı / Türü",
            "Kazanılacak Puan / TL Karşılığı",
            "Maksimum Kazanılabilir İndirim (TL)",
            "Maksimum Puan Limiti",
            "Maksimum Kazanım Limiti",
            "Sabit İndirim Tutarı (TL)",
            "İndirim Oranı (%)",
            "İndirim Türü",
            "İlave / Ücretsiz Taksit Sayısı",
            "Peşin Fiyatına Taksit Sayısı",
            "Peşin Fiyatına Taksit İmkanı",
            "Hoş Geldin Avantajı Türü",
            "Masraf Muafiyeti",
            "Tahsis / Masraf Durumu",
            "Kampanya Konusu",
        ],
    )


def _target_or_segment(row: pd.Series) -> str:
    return _first_meaningful(
        row,
        [
            "Geçerli Kartlar",
            "Kart / Müşteri Tipi",
            "Hedef Kitle (İlk Kez Müşteri Olanlar)",
            "Geçerli Marka / Sektör",
            "Sektör / Üye İşyeri",
            "Geçerli Sektör",
            "Kapsanan Ürün Kategorisi",
            "Finansman Amacı",
            "Sektör Kapsamı",
        ],
    )


def _normalize_campaign_rows(frame: pd.DataFrame, spending_amount: int, usage_type: str, card_user: bool, new_customer: bool) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        benefit = _main_benefit(row)
        days = _days_left(row.get("Bitiş Tarihi", ""))
        if days is None:
            deadline = "Tarih kampanya sayfasında"
        elif days < 0:
            deadline = "Süresi geçmiş görünüyor"
        elif days == 0:
            deadline = "Bugün son gün"
        elif days <= 30:
            deadline = f"{days} gün kaldı"
        else:
            deadline = clean_cell(row.get("Bitiş Tarihi", "")) or "Tarih kampanya sayfasında"

        records.append(
            {
                "Banka": clean_cell(row.get("Banka", "")),
                "Kampanya": clean_cell(row.get("Kampanya Adı", "")),
                "Tür": clean_cell(row.get("Kampanya Kategorisi", "")),
                "Ana Fayda": benefit,
                "Hedef Kitle": _target_or_segment(row),
                "Taksit": _first_combined(
                    row,
                    [
                        "İlave / Ücretsiz Taksit Sayısı",
                        "Azami Taksit Sınırı",
                        "Vade Farksız Taksit Sayısı (Ay)",
                        "Peşin Fiyatına Taksit Sayısı",
                        "Taksit İmkanı (Vade Farksız Taksit Sayısı)",
                        "Sonradan Ücretsiz / Kampanyalı Taksit Sayısı",
                    ],
                ),
                "İndirim / İade": _first_combined(
                    row,
                    [
                        "İndirim Türü",
                        "İndirim Oranı (%)",
                        "Sabit İndirim Tutarı (TL)",
                        "Maksimum Kazanılabilir İndirim (TL)",
                        "Prim İndirim Oranı (%)",
                        "Hediye Puan / İade Tutarı (TL)",
                    ],
                ),
                "Puan": _first_combined(
                    row,
                    [
                        "Kart Programı / Puan Türü",
                        "Kazanılacak Puan / TL Karşılığı",
                        "Maksimum Puan Limiti",
                        "Puan Yükleme Tarihi",
                        "Puan Son Kullanım Tarihi",
                    ],
                ),
                "Ödül": _first_combined(row, ["Ödül Tutarı / Türü", "Hoş Geldin Avantajı Türü", "Masraf Muafiyeti"]),
                "Min. Harcama": _first_meaningful(row, ["Asgari Harcama Tutarı (TL)", "Asgari Sepet Tutarı (TL)", "İşlem Başına Asgari Tutar (TL)", "Asgari Prim Tutarı"]),
                "Maks. Fayda": _first_meaningful(row, ["Maksimum Kazanılabilir İndirim (TL)", "Maksimum Puan Limiti", "Maksimum Kazanım Limiti"]),
                "Finansman Tutarı": _first_meaningful(row, ["Kampanyalı Finansman Tutarı (TL)", "Asgari - Azami Finansman Limiti (TL)", "Sıfır Kâr Paylı / Masrafsız Finansman Üst Limiti (TL)", "Asgari - Azami Finansman Tutarı", "Tanımlanan Esnaf / Müşteri Limiti (TL)", "Azami Tutar ve Vade Sınırı"]),
                "Vade": _first_meaningful(row, ["Kampanyalı Vade (Ay)", "Azami Vade", "Azami Finansman Vadesi", "Asgari - Azami Vade", "Vadesiz / Masrafsız Ödeme Süresi (30-60-90 Gün)", "Azami Erteleme Süresi (Ay)"]),
                "Kâr Payı": _first_meaningful(row, ["Kampanyalı Kâr Payı Oranı (%)", "İndirimli Kâr Payı Oranı (%)", "Sübvansiyonlu Kâr Payı Oranı (%)", "Kampanyalı Kâr Payı (%)", "Kampanyalı Kâr Payı (%)_Sağlık", "Kampanyalı Kâr Payı Oranı (%)_Umre", "Kâr Payı / Kâr-Zarar Ortaklık Oranı", "Vade Aşımı Kâr Payı Oranı (%)"]),
                "Başlangıç": clean_cell(row.get("Başlangıç Tarihi", "")),
                "Bitiş": clean_cell(row.get("Bitiş Tarihi", "")),
                "Kalan Süre": deadline,
                "Katılım Kanalı": clean_cell(row.get("Katılım Kanalı", "")),
                "Koşullar": _first_combined(row, CONDITION_COLUMNS, limit=3),
                "BANSA Uygunluk": "Uygun görünüyor",
                "BANSA Skoru": _scenario_fit_score(row, spending_amount, usage_type, card_user, new_customer),
                "Resmî Kaynak": clean_cell(row.get("Resmî Kaynak Linki", "")),
                "Kontrol Tarihi": clean_cell(row.get("Kontrol Tarihi", "")),
                "__days_left": 9999 if days is None else days,
                "__benefit_score": _benefit_score(row),
                "__ease_score": _ease_score(row),
                "__haystack": _campaign_text(row),
            }
        )

    normalized = pd.DataFrame(records)
    if normalized.empty:
        return normalized

    def _eligibility(row: pd.Series) -> str:
        score = float(row.get("BANSA Skoru", 0) or 0)
        text = str(row.get("__haystack", ""))
        if score < 0:
            return "Uygunluk düşük"
        if any(token in text for token in ("ek ürün", "belge", "kod", "üye işyeri")):
            return "Ek şartla uygun olabilir"
        return "Uygun görünüyor"

    normalized["BANSA Uygunluk"] = normalized.apply(_eligibility, axis=1)
    return normalized


def _friendly_campaign_value(value: object, column: str = "") -> str:
    text = clean_cell(value)
    if text:
        return text
    key = column.casefold()
    if "kaynak" in key or "link" in key or "tarih" in key or column.startswith("__"):
        return ""
    if any(token in key for token in ("fayda", "indirim", "puan", "ödül", "harcama", "taksit", "vade", "kâr", "kar", "finansman", "tutar", "limit")):
        return VALUE_DEPENDS_ON_TERMS
    if any(token in key for token in ("koşul", "kanal", "hedef", "kart", "müşteri")):
        return USER_FRIENDLY_MISSING
    return USER_FRIENDLY_MISSING


def _friendly_campaign_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in out.columns:
        if str(column).startswith("__"):
            continue
        out[column] = out[column].map(lambda value, c=column: _friendly_campaign_value(value, c))
    return out


def _filter_frame(frame: pd.DataFrame, selected_category: str, bank_filter: list[str], query: str, usage_type: str) -> pd.DataFrame:
    base = frame.copy()
    if selected_category != "Tümü":
        base = base[base["Kampanya Kategorisi"].eq(selected_category)].copy()
    if bank_filter:
        base = base[base["Banka"].isin(bank_filter)].copy()
    if usage_type != "Tümü":
        base = base[base.apply(lambda row: _contains_any(row, USAGE_KEYWORDS[usage_type]), axis=1)].copy()
    if query.strip():
        needle = query.strip().casefold()
        base = base[base.apply(lambda row: needle in _campaign_text(row), axis=1)].copy()
    return base


def _sort_normalized(frame: pd.DataFrame, priority: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    if priority == "En yüksek avantaj":
        return frame.sort_values(["__benefit_score", "BANSA Skoru", "Banka", "Kampanya"], ascending=[False, False, True, True], kind="stable")
    if priority == "Katılımı kolay":
        return frame.sort_values(["__ease_score", "BANSA Skoru", "Banka", "Kampanya"], ascending=[False, False, True, True], kind="stable")
    if priority == "Son günü yaklaşan":
        return frame.sort_values(["__days_left", "BANSA Skoru", "Banka", "Kampanya"], ascending=[True, False, True, True], kind="stable")
    if priority == "Online kullanıma uygun":
        online = frame["__haystack"].str.contains("online|internet|mobil|web|e-ticaret|uygulama", case=False, regex=True)
        out = frame.assign(__online=online.astype(int))
        return out.sort_values(["__online", "BANSA Skoru", "Banka", "Kampanya"], ascending=[False, False, True, True], kind="stable").drop(columns=["__online"])
    return frame.sort_values(["BANSA Skoru", "__benefit_score", "Banka", "Kampanya"], ascending=[False, False, True, True], kind="stable")


category_options = ["Tümü"] + [x for x in profiles if x in set(rows["Kampanya Kategorisi"])]
bank_options = sorted(rows["Banka"].unique().tolist(), key=str.casefold)

with st.container(border=True):
    render_section_lead(
        "1 · Kampanya ihtiyacınızı seçin",
        "Kategori, banka, harcama tutarı ve kullanım tipine göre kampanyaları kişisel senaryoya yaklaştırıyoruz.",
    )
    c1, c2, c3 = st.columns([1.2, 1.7, 1.15])
    with c1:
        selected_category = st.selectbox("Kampanya kategorisi", category_options)
    with c2:
        bank_filter = st.multiselect("Banka filtresi", bank_options, placeholder="Boş bırakın: tüm bankalar")
    with c3:
        spending_amount = int(
            st.number_input(
                "Tahmini harcama / işlem tutarı (TL)",
                min_value=0,
                max_value=10_000_000,
                value=5_000,
                step=500,
                format="%d",
            )
        )

    c4, c5, c6 = st.columns([1.25, 1.25, 1.5])
    with c4:
        usage_type = st.selectbox("Kullanım tipi", list(USAGE_KEYWORDS))
    with c5:
        priority = st.selectbox("Öncelik", PRIORITY_LABELS)
    with c6:
        query = st.text_input("Ara", placeholder="market, akaryakıt, eğitim, yeni müşteri...")

    e1, e2, e3 = st.columns([1.0, 1.0, 2.0])
    with e1:
        card_user = st.checkbox("Kart kampanyalarına açığım", value=True)
    with e2:
        new_customer = st.checkbox("Yeni müşteri teklifleri ilgimi çeker", value=False)
    with e3:
        st.caption("Bu seçimler yalnız sıralamayı ve öneri açıklamasını etkiler; resmî kampanya koşullarının yerine geçmez.")

filtered = _filter_frame(rows, selected_category, bank_filter, query, usage_type)
normalized = _normalize_campaign_rows(filtered, spending_amount, usage_type, card_user, new_customer)
normalized = _sort_normalized(normalized, priority)

source_count = int(filtered.get("Resmî Kaynak Linki", pd.Series(dtype=str)).astype(str).str.startswith("http").sum()) if not filtered.empty else 0
soon_count = 0
if not filtered.empty:
    soon_count = int(filtered["Bitiş Tarihi"].map(_days_left).map(lambda x: x is not None and 0 <= x <= 30).sum())

m1, m2, m3, m4 = st.columns(4)
with m1:
    render_insight_card("Aktif kampanya", str(len(filtered)), "Seçilen filtrelere uyan satır")
with m2:
    render_insight_card("Banka", str(filtered["Banka"].nunique() if not filtered.empty else 0), "Karşılaştırmaya giren banka")
with m3:
    render_insight_card("Yaklaşan son tarih", str(soon_count), "30 gün içinde biten kampanya")
with m4:
    render_insight_card("Resmî kaynak", str(source_count), "Kaynak linki bulunan satır")

render_section_lead(
    "2 · BANSA kampanya önerisi",
    "Önce en uygulanabilir seçenekleri öne çıkarıyoruz. Büyük tabloyu aşağıdaki açılır bölümde saklı tutuyoruz.",
)

if normalized.empty:
    st.info("Seçtiğiniz filtrelerle eşleşen aktif kampanya bulunamadı. Kategori veya kullanım tipi filtresini genişletebilirsiniz.")
else:
    top = normalized.iloc[0]
    explanation_parts = [
        f"{top['Banka']} tarafındaki {top['Kampanya']} kampanyası bu senaryoda öne çıkıyor.",
        f"Kategori: {top['Tür']}.",
    ]
    if clean_cell(top.get("Ana Fayda", "")):
        explanation_parts.append(f"Ana fayda: {top['Ana Fayda']}.")
    if clean_cell(top.get("Kalan Süre", "")):
        explanation_parts.append(f"Süre: {top['Kalan Süre']}.")
    explanation_parts.append(
        "Kampanya özel şartları ve müşteri uygunluğu değişebileceği için son kontrol resmî kampanya sayfasından yapılmalıdır."
    )
    render_recommendation_box(
        "BANSA önerisi",
        " ".join(explanation_parts),
        badge=f"Skor: {top['BANSA Skoru']}",
    )

    top_cols = public_campaign_columns(normalized, selected_category)
    if "BANSA Uygunluk" in normalized.columns and "BANSA Uygunluk" not in top_cols:
        insert_at = 2 if len(top_cols) >= 2 else len(top_cols)
        top_cols.insert(insert_at, "BANSA Uygunluk")
    if "Kalan Süre" in normalized.columns and "Kalan Süre" not in top_cols:
        top_cols.append("Kalan Süre")
    if "BANSA Skoru" in normalized.columns and "BANSA Skoru" not in top_cols:
        top_cols.append("BANSA Skoru")
    top_cols = [c for c in top_cols if c in normalized.columns and not c.startswith("__")]

    preview = _friendly_campaign_frame(normalized[top_cols].head(40))
    st.dataframe(
        preview,
        use_container_width=True,
        hide_index=True,
        height=min(560, 84 + 35 * max(5, len(preview))),
        column_config={"Resmî Kaynak": st.column_config.LinkColumn("Kaynak", display_text="Aç", width="small")},
    )

    st.download_button(
        "Öneri tablosunu CSV indir",
        preview.to_csv(index=False).encode("utf-8-sig"),
        file_name="bansa_kampanya_oneri_tablosu.csv",
        mime="text/csv",
    )

with st.expander("Detaylı kampanya karşılaştırma tablosunu göster", expanded=False):
    render_section_lead(
        "3 · Detaylı kampanya tablosu",
        "Kategoriye özel tüm sütunlar burada tutulur. Eksik veya kişiye/kanala bağlı alanlarda sayı uydurulmaz; kullanıcı dostu yönlendirme gösterilir.",
    )
    if filtered.empty:
        st.info("Detay tablosu için uygun kampanya bulunamadı.")
    else:
        if selected_category == "Tümü":
            detail_cols = COMMON_DETAIL_COLUMNS.copy()
            # Tümü görünümünde en dolu karar sütunlarını ekle.
            normalized_detail_cols = public_campaign_columns(normalized, "Tümü")
            detail = normalized[[c for c in normalized_detail_cols if c in normalized.columns and not c.startswith("__")]].copy()
            detail = _friendly_campaign_frame(detail)
            source_col = "Resmî Kaynak"
        else:
            detail_cols = []
            for column in COMMON_DETAIL_COLUMNS + profiles.get(selected_category, []):
                if column in filtered.columns and column not in detail_cols:
                    detail_cols.append(column)
            detail = _friendly_campaign_frame(filtered[detail_cols])
            source_col = "Resmî Kaynak Linki"
        st.dataframe(
            detail,
            use_container_width=True,
            hide_index=True,
            height=min(780, 84 + 35 * max(5, len(detail))),
            column_config={source_col: st.column_config.LinkColumn("Kaynak", display_text="Aç", width="small")},
        )
        st.download_button(
            "Detaylı kampanya tablosunu CSV indir",
            detail.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"bansa_kampanya_detay_{selected_category.lower().replace(' ', '_').replace('/', '-')}.csv",
            mime="text/csv",
        )

with st.expander("Kampanya yorumlama notları", expanded=False):
    render_section_lead(
        "4 · Veri güveni",
        "BANSA kampanya avantajını açıklarken yalnız statik doğrulanmış snapshot ve resmî kaynak linklerini kullanır.",
    )
    st.markdown(
        """
- Puan, indirim, taksit ve finansman bilgileri kampanya koşulunda açıkça yer alıyorsa görünür.
- Kişiye, karta, kanala veya kampanya koduna bağlı şartlarda kesin fayda uydurulmaz.
- Eksik alanlarda kullanıcıya kötü görünen ham veri mesajı yerine kampanya sayfası ve banka yönlendirmesi yapılır.
- Detaylı tablo varsayılan kapalıdır; jüri demosunda önce özet ve öneri bölümü gösterilir.
        """
    )
