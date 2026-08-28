import streamlit as st

from src.ui_theme import apply_bansa_theme

from src.repository import get_campaigns
from src.ui_display import (
    clean_campaign_title,
    display_text,
    format_number_tr,
    label_campaign_type,
)


st.set_page_config(
    page_title="Kampanyalar",
    page_icon="🏷️",
    layout="wide",
)

apply_bansa_theme()
st.title("Kampanyalar")

campaigns = get_campaigns()
if campaigns.empty:
    st.info("Kayıtlı kampanya bulunmuyor.")
    st.stop()

col1, col2, col3 = st.columns(3)
with col1:
    selected_banks = st.multiselect(
        "Banka",
        sorted(
            campaigns["bank_name"]
            .dropna()
            .unique()
        ),
    )
with col2:
    campaign_types = sorted(
        campaigns["campaign_type"]
        .dropna()
        .unique()
    )
    selected_types = st.multiselect(
        "Kampanya türü",
        campaign_types,
        format_func=label_campaign_type,
    )
with col3:
    status = st.selectbox(
        "Durum",
        [
            "Aktif",
            "Tümü",
            "Süresi dolmuş",
            "Belirsiz",
        ],
        index=0,
        help=(
            "Varsayılan olarak yalnızca aktif kampanyalar "
            "gösterilir."
        ),
    )

filtered = campaigns.copy()

if selected_banks:
    filtered = filtered[
        filtered["bank_name"].isin(selected_banks)
    ]
if selected_types:
    filtered = filtered[
        filtered["campaign_type"].isin(selected_types)
    ]

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

display = filtered[columns].copy()

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

for column in (
    "profit_share_rate",
    "maturity_months",
    "installment_count",
    "reward_amount",
    "discount_rate",
):
    display[column] = display[column].map(
        format_number_tr
    )

display["expense_status"] = display[
    "expense_status"
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
        "profit_share_rate": "Kâr Payı Oranı (%)",
        "maturity_months": "Vade Süresi (Ay)",
        "installment_count": "Taksit Sayısı",
        "reward_amount": "Ödül Tutarı (TL)",
        "discount_rate": "İndirim / İade Oranı (%)",
        "expense_status": "Masraf Bilgisi",
        "campaign_end_date": "Kampanya Bitiş Tarihi",
        "source_url": "Resmî Kaynak",
    }
)

st.write(
    f"Gösterilen kampanya sayısı: **{len(display)}**"
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
