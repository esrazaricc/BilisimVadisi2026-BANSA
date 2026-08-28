import pandas as pd
import streamlit as st

from src.ui_theme import apply_bansa_theme

from src.pipeline import analyze_text, analyze_url
from src.scraping.http_client import ScrapeError
from src.ui_display import (
    extraction_field_label,
    format_extraction_value,
    label_page_type,
)


st.set_page_config(
    page_title="Metin Analizi",
    page_icon="🔎",
    layout="wide",
)

apply_bansa_theme()
st.title("Kampanya Metni Analizi")

source_type = st.radio(
    "Veri kaynağı",
    ["URL", "Metin yapıştır"],
    horizontal=True,
)
bank_name = st.text_input(
    "Banka adı",
    placeholder="Örnek: Albaraka Türk",
)

if source_type == "URL":
    url = st.text_input("Resmî sayfa adresi")

    if st.button("Sayfayı analiz et", type="primary"):
        if not bank_name.strip() or not url.strip():
            st.error("Banka adı ve URL alanlarını doldurun.")
        else:
            try:
                st.session_state["analysis_result"] = analyze_url(
                    bank_name.strip(),
                    url.strip(),
                )
            except ScrapeError as error:
                st.error(str(error))
else:
    title = st.text_input("Sayfa veya kampanya başlığı")
    text = st.text_area("Ham metin", height=320)

    if st.button("Metni analiz et", type="primary"):
        if (
            not bank_name.strip()
            or not title.strip()
            or not text.strip()
        ):
            st.error(
                "Banka, başlık ve metin alanlarını doldurun."
            )
        else:
            st.session_state["analysis_result"] = analyze_text(
                bank_name.strip(),
                title.strip(),
                text.strip(),
            )

result = st.session_state.get("analysis_result")
if result:
    classification = result["classification"]

    st.divider()
    left, right = st.columns([1, 2])

    with left:
        st.subheader("Sayfa Sınıfı")
        st.metric(
            "Tür",
            label_page_type(classification["page_type"]),
        )
        st.metric(
            "Güven",
            f"%{classification['confidence'] * 100:.1f}",
        )

        if classification["is_campaign"]:
            st.success(
                "Bu sayfa kampanya olarak değerlendirildi."
            )
        else:
            st.warning(
                "Bu sayfa kampanya listesine eklenmeyecek."
            )

        st.write("**Sınıflandırma nedenleri**")
        for reason in classification["reasons"]:
            st.write(f"- {reason}")

    with right:
        st.subheader("Çıkarılan Bilgiler")

        extraction = result.get("extraction") or {}
        if not extraction:
            st.info(
                "Bu sayfa için yapılandırılmış kampanya alanı "
                "çıkarılmadı."
            )
        else:
            rows = [
                {
                    "Alan": extraction_field_label(key),
                    "Değer": format_extraction_value(
                        key,
                        value,
                    ),
                }
                for key, value in extraction.items()
            ]
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )

    if st.button("Analizi veritabanına kaydet"):
        saved_result = analyze_text(
            result["bank_name"],
            result["title"],
            result["raw_text"],
            source_url=result["source_url"],
            save=True,
        )
        st.success(
            "Kayıt tamamlandı. "
            f"Sayfa numarası: {saved_result['page_id']}"
        )
