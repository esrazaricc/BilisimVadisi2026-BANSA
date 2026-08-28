import streamlit as st

from src.ui_theme import apply_bansa_theme

from src.repository import get_pages

st.set_page_config(page_title="Ham Sayfalar", page_icon="🗂️", layout="wide")
st.title("Analiz Edilen Tüm Sayfalar")

apply_bansa_theme()
st.caption(
    "Standart ürün sayfaları bu ekranda tutulur ancak kampanya listesine aktarılmaz."
)

pages = get_pages()
if pages.empty:
    st.info("Henüz analiz edilmiş sayfa yok.")
else:
    columns = [
        "bank_name",
        "page_title",
        "page_type",
        "is_campaign",
        "classification_confidence",
        "classification_reason",
        "source_url",
        "retrieved_at",
    ]
    st.dataframe(pages[columns], use_container_width=True, hide_index=True)
