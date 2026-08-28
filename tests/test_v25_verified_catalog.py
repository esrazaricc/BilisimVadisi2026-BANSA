from __future__ import annotations

from pathlib import Path
import pandas as pd

from src.verified_catalog_repository import (
    load_active_campaign_catalog,
    load_finance_catalog,
    load_verified_scenarios,
)


def test_finance_catalog_has_full_official_source_coverage():
    frame = load_finance_catalog()
    assert len(frame) == 274
    assert frame["bank_name"].nunique() == 10
    assert frame["source_url"].astype(str).str.startswith("http").all()
    assert frame["product_summary"].astype(str).str.strip().ne("").all()
    assert not frame["product_summary"].astype(str).str.contains("Your browser does not support", case=False).any()


def test_campaign_catalog_is_date_gated_for_release_day():
    frame = load_active_campaign_catalog()
    assert not frame.empty
    assert frame["source_url"].astype(str).str.startswith("http").all()
    assert frame["main_benefit"].astype(str).str.strip().ne("").all()
    assert frame["conditions_summary"].astype(str).str.strip().ne("").all()
    end = pd.to_datetime(frame["end_date"], errors="coerce")
    assert not ((end.notna()) & (end < pd.Timestamp("2026-08-27"))).any()


def test_ziraat_bauhaus_installment_is_title_evidence_not_legal_maximum():
    frame = load_active_campaign_catalog()
    row = frame[
        frame["bank_name"].eq("Ziraat Katılım")
        & frame["campaign_name"].astype(str).str.contains("BAUHAUS", case=False, regex=False)
    ].iloc[0]
    assert row["installment"] == "3 taksit"
    assert row["main_benefit"] == "3 taksit"


def test_albaraka_dbs_summary_does_not_inherit_elus_sibling_content():
    frame = load_finance_catalog()
    row = frame[
        frame["bank_name"].eq("Albaraka Türk")
        & frame["product_name"].eq("DBS Fatura Teminatlı Kredi")
    ].iloc[0]
    summary = row["product_summary"].casefold()
    assert "fatura" in summary
    assert "teminat" in summary
    assert "elüs" not in summary


def test_verified_scenarios_have_canonical_source_and_default_100k_36_examples():
    frame = load_verified_scenarios().fillna("")
    assert frame["source_url"].astype(str).str.startswith("http").all()
    subset = frame[
        frame["product_family_key"].eq("konut_finansmani")
        & pd.to_numeric(frame["input_amount"], errors="coerce").eq(100000)
        & pd.to_numeric(frame["input_maturity_months"], errors="coerce").eq(36)
    ]
    assert not subset.empty
    assert {"Albaraka Türk", "Kuveyt Türk", "Türkiye Finans", "Vakıf Katılım", "Ziraat Katılım"}.issubset(set(subset["bank_name"]))


def test_current_turkiye_finans_reference_rates_in_verified_scenarios():
    frame = load_verified_scenarios().fillna("")
    tf = frame[frame["bank_name"].eq("Türkiye Finans")].copy()
    amount = pd.to_numeric(tf["input_amount"], errors="coerce")
    maturity = pd.to_numeric(tf["input_maturity_months"], errors="coerce")
    rate = pd.to_numeric(tf["profit_share_rate"], errors="coerce")
    tf = tf[amount.eq(100000) & maturity.eq(36)].copy()
    rate = pd.to_numeric(tf["profit_share_rate"], errors="coerce")
    housing = tf[tf["product_family_key"].eq("konut_finansmani")]
    need = tf[tf["product_family_key"].eq("ihtiyac_finansmani")]
    vehicle = tf[tf["product_family_key"].eq("arac_finansmani")]
    assert 3.58 in set(pd.to_numeric(housing["profit_share_rate"], errors="coerce"))
    assert 4.04 in set(pd.to_numeric(housing["profit_share_rate"], errors="coerce"))
    assert 3.80 in set(pd.to_numeric(need["profit_share_rate"], errors="coerce"))
    assert 5.70 in set(pd.to_numeric(need["profit_share_rate"], errors="coerce"))
    assert 3.48 in set(pd.to_numeric(vehicle["profit_share_rate"], errors="coerce"))
    assert 4.08 in set(pd.to_numeric(vehicle["profit_share_rate"], errors="coerce"))
