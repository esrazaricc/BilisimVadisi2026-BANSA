import streamlit as st

from src.repository import get_campaigns

st.set_page_config(page_title="Kampanyalar", page_icon="🏷️", layout="wide")
st.title("Kampanyalar")

campaigns = get_campaigns()
if campaigns.empty:
    st.info("Kayıtlı kampanya bulunmuyor.")
    st.stop()

col1, col2, col3 = st.columns(3)
with col1:
    selected_banks = st.multiselect(
        "Banka",
        sorted(campaigns["bank_name"].dropna().unique()),
    )
with col2:
    selected_types = st.multiselect(
        "Kampanya türü",
        sorted(campaigns["campaign_type"].dropna().unique()),
    )
with col3:
    status = st.selectbox(
        "Durum",
        ["Tümü", "Aktif", "Süresi dolmuş", "Belirsiz"],
    )

filtered = campaigns.copy()

if selected_banks:
    filtered = filtered[filtered["bank_name"].isin(selected_banks)]
if selected_types:
    filtered = filtered[filtered["campaign_type"].isin(selected_types)]

if status == "Aktif":
    filtered = filtered[filtered["is_active"] == 1]
elif status == "Süresi dolmuş":
    filtered = filtered[filtered["is_active"] == 0]
elif status == "Belirsiz":
    filtered = filtered[filtered["is_active"].isna()]

columns = [
    "bank_name",
    "campaign_name",
    "campaign_type",
    "target_audience",
    "profit_share_rate",
    "maturity_months",
    "installment_count",
    "reward_amount",
    "discount_rate",
    "expense_status",
    "campaign_end_date",
    "source_url",
]

st.write(f"Gösterilen kampanya sayısı: **{len(filtered)}**")
st.dataframe(filtered[columns], use_container_width=True, hide_index=True)
