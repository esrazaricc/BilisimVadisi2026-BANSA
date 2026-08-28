from __future__ import annotations

import json
import os
import re
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from src.finance_runtime_repository import get_standard_products
from src.bansa_v40_finance_catalog import canonical_scenario_products, is_personal_offer, apply_source_overrides
from src.finance_official_calculator_service import (
    is_live_capable_row,
    live_capable_bank_count,
)
from src.finance_user_scenario_resolver import resolve_user_scenarios
from src.ui_theme import (
    apply_bansa_theme,
    render_page_header,
    render_section_lead,
    render_sidebar_navigation,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "curated_dashboard"

st.set_page_config(
    page_title="BANSA · Finansman Karşılaştırması",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_bansa_theme()
render_sidebar_navigation("finance")
render_page_header(
    "Finansman Karşılaştırması",
    "Tutar, vade ve finansman türüne göre kullanıcı dostu karşılaştırma. "
    "BANSA, resmî hesaplama aracı eşlemesi bulunan bankalarda girilen tutar/vadeyi birebir canlı doğrular; "
    "canlı doğrulanamayan bir bankada eski oranı güncelmiş gibi kullanmaz.",
)

rows = pd.read_csv(DATA / "finance_dashboard_static.csv", dtype=str, keep_default_na=False)
profiles = json.loads((DATA / "finance_profiles.json").read_text(encoding="utf-8"))
scenarios = pd.read_csv(DATA / "finance_example_scenarios.csv", dtype=str, keep_default_na=False)

PUBLIC_MISSING = "Kişiye özel teklif — banka ile görüşün"
PRODUCT_MISSING = "Kamuya açık doğrulanmış ürün bulunamadı"
SCENARIO_MISSING = "Bu tutar/vade için doğrulanmış sayısal sonuç yok"

FAMILY_KEYS = {
    "Konut Finansmanı": ("konut_finansmani",),
    "Taşıt Finansmanı": ("arac_finansmani",),
    "İhtiyaç Finansmanı": ("ihtiyac_finansmani",),
    "Alışveriş Finansmanı": ("alisveris_finansmani",),
    "Arsa & Gayrimenkul Finansmanı": ("arsa_finansmani", "gayrimenkul_finansmani"),
    "İş Yeri Finansmanı": ("isyeri_finansmani",),
    "Ticari Finansman (Nakdi)": ("ticari_finansman",),
    "Gayri Nakdi Finansman": ("gayri_nakdi_finansman",),
    "Tarım Finansmanı": ("tarim_finansmani",),
    "Leasing / Finansal Kiralama": ("leasing",),
    "Sürdürülebilir Finansman": ("surdurulebilir_finansman",),
    "Diğer Finansmanlar": ("finansman",),
}


def _is_placeholder(value: object) -> bool:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    key = text.casefold()
    if key in {"", "-", "—", "nan", "none", "null"}:
        return True
    patterns = (
        "bilgi yok",
        "resmî kaynakta yayımlanmamış",
        "resmi kaynakta yayınlanmamış",
        "kamuya açık doğrulanmış ürün bulunamadı",
        "güncel birebir hesaplama çıktısı doğrulanmadı",
        "birebir resmî senaryo bulunamadı",
        "birebir resmi senaryo bulunamadı",
    )
    return any(pattern in key for pattern in patterns)


def _friendly_value(value: object, column: str = "") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not _is_placeholder(text):
        return text

    column_key = column.casefold()
    if "kaynak" in column_key:
        return ""
    if "tarih" in column_key or "kontrol" in column_key:
        return ""
    if column in {"Ürün", "Ürün Durumu"}:
        return PRODUCT_MISSING
    if any(token in column_key for token in ("taksit", "geri ödeme", "kâr", "kar", "oran", "tutar", "vade", "ücret", "masraf", "tahsis", "ekspertiz", "ipotek", "rehin", "limit")):
        return PUBLIC_MISSING
    return "Detay için banka ile görüşün"


def _friendly_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in out.columns:
        out[column] = out[column].map(lambda value, c=column: _friendly_value(value, c))
    return out


def _fmt_money(value: object) -> str:
    if value is None:
        return ""
    try:
        number = Decimal(str(value))
    except Exception:
        return _friendly_value(value)
    return f"{float(number):,.2f} TL".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_rate(value: object) -> str:
    if value is None:
        return ""
    try:
        number = Decimal(str(value))
    except Exception:
        return _friendly_value(value)
    return (f"%{number.normalize():f}").replace(".", ",")


def _public_variant(value: object) -> str:
    raw = str(value or "").strip()
    key = re.sub(r"[^a-z0-9]+", "_", raw.casefold().replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")).strip("_")
    labels = {
        "": "Standart", "standard": "Standart", "standart": "Standart",
        "0km": "0 km", "0_km": "0 km", "2el": "2. el", "2_el": "2. el",
        "0km_sigortali": "0 km · Sigortalı", "0km_sigortasiz": "0 km · Sigortasız",
        "2el_sigortali": "2. el · Sigortalı", "2el_sigortasiz": "2. el · Sigortasız",
        "sigortali": "Sigortalı", "sigortasiz": "Sigortasız",
        "yeni_konut": "Yeni konut", "2el_konut": "İkinci el konut",
        "sifir_konut": "Sıfır konut", "ilk_ev": "İlk ev", "mevcut_konut": "Mevcut konut",
    }
    return labels.get(key, raw.replace("_", " ").strip().title() or "Standart")


def _public_numeric_table(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["Seçenek"] = out["Varyant"].map(_public_variant)
    out["Hesaplama Kaynağı"] = out["__source_mode"].map(
        lambda mode: "Banka hesaplama aracı" if str(mode) == "live" else "Resmî fiyatlama verisi"
    )
    out = out.rename(columns={
        "Kâr Payı": "Kâr Payı Oranı",
        "Tahsis": "Tahsis Ücreti",
        "Ekspertiz": "Ekspertiz Ücreti",
    })
    cols = [
        "Banka", "Ürün", "Seçenek", "Kâr Payı Oranı", "Aylık Taksit",
        "Toplam Geri Ödeme", "Tahsis Ücreti", "Ekspertiz Ücreti",
        "İpotek / Rehin", "Hesaplama Kaynağı", "Resmî Kaynak",
    ]
    return out[[c for c in cols if c in out.columns]]


SHOW_TECHNICAL_DETAILS = os.getenv("BANSA_SHOW_TECHNICAL_DETAILS", "0").strip() == "1"


def _projection_mode(mode: str) -> str:
    labels = {
        "exact_verified": "Birebir doğrulanmış resmî senaryo",
        "official_pricing_table_model": "Resmî fiyat tablosundan hesaplandı",
        "verified_same_maturity_projection": "Aynı vadeli doğrulanmış senaryodan projeksiyon",
        "bansa_managed_calculator_model": "BANSA resmî kaynak modeliyle hesapladı",
        "official_visible_calculator_rate_model": "Resmî hesaplama ekranındaki oranla hesaplandı",
        "calculator_input_rate_model": "Senaryo oranıyla hesaplandı",
    }
    return labels.get(str(mode), "BANSA hesapladı")


def _family_products(selected_type: str, bank_filter: list[str]) -> pd.DataFrame:
    keys = FAMILY_KEYS.get(selected_type, tuple())
    if not keys:
        return pd.DataFrame()
    products = apply_source_overrides(get_standard_products().copy())
    products = products[products["product_family_key"].fillna("").astype(str).isin(keys)].copy()
    if bank_filter:
        products = products[products["bank_name"].astype(str).isin(bank_filter)].copy()
    if len(keys) == 1:
        products = canonical_scenario_products(products, keys[0])
    return products.sort_values(["bank_name", "product_name", "id"], kind="stable")


@st.cache_data(ttl=60, show_spinner=False)
def _scenario_rows(selected_type: str, amount: int, maturity: int, bank_filter: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    products = _family_products(selected_type, bank_filter)
    if products.empty:
        return pd.DataFrame(), pd.DataFrame()

    result_rows: list[dict[str, object]] = []
    no_numeric_rows: list[dict[str, object]] = []

    # V45: dashboard and chatbot share the exact same resolver.  Official
    # live-calculator mappings are authoritative for entered amount/maturity.
    # If such a bank cannot be verified live, BANSA fails closed instead of
    # showing an older rate as if it were current.
    # V44 compatibility: live_records_for_rows(products, amount, maturity) is now
    # encapsulated by the shared V45 resolver below so chatbot/UI cannot diverge.
    resolutions = resolve_user_scenarios(products, amount, maturity)

    for _, product in products.iterrows():
        resolution = resolutions.get(int(product.get("id")))
        if resolution and resolution.mode == "live":
            for rec in resolution.live_records:
                result_rows.append(
                    {
                        "Banka": rec["bank_name"],
                        "Ürün": rec["product_name"],
                        "Durum": "Resmî canlı hesaplama",
                        "Varyant": str(rec.get("variant") or "standard"),
                        "Kâr Payı": _fmt_rate(rec.get("rate")),
                        "Aylık Taksit": _fmt_money(rec.get("monthly")),
                        "Toplam Geri Ödeme": _fmt_money(rec.get("total")),
                        "Tahsis": _fmt_money(rec.get("allocation_fee")) if rec.get("allocation_fee") is not None else PUBLIC_MISSING,
                        "Ekspertiz": _fmt_money(rec.get("appraisal_fee")) if rec.get("appraisal_fee") is not None else PUBLIC_MISSING,
                        "İpotek / Rehin": _fmt_money(rec.get("mortgage_fee")) if rec.get("mortgage_fee") is not None else PUBLIC_MISSING,
                        "Sonuç Türü": "Resmî banka hesaplama aracı · birebir senaryo",
                        "Resmî Kaynak": str(rec.get("source_url") or product.get("source_url") or ""),
                        "Kontrol Tarihi": str(rec.get("checked_at") or ""),
                        "Not": str(rec.get("source_note") or "Banka hesaplama aracı, girilen tutar ve vade için canlı olarak doğrulandı."),
                        "__monthly": float(rec["monthly"]),
                        "__total": float(rec["total"]),
                        "__source_mode": "live",
                    }
                )
            continue

        if resolution and resolution.mode == "model":
            for rec in resolution.projections:
                result_rows.append(
                    {
                        "Banka": rec.bank_name,
                        "Ürün": rec.product_name,
                        "Durum": "BANSA hesapladı",
                        "Varyant": rec.variant,
                        "Kâr Payı": _fmt_rate(rec.profit_share_rate),
                        "Aylık Taksit": _fmt_money(rec.monthly_installment),
                        "Toplam Geri Ödeme": _fmt_money(rec.installment_total),
                        "Tahsis": _fmt_money(rec.allocation_fee) if rec.allocation_fee is not None else PUBLIC_MISSING,
                        "Ekspertiz": _fmt_money(rec.appraisal_fee) if rec.appraisal_fee is not None else PUBLIC_MISSING,
                        "İpotek / Rehin": _fmt_money(rec.mortgage_fee) if rec.mortgage_fee is not None else PUBLIC_MISSING,
                        "Sonuç Türü": _projection_mode(rec.mode),
                        "Resmî Kaynak": rec.source_url,
                        "Kontrol Tarihi": rec.checked_at,
                        "Not": rec.fee_note or "Nihai oran, masraf ve onay koşulları banka değerlendirmesine göre değişebilir.",
                        "__monthly": float(rec.monthly_installment),
                        "__total": float(rec.installment_total),
                        "__source_mode": "model",
                    }
                )
            continue

        if resolution and resolution.mode == "live_unavailable":
            status = "Resmî hesaplama aracı mevcut · anlık sonuç doğrulanamadı"
            action = "BANSA aracı eşleştirdi; exact sonucu tekrar deneyin veya resmî kaynağı açın"
        else:
            status = "Kişiye özel teklif" if is_personal_offer(product) else SCENARIO_MISSING
            action = "Güncel oran/limit için banka ile görüşün"
        no_numeric_rows.append(
            {
                "Banka": str(product.get("bank_name") or ""),
                "Ürün": str(product.get("product_name") or ""),
                "Durum": status,
                "Aksiyon": action,
                "Resmî Kaynak": str(product.get("source_url") or ""),
            }
        )

    numeric = pd.DataFrame(result_rows)
    if not numeric.empty:
        numeric = numeric.sort_values(["__monthly", "Banka", "Ürün"], kind="stable")
    offer_needed = pd.DataFrame(no_numeric_rows).drop_duplicates() if no_numeric_rows else pd.DataFrame()
    return numeric, offer_needed


SCENARIO_TYPES = {"Konut Finansmanı", "Taşıt Finansmanı", "İhtiyaç Finansmanı"}
NON_SCENARIO_SOURCE_NOTE = (
    "Bu finansman türü tutar/vade bazlı taksit hesabı ekranı değildir. "
    "Konut, taşıt ve ihtiyaç dışındaki ürünlerde kullanıcıdan tutar alınmaz; "
    "kaynaklı ürünler ve banka kapsamı sade şekilde gösterilir."
)
NON_SCENARIO_HIDE_TOKENS = (
    "tutar",
    "amount",
    "miktar",
    "taksit",
    "kâr payı",
    "kar payı",
    "oran",
    "masraf",
    "ücret",
    "komisyon tutarı",
)
CORE_SOURCE_COLUMNS = [
    "Banka",
    "Ürün",
    "Ürün Durumu",
    "Kullanıcı Türü",
    "Finansman Amacı",
    "Proje Kapsamı",
    "Finansman Alt Türü",
    "Kiralanabilir Varlık Türü",
    "Kullanım Amacı / Kapsam",
    "Faaliyet / Harcama Alanı",
    "Gayrimenkul Niteliği",
    "Başvuru Kanalı",
    "Özel Koşullar",
    "Fatura / Belge Şartı",
    "Teminat Şartı",
    "Teminat Şartları",
    "Resmî Kaynak",
]


def _is_verified_product_row(row: pd.Series) -> bool:
    return str(row.get("Ürün Durumu", "")).strip() == "Doğrulanmış ürün" and not _is_placeholder(row.get("Ürün", ""))


def _strip_amount_columns(columns: list[str]) -> list[str]:
    kept: list[str] = []
    for column in columns:
        key = column.casefold()
        if any(token in key for token in NON_SCENARIO_HIDE_TOKENS):
            continue
        kept.append(column)
    return kept


def _compact_columns(frame: pd.DataFrame, selected_type: str, profile_cols: list[str]) -> list[str]:
    if selected_type in SCENARIO_TYPES:
        return profile_cols
    preferred = [c for c in CORE_SOURCE_COLUMNS if c in frame.columns]
    remaining = [c for c in profile_cols if c in frame.columns and c not in preferred]
    return _strip_amount_columns(preferred + remaining)


def _non_scenario_value(value: object, column: str = "") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not _is_placeholder(text):
        return text
    column_key = column.casefold()
    if "kaynak" in column_key or "tarih" in column_key or "kontrol" in column_key:
        return ""
    if column == "Ürün":
        return "Açık kaynakta net ürün bulunamadı"
    if column == "Ürün Durumu":
        return "Kaynak doğrulaması bekliyor"
    return "Ürün koşuluna göre değişebilir"


def _non_scenario_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in out.columns:
        out[column] = out[column].map(lambda value, c=column: _non_scenario_value(value, c))
    return out


def _link_count(frame: pd.DataFrame) -> int:
    if frame.empty or "Resmî Kaynak" not in frame.columns:
        return 0
    return int(frame["Resmî Kaynak"].astype(str).str.startswith("http").sum())


opts = list(profiles.keys())
selected = opts[0]
base = rows[rows["Finansman Türü"].eq(selected)].copy()
with st.container(border=True):
    pre1, pre2 = st.columns([1.15, 2.25])
    with pre1:
        selected = st.selectbox("Finansman türü", opts)
    base = rows[rows["Finansman Türü"].eq(selected)].copy()
    banks = sorted(base["Banka"].unique().tolist(), key=str.casefold)
    with pre2:
        bank_filter = st.multiselect("Banka filtresi", banks, placeholder="Boş bırakın: 10 bankanın tamamı")

    requested_amount = 100_000
    requested_maturity = 36
    is_scenario_type = selected in SCENARIO_TYPES
    if is_scenario_type:
        c3, c4 = st.columns([1.0, 0.8])
        with c3:
            requested_amount = int(
                st.number_input(
                    "Tutar (TL)",
                    min_value=1_000,
                    max_value=100_000_000,
                    value=100_000,
                    step=10_000,
                    format="%d",
                )
            )
        with c4:
            requested_maturity = int(
                st.number_input(
                    "Vade (Ay)",
                    min_value=1,
                    max_value=240,
                    value=36,
                    step=1,
                    format="%d",
                )
            )
    else:
        st.info(NON_SCENARIO_SOURCE_NOTE)

if bank_filter:
    base = base[base["Banka"].isin(bank_filter)].copy()

profile_cols = [c for c in profiles[selected] if c in base.columns]
cols = _compact_columns(base, selected, profile_cols)
raw_base = base.copy()
base = _friendly_frame(base) if selected in SCENARIO_TYPES else _non_scenario_frame(base)
real_mask = raw_base.apply(_is_verified_product_row, axis=1) if not raw_base.empty else pd.Series(dtype=bool)
real = base.loc[real_mask].copy() if len(real_mask) else pd.DataFrame()
source_count = _link_count(raw_base.loc[real_mask]) if len(real_mask) else 0

if selected in SCENARIO_TYPES:
    render_section_lead(
        "1 · Size özel finansman senaryosu",
        "Tutar ve vade değiştikçe uygun bankalar aynı senaryoda karşılaştırılır. "
        "Resmî hesaplama aracı bulunan bankalarda sonuç doğrudan doğrulanır; diğerlerinde yalnız güncel ve doğrulanmış fiyatlama verisi kullanılır.",
    )

    with st.spinner("Resmî banka hesaplama araçları sorgulanıyor ve sonuçlar doğrulanıyor..."):
        numeric_results, offer_needed = _scenario_rows(selected, requested_amount, requested_maturity, bank_filter)
    scenario_label = f"{_fmt_money(requested_amount)} / {requested_maturity} ay"

    family_products = _family_products(selected, bank_filter)
    verified_bank_count = real["Banka"].nunique() if not real.empty else 0
    live_mapping_count = live_capable_bank_count(family_products) if not family_products.empty else 0
    numeric_bank_count = numeric_results["Banka"].nunique() if not numeric_results.empty else 0
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Kapsamdaki banka", 10)
    k2.metric("Bu üründe doğrulanmış banka", verified_bank_count)
    k3.metric("Canlı hesaplama destekleyen banka", live_mapping_count)
    k4.metric("Bu senaryoda sonuç veren banka", numeric_bank_count)

    if numeric_results.empty:
        st.warning(
            f"{selected} için {scenario_label} senaryosunda doğrulanmış sayısal taksit sonucu bulunamadı. "
            "Bu alan boş bırakılmadı; uygun bankalar aşağıda kişiye özel teklif olarak yönlendirildi."
        )
    else:
        best = numeric_results.iloc[0]
        live_bank_count = numeric_results.loc[numeric_results["__source_mode"].eq("live"), "Banka"].nunique()
        model_bank_count = numeric_results.loc[numeric_results["__source_mode"].eq("model"), "Banka"].nunique()
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Karşılaştırılan senaryo", scenario_label)
        s2.metric("Banka aracından doğrulanan", live_bank_count)
        s3.metric("Resmî fiyatlamayla hesaplanan", model_bank_count)
        s4.metric("En düşük aylık taksit", f"{best['Banka']} · {best['Aylık Taksit']}")
        public_numeric = _public_numeric_table(numeric_results)
        st.dataframe(
            public_numeric,
            use_container_width=True,
            hide_index=True,
            height=min(620, 84 + 35 * max(5, len(numeric_results))),
            column_config={"Resmî Kaynak": st.column_config.LinkColumn("Kaynak", display_text="Aç", width="small")},
        )

        # Internal source modes, ISO timestamps and calibration notes are useful
        # for QA but should not clutter the end-user table. They are opt-in for
        # technical/demo diagnostics only.
        if SHOW_TECHNICAL_DETAILS:
            with st.expander("Teknik doğrulama ayrıntıları", expanded=False):
                technical_cols = [
                    "Banka", "Ürün", "Varyant", "Sonuç Türü",
                    "Kontrol Tarihi", "Not", "Resmî Kaynak",
                ]
                st.dataframe(
                    numeric_results[[c for c in technical_cols if c in numeric_results.columns]],
                    use_container_width=True, hide_index=True,
                    column_config={"Resmî Kaynak": st.column_config.LinkColumn("Kaynak", display_text="Aç", width="small")},
                )

    if not offer_needed.empty:
        with st.expander("Sayısal sonucu bulunmayan bankaları göster", expanded=False):
            st.caption(
                "Bu bankaların bazılarında resmî hesaplama aracı BANSA'ya bağlıdır; ancak seçtiğiniz tutar/vade için anlık exact sonuç bu çalıştırmada doğrulanamamış olabilir. "
                "BANSA eski veya tahmini rakam göstermeden resmî kaynağı açık tutar."
            )
            st.dataframe(
                offer_needed,
                use_container_width=True,
                hide_index=True,
                height=min(460, 84 + 35 * max(5, len(offer_needed))),
                column_config={"Resmî Kaynak": st.column_config.LinkColumn("Kaynak", display_text="Aç", width="small")},
            )
else:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Kapsamdaki banka", 10)
    m2.metric("Karşılaştırılabilir ürün", len(real))
    m3.metric("Ürün bulunan banka", real["Banka"].nunique() if not real.empty else 0)
    m4.metric("Resmî kaynaklı ürün", source_count)

    render_section_lead(
        "1 · Kaynaklı ürünler ve kapsam",
        "Konut, taşıt ve ihtiyaç dışındaki finansmanlarda kullanıcıdan tutar alınmaz. Burada amaç taksit senaryosu değil; resmî kaynağı bulunan ürünleri bankaya özel arama alanından çıkarıp görünür hale getirmektir.",
    )
    source_cols = [c for c in cols if c in base.columns]
    verified_view = base.loc[real_mask, source_cols].copy() if len(real_mask) else pd.DataFrame(columns=source_cols)
    unresolved_view = base.loc[~real_mask, [c for c in ["Banka", "Ürün", "Resmî Kaynak"] if c in base.columns]].copy() if len(real_mask) else pd.DataFrame()

    if verified_view.empty:
        st.warning(
            "Bu finansman türünde banka filtresine uygun, resmî kaynağı doğrulanmış ürün bulunamadı. "
            "Detay bölümünde kaynak doğrulaması bekleyen bankaları görebilirsiniz."
        )
    else:
        st.dataframe(
            verified_view,
            use_container_width=True,
            hide_index=True,
            height=min(620, 84 + 35 * max(5, len(verified_view))),
            column_config={"Resmî Kaynak": st.column_config.LinkColumn("Kaynak", display_text="Aç", width="small")},
        )

    if not unresolved_view.empty:
        with st.expander("Açık kaynakta net ürün bulunamayan bankaları göster", expanded=False):
            st.caption(
                "Bu bölüm kişiye özel teklif tablosu değildir. Yalnızca mevcut resmî kaynaklarda ilgili finansman türüyle birebir eşleşen net ürün bulunamayan bankaları ayırır."
            )
            st.dataframe(
                unresolved_view,
                use_container_width=True,
                hide_index=True,
                height=min(420, 84 + 35 * max(5, len(unresolved_view))),
                column_config={"Resmî Kaynak": st.column_config.LinkColumn("Kaynak", display_text="Aç", width="small")},
            )

with st.expander("Detaylı ürün karşılaştırma tablosunu göster", expanded=False):
    render_section_lead(
        "2 · Detaylı ürün karşılaştırma tablosu",
        "Kategoriye özel karar sütunları burada saklanır. Konut, taşıt ve ihtiyaç dışındaki finansmanlarda tutar odaklı alanlar gizlenir; kullanıcıya ürün/kaynak kapsamı gösterilir.",
    )
    public_hidden = {"Kontrol Tarihi", "Doğrulama Yöntemi", "Not", "Ürün Durumu"}
    detail_cols = cols if SHOW_TECHNICAL_DETAILS else [c for c in cols if c not in public_hidden]
    detail_frame = _friendly_frame(base[detail_cols])
    st.dataframe(
        detail_frame,
        use_container_width=True,
        hide_index=True,
        height=min(760, 84 + 35 * max(5, len(base))),
        column_config={"Resmî Kaynak": st.column_config.LinkColumn("Kaynak", display_text="Aç", width="small")},
    )
    st.download_button(
        "Bu tabloyu CSV indir",
        detail_frame.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"bansa_{selected.lower().replace(' ', '_')}.csv",
        mime="text/csv",
    )

if selected in SCENARIO_TYPES and SHOW_TECHNICAL_DETAILS:
    sc = scenarios[scenarios["Finansman Türü"].eq(selected)].copy()
    if not sc.empty:
        if bank_filter:
            sc = sc[sc["Banka"].isin(bank_filter)].copy()
        if not sc.empty:
            with st.expander("Teknik referans senaryoları", expanded=False):
                label = _friendly_value(sc["Senaryo"].iloc[0]) if not sc.empty else ""
                render_section_lead(
                    f"3 · Referans snapshot — {label}",
                    "Bu bölüm yalnız geriye dönük doğrulama içindir; yeni karşılaştırmalar üstteki tutar/vade ekranından yapılır.",
                )
                s_cols = [
                    "Banka",
                    "Ürün",
                    "Varyant",
                    "Kâr Payı",
                    "Aylık Taksit",
                    "Toplam Geri Ödeme",
                    "Tahsis",
                    "Ekspertiz",
                    "İpotek / Rehin",
                    "Doğrulama Yöntemi",
                    "Resmî Kaynak",
                    "Kontrol Tarihi",
                ]
                s_cols = [c for c in s_cols if c in sc.columns]
                st.dataframe(
                    _friendly_frame(sc[s_cols]),
                    use_container_width=True,
                    hide_index=True,
                    height=min(620, 84 + 35 * max(5, len(sc))),
                    column_config={"Resmî Kaynak": st.column_config.LinkColumn("Kaynak", display_text="Aç", width="small")},
                )

render_section_lead(
    "4 · Veri güveni",
    "Banka evreni BDDK katılım bankaları listesine göre sabittir. Ürün verileri bankaların resmî sayfalarından oluşturulan statik snapshotta tutulur; sayısal senaryolar doğrulanmadan türetilmez. Kişiye özel oran veya limit gerektiren alanlarda kullanıcı bankaya yönlendirilir.",
)
