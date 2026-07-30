import streamlit as st

from src.db import init_db
from src.repository import dashboard_metrics, get_campaigns

st.set_page_config(
    page_title="BANSA Kampanya Analiz Sistemi",
    page_icon="📊",
    layout="wide",
)

init_db()

st.title("Katılım Bankacılığı Kampanya Analiz Sistemi")
st.caption(
    "Web sayfalarını kampanya, standart ürün ve diğer olarak ayırır. "
    "Karşılaştırma ekranına yalnızca gerçek kampanyalar alınır."
)

metrics = dashboard_metrics()
col1, col2, col3, col4 = st.columns(4)
col1.metric("Analiz edilen sayfa", metrics["total_pages"])
col2.metric("Gerçek kampanya", metrics["total_campaigns"])
col3.metric("Aktif kampanya", metrics["active_campaigns"])
col4.metric("Standart ürün sayfası", metrics["standard_products"])

st.subheader("Son eklenen kampanyalar")
campaigns = get_campaigns()

if campaigns.empty:
    st.info("Henüz kampanya kaydı yok. Sol menüden Metin Analizi ekranına geçebilirsiniz.")
else:
    columns = [
        "bank_name",
        "campaign_name",
        "campaign_type",
        "target_audience",
        "campaign_end_date",
        "source_url",
    ]
    st.dataframe(
        campaigns[columns].head(20),
        use_container_width=True,
        hide_index=True,
    )
