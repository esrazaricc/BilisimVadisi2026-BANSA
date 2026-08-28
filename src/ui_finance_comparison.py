from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.competition_fast_router import (
    _filter_products,
    _best_product_row,
    _structured_fee_value,
    _present,
    normalize,
)
from src.competition_natural_chat import _enrich_row, _source_url
from src.ui_table_density import clean_cell, sanitize_frame, select_dense_columns


_PRODUCT_FAMILY = {
    "Taşıt Finansmanı": "arac_finansmani",
    "Konut Finansmanı": "konut_finansmani",
    "İhtiyaç Finansmanı": "ihtiyac_finansmani",
    "Eğitim Finansmanı": "ihtiyac_finansmani",
    "Alışveriş Finansmanı": "alisveris_finansmani",
    "İş Yeri Finansmanı": "isyeri_finansmani",
    "İşyeri Finansmanı": "isyeri_finansmani",
    "Arsa Finansmanı": "arsa_finansmani",
    "Ticari Finansman": "ticari_finansman",
    "Gayri Nakdi Finansman": "gayri_nakdi_finansman",
    "Tarım Finansmanı": "tarim_finansmani",
    "Leasing / Finansal Kiralama": "leasing",
    "Sürdürülebilir Finansman": "surdurulebilir_finansman",
    "Gayrimenkul Finansmanı": "gayrimenkul_finansmani",
    "Diğer Finansman": "finansman",
}

_ROOT = Path(__file__).resolve().parents[1]
_CONSTRAINTS_PATH = _ROOT / "config" / "calculator_constraints.json"


def _money_short(value: object) -> str:
    try:
        number = float(value)
    except Exception:
        return ""
    return f"{number:,.0f} TL".replace(",", ".")


def _calculator_constraint_summary(bank: str, family: str | None) -> str:
    try:
        payload = json.loads(_CONSTRAINTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ""
    notes: list[str] = []
    for item in payload.get("constraints", []):
        if str(item.get("bank_name") or "") != str(bank):
            continue
        if family and str(item.get("family_key") or "") != family:
            continue
        product = str(item.get("calculator_product") or "Hesaplama aracı")
        max_amount = _money_short(item.get("max_financing_amount"))
        mode = str(item.get("amount_limit_mode") or "")
        min_term = item.get("min_maturity_months")
        max_term = item.get("max_maturity_months")
        observed = item.get("observed_maturity_months")
        parts = [product]
        if max_amount:
            parts.append(f"giriş ≤ {max_amount}")
        if min_term is not None and max_term is not None:
            parts.append(f"vade {int(min_term)}–{int(max_term)} ay")
        elif observed is not None:
            parts.append(f"yalnız {int(observed)} ay gözleminde doğrulandı")
        if item.get("max_vehicle_age") is not None:
            parts.append(f"2.el araç yaşı ≤ {int(item['max_vehicle_age'])}")
        if mode == "term_scoped_observation":
            parts.append("diğer vadelere genellenmez")
        notes.append(" · ".join(parts))
    return " | ".join(notes) if notes else ""


def _clean_markdown(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def _extract_markdown_table(answer: str) -> pd.DataFrame:
    # Streamlit/LLM markdown may contain blank lines between every table row.
    # Collect pipe rows globally instead of requiring strict adjacency.
    pipe_lines = [
        line.strip()
        for line in str(answer or "").splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    if len(pipe_lines) < 3:
        return pd.DataFrame()
    headers = [_clean_markdown(x) for x in pipe_lines[0].strip("|").split("|")]
    rows: list[list[str]] = []
    for line in pipe_lines[1:]:
        raw_cells = [x.strip() for x in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in raw_cells):
            continue
        vals = [_clean_markdown(x) for x in raw_cells]
        if len(vals) == len(headers):
            rows.append(vals)
    return pd.DataFrame(rows, columns=headers) if rows else pd.DataFrame()


def _extract_bullet_table(answer: str) -> pd.DataFrame:
    """Parse the mixed live/projection housing renderer without recalculating.

    This is UI-only parsing of already verified answer text. It never creates a
    financial number and therefore cannot bypass BANSA's finance safety layer.
    """
    lines = [line.strip() for line in str(answer or "").splitlines()]
    bank = None
    rows: list[dict] = []
    bank_heading = re.compile(r"^\*\*([^*]+):\*\*$")
    numeric = re.compile(
        r"^-\s*(.+?):\s*kâr payı\s*\*\*(%[^*]+)\*\*,\s*aylık\s*\*\*([^*]+)\*\*,\s*"
        r"(?:toplam geri ödeme|taksit toplamı)\s*\*\*([^*]+)\*\*\s*(.*)$",
        re.I,
    )
    for line in lines:
        mh = bank_heading.match(line)
        if mh:
            bank = _clean_markdown(mh.group(1))
            continue
        m = numeric.match(line)
        if not m or not bank:
            continue
        tail = _clean_markdown(m.group(5))
        source_type = "Canlı / birebir hesaplama" if "canlı" in tail or "birebir" in tail else "Resmî fiyatlama tablosu"
        row = {
            "Banka": bank,
            "Koşul": _clean_markdown(m.group(1)),
            "Kâr Payı": _clean_markdown(m.group(2)),
            "Aylık Taksit": _clean_markdown(m.group(3)),
            "Toplam Geri Ödeme": _clean_markdown(m.group(4)),
            "Kaynak Türü": source_type,
        }
        for segment in [part.strip(" .") for part in tail.split(" · ") if part.strip()]:
            sn = normalize(segment)
            if sn.startswith("tahsis "):
                row["Tahsis Ücreti"] = segment[len("tahsis "):].strip()
            elif sn.startswith("ekspertiz "):
                row["Ekspertiz"] = segment[len("ekspertiz "):].strip()
            elif sn.startswith("ipotek "):
                row["İpotek / Rehin"] = segment[len("ipotek "):].strip()
            elif sn.startswith("ucretler toplami "):
                row["Toplam Masraf"] = segment[len("ücretler toplamı "):].strip()
        rows.append(row)
    return pd.DataFrame(rows)


def _catalog_rows(product_label: str, selected_banks: Iterable[str], amount: float) -> dict[str, dict]:
    family = _PRODUCT_FAMILY.get(product_label)
    banks = tuple(selected_banks or ())
    query = (" ".join(banks) + " " + product_label).strip()
    try:
        work = _filter_products(query, banks, family)
    except Exception:
        return {}
    if work is None or work.empty:
        return {}

    output: dict[str, dict] = {}
    for bank, group in work.groupby("bank_name", sort=False):
        try:
            row = _enrich_row(_best_product_row(group, query, family))
        except Exception:
            row = group.iloc[0]

        max_m = row.get("maximum_maturity_months")
        ratio = row.get("maximum_financing_ratio")
        if str(bank) == "Dünya Katılım":
            # V21 correction: the official source shown by the user publishes
            # maturity bands only, not a percentage financing ratio.
            ratio = None

        allocation, _ = _structured_fee_value(row, "allocation_fee", requested_amount=float(amount))
        appraisal, _ = _structured_fee_value(row, "appraisal_fee", requested_amount=float(amount))
        mortgage, _ = _structured_fee_value(row, "mortgage_fee", requested_amount=float(amount))

        pricing = ""
        if _present(row.get("profit_share_rate")):
            pricing = "%" + str(row.get("profit_share_rate")).replace(".", ",")
        else:
            pricing = str(row.get("profit_share_rate_text") or "").strip()

        maturity_rules = str(row.get("maturity_rules_text") or "").strip()
        ratio_rules = str(row.get("financing_ratio_rules_text") or "").strip()
        if str(bank) == "Dünya Katılım":
            ratio_rules = ""

        min_amount = row.get("minimum_financing_amount")
        max_amount = row.get("maximum_financing_amount")
        if _present(min_amount) and _present(max_amount):
            amount_limit = f"{_money_short(min_amount)}–{_money_short(max_amount)}"
        elif _present(max_amount):
            amount_limit = f"≤ {_money_short(max_amount)}"
        elif _present(min_amount):
            amount_limit = f"≥ {_money_short(min_amount)}"
        else:
            amount_limit = ""

        special = str(row.get("vehicle_age_rules_text") or "").strip()
        if not special and _present(row.get("housing_first_home_rules_text")):
            special = "Konut değeri / enerji sınıfına göre finansman oranları değişebilir"

        output[str(bank)] = {
            "Ürün": str(row.get("product_name") or product_label),
            "Vade / Vade Bantları": maturity_rules or (f"{int(float(max_m))} aya kadar" if _present(max_m) else ""),
            "Finansman Oranı / Kuralı": ratio_rules or (f"Azami %{float(ratio):g}" if _present(ratio) else ""),
            "Finansman Tutar Limiti": amount_limit,
            "Hesaplama Aracı Sınırı": _calculator_constraint_summary(str(bank), family),
            "Özel Koşul": clean_cell(special),
            "Tahsis Ücreti": clean_cell(allocation),
            "Ekspertiz": clean_cell(appraisal),
            "İpotek / Rehin": clean_cell(mortgage),
            "Fiyatlama Bilgisi": clean_cell(pricing),
            "Resmî Kaynak": _source_url(row),
        }
    return output


def build_finance_comparison_table(
    answer: str,
    *,
    product_label: str,
    amount: float,
    selected_banks: Iterable[str] = (),
) -> pd.DataFrame:
    """Build a dense decision table from BANSA's already verified answer.

    Numeric scenario values are parsed only from the final verified BANSA
    response. Catalog fields merely supplement non-numeric product metadata.
    No rate/payment calculation happens in this presentation module.
    """
    numeric = _extract_markdown_table(answer)
    if numeric.empty:
        numeric = _extract_bullet_table(answer)

    catalog = _catalog_rows(product_label, selected_banks, amount)

    if numeric.empty:
        rows = []
        for bank, meta in catalog.items():
            rows.append({
                "Banka": bank,
                "Ürün": meta["Ürün"],
                "Koşul": "",
                "Kâr Payı": meta["Fiyatlama Bilgisi"],
                "Aylık Taksit": "",
                "Toplam Geri Ödeme": "",
                "Durum": "Güncel sayısal sonuç yok",
                "Vade / Vade Bantları": meta["Vade / Vade Bantları"],
                "Finansman Oranı / Kuralı": meta["Finansman Oranı / Kuralı"],
                "Finansman Tutar Limiti": meta["Finansman Tutar Limiti"],
                "Hesaplama Aracı Sınırı": meta["Hesaplama Aracı Sınırı"],
                "Özel Koşul": meta["Özel Koşul"],
                "Tahsis Ücreti": meta["Tahsis Ücreti"],
                "Ekspertiz": meta["Ekspertiz"],
                "İpotek / Rehin": meta["İpotek / Rehin"],
                "Toplam Masraf": "",
                "Kaynak Türü": "Ürün kaydı",
                "Resmî Kaynak": meta["Resmî Kaynak"],
            })
        return sanitize_frame(pd.DataFrame(rows))

    # Normalize current renderer column names.
    rename = {
        "Masraf notu": "Masraf Notu",
        "Doğrulanmış masraf": "Masraf Notu",
    }
    numeric = numeric.rename(columns=rename).copy()
    if "Banka" not in numeric.columns:
        return numeric

    dense_rows: list[dict] = []
    seen_banks: set[str] = set()
    for _, row in numeric.iterrows():
        bank = str(row.get("Banka") or "").strip()
        if not bank:
            continue
        seen_banks.add(bank)
        meta = catalog.get(bank, {})
        dense = {
            "Banka": bank,
            "Ürün": meta.get("Ürün", product_label),
            "Koşul": str(row.get("Koşul") or "Standart"),
            "Kâr Payı": clean_cell(row.get("Kâr payı") or row.get("Kâr Payı") or meta.get("Fiyatlama Bilgisi", "")),
            "Aylık Taksit": clean_cell(row.get("Aylık taksit") or row.get("Aylık Taksit") or ""),
            "Toplam Geri Ödeme": clean_cell(row.get("Toplam geri ödeme") or row.get("Toplam Geri Ödeme") or ""),
            "Durum": "Doğrulandı",
            "Vade / Vade Bantları": meta.get("Vade / Vade Bantları", ""),
            "Finansman Oranı / Kuralı": meta.get("Finansman Oranı / Kuralı", ""),
            "Finansman Tutar Limiti": meta.get("Finansman Tutar Limiti", ""),
            "Hesaplama Aracı Sınırı": meta.get("Hesaplama Aracı Sınırı", ""),
            "Özel Koşul": meta.get("Özel Koşul", ""),
            "Tahsis Ücreti": clean_cell(row.get("Tahsis Ücreti") or meta.get("Tahsis Ücreti", "")),
            "Ekspertiz": clean_cell(row.get("Ekspertiz") or meta.get("Ekspertiz", "")),
            "İpotek / Rehin": clean_cell(row.get("İpotek / Rehin") or meta.get("İpotek / Rehin", "")),
            "Toplam Masraf": clean_cell(row.get("Toplam Masraf") or row.get("Masraf Notu") or ""),
            "Kaynak Türü": clean_cell(row.get("Kaynak Türü") or "Güncel doğrulanmış senaryo"),
            "Resmî Kaynak": meta.get("Resmî Kaynak", ""),
        }
        dense_rows.append(dense)

    # Add product rows for selected/all scoped banks that had no current
    # numeric scenario, so the comparison remains information-dense without
    # inventing payments.
    for bank, meta in catalog.items():
        if bank in seen_banks:
            continue
        dense_rows.append({
            "Banka": bank,
            "Ürün": meta["Ürün"],
            "Koşul": "",
            "Kâr Payı": meta["Fiyatlama Bilgisi"],
            "Aylık Taksit": "",
            "Toplam Geri Ödeme": "",
            "Durum": "Güncel sayısal sonuç yok",
            "Vade / Vade Bantları": meta["Vade / Vade Bantları"],
            "Finansman Oranı / Kuralı": meta["Finansman Oranı / Kuralı"],
            "Finansman Tutar Limiti": meta["Finansman Tutar Limiti"],
            "Hesaplama Aracı Sınırı": meta["Hesaplama Aracı Sınırı"],
            "Özel Koşul": meta["Özel Koşul"],
            "Tahsis Ücreti": meta["Tahsis Ücreti"],
            "Ekspertiz": meta["Ekspertiz"],
            "İpotek / Rehin": meta["İpotek / Rehin"],
            "Toplam Masraf": "",
            "Kaynak Türü": "Ürün kaydı",
            "Resmî Kaynak": meta["Resmî Kaynak"],
        })

    columns = [
        "Banka", "Ürün", "Koşul", "Kâr Payı", "Aylık Taksit",
        "Toplam Geri Ödeme", "Durum", "Vade / Vade Bantları", "Finansman Oranı / Kuralı",
        "Finansman Tutar Limiti", "Hesaplama Aracı Sınırı", "Özel Koşul",
        "Tahsis Ücreti", "Ekspertiz", "İpotek / Rehin", "Toplam Masraf",
        "Kaynak Türü", "Resmî Kaynak",
    ]
    return sanitize_frame(pd.DataFrame(dense_rows, columns=columns))
