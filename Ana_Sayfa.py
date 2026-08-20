import streamlit as st

from src.db import init_db
from src.repository import dashboard_metrics, get_campaigns
from src.ui_display import (
    clean_campaign_title,
    display_text,
    label_campaign_type,
)


st.set_page_config(
    page_title="BANSA Kampanya Analiz Sistemi",
    page_icon="📊",
    layout="wide",
)

init_db()

st.title("Katılım Bankacılığı Kampanya Analiz Sistemi")
st.caption(
    "Katılım bankalarının kampanyalarını yapılandırılmış biçimde "
    "analiz eder ve karşılaştırır."
)

metrics = dashboard_metrics()
col1, col2, col3, col4 = st.columns(4)
col1.metric("Analiz edilen sayfa", metrics["total_pages"])
col2.metric("Gerçek kampanya", metrics["total_campaigns"])
col3.metric("Aktif kampanya", metrics["active_campaigns"])
col4.metric("Standart ürün sayfası", metrics["standard_products"])

st.subheader("Son Eklenen Aktif Kampanyalar")
campaigns = get_campaigns()

if not campaigns.empty and "is_active" in campaigns.columns:
    campaigns = campaigns[
        campaigns["is_active"] == 1
    ].copy()

if campaigns.empty:
    st.info(
        "Henüz aktif kampanya kaydı bulunmuyor. "
        "Metin Analizi ekranından manuel analiz de yapabilirsiniz."
    )
else:
    columns = [
        "bank_name",
        "campaign_name",
        "campaign_type",
        "target_audience",
        "campaign_end_date",
        "source_url",
    ]

    display = campaigns[columns].head(20).copy()
    display["campaign_name"] = display.apply(
        lambda row: clean_campaign_title(
            row["campaign_name"],
            row["bank_name"],
        ),
        axis=1,
    )
    display["campaign_type"] = display[
        "campaign_type"
    ].map(label_campaign_type)
    display["target_audience"] = display[
        "target_audience"
    ].map(display_text)
    display["campaign_end_date"] = display[
        "campaign_end_date"
    ].map(display_text)

    display = display.rename(
        columns={
            "bank_name": "Banka",
            "campaign_name": "Kampanya",
            "campaign_type": "Kampanya Türü",
            "target_audience": "Hedef Kitle",
            "campaign_end_date": "Bitiş Tarihi",
            "source_url": "Resmî Kaynak",
        }
    )

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Resmî Kaynak": st.column_config.LinkColumn(
                "Resmî Kaynak",
                display_text="Kampanyayı Aç",
            )
        },
    )
