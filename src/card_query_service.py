"""User-facing deterministic card lookup for BANSA.

Card questions are answered from the curated verified card snapshot, never by
searching campaign text.  This prevents product questions such as
"DKart Debit kart ücreti ne kadar?" from being hijacked by a campaign that
happens to mention the same card name.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
import re

import pandas as pd

from src.competition_fast_router import FastRouteAnswer, normalize

ROOT = Path(__file__).resolve().parents[1]
CARD_CSV = ROOT / "data" / "curated_dashboard" / "cards_dashboard_static.csv"

_CARD_ATTRIBUTE_MARKERS = (
    "ucret", "aidat", "yillik", "temassiz", "nfc", "qr", "taksit",
    "puan", "odul", "mil", "nakit iade", "internet", "yurt disi",
    "yurtdisi", "nakit avans", "basvuru", "ozellik", "avantaj",
    "sanal kart", "ek kart",
)
_CARD_PRODUCT_MARKERS = ("kart", "debit", "credit", "platinum", "world", "paraf", "dkart")


def _is_missing(value: object) -> bool:
    text = normalize(str(value or ""))
    return (
        not text
        or text in {"-", "nan", "none", "null", "belirtilmedi"}
        or "bilgi yok" in text
        or "resmi kaynakta yayimlanmamis" in text
        or "dogrulanamadi" in text
    )


def is_card_product_query(query: str) -> bool:
    q = normalize(query)
    # Explicit campaign wording belongs to the campaign engine.
    if "kampanya" in q or "kampany" in q:
        return False
    has_product = any(marker in q for marker in _CARD_PRODUCT_MARKERS)
    has_attribute = any(marker in q for marker in _CARD_ATTRIBUTE_MARKERS)
    return bool(has_product and has_attribute)


@lru_cache(maxsize=1)
def _cards() -> pd.DataFrame:
    try:
        frame = pd.read_csv(CARD_CSV, dtype=str, keep_default_na=False)
    except Exception:
        return pd.DataFrame()
    return frame


def _candidate_score(query: str, row: pd.Series) -> float:
    q = normalize(query)
    name = normalize(row.get("Kart Adı"))
    bank = normalize(row.get("Banka"))
    if not name:
        return -1.0
    name_tokens = [t for t in name.split() if len(t) >= 3 and t not in {"kredi", "karti", "kart"}]
    hits = sum(1 for token in name_tokens if token in q)
    phrase_bonus = 5.0 if name in q else 0.0
    bank_bonus = 1.0 if bank and bank in q else 0.0
    sim = SequenceMatcher(None, q, name).ratio()
    return phrase_bonus + hits * 1.5 + bank_bonus + sim


def _best_card(query: str) -> pd.Series | None:
    frame = _cards()
    if frame.empty:
        return None
    scored = [(_candidate_score(query, row), idx) for idx, row in frame.iterrows()]
    scored.sort(reverse=True)
    if not scored or scored[0][0] < 1.3:
        return None
    return frame.loc[scored[0][1]]


def _clean_value(value: object, *, fallback: str = "Resmî ürün sayfasında sayısal bilgi yayımlanmamış.") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if _is_missing(text):
        return fallback
    return text


def answer_card_query(query: str) -> FastRouteAnswer | None:
    if not is_card_product_query(query):
        return None
    row = _best_card(query)
    if row is None:
        return FastRouteAnswer(
            text=(
                "Kart adını doğrulanmış kart kataloğunda net eşleştiremedim. "
                "Banka ve kart adını birlikte yazarsanız kart ürününü doğrudan kontrol edebilirim."
            ),
            route="card_product_clarification",
            answer_mode="card",
            reasons=("card_intent", "card_identity_not_resolved"),
        )

    q = normalize(query)
    bank = str(row.get("Banka") or "").strip()
    card = str(row.get("Kart Adı") or "Kart").strip()
    source = str(row.get("Resmî Kaynak") or "").strip()
    lines = [f"### {bank} · {card}"]

    if any(x in q for x in ("ucret", "aidat", "yillik")):
        value = _clean_value(row.get("Yıllık Kart Ücreti"))
        if "0 tl" in normalize(value) or "ucret yok" in normalize(value) or "ucretsiz" in normalize(value):
            lines.append(f"**Kart ücreti: {value}.**")
        else:
            lines.append(f"**Yıllık kart ücreti:** {value}")
    elif "temassiz" in q:
        value = _clean_value(row.get("Temassız"), fallback="Temassız özelliği resmî ürün kaynağında doğrulanamadı.")
        if normalize(value).startswith("var") or normalize(value) in {"evet", "mevcut"}:
            detail = value
            # Avoid user-facing repetition such as "var. Var – 2.500 TL...".
            detail = re.sub(r"^\s*Var\s*[–—-]?\s*", "", detail, flags=re.I).strip()
            if detail:
                lines.append(f"**Evet, temassız özelliği var.** {detail}")
            else:
                lines.append("**Evet, temassız özelliği var.**")
        else:
            lines.append(f"**Temassız:** {value}")
    elif "nfc" in q or "qr" in q:
        lines.append(f"**QR / NFC:** {_clean_value(row.get('QR / NFC'), fallback='QR / NFC bilgisi resmî ürün kaynağında doğrulanamadı.')}" )
    elif "taksit" in q:
        lines.append(f"**Taksit / vade farksız:** {_clean_value(row.get('Taksit / Vade Farksız'))}")
    elif any(x in q for x in ("puan", "odul", "mil", "nakit iade")):
        lines.append(f"**Puan / ödül / mil:** {_clean_value(row.get('Puan / Nakit İade / Mil'))}")
    elif "internet" in q:
        lines.append(f"**İnternet alışverişi:** {_clean_value(row.get('İnternet Alışverişi'))}")
    elif "yurt disi" in q or "yurtdisi" in q:
        lines.append(f"**Yurt dışı kullanım:** {_clean_value(row.get('Yurt Dışı Kullanım'))}")
    elif "nakit avans" in q:
        lines.append(f"**Nakit avans:** {_clean_value(row.get('Nakit Avans'))}")
    elif "basvuru" in q:
        lines.append(f"**Başvuru:** {_clean_value(row.get('Başvuru Kanalı'))}")
    else:
        facts = []
        for label, column in (
            ("Kart türü", "Kart Türü"),
            ("Kart ücreti", "Yıllık Kart Ücreti"),
            ("Temassız", "Temassız"),
            ("Ödül", "Puan / Nakit İade / Mil"),
            ("Taksit", "Taksit / Vade Farksız"),
        ):
            value = row.get(column)
            if not _is_missing(value):
                facts.append(f"- **{label}:** {value}")
        lines.extend(facts or ["Bu kart için doğrulanmış temel özellikler sınırlı; resmî ürün sayfasını kontrol edebilirsiniz."])

    if source.startswith("http"):
        lines.append(f"[Resmî kart sayfası]({source})")

    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="card_product_fact",
        answer_mode="card",
        finance_result_count=0,
        reasons=("card_intent", "verified_card_catalog", "campaign_hijack_blocked"),
    )
