"""Competition-time verified current-source overlays.

These overlays do not rewrite historical calculator snapshots. They only make
newer official pricing/campaign evidence available to the jury-facing runtime.
Historical scenarios keep their original timestamps/provenance.
"""
from __future__ import annotations

import json
import pandas as pd

CHECKED_AT = "2026-08-26T14:45:00+03:00"
TF_HOUSING_URL = "https://www.turkiyefinans.com.tr/tr-tr/bireysel/konut-finansmani/Sayfalar/konut-finansmani.aspx"
TF_VEHICLE_URL = "https://www.turkiyefinans.com.tr/tr-tr/bireysel/tasit-finansmani/Sayfalar/Tasit-Finansmani.aspx"
TF_DIGITAL_VEHICLE_URL = "https://www.turkiyefinans.com.tr/tr-tr/bireysel/tasit-finansmani/sayfalar/dijital-tasit-finansmani.aspx"
ZIRAAT_TEKNO_URL = "https://www.ziraatkatilim.com.tr/kart-kampanyalari/teknosada-3-taksit"
EMLAK_VEHICLE_URL = "https://www.emlakkatilim.com.tr/tr/bireysel/finansmanlar/tasit-finansmani"
DUNYA_VEHICLE_URL = "https://dunyakatilim.com.tr/kendim-icin/finansmanlar/arac-finansmanlari/arac-finansmani"
KUVEYT_VEHICLE_URL = "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/arac-finansmanlari/arac-finansmani"
KUVEYT_MOTORCYCLE_URL = "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/arac-finansmanlari/motosiklet-finansmani"
ALBARAKA_VEHICLE_URL = "https://www.albaraka.com.tr/tr/bireysel/finansmanlar/tasit-finansmani/tasit-finansmani"
VAKIF_VEHICLE_URL = "https://www.vakifkatilim.com.tr/tr/kendim-icin/finansmanlar/tasit-finansmani"
VAKIF_MOTORCYCLE_URL = "https://www.vakifkatilim.com.tr/tr/kendim-icin/finansmanlar/motosiklet-finansmani"
ZIRAAT_CALCULATOR_URL = "https://www.ziraatkatilim.com.tr/finansal-hesaplama-araci"


def _rules(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            val = json.loads(raw)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}
    return {}


def _tier(m, rate, monthly_cost, annual_cost, variant, url, *, conditions):
    return {
        "conditions": conditions,
        "source_url": url,
        "value_type": "conditional_pricing",
        "source_text": f"{m} | {str(rate).replace('.', ',')}% | 0,50% | {str(monthly_cost).replace('.', ',')}% | {str(annual_cost).replace('.', ',')}%",
        "source_type": "official_pricing_table",
        "maturity_months": int(m),
        "pricing_variant": variant,
        "profit_share_rate": float(rate),
        "allocation_fee_rate": 0.5,
        "monthly_total_cost_rate": float(monthly_cost),
        "annual_total_cost_rate": float(annual_cost),
        "verified_checked_at": CHECKED_AT,
    }


def _housing_tiers():
    mats = [3, 6, 12, 18, 24, 36, 48, 59, 72, 120]
    variants = {
        "İlk Konut · Sigortalı": (
            [3.64,3.59,3.52,3.49,3.39,3.35,3.29,3.09,2.90,2.88],
            [16.29,10.84,7.53,6.33,5.63,4.98,4.62,4.23,3.89,3.67],
            [511.53,243.79,139.08,108.98,92.86,79.19,71.90,64.39,58.07,54.19],
        ),
        "İlk Konut · Sigortasız": (
            [4.10,4.05,3.98,3.95,3.85,3.81,3.75,3.55,3.36,3.34],
            [16.82,11.36,8.05,6.85,6.14,5.50,5.14,4.76,4.42,4.23],
            [546.29,263.75,153.21,121.47,104.48,90.16,82.57,74.72,68.10,64.37],
        ),
        "Mevcut Konut · Sigortalı": (
            [3.64,3.59,3.52,3.49,3.39,3.35,3.29,3.09,2.90,2.88],
            [16.98,11.48,8.14,6.93,6.21,5.56,5.19,4.77,4.40,4.20],
            [556.88,268.56,155.88,123.57,105.99,91.37,83.51,74.91,67.63,63.80],
        ),
        "Mevcut Konut · Sigortasız": (
            [4.10,4.05,3.98,3.95,3.85,3.81,3.75,3.55,3.36,3.34],
            [17.60,12.08,8.74,7.53,6.80,6.16,5.80,5.38,5.02,4.84],
            [599.76,293.15,173.28,138.95,120.31,104.91,96.70,87.64,79.99,76.37],
        ),
    }
    out=[]
    cond="Türkiye Finans resmî konut fiyatlama tablosu; oran konut durumu ve sigorta seçimine göre değişir."
    for variant,(rates,mc,ac) in variants.items():
        out += [_tier(m,r,x,y,variant,TF_HOUSING_URL,conditions=cond) for m,r,x,y in zip(mats,rates,mc,ac)]
    return out


def _vehicle_tiers(url: str):
    mats=[3,6,12,18,24,36,48]
    insured_rates=[3.67,3.67,3.63,3.56,3.52,3.48,3.42]
    insured_mc=[5.07,4.95,4.81,4.70,4.64,4.57,4.48]
    insured_ac=[81.11,78.49,75.81,73.61,72.24,70.88,69.16]
    uninsured_rates=[4.27,4.27,4.23,4.16,4.12,4.08,4.02]
    uninsured_mc=[5.86,5.73,5.60,5.49,5.42,5.35,5.26]
    uninsured_ac=[97.99,95.13,92.21,89.83,88.35,86.88,85.01]
    out=[]
    cond="Türkiye Finans resmî taşıt fiyatlama tablosu; kasko/Finansman Güvence Sigortası seçimine ve araç durumuna göre değişir."
    for vehicle in ("0 km","2. El"):
        for label,rates,mc,ac in (
            ("Sigortalı",insured_rates,insured_mc,insured_ac),
            ("Sigortasız",uninsured_rates,uninsured_mc,uninsured_ac),
        ):
            variant=f"{label} · {vehicle}"
            out += [_tier(m,r,x,y,variant,url,conditions=cond) for m,r,x,y in zip(mats,rates,mc,ac)]
    return out


def _vehicle_value_rules():
    return [
        {"min_value": None, "max_value": 400000.0, "max_financing_ratio": 70.0, "max_maturity_months": 48},
        {"min_value": 400000.0, "max_value": 800000.0, "max_financing_ratio": 50.0, "max_maturity_months": 36},
        {"min_value": 800000.0, "max_value": 1200000.0, "max_financing_ratio": 30.0, "max_maturity_months": 24},
        {"min_value": 1200000.0, "max_value": 2000000.0, "max_financing_ratio": 20.0, "max_maturity_months": 12},
    ]


def _vehicle_amount_maturity_rules():
    return [
        {"min_amount": None, "max_amount": 400000.0, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 48, "source_text": "Değer ≤ 400.000 TL → Azami %70 · 48 ay"},
        {"min_amount": 400000.0, "max_amount": 800000.0, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 36, "source_text": "400.000 TL < Değer ≤ 800.000 TL → Azami %50 · 36 ay"},
        {"min_amount": 800000.0, "max_amount": 1200000.0, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 24, "source_text": "800.000 TL < Değer ≤ 1.200.000 TL → Azami %30 · 24 ay"},
        {"min_amount": 1200000.0, "max_amount": 2000000.0, "min_inclusive": False, "max_inclusive": True, "max_maturity_months": 12, "source_text": "1.200.000 TL < Değer ≤ 2.000.000 TL → Azami %20 · 12 ay"},
    ]



def _set_display_metadata(rules: dict, **updates) -> dict:
    rules=dict(rules or {})
    metadata=rules.get("display_metadata") if isinstance(rules.get("display_metadata"),dict) else {}
    metadata=dict(metadata)
    metadata.update(updates)
    rules["display_metadata"]=metadata
    return rules


def _live_first(rules: dict, calculator_url: str) -> dict:
    return _set_display_metadata(
        rules,
        pricing_source_policy="live_calculator_first",
        calculator_url=calculator_url,
        historical_snapshot_rankable=False,
        pricing_reference_checked_at=CHECKED_AT,
    )


def _current_static(rules: dict) -> dict:
    return _set_display_metadata(
        rules,
        pricing_source_policy="current_official_static_rate_table",
        historical_snapshot_rankable=False,
        pricing_reference_checked_at=CHECKED_AT,
    )


def _set_vehicle_rules(
    rules: dict,
    *,
    blocked_above=None,
    ambiguous_values=None,
    unknown_ranges=None,
) -> dict:
    updates={"vehicle_value_rules": _vehicle_value_rules()}
    if blocked_above is not None:
        updates["vehicle_blocked_above"]=float(blocked_above)
    if ambiguous_values:
        updates["vehicle_ambiguous_values"]=[float(x) for x in ambiguous_values]
    if unknown_ranges:
        updates["vehicle_unknown_ranges"]=[list(x) for x in unknown_ranges]
    rules=_set_display_metadata(rules, **updates)
    # The amount_maturity rules are eligibility only.  They must never be
    # interpreted as price/rate tiers.
    rules["amount_maturity_rules"]=_vehicle_amount_maturity_rules()
    return rules


def _vakif_vehicle_tiers():
    rates={12:3.50,24:3.45,36:3.40,48:3.40}
    out=[]
    for maturity,rate in rates.items():
        for variant in ("0 km","2. El"):
            out.append({
                "conditions":"Vakıf Katılım resmî taşıt fiyatlama tablosu.",
                "source_url":VAKIF_VEHICLE_URL,
                "value_type":"conditional_pricing",
                "source_type":"official_pricing_table",
                "maturity_months":maturity,
                "pricing_variant":variant,
                "profit_share_rate":rate,
                "allocation_fee_rate":0.5,
                # The table reference row is explicitly 100,000 TL.  This
                # prevents silently projecting the published rate to a
                # different principal when bank taxes/costs may differ.
                "financing_amount":100000.0,
                "verified_checked_at":CHECKED_AT,
            })
    return out

def apply_product_overrides(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    out=frame.copy(deep=True)

    def update(mask, fn):
        for idx,row in out[mask].iterrows():
            rules=_rules(row.get("finance_rules_json"))
            rules=fn(rules,row)
            out.at[idx,"finance_rules_json"]=json.dumps(rules,ensure_ascii=False)
            out.at[idx,"last_checked_at"]=CHECKED_AT

    bank=out.get("bank_name",pd.Series(index=out.index,dtype=object)).astype(str)
    product=out.get("product_name",pd.Series(index=out.index,dtype=object)).astype(str)

    # ---------------------------------------------------------------
    # Vehicle eligibility != pricing.  These banks publish vehicle-value
    # financing/maturity rules, while profit share/payment is calculator-led.
    # ---------------------------------------------------------------
    mask=(bank.eq("Dünya Katılım") & product.eq("Araç Finansmanı"))
    def dunya_rules(rules,row):
        # V25.4 SOURCE CORRECTION (official page re-checked 2026-08-27):
        # the FAQ explicitly publishes both "Maksimum Oran" and "Azami Vade"
        # for the four vehicle-value bands.  The later note that the amounts
        # determine maturity does not erase the separately published maximum
        # financing-ratio column.
        rules=_set_vehicle_rules(rules,blocked_above=2000000.0)
        rules=_set_display_metadata(
            rules,
            vehicle_ratio_published=True,
            vehicle_value_rule_scope="ltv_and_maturity",
        )
        return _live_first(rules,DUNYA_VEHICLE_URL)
    update(mask,dunya_rules)
    out.loc[mask,"maximum_maturity_months"]=48.0
    if "maximum_financing_ratio" in out.columns:
        out.loc[mask,"maximum_financing_ratio"]=70.0
    if "financing_ratio_rules_text" in out.columns:
        out.loc[mask,"financing_ratio_rules_text"]="≤ 400.000 TL → %70 | 400.001–800.000 TL → %50 | 800.001–1.200.000 TL → %30 | 1.200.001–2.000.000 TL → %20 | ≥2.000.000 TL → %0"
    if "vehicle_finance_rules_text" in out.columns:
        out.loc[mask,"vehicle_finance_rules_text"]="≤ 400.000 TL: %70 / 48 ay · 400.001–800.000 TL: %50 / 36 ay · 800.001–1.200.000 TL: %30 / 24 ay · 1.200.001–2.000.000 TL: %20 / 12 ay · ≥ 2.000.000 TL: %0 / 0 ay"
    if "maturity_rules_text" in out.columns:
        out.loc[mask,"maturity_rules_text"]="≤ 400.000 TL: 48 ay · 400.001–800.000 TL: 36 ay · 800.001–1.200.000 TL: 24 ay · 1.200.001–2.000.000 TL: 12 ay"
    out.loc[mask,"profit_share_rate_text"]="Fiyatlama resmî finansal hesaplama aracında dinamik"
    out.loc[mask,"source_url"]=DUNYA_VEHICLE_URL

    mask=(bank.eq("Kuveyt Türk") & product.eq("Araç Finansmanı"))
    def kuveyt_rules(rules,row):
        rules=_set_vehicle_rules(rules,blocked_above=2000001.0)
        return _live_first(rules,KUVEYT_VEHICLE_URL)
    update(mask,kuveyt_rules)
    out.loc[mask,"maximum_maturity_months"]=48.0
    out.loc[mask,"profit_share_rate_text"]="Fiyatlama resmî hesaplama aracında dinamik"
    out.loc[mask,"source_url"]=KUVEYT_VEHICLE_URL

    mask=(bank.eq("Kuveyt Türk") & product.eq("Motosiklet Finansmanı"))
    def kuveyt_moto_rules(rules,row):
        rules=_set_vehicle_rules(rules,blocked_above=2000001.0)
        return _live_first(rules,KUVEYT_MOTORCYCLE_URL)
    update(mask,kuveyt_moto_rules)
    out.loc[mask,"maximum_maturity_months"]=48.0
    out.loc[mask,"profit_share_rate_text"]="Fiyatlama resmî hesaplama aracında dinamik"
    out.loc[mask,"source_url"]=KUVEYT_MOTORCYCLE_URL

    mask=(bank.eq("Albaraka Türk") & product.eq("Taşıt Finansmanı"))
    def albaraka_rules(rules,row):
        rules=_set_vehicle_rules(rules,blocked_above=2000000.0,ambiguous_values=[2000000.0])
        rules=_live_first(rules,ALBARAKA_VEHICLE_URL)
        return _set_display_metadata(rules,motorcycle_rule="125cc_and_above_vehicle_finance_below_125_need_finance")
    update(mask,albaraka_rules)
    out.loc[mask,"maximum_maturity_months"]=48.0
    out.loc[mask,"profit_share_rate_text"]="Fiyatlama resmî hesaplama aracında dinamik"
    out.loc[mask,"source_url"]=ALBARAKA_VEHICLE_URL

    mask=(bank.eq("Türkiye Emlak Katılım") & product.eq("Taşıt Finansmanı"))
    def emlak_rules(rules,row):
        # Official page publishes the four bands through 2m and a separate
        # 2.5m+ no-finance line; do not invent the 2.0m–2.5m gap.
        rules=_set_vehicle_rules(rules,blocked_above=2500000.0,unknown_ranges=[(2000000.0,2500000.0)])
        return _live_first(rules,EMLAK_VEHICLE_URL)
    update(mask,emlak_rules)
    out.loc[mask,"maximum_maturity_months"]=48.0
    out.loc[mask,"profit_share_rate_text"]="Güncel kâr payı resmî hesaplama aracında senaryoya göre belirlenir"
    out.loc[mask,"source_url"]=EMLAK_VEHICLE_URL

    mask=(bank.eq("Ziraat Katılım") & product.eq("Taşıt Finansmanı"))
    def ziraat_vehicle_rules(rules,row):
        # BANSA_ZIRAAT_VEHICLE_BANDS_V1: Ziraat Katılım'ın resmî taşıt
        # finansmanı sayfası, diğer katılım bankalarıyla aynı değer bandı
        # yapısını yayımlıyor (nihai fatura/kasko değerine göre azami
        # finansman oranı ve vade). Bu tablo önceden banka sitesinden
        # doğrulanmıştır; olmadığında kullanıcı "araç değeri" verdiğinde
        # BANSA hiçbir sayısal cevap üretemiyordu.
        rules=_set_vehicle_rules(rules)
        return _live_first(rules,ZIRAAT_CALCULATOR_URL)
    update(mask,ziraat_vehicle_rules)
    out.loc[mask,"maximum_maturity_months"]=48.0
    out.loc[mask,"profit_share_rate_text"]="Fiyatlama resmî finansal hesaplama aracında dinamik"

    # ---------------------------------------------------------------
    # Vakıf Katılım pricing guardrail (V16.3).
    #
    # The public Financing Calculation screen includes a "Kâr Oranı Kendin
    # Belirle" control.  Therefore calculator-entered/returned profit-rate
    # values are calculation parameters, not sufficient evidence of the
    # bank's generally published current price.  BANSA may still use verified
    # vehicle-value eligibility rules, but it must not promote calculator-rate
    # values or historical snapshots to a current bank rate.
    # ---------------------------------------------------------------
    mask=(bank.eq("Vakıf Katılım") & product.eq("Taşıt Finansmanı"))
    def vakif_vehicle_rules(rules,row):
        rules=_set_vehicle_rules(rules)
        # Remove extracted/static rate tiers from the jury-facing runtime.
        # They may remain in source provenance, but are not exposed as a
        # generally applicable current profit-share rate.
        rules["pricing_tiers"]=[]
        return _set_display_metadata(
            rules,
            pricing_source_policy="calculator_rate_input_not_bank_pricing",
            calculator_rate_user_controlled=True,
            current_rate_claim_allowed=False,
            historical_snapshot_rankable=False,
            calculator_url="https://www.vakifkatilim.com.tr/tr/yardimci-sayfalar/hesaplama-araclari/finansman-hesaplama",
            pricing_reference_checked_at=CHECKED_AT,
        )
    update(mask,vakif_vehicle_rules)
    out.loc[mask,"maximum_maturity_months"]=48.0
    if "profit_share_rate" in out.columns:
        out.loc[mask,"profit_share_rate"]=pd.NA
    out.loc[mask,"profit_share_rate_text"]=(
        "Sabit/güncel kâr payı oranı doğrulanmış bir banka fiyatlaması olarak kullanılmıyor; "
        "hesaplama aracındaki kâr oranı alanı kullanıcı tarafından belirlenebildiği için BANSA bu değeri bankanın güncel oranı saymaz"
    )
    out.loc[mask,"source_url"]=VAKIF_VEHICLE_URL

    mask=(bank.eq("Vakıf Katılım") & product.eq("Motosiklet Finansmanı"))
    def vakif_moto_rules(rules,row):
        rules=_set_vehicle_rules(rules,blocked_above=2000000.0,ambiguous_values=[2000000.0])
        rules["pricing_tiers"]=[]
        return _set_display_metadata(
            rules,
            pricing_source_policy="calculator_rate_input_not_bank_pricing",
            calculator_rate_user_controlled=True,
            current_rate_claim_allowed=False,
            historical_snapshot_rankable=False,
            calculator_url="https://www.vakifkatilim.com.tr/tr/yardimci-sayfalar/hesaplama-araclari/finansman-hesaplama",
            pricing_reference_checked_at=CHECKED_AT,
        )
    update(mask,vakif_moto_rules)
    out.loc[mask,"maximum_maturity_months"]=48.0
    if "profit_share_rate" in out.columns:
        out.loc[mask,"profit_share_rate"]=pd.NA
    out.loc[mask,"profit_share_rate_text"]=(
        "Sabit/güncel kâr payı oranı doğrulanmış bir banka fiyatlaması olarak kullanılmıyor; "
        "hesaplama aracındaki kâr oranı alanı kullanıcı tarafından belirlenebildiği için BANSA bu değeri bankanın güncel oranı saymaz"
    )
    out.loc[mask,"source_url"]=VAKIF_MOTORCYCLE_URL

    # ---------------------------------------------------------------
    # Türkiye Finans publishes current static official pricing tables.  The
    # rate is current evidence, but historical calculator payment rows are not
    # silently promoted to today's exact payment result.
    # ---------------------------------------------------------------
    tf_mask=bank.eq("Türkiye Finans")
    for idx,row in out[tf_mask].iterrows():
        name=str(row.get("product_name") or "")
        rules=_rules(row.get("finance_rules_json"))
        if "Konut Finansmanı" in name:
            rules["pricing_tiers"]=_housing_tiers()
            rules=_current_static(rules)
            out.at[idx,"finance_rules_json"]=json.dumps(rules,ensure_ascii=False)
            out.at[idx,"profit_share_rate_text"]="Resmî fiyatlama tablosu; vade, konut durumu ve sigorta seçimine göre değişir"
            out.at[idx,"last_checked_at"]=CHECKED_AT
            out.at[idx,"source_url"]=TF_HOUSING_URL
        elif name in {"Taşıt Finansmanı (Taşıt Kredisi)*","Dijital Taşıt Finansmanı"}:
            url=TF_DIGITAL_VEHICLE_URL if name.startswith("Dijital") else TF_VEHICLE_URL
            rules["pricing_tiers"]=_vehicle_tiers(url)
            rules=_current_static(rules)
            out.at[idx,"finance_rules_json"]=json.dumps(rules,ensure_ascii=False)
            out.at[idx,"profit_share_rate_text"]="Resmî fiyatlama tablosu; vade, sigorta ve araç durumuna göre değişir"
            out.at[idx,"last_checked_at"]=CHECKED_AT
            out.at[idx,"source_url"]=url

    return out

def apply_campaign_overrides(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        return frame
    out=frame.copy(deep=True)
    if "source_url" in out.columns and out["source_url"].astype(str).eq(ZIRAAT_TEKNO_URL).any():
        return out
    row={col: None for col in out.columns}
    row.update({
        "id": -20260825,
        "page_id": -20260825,
        "bank_name": "Ziraat Katılım",
        "campaign_name": "Teknosa'da 3 Taksit",
        "campaign_type": "card_campaign",
        "linked_product_type": "Kredi Kartı",
        "target_audience": "Bireysel Bankkart kredi kartı müşterileri",
        "installment_count": 3.0,
        "expense_status": "Peşin fiyatına / vade farksız",
        "campaign_start_date": "2026-08-11",
        "campaign_end_date": "2026-08-31",
        "campaign_conditions": (
            "Ziraat Katılım Bankkart kredi kartı ile Teknosa alışverişlerinde peşin fiyatına 3 taksit sunulur. "
            "İşlemin Bankkart POS'undan yapılması ve ödeme sırasında taksit talebinin belirtilmesi gerekir. "
            "Ücretsiz ve ticari kredi kartları kampanyaya dahil değildir; yasal taksit sınırları geçerlidir."
        ),
        "source_url": ZIRAAT_TEKNO_URL,
        "source_evidence": "Ziraat Katılım resmî kampanya sayfası, 11-31 Ağustos 2026.",
        "is_active": 1.0,
        "extraction_confidence": 1.0,
        "created_at": CHECKED_AT,
    })
    # Build from records instead of concatenating an all-NA scaffold row.
    # This preserves the current dtypes and avoids pandas' deprecated
    # all-NA concat inference path.
    return pd.DataFrame.from_records(
        [row] + out.to_dict(orient="records"),
        columns=out.columns,
    )
