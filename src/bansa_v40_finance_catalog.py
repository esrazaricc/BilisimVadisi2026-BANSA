"""BANSA V43 managed finance calculation catalog.

This module is a deterministic, jury-facing finance rate calibration layer. It
is not a crawler and it does not call bank websites at runtime.  It stores the
user-approved official source links and screenshot/snapshot rates that BANSA
uses for internal calculations.

V43 change
----------
Earlier V40/V41 catalog entries sometimes treated calculator-screen / scenario
rates as if they were fixed public rates.  V43 separates that explicitly: the
main usable rates below are labelled as official calculator snapshots, and the
same data is used by the dashboard and chatbot.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
import unicodedata

import pandas as pd

CHECKED_AT = "2026-08-28T01:05:00+03:00"

FAMILY_HOUSING = "konut_finansmani"
FAMILY_VEHICLE = "arac_finansmani"
FAMILY_NEED = "ihtiyac_finansmani"
TARGET_FAMILIES = {FAMILY_HOUSING, FAMILY_VEHICLE, FAMILY_NEED}

# User-approved official source URLs. These are provenance links only; the UI
# must not use them as the primary action instead of calculating inside BANSA.
ALBARAKA_HOUSING_URL = "https://www.albaraka.com.tr/tr/hesaplama-araclari/finansman-hesaplama/konut-finansmani-hesaplama"
KUVEYT_HOUSING_URL = "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/surdurulebilir-finansmanlar/yesil-konut-finansmani"
DUNYA_HOUSING_URL = "https://dunyakatilim.com.tr/kendim-icin/finansmanlar/konut-finansmanlari/konut-finansmani"
TF_HOUSING_URL = "https://www.turkiyefinans.com.tr/tr-tr/bireysel/konut-finansmani/Sayfalar/konut-finansmani.aspx"
VAKIF_CALCULATOR_URL = "https://www.vakifkatilim.com.tr/tr/yardimci-sayfalar/hesaplama-araclari/finansman-hesaplama"

ALBARAKA_VEHICLE_URL = "https://basvur.albaraka.com.tr/jet-finansman?Fin=3&Sub=139"
KUVEYT_VEHICLE_URL = "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/surdurulebilir-finansmanlar/surdurulebilir-arac-finansmani"
DUNYA_VEHICLE_URL = "https://dunyakatilim.com.tr/kendim-icin/finansmanlar/arac-finansmanlari/arac-finansmani"
TF_DIGITAL_VEHICLE_URL = "https://www.turkiyefinans.com.tr/tr-tr/bireysel/tasit-finansmani/sayfalar/dijital-tasit-finansmani.aspx"
TF_COMMERCIAL_VEHICLE_URL = "https://www.turkiyefinans.com.tr/tr-tr/bireysel/tasit-finansmani/Sayfalar/taksitli-ticari-tasit-finansmani.aspx"

ALBARAKA_NEED_URL = "https://www.albaraka.com.tr/tr/hesaplama-araclari/finansman-hesaplama/ihtiyac-finansmani-hesaplama"
DUNYA_NEED_URL = "https://dunyakatilim.com.tr/kendim-icin/finansmanlar/ihtiyac-finansmani"
TF_NEED_URL = "https://www.turkiyefinans.com.tr/tr-tr/bireysel/ihtiyac-finansmani/Sayfalar/dijital-ihtiyac-finansmani.aspx"
KUVEYT_NEED_URLS = {
    "Bisiklet Finansmanı": "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/ihtiyac-finansmanlari/bisiklet-finansmani",
    "Elektrikli Araç Şarj Ünitesi Finansmanı": "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/ihtiyac-finansmanlari/elektrikli-arac-sarj-unitesi-finansmani",
    "Eğitim Finansmanı": "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/ihtiyac-finansmanlari/egitim-finansmani",
    "Hac-Umre Finansmanı": "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/ihtiyac-finansmanlari/hac-umre-finansmani",
    "Kira Finansmanı": "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/ihtiyac-finansmanlari/kira-finansmani",
    "Seyahat Finansmanı": "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/ihtiyac-finansmanlari/seyahat-finansmani",
    "Tekne Tüketici Finansmanı": "https://www.kuveytturk.com.tr/kendim-icin/finansmanlar/ihtiyac-finansmanlari/tekne-tuketici-finansmani",
}

CALCULATED_BANKS = {
    FAMILY_HOUSING: {"Albaraka Türk", "Kuveyt Türk", "Dünya Katılım", "Türkiye Finans", "Vakıf Katılım"},
    FAMILY_VEHICLE: {"Albaraka Türk", "Kuveyt Türk", "Dünya Katılım", "Türkiye Finans", "Vakıf Katılım"},
    FAMILY_NEED: {"Albaraka Türk", "Kuveyt Türk", "Dünya Katılım", "Türkiye Finans", "Vakıf Katılım"},
}

PERSONAL_OFFER_BANKS = {
    FAMILY_HOUSING: {"Türkiye Emlak Katılım", "Ziraat Katılım"},
    FAMILY_VEHICLE: {"Türkiye Emlak Katılım", "Ziraat Katılım"},
    FAMILY_NEED: {"Türkiye Emlak Katılım", "Ziraat Katılım", "Adil Katılım", "Hayat Finans"},
}

# Canonical rows shown in the scenario calculator so the page does not spam
# several near-duplicate products for the same bank. project_row remains able
# to calculate aliases where safe.
CANONICAL_PRODUCT_IDS = {
    FAMILY_HOUSING: {3, 33, 67, 97, 242, 296, 377},
    FAMILY_VEHICLE: {1, 23, 61, 87, 230, 286, 347},
    FAMILY_NEED: {4, 46, 47, 48, 49, 51, 52, 53, 70, 121, 226, 273, 318, 341},
}

# V43 user-approved official calculator snapshots.  The snapshot fields are
# used as regression fixtures as well as UI provenance.  The rate is applied as
# the canonical internal BANSA rate for the bank/family unless a future user
# calibration overrides it.
CALIBRATED_SNAPSHOTS: dict[tuple[str, str], dict[str, Any]] = {
    (FAMILY_HOUSING, "Albaraka Türk"): {
        "variant": "Konut Finansmanı",
        "rate": "3.04",
        "max_maturity": 120,
        "source_url": ALBARAKA_HOUSING_URL,
        "base_amount": "500000",
        "base_maturity": 20,
        "base_monthly_installment": "33765.42",
        "base_total_payment": "675308.89",
        "fees_total": "29826.27",
        "annual_cost_rate": "54.95",
        "note": "Albaraka resmî konut finansmanı hesaplama ekranı snapshotı; nihai oran, ücretler ve onay banka değerlendirmesine göre değişebilir.",
    },
    (FAMILY_HOUSING, "Kuveyt Türk"): {
        "variant": "Konut Finansmanı",
        "rate": "2.9900",
        "max_maturity": 120,
        "source_url": KUVEYT_HOUSING_URL,
        "base_amount": "500000",
        "base_maturity": 120,
        "base_monthly_installment": "15398.82",
        "base_total_payment": "1847868.29",
        "note": "Kuveyt Türk resmî konut hesaplama ekranı snapshotı; ekspertiz, ipotek, sigorta ve nihai koşullar değişebilir.",
    },
    (FAMILY_HOUSING, "Türkiye Finans"): {
        "variant": "Konut Finansmanı",
        "rate": "2.88",
        "max_maturity": 120,
        "source_url": TF_HOUSING_URL,
        "base_amount": "500000",
        "base_maturity": 120,
        "base_monthly_installment": "14893.49",
        "base_total_payment": "1787218.80",
        "note": "Türkiye Finans resmî konut hesaplama ekranı snapshotı; varyant ayrımı kullanıcıya gösterilmeden canonical konut oranı olarak uygulanır.",
    },
    (FAMILY_HOUSING, "Vakıf Katılım"): {
        "variant": "Konut Finansmanı",
        "rate": "2.99",
        "max_maturity": 120,
        "source_url": VAKIF_CALCULATOR_URL,
        "base_amount": "100000",
        "base_maturity": 60,
        "base_monthly_installment": "3605.56",
        "base_total_payment": "216333.48",
        "appraisal_fee": "25000.00",
        "mortgage_fee": "1000.00",
        "note": "Vakıf Katılım sıfır konut finansmanı hesaplama ekranı snapshotı; ekspertiz, ipotek ve nihai koşullar değişebilir.",
    },
    (FAMILY_VEHICLE, "Albaraka Türk"): {
        "variant": "Taşıt Finansmanı",
        "rate": "3.55",
        "max_maturity": 48,
        "source_url": ALBARAKA_VEHICLE_URL,
        "base_amount": "267500",
        "base_maturity": 12,
        "base_monthly_installment": "29572.47",
        "base_total_payment": "356407.19",
        "installments_total": "354869.06",
        "fees_total": "1538.13",
        "annual_cost_rate": "73.97",
        "note": "Albaraka sıfır taşıt finansmanı hesaplama ekranı snapshotı; araç satış değeri, masraflar ve nihai onay değişebilir.",
    },
    (FAMILY_VEHICLE, "Kuveyt Türk"): {
        "variant": "Taşıt Finansmanı",
        "rate": "3.3900",
        "max_maturity": 48,
        "source_url": KUVEYT_VEHICLE_URL,
        "base_amount": "500000",
        "base_maturity": 48,
        "base_monthly_installment": "25216.76",
        "base_total_payment": "1210404.67",
        "note": "Kuveyt Türk yeni binek araç finansmanı hesaplama ekranı snapshotı; araç türü/değeri ve banka koşulları değişebilir.",
    },
    (FAMILY_VEHICLE, "Türkiye Finans"): {
        "variant": "Taşıt Finansmanı",
        "rate": "3.42",
        "max_maturity": 48,
        "source_url": TF_DIGITAL_VEHICLE_URL,
        "base_amount": "100000",
        "base_maturity": 48,
        "base_monthly_installment": "5074.96",
        "base_total_payment": "243598.08",
        "note": "Türkiye Finans sigortalı taşıt finansmanı 0 km hesaplama ekranı snapshotı; sigorta/kasko ve nihai koşullar değişebilir.",
    },
    (FAMILY_VEHICLE, "Vakıf Katılım"): {
        "variant": "Taşıt Finansmanı",
        "rate": "3.29",
        "max_maturity": 48,
        "source_url": VAKIF_CALCULATOR_URL,
        "base_amount": "100000",
        "base_maturity": 24,
        "base_monthly_installment": "6746.01",
        "base_total_payment": "161904.12",
        "note": "Vakıf Katılım taşıt finansmanı 0 km hesaplama ekranı snapshotı; araç değeri, sigorta/kasko ve banka koşulları değişebilir.",
    },
    (FAMILY_NEED, "Albaraka Türk"): {
        "variant": "İhtiyaç Finansmanı",
        "rate": "4.00",
        "max_maturity": 36,
        "source_url": ALBARAKA_NEED_URL,
        "base_amount": "150000",
        "base_maturity": 23,
        "base_monthly_installment": "11349.76",
        "base_total_payment": "261044.84",
        "fees_total": "862.50",
        "annual_cost_rate": "85.11",
        "note": "Albaraka ihtiyaç finansmanı hesaplama ekranı snapshotı; fatura/proforma, belge ve nihai onay koşulları değişebilir.",
    },
    (FAMILY_NEED, "Türkiye Finans"): {
        "variant": "İhtiyaç Finansmanı",
        "rate": "3.80",
        "max_maturity": 36,
        "source_url": TF_NEED_URL,
        "base_amount": "100000",
        "base_maturity": 36,
        "base_monthly_installment": "5996.94",
        "base_total_payment": "215889.84",
        "note": "Türkiye Finans ihtiyaç finansmanı hesaplama ekranı snapshotı; tahsis, sigorta ve nihai banka koşulları değişebilir.",
    },
    (FAMILY_NEED, "Kuveyt Türk"): {
        "variant": "İhtiyaç Finansmanı",
        "rate": "4.0100",
        "max_maturity": 36,
        "source_url": "",
        "base_amount": "500000",
        "base_maturity": 12,
        "base_monthly_installment": "57092.42",
        "base_total_payment": "685108.95",
        "note": "Kuveyt Türk ihtiyaç finansmanı hesaplama ekranı snapshotı; ödenecek toplam tutar finansman tahsis ücretini içermeyebilir.",
    },
    (FAMILY_NEED, "Vakıf Katılım"): {
        "variant": "İhtiyaç Finansmanı",
        "rate": "3.99",
        "max_maturity": 36,
        "source_url": VAKIF_CALCULATOR_URL,
        "base_amount": "100000",
        "base_maturity": 18,
        "base_monthly_installment": "8680.05",
        "base_total_payment": "156240.94",
        "note": "Vakıf Katılım ihtiyaç finansmanı hesaplama ekranı snapshotı; tahsis, sigorta ve banka koşulları değişebilir.",
    },
}

# Dünya Katılım için kullanıcı henüz ekran-snapshot göndermediği için V42 kaynak
# modeli korunur; UI/chatbot bunu resmî hesaplama ekranı referansı olarak açıklar.
REFERENCE_RATES = {
    (FAMILY_HOUSING, "Dünya Katılım"): [("Konut Finansmanı", "3.99", 120, DUNYA_HOUSING_URL)],
    (FAMILY_VEHICLE, "Dünya Katılım"): [("Araç Finansmanı", "3.99", 48, DUNYA_VEHICLE_URL)],
    (FAMILY_NEED, "Dünya Katılım"): [("İhtiyaç Finansmanı", "3.99", 36, DUNYA_NEED_URL)],
}

ALBARAKA_NEED_NAMES = {
    "jet finansman",
    "ihtiyac finansmani",
    "egitim finansmani",
    "hac ve umre finansmani",
    "subesiz umre finansmani",
    "motosiklet",
    "atv",
    "bisiklet",
}

SOURCE_BY_BANK_FAMILY = {
    (FAMILY_HOUSING, "Albaraka Türk"): ALBARAKA_HOUSING_URL,
    (FAMILY_HOUSING, "Kuveyt Türk"): KUVEYT_HOUSING_URL,
    (FAMILY_HOUSING, "Dünya Katılım"): DUNYA_HOUSING_URL,
    (FAMILY_HOUSING, "Türkiye Finans"): TF_HOUSING_URL,
    (FAMILY_HOUSING, "Vakıf Katılım"): VAKIF_CALCULATOR_URL,
    (FAMILY_VEHICLE, "Albaraka Türk"): ALBARAKA_VEHICLE_URL,
    (FAMILY_VEHICLE, "Kuveyt Türk"): KUVEYT_VEHICLE_URL,
    (FAMILY_VEHICLE, "Dünya Katılım"): DUNYA_VEHICLE_URL,
    (FAMILY_VEHICLE, "Türkiye Finans"): TF_DIGITAL_VEHICLE_URL,
    (FAMILY_VEHICLE, "Vakıf Katılım"): VAKIF_CALCULATOR_URL,
    (FAMILY_NEED, "Albaraka Türk"): ALBARAKA_NEED_URL,
    (FAMILY_NEED, "Dünya Katılım"): DUNYA_NEED_URL,
    (FAMILY_NEED, "Türkiye Finans"): TF_NEED_URL,
    (FAMILY_NEED, "Vakıf Katılım"): VAKIF_CALCULATOR_URL,
}


def _norm(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    tr = str.maketrans({"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"})
    return text.translate(tr)


def _d(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except Exception:
        pass
    try:
        return Decimal(str(value).replace(",", "."))
    except Exception:
        return None


def canonical_source_url(row: Any) -> str:
    getter = getattr(row, "get", lambda k, d=None: d)
    family = _norm(getter("product_family_key", ""))
    bank = str(getter("bank_name", "") or "")
    product = str(getter("product_name", "") or "")
    if family == FAMILY_NEED and bank == "Kuveyt Türk":
        return KUVEYT_NEED_URLS.get(product, KUVEYT_NEED_URLS.get("Elektrikli Araç Şarj Ünitesi Finansmanı", ""))
    return SOURCE_BY_BANK_FAMILY.get((family, bank), str(getter("source_url", "") or ""))


def is_personal_offer(row: Any) -> bool:
    family = _norm(row.get("product_family_key"))
    bank = str(row.get("bank_name") or "")
    return family in TARGET_FAMILIES and bank in PERSONAL_OFFER_BANKS.get(family, set())


def is_calculated_bank(row: Any) -> bool:
    family = _norm(row.get("product_family_key"))
    bank = str(row.get("bank_name") or "")
    return family in TARGET_FAMILIES and bank in CALCULATED_BANKS.get(family, set())


def _snapshot_option(snapshot: dict[str, Any], *, source_url: str | None = None, variant: str | None = None) -> dict[str, Any]:
    out = dict(snapshot)
    out.update({
        "variant": variant or snapshot.get("variant") or "Standart",
        "rate": Decimal(str(snapshot["rate"])),
        "mode": "official_calculator_snapshot_model",
        "source_kind": "official_calculator_snapshot",
        "source_url": source_url or snapshot.get("source_url") or "",
        "checked_at": CHECKED_AT,
        "allocation_fee_rate": Decimal("0.50"),
    })
    return out


def managed_rate_options(row: Any, amount: Decimal, maturity: int) -> list[dict[str, Any]]:
    """Return approved BANSA internal calculation options for a product row."""
    family = _norm(row.get("product_family_key"))
    bank = str(row.get("bank_name") or "")
    product = str(row.get("product_name") or "")
    pnorm = _norm(product)

    if family not in TARGET_FAMILIES or not is_calculated_bank(row) or is_personal_offer(row):
        return []

    # Kuveyt Türk needs are alt-product based but use the same user-approved
    # V43 need snapshot rate unless a later calibration overrides a subproduct.
    if family == FAMILY_NEED and bank == "Kuveyt Türk":
        if product not in KUVEYT_NEED_URLS or int(maturity) > 36:
            return []
        snap = CALIBRATED_SNAPSHOTS[(FAMILY_NEED, "Kuveyt Türk")]
        return [_snapshot_option(snap, source_url=KUVEYT_NEED_URLS[product], variant=product)]

    # Albaraka need: keep fatura/proforma based products, including the user-
    # supplied motorcycle/ATV/bicycle example; do not force unrelated Albaraka
    # products into generic needs.
    if family == FAMILY_NEED and bank == "Albaraka Türk":
        if not any(name in pnorm for name in ALBARAKA_NEED_NAMES):
            return []
        if amount > Decimal("500000"):
            return []
        if int(maturity) > 36:
            return []
        return [_snapshot_option(CALIBRATED_SNAPSHOTS[(family, bank)])]

    # Türkiye Finans commercial vehicle link remains available as provenance, but
    # the user-approved V43 instruction is to keep one simple vehicle snapshot in
    # the dashboard/chatbot rather than exposing variant complexity.

    snap = CALIBRATED_SNAPSHOTS.get((family, bank))
    if snap is not None:
        max_maturity = int(snap.get("max_maturity") or 0)
        if max_maturity and int(maturity) > max_maturity:
            return []
        return [_snapshot_option(snap)]

    # Dünya Katılım: keep V42 source model until a screenshot/snapshot is sent.
    # It still calculates but is not labelled as a calibrated snapshot.
    out: list[dict[str, Any]] = []
    for variant, rate_text, max_maturity, url in REFERENCE_RATES.get((family, bank), []):
        if int(maturity) > int(max_maturity):
            continue
        if family == FAMILY_NEED:
            max_need = _need_max_maturity(amount)
            if max_need is None or int(maturity) > max_need:
                continue
        out.append({
            "variant": variant,
            "rate": Decimal(str(rate_text)),
            "mode": "official_calculator_reference_model",
            "source_kind": "official_calculator_reference",
            "source_url": url,
            "checked_at": CHECKED_AT,
            "note": "Resmî sayfada hesaplama aracı bulunur; Dünya Katılım için kullanıcı tarafından ayrı ekran snapshotı gönderilmediğinden V42 kaynak modeli korunmuştur.",
            "allocation_fee_rate": Decimal("0.50"),
        })
    return out


def _need_max_maturity(amount: Decimal) -> int | None:
    if amount <= Decimal("125000"):
        return 36
    if amount <= Decimal("250000"):
        return 24
    if amount <= Decimal("500000"):
        return 12
    return None


def apply_source_overrides(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply V43 source/status labels to a products frame without touching DB files."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    out = frame.copy(deep=True)
    if "source_url" not in out.columns:
        return out
    for idx, row in out.iterrows():
        family = _norm(row.get("product_family_key"))
        if family not in TARGET_FAMILIES:
            continue
        bank = str(row.get("bank_name") or "")
        if is_calculated_bank(row):
            url = canonical_source_url(row)
            if url:
                out.at[idx, "source_url"] = url
            if "profit_share_rate_text" in out.columns:
                snap = CALIBRATED_SNAPSHOTS.get((family, bank))
                if snap:
                    out.at[idx, "profit_share_rate_text"] = f"%{str(snap['rate']).replace('.', ',')} · resmî hesaplama ekranı snapshotı"
                else:
                    out.at[idx, "profit_share_rate_text"] = "BANSA iç hesaplamada kullanılan kaynak modeline göre"
        elif bank in PERSONAL_OFFER_BANKS.get(family, set()):
            if "profit_share_rate_text" in out.columns:
                out.at[idx, "profit_share_rate_text"] = "Kişiye özel teklif; güncel koşullar banka değerlendirmesine göre değişebilir"
    return out


def canonical_scenario_products(frame: pd.DataFrame, family_key: str) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    family_key = _norm(family_key)
    ids = CANONICAL_PRODUCT_IDS.get(family_key)
    if not ids or "id" not in frame.columns:
        return frame
    numeric_ids = pd.to_numeric(frame["id"], errors="coerce")
    preferred = frame[numeric_ids.isin(ids)].copy()
    return preferred if not preferred.empty else frame
