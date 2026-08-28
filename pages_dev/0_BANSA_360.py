from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.finance_runtime_repository import (
    get_standard_products,
    get_verified_finance_scenarios,
)
from src.repository import get_campaigns
from src.ui_theme import apply_bansa_theme
from src.competition_fast_router import _structured_fee_value


st.set_page_config(
    page_title="BANSA 360",
    page_icon="🏦",
    layout="wide",
)
apply_bansa_theme()

BDDK_BANKS = (
    "Adil Katılım",
    "Albaraka Türk",
    "Dünya Katılım",
    "Hayat Finans",
    "Kuveyt Türk",
    "T.O.M. Katılım",
    "Türkiye Emlak Katılım",
    "Türkiye Finans",
    "Vakıf Katılım",
    "Ziraat Katılım",
)

MISSING = "Resmî kaynakta belirtilmemiş"


def present(value) -> bool:
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except Exception:
        pass
    return bool(str(value).strip())


def money(value) -> str:
    if not present(value):
        return MISSING
    try:
        number = float(value)
    except Exception:
        return str(value)
    return f"{number:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") + " TL"


def rate(value, text=None) -> str:
    if present(value):
        return "%" + f"{float(value):.2f}".replace(".", ",")
    if present(text):
        return str(text).strip()
    return "Hesaplama aracında dinamik / " + MISSING


def maturity(row) -> str:
    if present(row.get("maximum_maturity_months")):
        return f"{int(float(row.get('maximum_maturity_months')))} ay"
    if present(row.get("maturity_rules_text")):
        return str(row.get("maturity_rules_text")).strip()
    return MISSING


def scope_label(value) -> str:
    v = str(value or "").strip().casefold()
    if v == "bireysel":
        return "Bireysel"
    if v == "ticari":
        return "Ticari / KOBİ"
    return MISSING


products = get_standard_products().copy()
scenarios = get_verified_finance_scenarios().copy()
campaigns = get_campaigns().copy()

scenario_by_product: dict[int, pd.Series] = {}
if not scenarios.empty:
    scenarios["_checked"] = pd.to_datetime(scenarios["checked_at"], errors="coerce")
    for product_id, group in scenarios.groupby("product_id"):
        verified = group[group["scenario_status"].astype(str).str.contains("verified", case=False, na=False)]
        if verified.empty:
            continue
        scenario_by_product[int(product_id)] = verified.sort_values("_checked", ascending=False).iloc[0]

# Current campaign date gate.
if not campaigns.empty:
    if "is_active" in campaigns.columns:
        campaigns = campaigns[(campaigns["is_active"].isna()) | (campaigns["is_active"] == 1)].copy()
    today = pd.Timestamp(date.today())
    if "campaign_start_date" in campaigns.columns:
        starts = pd.to_datetime(campaigns["campaign_start_date"], errors="coerce")
        campaigns = campaigns[starts.isna() | starts.le(today)].copy()
    if "campaign_end_date" in campaigns.columns:
        ends = pd.to_datetime(campaigns["campaign_end_date"], errors="coerce")
        campaigns = campaigns[ends.isna() | ends.ge(today)].copy()


st.markdown(
    """
    <div style="padding:1.6rem 1.8rem;border:1px solid rgba(120,120,120,.25);border-radius:22px;">
      <div style="font-size:.85rem;letter-spacing:.12em;font-weight:700;opacity:.7;">BANSA 360 · BDDK TAM KAPSAM</div>
      <div style="font-size:2.2rem;font-weight:800;margin-top:.25rem;">Katılım Bankacılığı Karar Merkezi</div>
      <div style="font-size:1.02rem;opacity:.78;margin-top:.45rem;">Finansman ürünleri, güncel kampanyalar ve doğrulanmış hesaplama örnekleri tek ekranda.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("")
metric1, metric2, metric3, metric4 = st.columns(4)
metric1.metric("BDDK kapsamı", f"{len(BDDK_BANKS)}/10 banka")
metric2.metric("Finansman ürünü", f"{len(products):,}".replace(",", "."))
metric3.metric("Aktif kampanya", f"{len(campaigns):,}".replace(",", "."))
metric4.metric("Doğrulanmış hesaplama", f"{len(scenarios):,}".replace(",", "."))

st.markdown("")
coverage_rows = []
for bank in BDDK_BANKS:
    coverage_rows.append({
        "Banka": bank,
        "Finansman Ürünü": int((products["bank_name"] == bank).sum()),
        "Aktif Kampanya": int((campaigns["bank_name"] == bank).sum()) if not campaigns.empty else 0,
        "Durum": "✅ Kapsamda",
    })
coverage = pd.DataFrame(coverage_rows)
with st.expander("🏦 BDDK banka kapsamı", expanded=False):
    st.dataframe(coverage, hide_index=True, use_container_width=True)

finance_tab, campaign_tab = st.tabs(["💳 Finansman Kataloğu", "🎁 Güncel Kampanyalar"])

with finance_tab:
    banks = st.multiselect("Banka", BDDK_BANKS, default=list(BDDK_BANKS), key="finance_banks")
    families = sorted(products["product_family"].dropna().astype(str).unique().tolist())
    selected_family = st.selectbox("Finansman türü", ["Tümü"] + families)

    work = products[products["bank_name"].isin(banks)].copy()
    if selected_family != "Tümü":
        work = work[work["product_family"].astype(str) == selected_family].copy()

    rows = []
    for _, row in work.iterrows():
        product_id = int(row["id"])
        scenario = scenario_by_product.get(product_id)

        published_rate = rate(row.get("profit_share_rate"), row.get("profit_share_rate_text"))
        calculator = "Doğrulanmış hesaplama örneği yok"
        allocation = MISSING
        appraisal = MISSING
        mortgage_insurance = MISSING

        # Authoritative normalized fee rule always wins over a one-off
        # calculator scenario. Scenario values remain visible only as examples.
        allocation_rule, _ = _structured_fee_value(row, "allocation_fee")
        appraisal_rule, _ = _structured_fee_value(row, "appraisal_fee")
        mortgage_rule, _ = _structured_fee_value(row, "mortgage_fee")
        insurance_rule, _ = _structured_fee_value(row, "insurance_fee")

        if allocation_rule:
            allocation = allocation_rule
        if appraisal_rule:
            appraisal = appraisal_rule
        mi_parts = []
        if mortgage_rule:
            mi_parts.append("İpotek: " + mortgage_rule)
        if insurance_rule:
            mi_parts.append("Sigorta: " + insurance_rule)
        if mi_parts:
            mortgage_insurance = " · ".join(mi_parts)

        if scenario is not None:
            calculator = (
                "✅ Doğrulanmış örnek: "
                f"{money(scenario.get('input_amount'))} / {int(scenario.get('input_maturity_months'))} ay · "
                f"{rate(scenario.get('profit_share_rate'))} · aylık {money(scenario.get('monthly_installment'))}"
            )
            if (not present(row.get("profit_share_rate"))) and present(scenario.get("profit_share_rate")):
                published_rate = "Dinamik · doğrulanmış örnek " + rate(scenario.get("profit_share_rate"))
            if allocation == MISSING and present(scenario.get("allocation_fee")):
                allocation = "Yalnız doğrulanmış örnekte " + money(scenario.get("allocation_fee"))
            if appraisal == MISSING and present(scenario.get("appraisal_fee")):
                appraisal = "Yalnız doğrulanmış örnekte " + money(scenario.get("appraisal_fee"))
            if mortgage_insurance == MISSING and present(scenario.get("mortgage_fee")):
                mortgage_insurance = "Yalnız doğrulanmış örnekte ipotek " + money(scenario.get("mortgage_fee"))

        if bool(row.get("allocation_fee_waived")) if present(row.get("allocation_fee_waived")) else False:
            allocation = "Muaf / alınmıyor"
        if bool(row.get("insurance_fee_waived")) if present(row.get("insurance_fee_waived")) else False:
            if mortgage_insurance == MISSING:
                mortgage_insurance = "Sigorta masrafı muaf"

        rows.append({
            "Banka Adı": row.get("bank_name") or MISSING,
            "Finansman Türü": row.get("product_family") or MISSING,
            "Ürün": row.get("product_name") or MISSING,
            "Kâr Payı / Fiyatlama": published_rate,
            "Azami Vade": maturity(row),
            "Tahsis Ücreti": allocation,
            "Ekspertiz Ücreti": appraisal,
            "İpotek / Sigorta Masrafı": mortgage_insurance,
            "Hedef Kitle": scope_label(row.get("scope")),
            "Hesaplama Botu": calculator,
            "Kaynak URL": row.get("source_url") or MISSING,
            "Son Kontrol": str(row.get("last_checked_at") or MISSING)[:19],
        })

    finance_view = pd.DataFrame(rows)
    if finance_view.empty:
        st.info("Bu filtreyle eşleşen finansman ürünü yok.")
    else:
        finance_view = finance_view.fillna(MISSING).replace("", MISSING)
        st.dataframe(
            finance_view,
            hide_index=True,
            use_container_width=True,
            height=620,
            column_config={
                "Kaynak URL": st.column_config.LinkColumn("Resmî Kaynak", display_text="Aç"),
            },
        )
        st.caption("Boş hücre yerine yalnız veri kaynağının durumunu açıklayan standart etiketler kullanılır; finansal rakam uydurulmaz.")

with campaign_tab:
    campaign_banks = st.multiselect("Banka", BDDK_BANKS, default=list(BDDK_BANKS), key="campaign_banks")
    cwork = campaigns[campaigns["bank_name"].isin(campaign_banks)].copy() if not campaigns.empty else campaigns.copy()

    crows = []
    for _, row in cwork.iterrows():
        benefit_parts = []
        if present(row.get("reward_amount")):
            benefit_parts.append(money(row.get("reward_amount")))
        if present(row.get("shopping_points")):
            benefit_parts.append(f"{int(float(row.get('shopping_points'))):,}".replace(",", ".") + " puan")
        if present(row.get("discount_rate")):
            benefit_parts.append("%" + f"{float(row.get('discount_rate')):.0f}" + " indirim")
        if present(row.get("maximum_benefit")):
            benefit_parts.append("Azami " + money(row.get("maximum_benefit")))
        if present(row.get("installment_count")):
            benefit_parts.append(f"{int(float(row.get('installment_count')))} taksit")

        crows.append({
            "Banka Adı": row.get("bank_name") or MISSING,
            "Kampanya Başlığı": row.get("campaign_name") or MISSING,
            "Kategori": row.get("campaign_type") or MISSING,
            "Ödül / Puan / İndirim": " · ".join(benefit_parts) if benefit_parts else MISSING,
            "Son Geçerlilik": row.get("campaign_end_date") or MISSING,
            "Katılım Koşulu": str(row.get("campaign_conditions") or MISSING)[:420],
            "Masraf Durumu": row.get("expense_status") or MISSING,
            "Kaynak URL": row.get("source_url") or MISSING,
        })

    campaign_view = pd.DataFrame(crows)
    if campaign_view.empty:
        st.info("Seçilen bankalar için güncel aktif kampanya kaydı bulunmuyor.")
    else:
        campaign_view = campaign_view.fillna(MISSING).replace("", MISSING)
        st.dataframe(
            campaign_view,
            hide_index=True,
            use_container_width=True,
            height=620,
            column_config={
                "Kaynak URL": st.column_config.LinkColumn("Resmî Kaynak", display_text="Aç"),
            },
        )
        st.caption("Kampanyalar aktiflik ve tarih kapısından geçirilerek gösterilir.")
