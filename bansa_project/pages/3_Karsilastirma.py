from __future__ import annotations

import pandas as pd
import streamlit as st

from src.repository import get_campaigns


st.set_page_config(
    page_title="Kampanya Karşılaştırma",
    page_icon="⚖️",
    layout="wide",
)
st.title("Benzer Kampanyaları Karşılaştır")
st.caption(
    "Önce karşılaştırma türünü seçin; ardından yalnızca o türe "
    "ait kampanyalar arasından seçim yapın."
)


CAMPAIGN_TYPE_LABELS = {
    "finance_campaign": "Diğer Finansman",
    "card_campaign": "Kart ve Taksit Kampanyaları",
    "discount_campaign": "İndirim Kampanyaları",
    "points_campaign": "Puan Kampanyaları",
    "new_customer_campaign": "Yeni Müşteri Kampanyaları",
    "insurance_campaign": "Sigorta Kampanyaları",
    "other_campaign": "Diğer Kampanyalar",
}

COLUMN_LABELS = {
    "bank_campaign": "Banka / Kampanya",
    "linked_product_type": "Finansman Türü",
    "target_audience": "Hedef Kitle",
    "profit_share_rate": "Kâr Payı Oranı (%)",
    "financing_amount": "Finansman Tutarı (TL)",
    "maturity_months": "Vade Süresi (Ay)",
    "installment_count": "Taksit Sayısı",
    "reward_amount": "Ödül Tutarı (TL)",
    "discount_rate": "İndirim / İade Oranı (%)",
    "shopping_points": "Alışveriş Puanı",
    "minimum_spending": "Minimum Harcama (TL)",
    "maximum_benefit": "Maksimum Fayda (TL)",
    "expense_status": "Masraf Bilgisi",
    "campaign_end_date": "Kampanya Bitiş Tarihi",
    "source_url": "Resmî Kaynak",
}


def has_value(value: object) -> bool:
    return (
        value is not None
        and not pd.isna(value)
        and str(value).strip() != ""
    )


def comparison_type(row: pd.Series) -> str:
    """
    Finansman kampanyalarında ayrıntılı finansman türünü,
    diğer kampanyalarda genel kampanya grubunu kullanır.
    """
    if (
        row.get("campaign_type") == "finance_campaign"
        and has_value(row.get("linked_product_type"))
    ):
        return str(row["linked_product_type"]).strip()

    campaign_type = str(row.get("campaign_type") or "")
    return CAMPAIGN_TYPE_LABELS.get(
        campaign_type,
        campaign_type or "Diğer Kampanyalar",
    )


def format_turkish_number(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if number.is_integer():
        return f"{int(number):,}".replace(",", ".")

    return (
        f"{number:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def prepare_display(
    frame: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    display = frame.copy()
    display["bank_campaign"] = (
        display["bank_name"].fillna("")
        + " — "
        + display["campaign_name"].fillna("")
    )

    selected = [
        column
        for column in columns
        if column in display.columns
    ]
    display = display[selected].copy()

    numeric_columns = (
        "profit_share_rate",
        "financing_amount",
        "maturity_months",
        "installment_count",
        "reward_amount",
        "discount_rate",
        "shopping_points",
        "minimum_spending",
        "maximum_benefit",
    )

    for column in numeric_columns:
        if column in display.columns:
            display[column] = display[column].apply(
                format_turkish_number
            )

    return display.rename(columns=COLUMN_LABELS)


def default_campaign_labels(
    options_frame: pd.DataFrame,
) -> list[str]:
    """
    Karşılaştırma açıldığında mümkün olduğunca farklı bankalardan
    birer kampanya seçer.
    """
    selected: list[str] = []

    for _, row in options_frame.drop_duplicates(
        subset=["bank_name"]
    ).iterrows():
        selected.append(row["option_label"])
        if len(selected) == 3:
            break

    if len(selected) < 2:
        for label in options_frame["option_label"]:
            if label not in selected:
                selected.append(label)
            if len(selected) == min(3, len(options_frame)):
                break

    return selected


campaigns = get_campaigns()

if campaigns.empty:
    st.info("Karşılaştırılacak kampanya bulunmuyor.")
    st.stop()

campaigns = campaigns.copy()
campaigns["comparison_type"] = campaigns.apply(
    comparison_type,
    axis=1,
)

comparison_types = sorted(
    campaigns["comparison_type"]
    .dropna()
    .astype(str)
    .unique()
    .tolist(),
    key=str.casefold,
)

selected_comparison_type = st.selectbox(
    "Karşılaştırılacak kampanya türü",
    options=comparison_types,
    help=(
        "Örneğin Konut Finansmanı, Taşıt Finansmanı, "
        "İndirim Kampanyaları veya Puan Kampanyaları."
    ),
)

subset = campaigns[
    campaigns["comparison_type"]
    == selected_comparison_type
].copy()

subset["option_label"] = (
    subset["bank_name"].fillna("")
    + " — "
    + subset["campaign_name"].fillna("")
)

available_bank_count = subset["bank_name"].nunique()
st.caption(
    f"Bu türde {len(subset)} kampanya ve "
    f"{available_bank_count} banka bulunuyor."
)

if available_bank_count < 2:
    st.warning(
        "Bu karşılaştırma türü şu anda yalnızca bir bankada "
        "bulunuyor. Bankalar arası karşılaştırma için aynı türde "
        "en az iki bankanın kampanyası gerekir."
    )

options = {
    row["option_label"]: row["id"]
    for _, row in subset.iterrows()
}

if not options:
    st.info("Bu türde karşılaştırılabilecek kampanya bulunmuyor.")
    st.stop()

selected_labels = st.multiselect(
    "Karşılaştırılacak kampanyalar",
    options=list(options.keys()),
    default=default_campaign_labels(subset),
    help=(
        "Seçtiğiniz türe ait kampanyalar burada listelenir. "
        "Birden fazla bankadan kampanya seçebilirsiniz."
    ),
)

if not selected_labels:
    st.warning("En az bir kampanya seçin.")
    st.stop()

selected_ids = [
    options[label]
    for label in selected_labels
]
selected = subset[
    subset["id"].isin(selected_ids)
].copy()

is_finance_type = bool(
    (
        selected["campaign_type"]
        == "finance_campaign"
    ).all()
)

if is_finance_type:
    table_columns = [
        "bank_campaign",
        "profit_share_rate",
        "financing_amount",
        "maturity_months",
        "installment_count",
        "expense_status",
        "campaign_end_date",
        "source_url",
    ]
else:
    table_columns = [
        "bank_campaign",
        "target_audience",
        "reward_amount",
        "discount_rate",
        "shopping_points",
        "minimum_spending",
        "maximum_benefit",
        "campaign_end_date",
        "source_url",
    ]

display = prepare_display(
    selected,
    table_columns,
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

if len(selected) < 2:
    st.info(
        "Gerçek bir karşılaştırma için en az iki kampanya seçin."
    )
    st.stop()

st.subheader("Kriterlere Göre Öne Çıkan Kampanyalar")

if is_finance_type:
    rules = [
        (
            "En düşük kâr payı",
            "profit_share_rate",
            True,
            "%",
        ),
        (
            "En yüksek finansman tutarı",
            "financing_amount",
            False,
            " TL",
        ),
        (
            "En uzun vade",
            "maturity_months",
            False,
            " ay",
        ),
        (
            "En fazla taksit",
            "installment_count",
            False,
            " taksit",
        ),
    ]
else:
    rules = [
        (
            "En yüksek ödül",
            "reward_amount",
            False,
            " TL",
        ),
        (
            "En yüksek indirim veya iade",
            "discount_rate",
            False,
            "%",
        ),
        (
            "En yüksek alışveriş puanı",
            "shopping_points",
            False,
            " puan",
        ),
        (
            "En yüksek maksimum fayda",
            "maximum_benefit",
            False,
            " TL",
        ),
    ]

found_rule = False

for label, column, ascending, suffix in rules:
    if column not in selected.columns:
        continue

    valid_rows = selected.dropna(subset=[column])
    if valid_rows.empty:
        continue

    found_rule = True
    best = valid_rows.sort_values(
        column,
        ascending=ascending,
    ).iloc[0]

    st.write(
        f"**{label}:** "
        f"{best['bank_name']} — "
        f"{best['campaign_name']} "
        f"({format_turkish_number(best[column])}{suffix})"
    )

if not found_rule:
    st.info(
        "Seçilen kampanyalarda öne çıkan kriterler için "
        "yeterli sayısal veri bulunmuyor."
    )
