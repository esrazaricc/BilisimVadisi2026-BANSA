import streamlit as st

from src.repository import get_campaigns

st.set_page_config(page_title="Karşılaştırma", page_icon="⚖️", layout="wide")
st.title("Benzer Kampanyaları Karşılaştır")

campaigns = get_campaigns()
if campaigns.empty:
    st.info("Karşılaştırılacak kampanya bulunmuyor.")
    st.stop()

campaign_types = sorted(campaigns["campaign_type"].dropna().unique())
selected_type = st.selectbox("Kampanya türü", campaign_types)

subset = campaigns[campaigns["campaign_type"] == selected_type].copy()

options = {
    f"{row['bank_name']} - {row['campaign_name']}": row["id"]
    for _, row in subset.iterrows()
}

default_labels = list(options.keys())[:3]
selected_labels = st.multiselect(
    "Karşılaştırılacak kampanyalar",
    list(options.keys()),
    default=default_labels,
)

if selected_labels:
    selected_ids = [options[label] for label in selected_labels]
    subset = subset[subset["id"].isin(selected_ids)]

columns = [
    "bank_name",
    "campaign_name",
    "profit_share_rate",
    "maturity_months",
    "installment_count",
    "reward_amount",
    "discount_rate",
    "minimum_spending",
    "maximum_benefit",
    "expense_status",
    "campaign_end_date",
]

st.dataframe(subset[columns], use_container_width=True, hide_index=True)

if subset.empty:
    st.warning("En az bir kampanya seçin.")
    st.stop()

st.subheader("Kriterlere göre öne çıkan kampanyalar")

rules = [
    ("En düşük kâr payı", "profit_share_rate", True, "%"),
    ("En uzun vade", "maturity_months", False, " ay"),
    ("En yüksek ödül", "reward_amount", False, " TL"),
    ("En yüksek indirim veya iade", "discount_rate", False, "%"),
]

for label, column, ascending, suffix in rules:
    valid_rows = subset.dropna(subset=[column])
    if valid_rows.empty:
        continue

    best = valid_rows.sort_values(column, ascending=ascending).iloc[0]
    st.write(
        f"**{label}:** {best['bank_name']} — {best['campaign_name']} "
        f"({best[column]}{suffix})"
    )
