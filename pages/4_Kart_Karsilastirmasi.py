from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

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
CARD_FRIENDLY_MISSING = "Detay için banka ürün sayfasını inceleyin"

st.set_page_config(
    page_title="BANSA · Kart Karşılaştırması",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_bansa_theme()
render_sidebar_navigation("cards")
render_page_header(
    "Kart Karşılaştırması",
    "Katılım bankalarının bireysel kredi ve banka kartlarını "
    "kart ücreti, ödül, taksit ve dijital kullanım özelliklerine göre karşılaştırın.",
)

rows = pd.read_csv(
    DATA / "cards_dashboard_static.csv",
    dtype=str,
    keep_default_na=False,
)

# Kart Karşılaştırması yalnızca gerçek kredi/banka kartı ürünlerine
# odaklanır. Ek kart, sanal/dijital kart varyantları ve ticari/tarım
# kartları (bunlar ayrı bir kurumsal/tarım bankacılığı ihtiyacına hizmet
# eder ve bireysel kart karşılaştırmasını karmaşıklaştırır) bu görünümden
# çıkarılmıştır.
_EXCLUDED_CARD_TYPES = {
    "Sanal Kart",
    "Sanal Kredi Kartı",
    "Dijital Kredi Kartı",
    "Ek Kart",
    "Ek Kredi Kartı",
    "Ek Banka Kartı",
    "Tarım Kartı",
    "Ticari Kart",
    "Ticari Finansman Kartı",
    "Ticari Kredi Kartı",
}
rows = rows[~rows["Kart Türü"].isin(_EXCLUDED_CARD_TYPES)].copy()

real_rows = rows[~rows["Kart Türü"].eq("Ürün yayımlanmamış")].copy()




def _is_missing_value(value: object) -> bool:
    text = str(value or "").strip()
    key = text.casefold()
    if key in {"", "-", "—", "nan", "none", "null", "belirtilmedi"}:
        return True
    return any(
        marker in key
        for marker in (
            "bilgi yok",
            "resmî kaynakta yayımlanmamış",
            "resmi kaynakta yayınlanmamış",
            "doğrulanamadı",
        )
    )


def _friendly_card_value(value: object, column: str = "") -> str:
    text = str(value or "").strip()
    if not _is_missing_value(text):
        return text
    key = column.casefold()
    if "kaynak" in key or "tarih" in key:
        return ""
    if any(token in key for token in ("ücret", "aidat", "ödül", "puan", "mil", "taksit", "avans", "limit")):
        return "Ürün koşuluna göre değişebilir"
    if any(token in key for token in ("başvuru", "avantaj", "kullanım", "özellik", "kart")):
        return CARD_FRIENDLY_MISSING
    return CARD_FRIENDLY_MISSING


def _friendly_card_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in out.columns:
        out[column] = out[column].map(lambda value, c=column: _friendly_card_value(value, c))
    return out

priority_rules = {
    "Tümü": [],
    "Aidatsız": ["0 TL", "ücretsiz", "ücret yok", "masraf yok", "aidat yok"],
    "Puan / Ödül": ["puan", "bonus", "worldpuan", "bankkart lira", "altın", "nakit iade", "parafpara"],
    "Taksit": ["taksit"],
    "Seyahat / Mil": ["mil", "miles&smiles", "seyahat"],
    "Aile / Genç": ["aile", "kampüs", "trend", "genç", "8 yaş"],
    "Premium": ["premium", "platinum", "gold", "özel", "âlâ", "black", "elite"],
}

with st.container(border=True):
    c1, c2, c3, c4 = st.columns([1.15, 1.55, 1.25, 1.4])

    with c1:
        type_options = ["Tümü"] + sorted(
            real_rows["Kart Türü"].unique().tolist(),
            key=str.casefold,
        )
        card_type = st.selectbox("Kart türü", type_options)

    with c2:
        bank_options = sorted(rows["Banka"].unique().tolist(), key=str.casefold)
        banks = st.multiselect(
            "Banka filtresi",
            bank_options,
            placeholder="Boş bırakın: 10 bankanın tamamı",
        )

    with c3:
        priority = st.selectbox("Kullanım önceliği", list(priority_rules))

    with c4:
        query = st.text_input(
            "Ara",
            placeholder="aidatsız, mil, World, TROY, aile...",
        )

base = rows.copy()

if card_type != "Tümü":
    base = base[base["Kart Türü"].eq(card_type)]

if banks:
    base = base[base["Banka"].isin(banks)]

def row_contains_terms(row, terms):
    haystack = " ".join(map(str, row.values)).casefold()
    return any(term.casefold() in haystack for term in terms)

terms = priority_rules[priority]
if terms:
    base = base[base.apply(lambda r: row_contains_terms(r, terms), axis=1)]

if query.strip():
    q = query.strip().casefold()
    base = base[
        base.apply(
            lambda r: q in " ".join(map(str, r.values)).casefold(),
            axis=1,
        )
    ]

m1, m2, m3, m4 = st.columns(4)
with m1:
    render_insight_card("BDDK banka evreni", "10", "Katılım bankası kapsamı")
with m2:
    render_insight_card(
        "Doğrulanmış kart",
        str(int((base["Kart Türü"] != "Ürün yayımlanmamış").sum())),
        "Filtreye uyan ürün satırı",
    )
with m3:
    render_insight_card(
        "Banka",
        str(int(base.loc[base["Kart Türü"] != "Ürün yayımlanmamış", "Banka"].nunique())),
        "Kart ürünü doğrulanan banka",
    )
with m4:
    render_insight_card(
        "Aidatsız ifade",
        str(
            int(
                base["Yıllık Kart Ücreti"].str.contains(
                    r"0 TL|ücretsiz|ücret yok|masraf yok|aidat yok",
                    case=False,
                    regex=True,
                ).sum()
            )
        ),
        "Ücret avantajı bulunan satır",
    )

render_section_lead(
    "1 · Kart karşılaştırma tablosu",
    "Kart ücreti, ödül programı, taksit, temassız/dijital kullanım ve öne çıkan "
    "avantajlar yan yana gösterilir. Resmî kaynakta yayımlanmayan özellik tahmin edilmez.",
)

display_cols = [
    "Banka",
    "Kart Adı",
    "Kart Türü",
    "Müşteri Segmenti",
    "Ödeme Ağı",
    "Kart Programı / Ödül",
    "Yıllık Kart Ücreti",
    "Taksit / Vade Farksız",
    "Puan / Nakit İade / Mil",
    "Temassız",
    "QR / NFC",
    "Sanal Kart",
    "İnternet Alışverişi",
    "Yurt Dışı Kullanım",
    "Öne Çıkan Avantaj",
    "Resmî Kaynak",
]

if not base.empty:
    top_row = base.iloc[0]
    render_recommendation_box(
        "Kart özeti",
        f"{top_row['Banka']} · {top_row['Kart Adı']} seçili filtrelerle eşleşen kartlardan biridir. Karar verirken kart ücreti, ödül yapısı ve kullanım özelliklerini birlikte değerlendirin.",
        badge="Seçili filtrelerle eşleşiyor",
    )

display_base = _friendly_card_frame(base[display_cols])

st.dataframe(
    display_base,
    use_container_width=True,
    hide_index=True,
    height=min(820, 84 + 35 * max(5, len(base))),
    column_config={
        "Resmî Kaynak": st.column_config.LinkColumn(
            "Kaynak",
            display_text="Aç",
            width="small",
        )
    },
)

st.download_button(
    "Kart tablosunu CSV indir",
    display_base.to_csv(index=False).encode("utf-8-sig"),
    file_name="bansa_kart_karsilastirmasi.csv",
    mime="text/csv",
)

render_section_lead(
    "2 · Kart detay görünümü",
    "Bir kartı seçerek ek kart, nakit avans, başvuru ve doğruluk notu gibi "
    "tabloya sığmayan ayrıntıları inceleyebilirsiniz.",
)

if base.empty:
    st.info("Seçtiğiniz filtrelerle eşleşen kart bulunamadı.")
else:
    labels = (base["Banka"] + " · " + base["Kart Adı"]).tolist()
    selected_label = st.selectbox("Kart seç", labels)

    detail = base[
        (base["Banka"] + " · " + base["Kart Adı"]).eq(selected_label)
    ].iloc[0]

    detail_pairs = [
        ("Banka", detail["Banka"]),
        ("Kart", detail["Kart Adı"]),
        ("Kart türü", detail["Kart Türü"]),
        ("Yıllık kart ücreti", _friendly_card_value(detail["Yıllık Kart Ücreti"], "Yıllık Kart Ücreti")),
        ("Taksit / vade farksız", _friendly_card_value(detail["Taksit / Vade Farksız"], "Taksit / Vade Farksız")),
        ("Puan / ödül / mil", _friendly_card_value(detail["Puan / Nakit İade / Mil"], "Puan / Nakit İade / Mil")),
        ("Temassız", _friendly_card_value(detail["Temassız"], "Temassız")),
        ("QR / NFC", _friendly_card_value(detail["QR / NFC"], "QR / NFC")),
        ("Sanal kart", _friendly_card_value(detail["Sanal Kart"], "Sanal Kart")),
        ("Ek kart", _friendly_card_value(detail["Ek Kart"], "Ek Kart")),
        ("İnternet alışverişi", _friendly_card_value(detail["İnternet Alışverişi"], "İnternet Alışverişi")),
        ("Yurt dışı kullanım", _friendly_card_value(detail["Yurt Dışı Kullanım"], "Yurt Dışı Kullanım")),
        ("Nakit avans", _friendly_card_value(detail["Nakit Avans"], "Nakit Avans")),
        ("Başvuru kanalı", _friendly_card_value(detail["Başvuru Kanalı"], "Başvuru Kanalı")),
    ]

    for label, value in detail_pairs:
        st.markdown(f"**{label}:** {value}")

    st.markdown(f"[Resmî ürün kaynağını aç]({detail['Resmî Kaynak']})")

render_section_lead(
    "3 · Veri güveni",
    "Bu sayfa 27.08.2026 tarihli statik snapshot kullanır; çalışma anında web "
    "scraping yapmaz. Bir özellik güncel resmî ürün/ücret sayfasında "
    "doğrulanamadıysa kullanıcı dostu banka yönlendirmesi gösterilir.",
)
