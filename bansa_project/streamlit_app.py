from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Bansa Veri Kontrol Paneli",
    page_icon="🏦",
    layout="wide",
)

STATUS_LABELS = {
    "active": "Aktif",
    "expired": "Süresi Dolmuş",
    "upcoming": "Yaklaşan",
    "removed": "Kaldırılmış",
    "unknown": "Bilinmiyor",
}

CATEGORY_LABELS = {
    "finance_campaign": "Finansman",
    "card_campaign": "Kart / Taksit",
    "discount_campaign": "İndirim",
    "points_campaign": "Puan",
    "new_customer_campaign": "Yeni Müşteri",
    "insurance_campaign": "Sigorta",
    "other_campaign": "Diğer",
    "service_information": "Hizmet Bilgisi",
    "duplicate": "Mükerrer",
    "unclassified": "Sınıflandırılmamış",
}

RECORD_LABELS = {
    "campaign": "Kampanya",
    "duplicate": "Mükerrer",
    "service_information": "Hizmet Bilgisi",
    "standard_product": "Standart Ürün",
    "needs_review": "İnceleme Gerekli",
    "unclassified": "Sınıflandırılmamış",
}


def resolve_database_path() -> Path:
    configured = os.getenv("BANSA_DB_PATH", "").strip()
    candidates = []

    if configured:
        candidates.append(Path(configured))

    project_root = Path(__file__).resolve().parent
    candidates.extend(
        [
            project_root / "data" / "campaigns.db",
            project_root / "campaigns.db",
            Path.cwd() / "data" / "campaigns.db",
            Path.cwd() / "campaigns.db",
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return candidates[0] if candidates else Path("data/campaigns.db")


DB_PATH = resolve_database_path()


@st.cache_resource
def open_database(path: str) -> sqlite3.Connection:
    database = Path(path).resolve()
    if not database.exists():
        raise FileNotFoundError(
            f"Veritabanı bulunamadı: {database}"
        )

    uri = f"file:{database.as_posix()}?mode=ro"
    connection = sqlite3.connect(
        uri,
        uri=True,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    return connection


@st.cache_data(ttl=60)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    connection = open_database(str(DB_PATH))
    return pd.read_sql_query(sql, connection, params=params)


def sql_placeholders(values: Iterable[str]) -> str:
    return ",".join("?" for _ in values)


def format_number(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if number.is_integer():
        return f"{int(number):,}".replace(",", ".")
    return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def label_status(value: object) -> str:
    key = str(value or "unknown")
    return STATUS_LABELS.get(key, key)


def label_category(value: object) -> str:
    key = str(value or "unclassified")
    return CATEGORY_LABELS.get(key, key)


def label_record(value: object) -> str:
    key = str(value or "unclassified")
    return RECORD_LABELS.get(key, key)


def load_campaigns(selected_banks: list[str]) -> pd.DataFrame:
    placeholders = sql_placeholders(selected_banks)
    return query(
        f"""
        SELECT
            id,
            bank_name,
            title,
            source_group,
            record_kind,
            campaign_category,
            current_status,
            listing_status,
            fetch_status,
            comparison_eligible,
            classification_confidence,
            start_date,
            end_date,
            is_current,
            first_seen_at,
            last_seen_at,
            last_checked_at,
            source_url,
            clean_text,
            classification_reason
        FROM live_campaigns
        WHERE bank_name IN ({placeholders})
        ORDER BY bank_name, title
        """,
        tuple(selected_banks),
    )


def load_finance(selected_banks: list[str]) -> pd.DataFrame:
    placeholders = sql_placeholders(selected_banks)
    return query(
        f"""
        SELECT
            c.id,
            c.bank_name,
            c.title,
            c.current_status,
            c.is_current,
            c.source_url,
            f.finance_type,
            f.profit_share_rate_text,
            f.financing_amount_text,
            f.maturity_text,
            f.grace_period_months,
            f.installment_count,
            f.allocation_fee_status,
            f.expense_status,
            f.expense_details,
            f.campaign_advantage,
            f.extraction_confidence
        FROM live_campaigns AS c
        INNER JOIN live_campaign_finance_details AS f
            ON f.campaign_id = c.id
        WHERE c.bank_name IN ({placeholders})
          AND c.record_kind = 'campaign'
        ORDER BY c.bank_name, c.title
        """,
        tuple(selected_banks),
    )


def load_benefits(selected_banks: list[str]) -> pd.DataFrame:
    placeholders = sql_placeholders(selected_banks)
    return query(
        f"""
        SELECT
            c.id,
            c.bank_name,
            c.title,
            c.campaign_category,
            c.current_status,
            c.is_current,
            c.source_url,
            b.benefit_type,
            b.amount,
            b.rate,
            b.points,
            b.minimum_spending,
            b.maximum_benefit,
            b.description,
            b.evidence
        FROM live_campaigns AS c
        INNER JOIN live_campaign_benefits AS b
            ON b.campaign_id = c.id
        WHERE c.bank_name IN ({placeholders})
        ORDER BY c.bank_name, c.title, b.benefit_type
        """,
        tuple(selected_banks),
    )


def load_audiences(selected_banks: list[str]) -> pd.DataFrame:
    placeholders = sql_placeholders(selected_banks)
    return query(
        f"""
        SELECT
            c.id,
            c.bank_name,
            c.title,
            c.campaign_category,
            c.source_url,
            a.audience_type,
            a.audience_label,
            a.details
        FROM live_campaigns AS c
        INNER JOIN live_campaign_audiences AS a
            ON a.campaign_id = c.id
        WHERE c.bank_name IN ({placeholders})
        ORDER BY c.bank_name, c.title, a.audience_type
        """,
        tuple(selected_banks),
    )


def load_changes(selected_banks: list[str]) -> pd.DataFrame:
    placeholders = sql_placeholders(selected_banks)
    return query(
        f"""
        SELECT
            bank_name,
            source_url,
            change_type,
            old_status,
            new_status,
            changed_at,
            details_json
        FROM live_campaign_changes
        WHERE bank_name IN ({placeholders})
        ORDER BY changed_at DESC
        """,
        tuple(selected_banks),
    )


def dataframe_with_link(
    frame: pd.DataFrame,
    *,
    height: int = 520,
) -> None:
    column_config = {}
    if "Kaynak" in frame.columns:
        column_config["Kaynak"] = st.column_config.LinkColumn(
            "Kaynak",
            display_text="Resmî sayfa",
        )
    if "Sınıflandırma Güveni" in frame.columns:
        column_config["Sınıflandırma Güveni"] = (
            st.column_config.ProgressColumn(
                "Sınıflandırma Güveni",
                min_value=0.0,
                max_value=1.0,
                format="%.2f",
            )
        )
    if "Çıkarım Güveni" in frame.columns:
        column_config["Çıkarım Güveni"] = (
            st.column_config.ProgressColumn(
                "Çıkarım Güveni",
                min_value=0.0,
                max_value=1.0,
                format="%.2f",
            )
        )

    st.dataframe(
        frame,
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config=column_config,
    )


st.title("Bansa — Katılım Bankaları Kontrol Paneli")
st.caption(
    "Bu ekran yalnızca campaigns.db dosyasını okur; "
    "veritabanında hiçbir değişiklik yapmaz."
)

if not DB_PATH.exists():
    st.error(
        "campaigns.db bulunamadı. Dosyayı proje içindeki "
        "`data/campaigns.db` konumuna koyun veya "
        "`BANSA_DB_PATH` ortam değişkenini ayarlayın."
    )
    st.stop()

all_banks = query(
    """
    SELECT DISTINCT bank_name
    FROM live_campaigns
    ORDER BY bank_name
    """
)["bank_name"].tolist()

default_banks = [
    bank
    for bank in (
        "Albaraka Türk",
        "Dünya Katılım",
        "Kuveyt Türk",
        "Türkiye Finans",
        "Ziraat Katılım",
    )
    if bank in all_banks
]

with st.sidebar:
    st.header("Filtreler")
    selected_banks = st.multiselect(
        "Bankalar",
        options=all_banks,
        default=default_banks or all_banks,
    )
    include_noncurrent = st.checkbox(
        "Güncel olmayan kayıtları göster",
        value=False,
    )
    st.divider()
    st.caption(f"Veritabanı: `{DB_PATH}`")
    if st.button("Veriyi yenile"):
        st.cache_data.clear()
        st.rerun()

if not selected_banks:
    st.warning("En az bir banka seçin.")
    st.stop()

campaigns = load_campaigns(selected_banks)
visible_campaigns = campaigns.copy()
if not include_noncurrent:
    visible_campaigns = visible_campaigns[
        visible_campaigns["is_current"] == 1
    ].copy()

campaign_rows = visible_campaigns[
    visible_campaigns["record_kind"] == "campaign"
].copy()

active_count = int(
    (
        (campaign_rows["current_status"] == "active")
        & (campaign_rows["is_current"] == 1)
    ).sum()
)
expired_count = int(
    (campaign_rows["current_status"] == "expired").sum()
)
duplicate_count = int(
    (campaigns["record_kind"] == "duplicate").sum()
)
review_count = int(
    campaigns["record_kind"].isin(
        ["needs_review", "unclassified"]
    ).sum()
)
fetch_error_count = int(
    (campaigns["fetch_status"] != "ok").sum()
)

metric_columns = st.columns(6)
metric_columns[0].metric(
    "Güncel kampanya",
    int(
        (
            (campaigns["record_kind"] == "campaign")
            & (campaigns["is_current"] == 1)
        ).sum()
    ),
)
metric_columns[1].metric("Aktif", active_count)
metric_columns[2].metric("Süresi dolmuş", expired_count)
metric_columns[3].metric("Mükerrer", duplicate_count)
metric_columns[4].metric("İnceleme gerekli", review_count)
metric_columns[5].metric("Fetch sorunu", fetch_error_count)

tabs = st.tabs(
    [
        "Genel Bakış",
        "Kampanyalar",
        "Finansman Karşılaştırması",
        "Fayda ve Hedef Kitle",
        "Veri Kalitesi",
        "Değişiklik Geçmişi",
    ]
)

with tabs[0]:
    left, right = st.columns(2)

    with left:
        st.subheader("Banka bazında kayıtlar")
        bank_summary = (
            campaigns.groupby("bank_name", dropna=False)
            .agg(
                Toplam=("id", "count"),
                Güncel=("is_current", "sum"),
                Kampanya=(
                    "record_kind",
                    lambda values: int(
                        (values == "campaign").sum()
                    ),
                ),
                Mükerrer=(
                    "record_kind",
                    lambda values: int(
                        (values == "duplicate").sum()
                    ),
                ),
            )
            .reset_index()
            .rename(columns={"bank_name": "Banka"})
        )
        dataframe_with_link(bank_summary, height=210)

    with right:
        st.subheader("Güncel kampanya kategorileri")
        category_summary = (
            campaign_rows.groupby(
                ["bank_name", "campaign_category"],
                dropna=False,
            )
            .size()
            .reset_index(name="Adet")
        )
        category_summary["Kategori"] = category_summary[
            "campaign_category"
        ].map(label_category)
        chart_data = category_summary.pivot_table(
            index="Kategori",
            columns="bank_name",
            values="Adet",
            fill_value=0,
            aggfunc="sum",
        )
        st.bar_chart(chart_data)

    st.subheader("Durum dağılımı")
    status_summary = (
        campaign_rows.groupby(
            ["bank_name", "current_status"],
            dropna=False,
        )
        .size()
        .reset_index(name="Adet")
    )
    status_summary["Durum"] = status_summary[
        "current_status"
    ].map(label_status)
    status_chart = status_summary.pivot_table(
        index="Durum",
        columns="bank_name",
        values="Adet",
        fill_value=0,
        aggfunc="sum",
    )
    st.bar_chart(status_chart)

with tabs[1]:
    st.subheader("Kampanya kayıtları")

    filter_columns = st.columns(4)
    categories = sorted(
        visible_campaigns["campaign_category"]
        .dropna()
        .unique()
        .tolist()
    )
    statuses = sorted(
        visible_campaigns["current_status"]
        .dropna()
        .unique()
        .tolist()
    )
    record_kinds = sorted(
        visible_campaigns["record_kind"]
        .dropna()
        .unique()
        .tolist()
    )

    selected_categories = filter_columns[0].multiselect(
        "Kategori",
        options=categories,
        format_func=label_category,
    )
    selected_statuses = filter_columns[1].multiselect(
        "Durum",
        options=statuses,
        format_func=label_status,
    )
    selected_records = filter_columns[2].multiselect(
        "Kayıt türü",
        options=record_kinds,
        format_func=label_record,
    )
    search_text = filter_columns[3].text_input(
        "Başlıkta ara"
    ).strip()

    filtered = visible_campaigns.copy()
    if selected_categories:
        filtered = filtered[
            filtered["campaign_category"].isin(
                selected_categories
            )
        ]
    if selected_statuses:
        filtered = filtered[
            filtered["current_status"].isin(selected_statuses)
        ]
    if selected_records:
        filtered = filtered[
            filtered["record_kind"].isin(selected_records)
        ]
    if search_text:
        filtered = filtered[
            filtered["title"]
            .fillna("")
            .str.contains(
                search_text,
                case=False,
                regex=False,
            )
        ]

    display = filtered[
        [
            "bank_name",
            "title",
            "record_kind",
            "campaign_category",
            "current_status",
            "source_group",
            "classification_confidence",
            "end_date",
            "source_url",
        ]
    ].copy()
    display.columns = [
        "Banka",
        "Kampanya",
        "Kayıt Türü",
        "Kategori",
        "Durum",
        "Kaynak Grubu",
        "Sınıflandırma Güveni",
        "Bitiş Tarihi",
        "Kaynak",
    ]
    display["Kayıt Türü"] = display["Kayıt Türü"].map(
        label_record
    )
    display["Kategori"] = display["Kategori"].map(
        label_category
    )
    display["Durum"] = display["Durum"].map(label_status)

    st.caption(f"Gösterilen kayıt: {len(display)}")
    dataframe_with_link(display)

    if not filtered.empty:
        selected_id = st.selectbox(
            "Detayını incele",
            options=filtered["id"].tolist(),
            format_func=lambda campaign_id: (
                filtered.loc[
                    filtered["id"] == campaign_id,
                    "title",
                ].iloc[0]
                or f"Kayıt {campaign_id}"
            ),
        )
        record = filtered[
            filtered["id"] == selected_id
        ].iloc[0]

        with st.expander(
            "Seçili kampanyanın metni ve sınıflandırması",
            expanded=False,
        ):
            st.markdown(
                f"**Banka:** {record['bank_name']}  \n"
                f"**Kategori:** {label_category(record['campaign_category'])}  \n"
                f"**Durum:** {label_status(record['current_status'])}  \n"
                f"**Sınıflandırma nedeni:** "
                f"{record['classification_reason'] or '—'}"
            )
            st.text_area(
                "Temizlenmiş kampanya metni",
                value=record["clean_text"] or "",
                height=260,
                disabled=True,
            )

with tabs[2]:
    finance = load_finance(selected_banks)
    if not include_noncurrent:
        finance = finance[finance["is_current"] == 1].copy()

    st.subheader("Finansman kampanyaları")
    st.caption(
        "Oran, finansman tutarı, vade, taksit, erteleme ve "
        "masraf alanlarını yan yana kontrol edin."
    )

    finance_display = finance[
        [
            "bank_name",
            "title",
            "finance_type",
            "profit_share_rate_text",
            "financing_amount_text",
            "maturity_text",
            "installment_count",
            "grace_period_months",
            "allocation_fee_status",
            "expense_status",
            "campaign_advantage",
            "extraction_confidence",
            "source_url",
        ]
    ].copy()
    finance_display.columns = [
        "Banka",
        "Kampanya",
        "Finansman Türü",
        "Kâr Payı",
        "Finansman Tutarı",
        "Vade",
        "Taksit",
        "Erteleme (Ay)",
        "Tahsis Ücreti",
        "Masraf",
        "Kampanya Avantajı",
        "Çıkarım Güveni",
        "Kaynak",
    ]
    dataframe_with_link(finance_display, height=610)

    st.subheader("Eksik finansman alanları")
    finance_check = finance.copy()
    finance_check["Eksik Alanlar"] = finance_check.apply(
        lambda row: ", ".join(
            label
            for field, label in (
                ("profit_share_rate_text", "Kâr payı"),
                ("financing_amount_text", "Finansman tutarı"),
                ("maturity_text", "Vade"),
                ("installment_count", "Taksit"),
                ("allocation_fee_status", "Tahsis ücreti"),
                ("expense_status", "Masraf"),
            )
            if pd.isna(row[field])
            or str(row[field]).strip() == ""
        ),
        axis=1,
    )
    missing_finance = finance_check[
        finance_check["Eksik Alanlar"] != ""
    ][
        [
            "bank_name",
            "title",
            "finance_type",
            "Eksik Alanlar",
            "campaign_advantage",
            "source_url",
        ]
    ].copy()
    missing_finance.columns = [
        "Banka",
        "Kampanya",
        "Finansman Türü",
        "Eksik Alanlar",
        "Kampanya Avantajı",
        "Kaynak",
    ]
    st.info(
        "Bir alanın boş olması her zaman hata değildir; "
        "resmî kampanya metninde belirtilmemiş olabilir."
    )
    dataframe_with_link(missing_finance, height=360)

with tabs[3]:
    benefit_tab, audience_tab = st.tabs(
        ["Kampanya Faydaları", "Hedef Kitleler"]
    )

    with benefit_tab:
        benefits = load_benefits(selected_banks)
        benefit_types = sorted(
            benefits["benefit_type"].dropna().unique().tolist()
        )
        selected_benefit_types = st.multiselect(
            "Fayda türü",
            options=benefit_types,
        )
        if selected_benefit_types:
            benefits = benefits[
                benefits["benefit_type"].isin(
                    selected_benefit_types
                )
            ]

        benefit_display = benefits[
            [
                "bank_name",
                "title",
                "benefit_type",
                "amount",
                "rate",
                "points",
                "minimum_spending",
                "maximum_benefit",
                "description",
                "source_url",
            ]
        ].copy()
        benefit_display.columns = [
            "Banka",
            "Kampanya",
            "Fayda Türü",
            "Tutar",
            "Oran",
            "Puan",
            "Minimum Harcama",
            "Maksimum Fayda",
            "Açıklama",
            "Kaynak",
        ]
        dataframe_with_link(benefit_display)

    with audience_tab:
        audiences = load_audiences(selected_banks)
        audience_display = audiences[
            [
                "bank_name",
                "title",
                "audience_label",
                "details",
                "source_url",
            ]
        ].copy()
        audience_display.columns = [
            "Banka",
            "Kampanya",
            "Hedef Kitle",
            "Ayrıntı",
            "Kaynak",
        ]
        dataframe_with_link(audience_display)

with tabs[4]:
    st.subheader("Otomatik kalite kontrolleri")

    quality_rows = []

    for bank in selected_banks:
        bank_rows = campaigns[campaigns["bank_name"] == bank]

        quality_rows.extend(
            [
                {
                    "Banka": bank,
                    "Kontrol": "Fetch hatası",
                    "Adet": int(
                        (bank_rows["fetch_status"] != "ok").sum()
                    ),
                },
                {
                    "Banka": bank,
                    "Kontrol": "İnceleme gereken kayıt",
                    "Adet": int(
                        bank_rows["record_kind"]
                        .isin(
                            [
                                "needs_review",
                                "unclassified",
                            ]
                        )
                        .sum()
                    ),
                },
                {
                    "Banka": bank,
                    "Kontrol": "Mükerrer kayıt",
                    "Adet": int(
                        (
                            bank_rows["record_kind"]
                            == "duplicate"
                        ).sum()
                    ),
                },
                {
                    "Banka": bank,
                    "Kontrol": "Başlığı eksik",
                    "Adet": int(
                        bank_rows["title"]
                        .fillna("")
                        .str.strip()
                        .eq("")
                        .sum()
                    ),
                },
                {
                    "Banka": bank,
                    "Kontrol": "Kaynak URL eksik",
                    "Adet": int(
                        bank_rows["source_url"]
                        .fillna("")
                        .str.strip()
                        .eq("")
                        .sum()
                    ),
                },
                {
                    "Banka": bank,
                    "Kontrol": "Düşük sınıflandırma güveni (<0,70)",
                    "Adet": int(
                        (
                            bank_rows[
                                "classification_confidence"
                            ].fillna(0)
                            < 0.70
                        ).sum()
                    ),
                },
            ]
        )

    quality_frame = pd.DataFrame(quality_rows)
    quality_pivot = quality_frame.pivot(
        index="Kontrol",
        columns="Banka",
        values="Adet",
    ).fillna(0)
    st.dataframe(
        quality_pivot,
        use_container_width=True,
    )

    issues = campaigns[
        (campaigns["fetch_status"] != "ok")
        | campaigns["record_kind"].isin(
            ["needs_review", "unclassified"]
        )
        | (
            campaigns["classification_confidence"]
            .fillna(0)
            < 0.70
        )
    ].copy()

    if issues.empty:
        st.success(
            "Fetch hatası, sınıflandırılmamış kayıt veya "
            "düşük güvenli kayıt bulunmadı."
        )
    else:
        issue_display = issues[
            [
                "bank_name",
                "title",
                "record_kind",
                "campaign_category",
                "fetch_status",
                "classification_confidence",
                "classification_reason",
                "source_url",
            ]
        ].copy()
        issue_display.columns = [
            "Banka",
            "Kampanya",
            "Kayıt Türü",
            "Kategori",
            "Fetch",
            "Sınıflandırma Güveni",
            "Neden",
            "Kaynak",
        ]
        dataframe_with_link(issue_display)

with tabs[5]:
    changes = load_changes(selected_banks)
    st.subheader("Son değişiklikler")

    if changes.empty:
        st.info("Değişiklik kaydı bulunmuyor.")
    else:
        change_types = sorted(
            changes["change_type"].dropna().unique().tolist()
        )
        selected_change_types = st.multiselect(
            "Değişiklik türü",
            options=change_types,
        )
        if selected_change_types:
            changes = changes[
                changes["change_type"].isin(
                    selected_change_types
                )
            ]

        change_display = changes[
            [
                "bank_name",
                "change_type",
                "old_status",
                "new_status",
                "changed_at",
                "source_url",
            ]
        ].copy()
        change_display.columns = [
            "Banka",
            "Değişiklik",
            "Eski Durum",
            "Yeni Durum",
            "Tarih",
            "Kaynak",
        ]
        change_display["Eski Durum"] = change_display[
            "Eski Durum"
        ].map(label_status)
        change_display["Yeni Durum"] = change_display[
            "Yeni Durum"
        ].map(label_status)
        dataframe_with_link(change_display)

