"""BANSA competition-safe fast router.

This module is intentionally deterministic and local-first.
It answers structured finance/campaign questions directly from BANSA's
validated local snapshots before the slower local LLM/RAG path is tried.

Design goals:
- typo tolerant bank/product recognition,
- no raw UNVERIFIED/error messages in the UI,
- graceful degradation: exact local evidence -> catalog -> RAG/guide,
- never invent a financial number,
- keep official source URLs attached to factual answers.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from datetime import date
from decimal import Decimal
import math
import re
import json
import unicodedata
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class FastRouteAnswer:
    text: str
    route: str
    answer_mode: str
    backend: str = "competition_fast_router"
    finance_result_count: int = 0
    reasons: tuple[str, ...] = ()


BANK_ALIASES: dict[str, tuple[str, ...]] = {
    "Adil Katılım": (
        "adil katilim", "adil katılım", "adil",
    ),
    "Albaraka Türk": (
        "albaraka turk", "albaraka türk", "albaraka", "al baraka", "baraka",
    ),
    "Dünya Katılım": (
        "dunya katilim", "dünya katılım", "dunya", "dünya",
    ),
    "Hayat Finans": (
        "hayat finans", "hayat",
    ),
    "Kuveyt Türk": (
        "kuveyt turk", "kuveyt türk", "kuveytturk", "kuveyt", "kuveyt bank",
    ),
    "T.O.M. Katılım": (
        "t.o.m. katilim", "tom katilim", "tom bank", "tombank", "tom",
    ),
    "Türkiye Emlak Katılım": (
        "turkiye emlak katilim", "türkiye emlak katılım", "emlak katilim",
        "emlak katılım", "emlak",
    ),
    "Türkiye Finans": (
        "turkiye finans", "türkiye finans", "turkiye fnans", "türkiye fnans",
        "turkye finans", "türkşye finans", "turkiye finansi", "türkiye finansı", "tfkb",
    ),
    "Vakıf Katılım": (
        "vakif katilim", "vakıf katılım", "vakf katlm", "vakif katlm",
        "vakif", "vakıf",
    ),
    "Ziraat Katılım": (
        "ziraat katilim", "ziraat katılım", "ziraat",
    ),
}


FAMILY_ALIASES: dict[str, tuple[str, ...]] = {
    "konut_finansmani": (
        "konut finansmani", "konut", "ev finansmani", "ev", "daire", "mortgage",
        "apartman", "ilk evim", "ev satin almak", "ev satın almak", "ev almak",
    ),
    "arac_finansmani": (
        "tasit finansmani", "taşıt finansmanı", "tasit", "taşıt", "arac finansmani",
        "araç finansmanı", "arac", "araç", "araba", "otomobil", "oto", "motosiklet",
        "motorsiklet", "motosklet", "motor finansmani", "motor", "sifir arac",
        "sıfır araç", "ikinci el arac", "ikinci el araç", "2 el araç", "2. el araç",
        "araba almak", "araç almak",
    ),
    "ihtiyac_finansmani": (
        "ihtiyac finansmani", "ihtiyaç finansmanı", "ihtiyac", "ihtiyaç",
        "tuketici finansmani", "tüketici finansmanı", "egitim finansmani",
        "eğitim finansmanı", "hac finansmani", "umre finansmani",
        "telefon", "laptop", "bilgisayar", "beyaz esya", "beyaz eşya",
        "mobilya", "dugun", "düğün", "egitim", "eğitim", "seyahat", "tatil",
        "kisisel ihtiyac", "kişisel ihtiyaç",
    ),
    "alisveris_finansmani": (
        "alisveris finansmani", "alışveriş finansmanı", "alisveris", "alışveriş",
    ),
    "arsa_finansmani": (
        "arsa finansmani", "arsa finansmanı", "arsa",
    ),
    "isyeri_finansmani": (
        "is yeri finansmani", "iş yeri finansmanı", "isyeri finansmani", "isyeri",
    ),
    "ticari_finansman": (
        "ticari finansman", "isletme finansmani", "işletme finansmanı", "kobi finansman",
        "isletmem", "işletmem", "sirketim", "şirketim", "is yerim", "iş yerim",
        "makine alacagim", "makine alacağım", "ticari arac", "ticari araç",
        "uretim", "üretim", "stok", "isletme sermayesi", "işletme sermayesi",
    ),
}


PRODUCT_HINTS: dict[str, tuple[str, ...]] = {
    "motosiklet": ("motosiklet", "motorsiklet", "motosklet", "motor"),
    "bisiklet": ("bisiklet",),
    "egitim": ("egitim", "eğitim"),
    "hac": ("hac", "umre"),
    "dijital": ("dijital",),
    "yesil": ("yesil", "yeşil", "cevre dostu", "çevre dostu"),
}


CAMPAIGN_WORDS = (
    "kampanya", "kampanyalar", "firsat", "fırsat", "puan", "worldpuan",
    "altin puan", "altın puan", "parafpara", "indirim", "odul", "ödül",
    "cek", "çek", "taksit firsati", "taksit fırsatı", "market",
)

FINANCE_WORDS = (
    "finansman", "kredi", "vade", "kar payi", "kâr payı", "karpayi", "oran",
    "faiz", "taksit", "geri odeme", "geri ödeme", "tahsis", "ekspertiz",
    "ipotek", "sigorta", "masraf", "ucret", "ücret", "limit", "hesapla",
)

COMPARE_WORDS = (
    "karsilastir", "karşılaştır", "kiyasla", "kıyasla", "hangisi", "daha avantajli",
    "daha avantajlı", "en avantajli", "en avantajlı", "en ucuz", "en dusuk", "en düşük",
)


BAD_FAILURE_MARKERS = (
    "unverified",
    "doğrulanmış kaynaklardan güvenli bir yanıt oluşturulamadı",
    "doğrulanmış kaynaklarla güvenilir biçimde yanıtlayamıyorum",
    "bu soruyu mevcut doğrulanmış kaynaklarla güvenilir biçimde yanıtlayamıyorum",
    "yanıt oluşturulurken teknik bir hata oluştu",
)


def normalize(value: str) -> str:
    text = str(value or "")
    text = text.translate(str.maketrans({
        "ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G",
        "ü": "u", "Ü": "U", "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
    }))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"[^a-z0-9%.,:+-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(token for token in normalize(value).split() if token)


def _contains_phrase(norm_query: str, phrase: str) -> bool:
    p = normalize(phrase)
    return bool(p and re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", norm_query))


def _window_similarity(query: str, alias: str) -> float:
    q_tokens = _tokens(query)
    a_tokens = _tokens(alias)
    if not q_tokens or not a_tokens:
        return 0.0
    width = len(a_tokens)
    best = 0.0
    for size in range(max(1, width - 1), min(len(q_tokens), width + 1) + 1):
        for i in range(0, len(q_tokens) - size + 1):
            candidate = " ".join(q_tokens[i:i + size])
            best = max(best, SequenceMatcher(None, candidate, " ".join(a_tokens)).ratio())
    return best


def detect_banks(query: str) -> tuple[str, ...]:
    norm = normalize(query)
    found: list[tuple[int, str]] = []

    # Exact/alias pass. Longest aliases win, avoiding "turkiye" style false matches.
    for bank, aliases in BANK_ALIASES.items():
        best_pos = None
        for alias in sorted(aliases, key=lambda x: len(normalize(x)), reverse=True):
            a = normalize(alias)
            # Turkish case/possessive suffixes may attach to a bank name
            # ("ziraat katilimin", "kuveytturkun", "vakif katilimda").
            # Accept those suffixes without making short aliases match inside
            # unrelated words.
            suffix = r"(?:in|nin|un|nun|da|de|ta|te|dan|den|tan|ten)?"
            match = re.search(
                r"(?<![a-z0-9])" + re.escape(a) + suffix + r"(?![a-z0-9])",
                norm,
            )
            if match:
                best_pos = match.start()
                break
        if best_pos is not None:
            found.append((best_pos, bank))

    if found:
        found.sort()
        ordered: list[str] = []
        for _, bank in found:
            # Prefer Türkiye Emlak over any accidental Türkiye Finans alias overlap.
            if bank not in ordered:
                ordered.append(bank)
        return tuple(ordered)

    # Fuzzy typo pass. Require a strong score and at least one informative token overlap.
    scored: list[tuple[float, str]] = []
    q_tokens = set(_tokens(query))
    for bank, aliases in BANK_ALIASES.items():
        score = max(_window_similarity(query, alias) for alias in aliases)
        alias_tokens = set().union(*(set(_tokens(a)) for a in aliases))
        generic_bank_tokens = {"katilim", "bank", "bankasi", "finans", "turkiye"}
        distinctive_alias_tokens = alias_tokens - generic_bank_tokens
        informative_overlap = bool(q_tokens & distinctive_alias_tokens)
        # Generic phrases such as "bütün katılım bankaları" must never fuzzy-
        # match T.O.M./Dünya/etc. A bank needs a distinctive token overlap, or
        # an exceptionally strong full-window typo match.
        if score >= 0.72 and (informative_overlap or score >= 0.90):
            scored.append((score, bank))

    scored.sort(reverse=True)
    if not scored:
        return tuple()
    top = scored[0][0]
    return tuple(bank for score, bank in scored if score >= max(0.76, top - 0.06))


def detect_family(query: str) -> str | None:
    norm = normalize(query)
    best: tuple[int, str] | None = None
    for family, aliases in FAMILY_ALIASES.items():
        for alias in aliases:
            a = normalize(alias)
            if _contains_phrase(norm, a):
                candidate = (len(a), family)
                if best is None or candidate[0] > best[0]:
                    best = candidate
    return best[1] if best else None


def detect_product_hint(query: str) -> str | None:
    norm = normalize(query)
    best: tuple[int, str] | None = None
    for hint, aliases in PRODUCT_HINTS.items():
        for alias in aliases:
            a = normalize(alias)
            if _contains_phrase(norm, a) or _window_similarity(norm, a) >= 0.82:
                candidate = (len(a), hint)
                if best is None or candidate[0] > best[0]:
                    best = candidate
    return best[1] if best else None


def detect_attribute(query: str) -> str | None:
    q = normalize(query)

    # A financing/LTV ratio is not a pricing/profit-share rate.  Resolve the
    # explicit product-policy wording first so phrases such as "finansman
    # oranı" or "yüzde kaç finansman" cannot be misrouted to pricing.
    if any(x in q for x in (
        "finansman orani", "finansman yuzdesi", "yuzde kac finansman",
        "ne kadarini finanse", "kasko degerinin ne kadari", "fatura degerinin ne kadari",
        "azami finansman orani", "maksimum finansman orani",
    )):
        return "financing_ratio"

    # Intent precedence matters: "sigortali tasit kar payi orani" asks for
    # pricing, not the insurance fee.  A fee route is selected only when the
    # user explicitly asks for the insurance cost/fee.
    if any(x in q for x in ("kar payi", "karpayi", "kar orani", "faiz")):
        return "profit_share_rate"

    if any(x in q for x in ("ekspertiz", "degerleme", "degerleme ucreti")):
        return "appraisal_fee"
    if any(x in q for x in ("tahsis", "dosya masraf", "dosya ucret", "kullandirim ucret")):
        return "allocation_fee"
    if any(x in q for x in ("ipotek", "rehin")):
        return "mortgage_fee"
    if any(x in q for x in (
        "sigorta masraf", "sigorta ucret", "sigorta bedel", "sigortanin ucreti",
        "sigorta ne kadar", "sigortasi ne kadar",
    )):
        return "insurance_fee"
    if any(x in q for x in ("masraf", "ucret", "ucreti", "ucretler")):
        return "fees"

    if any(x in q for x in (
        "minimum vade", "min vade", "asgari vade", "en az kac ay", "en kisa vade"
    )):
        return "minimum_maturity"

    asks_maturity_fact = any(
        x in q
        for x in (
            "azami vade", "maksimum vade", "max vade", "kac ay",
            "vadesi nedir", "vadesi ne", "vade nedir", "vade ne kadar",
            "vade kac", "en uzun vade", "en fazla kac ay",
        )
    )
    has_numeric_maturity_slot = bool(
        re.search(r"(?<!\d)\d{1,3}\s*(?:ay\s*)?(?:vade|aylik)?\b", q)
        and re.search(r"(?<!\d)\d{1,3}\s*ay\b", q)
    )
    if asks_maturity_fact or ("vade" in q and not has_numeric_maturity_slot):
        return "maximum_maturity"

    if any(x in q for x in ("limit", "en fazla ne kadar", "maksimum tutar", "azami tutar")):
        return "maximum_amount"

    # BANSA_ATTR_PAYMENT_V1: "aylık ödemem ne kadar olur", "taksitim ne olur"
    # gibi sorular taksit/toplam ödeme tutarını ister, vadeyi değil. "En düşük
    # aylık taksit hangisinde?" gibi karşılaştırma soruları ise ayrı bir
    # karşılaştırma akışına gitmelidir; bu yüzden "en düşük/en yüksek ...
    # hangisinde/hangi banka" kalıpları burada hariç tutulur.
    is_comparison_phrasing = any(
        x in q for x in ("hangisinde", "hangi banka", "en dusuk", "en yuksek")
    )
    if not is_comparison_phrasing and any(x in q for x in (
        "aylik odeme", "aylik taksit", "ayda ne kadar", "ayda kac tl",
        "taksitim ne", "taksit tutari", "taksit ne kadar", "aylik ne kadar",
        "ne kadar odeyecegim", "ne kadar odeme yaparim",
    )):
        return "monthly_installment"

    if not is_comparison_phrasing and any(x in q for x in (
        "toplam geri odeme", "toplam odeme", "toplam maliyet",
        "toplamda ne kadar", "topluca ne kadar", "toplam ne kadar odeyecegim",
        "toplam ne oder", "genel toplam",
    )):
        return "total_repayment"

    return None


def is_campaign_query(query: str) -> bool:
    q = normalize(query)
    return any(normalize(word) in q for word in CAMPAIGN_WORDS)


def is_finance_query(query: str) -> bool:
    q = normalize(query)
    return detect_family(query) is not None or any(normalize(word) in q for word in FINANCE_WORDS)


def is_compare_query(query: str) -> bool:
    q = normalize(query)
    return len(detect_banks(query)) >= 2 or any(normalize(word) in q for word in COMPARE_WORDS)


def _parse_scaled_number(raw: str, unit: str | None) -> float | None:
    value = str(raw).strip()
    if not value:
        return None
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    elif value.count(".") == 1 and len(value.split(".")[-1]) == 3:
        value = value.replace(".", "")
    else:
        value = value.replace(".", "") if value.count(".") > 1 else value
    try:
        number = float(value)
    except ValueError:
        return None
    if unit == "bin":
        number *= 1_000
    elif unit == "milyon":
        number *= 1_000_000
    return number


def parse_amount_and_maturity(query: str) -> tuple[float | None, int | None]:
    q = normalize(query)
    maturity = None
    m = re.search(r"(?<!\d)(\d{1,3})\s*(?:ay|aylik|aylık)\b", q)
    if m:
        maturity = int(m.group(1))

    amount = None

    # Turkish composite amounts are common in conversational finance queries:
    #   "1 milyon 500 bin TL"
    #   "2 milyon 250 bin"
    # The old parser stopped at the first "milyon" token and interpreted the
    # first example as 1.000.000 TL.  Resolve the composite form before the
    # generic single-unit patterns so vehicle-value bands and scenario slots
    # receive the real amount.
    composite = re.search(
        r"(?<!\d)(\d+(?:[.,]\d+)?)\s*milyon\s+(\d+(?:[.,]\d+)?)\s*bin\s*(?:tl|₺)?\b",
        q,
    )
    if composite:
        millions = _parse_scaled_number(composite.group(1), "milyon")
        thousands = _parse_scaled_number(composite.group(2), "bin")
        if millions is not None and thousands is not None:
            amount = float(millions) + float(thousands)

    patterns = (
        r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(bin|milyon)\s*(?:tl|₺)?\b",
        r"(?<!\d)(\d[\d.]*(?:,\d+)?)\s*(?:tl|₺)\b",
    )
    for pattern in patterns if amount is None else ():
        m = re.search(pattern, q)
        if not m:
            continue
        unit = m.group(2) if (m.lastindex or 0) >= 2 else None
        amount = _parse_scaled_number(m.group(1), unit)
        if amount is not None:
            break

    # Common compact form: "75000 24 ay".
    if amount is None and maturity is not None:
        numbers = re.findall(r"(?<!\d)(\d{4,9})(?!\d)", q.replace(".", ""))
        for raw in numbers:
            value = float(raw)
            if value >= 5_000:
                amount = value
                break
    return amount, maturity


def _present(value) -> bool:
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except Exception:
        pass
    return bool(str(value).strip())


def _fmt_money(value) -> str:
    if not _present(value):
        return "Resmî kaynakta belirtilmemiş"
    try:
        num = float(value)
    except Exception:
        return str(value)
    return f"{num:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") + " TL"


def _fmt_rate(value, text=None) -> str:
    if _present(value):
        return ("%" + f"{float(value):.2f}".replace(".", ","))
    if _present(text):
        return str(text).strip()
    return "Resmî kaynakta sayısal oran yayımlanmamış"


def _fmt_maturity(value, rules=None) -> str:
    if _present(value):
        return f"{int(float(value))} ay"
    if _present(rules):
        return str(rules).strip()
    return "Resmî kaynakta sayısal vade yayımlanmamış"


def _safe_text(value, default="Resmî kaynakta belirtilmemiş") -> str:
    if _present(value):
        return str(value).strip()
    return default


def _display_metadata(row) -> dict:
    raw = row.get("finance_rules_json") if hasattr(row, "get") else None
    if isinstance(raw, dict):
        rules = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            rules = json.loads(raw)
        except Exception:
            rules = {}
    else:
        rules = {}
    metadata = rules.get("display_metadata") if isinstance(rules, dict) else {}
    return dict(metadata) if isinstance(metadata, dict) else {}


def _current_rate_claim_allowed(row) -> bool:
    return bool(_display_metadata(row).get("current_rate_claim_allowed", True))


@lru_cache(maxsize=1)
def _products() -> pd.DataFrame:
    try:
        from src.postgres_repository import get_standard_products
        frame = get_standard_products()
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            from src.competition_current_overrides import apply_product_overrides
            from src.bansa_v40_finance_catalog import apply_source_overrides
            return apply_source_overrides(apply_product_overrides(frame.copy(deep=True)))
    except Exception:
        pass
    from src.finance_runtime_repository import get_standard_products
    from src.competition_current_overrides import apply_product_overrides
    from src.bansa_v40_finance_catalog import apply_source_overrides
    return apply_source_overrides(apply_product_overrides(get_standard_products().copy(deep=True)))


@lru_cache(maxsize=1)
def _scenarios() -> pd.DataFrame:
    from src.finance_runtime_repository import get_verified_finance_scenarios
    return get_verified_finance_scenarios().copy(deep=True)


@lru_cache(maxsize=1)
def _campaigns() -> pd.DataFrame:
    from src.repository import get_campaigns
    from src.competition_current_overrides import apply_campaign_overrides
    return apply_campaign_overrides(get_campaigns().copy(deep=True))


def clear_fast_router_cache() -> None:
    _products.cache_clear()
    _scenarios.cache_clear()
    _campaigns.cache_clear()


def _filter_products(query: str, banks: Iterable[str], family: str | None) -> pd.DataFrame:
    frame = _products()
    work = frame.copy()
    banks = tuple(banks)
    if banks:
        work = work[work["bank_name"].astype(str).isin(banks)].copy()
    if family:
        aliases = {family}
        if family == "arac_finansmani":
            aliases.add("tasit_finansmani")
        work = work[work["product_family_key"].fillna("").astype(str).isin(aliases)].copy()

    hint = detect_product_hint(query)
    if hint and not work.empty:
        alias_map = {
            "motosiklet": ("motosiklet", "motor"),
            "bisiklet": ("bisiklet",),
            "egitim": ("egitim", "eğitim"),
            "hac": ("hac", "umre"),
            "dijital": ("dijital",),
            "yesil": ("yesil", "yeşil", "cevre", "çevre"),
        }
        aliases = alias_map.get(hint, (hint,))
        mask = work["product_name"].fillna("").astype(str).apply(
            lambda x: any(normalize(a) in normalize(x) for a in aliases)
        )
        narrowed = work[mask].copy()
        if not narrowed.empty:
            work = narrowed
    return work



def _product_match_score(row, query: str, family: str | None) -> tuple:
    """Prefer the canonical/generic product that best matches the user's words."""
    name = normalize(row.get("product_name"))
    q = normalize(query)
    hint = detect_product_hint(query)

    score = 0
    if name and name in q:
        score += 100

    q_tokens = set(_tokens(query))
    n_tokens = set(_tokens(str(row.get("product_name") or "")))
    score += 8 * len(q_tokens & n_tokens)

    if hint:
        hint_aliases = {
            "motosiklet": ("motosiklet", "motor"),
            "bisiklet": ("bisiklet",),
            "egitim": ("egitim",),
            "hac": ("hac", "umre"),
            "dijital": ("dijital",),
            "yesil": ("yesil", "cevre"),
        }.get(hint, (hint,))
        if any(normalize(a) in name for a in hint_aliases):
            score += 80

    canonical_names = {
        "konut_finansmani": ("konut finansmani",),
        "arac_finansmani": ("tasit finansmani", "arac finansmani", "motosiklet finansmani"),
        "ihtiyac_finansmani": ("ihtiyac finansmani",),
        "alisveris_finansmani": ("alisveris finansmani",),
        "arsa_finansmani": ("arsa finansmani",),
        "isyeri_finansmani": ("is yeri finansmani", "isyeri finansmani"),
        "ticari_finansman": ("isletme finansmani", "ticari finansman"),
    }.get(family, ())
    for target in canonical_names:
        target_n = normalize(target)
        if name == target_n:
            score += 70
        elif target_n in name:
            score += 30

    # Generic products should beat specialty variants when the query itself
    # did not ask for that specialty.
    specialty_tokens = ("kentsel", "yesil", "ilk evim", "gurbet", "enerji", "bes", "teminatli", "dijital")
    for token in specialty_tokens:
        if normalize(token) in name and normalize(token) not in q:
            score -= 25

    # Prefer rows that have useful normalized fields / verified scenarios.
    if _present(row.get("maximum_maturity_months")):
        score += 3
    if _present(row.get("profit_share_rate")) or _present(row.get("profit_share_rate_text")):
        score += 2

    return (score, -len(name), name)


def _best_product_row(group: pd.DataFrame, query: str, family: str | None):
    if group.empty:
        raise ValueError("empty product group")
    ranked = []
    for idx, row in group.iterrows():
        ranked.append((_product_match_score(row, query, family), idx))
    ranked.sort(reverse=True)
    return group.loc[ranked[0][1]]


def _exact_snapshot_rows(product_ids: Iterable[int], amount: float, maturity: int) -> pd.DataFrame:
    scenarios = _scenario_rows_for_products(product_ids)
    if scenarios.empty:
        return scenarios
    a = pd.to_numeric(scenarios["input_amount"], errors="coerce")
    m = pd.to_numeric(scenarios["input_maturity_months"], errors="coerce")
    status = scenarios["scenario_status"].fillna("").astype(str).str.contains("verified", case=False)
    return scenarios[status & a.eq(float(amount)) & m.eq(int(maturity))].copy()


def _tf_local_variant_rows(row, amount: float, maturity: int) -> list[dict]:
    """Use the already-verified local Türkiye Finans model without network access."""
    if str(row.get("bank_name") or "") != "Türkiye Finans":
        return []
    if str(row.get("product_family_key") or "") != "ihtiyac_finansmani":
        return []
    try:
        from src.finance_live_contract import LiveCalculationRequest
        from src.finance_verified_local_models import resolve_verified_local_variants
        request = LiveCalculationRequest(
            product_id=int(row.get("id")),
            bank_name=str(row.get("bank_name")),
            product_name=str(row.get("product_name")),
            family_key=str(row.get("product_family_key")),
            amount=Decimal(str(amount)),
            maturity_months=int(maturity),
            variant=None,
            metadata={},
        )
        results = resolve_verified_local_variants(request)
    except Exception:
        return []
    output = []
    for result in results or ():
        output.append({
            "input_amount": float(result.calculated_amount),
            "input_maturity_months": int(result.calculated_maturity_months),
            "input_variant": str((result.raw_output or {}).get("variant") or ""),
            "profit_share_rate": float(result.profit_share_rate),
            "monthly_installment": float(result.monthly_installment),
            "total_repayment": float(result.total_repayment),
            "allocation_fee": result.allocation_fee,
            "mortgage_fee": result.mortgage_fee,
            "appraisal_fee": result.appraisal_fee,
            "total_fees": result.total_fees,
            "source_url": result.source_url,
            "source_kind": result.source_kind,
        })
    return output


def _exact_finance_answer(query: str, banks: tuple[str, ...], family: str | None, amount: float | None, maturity: int | None) -> FastRouteAnswer | None:
    if amount is None or maturity is None or family is None:
        return None
    work = _filter_products(query, banks, family)
    if work.empty:
        return None

    bank_groups = list(work.groupby("bank_name", sort=False))
    selected = []
    for bank, group in bank_groups:
        selected.append(_best_product_row(group, query, family))

    records: list[dict] = []
    missing_banks = []
    for row in selected:
        bank = str(row.get("bank_name"))
        exact = _exact_snapshot_rows((int(row.get("id")),), amount, maturity)
        bank_records = []
        if not exact.empty:
            for _, srow in exact.iterrows():
                bank_records.append({
                    "bank_name": bank,
                    "product_name": str(row.get("product_name")),
                    "variant": _safe_text(srow.get("input_variant"), "standard"),
                    "rate": srow.get("profit_share_rate"),
                    "monthly": srow.get("monthly_installment"),
                    "total": srow.get("total_repayment"),
                    "fees": srow.get("total_fees"),
                    "source_url": _safe_text(srow.get("source_url"), "") or _safe_text(row.get("source_url"), ""),
                    "source_kind": _safe_text(srow.get("source_kind"), "snapshot"),
                })
        else:
            for item in _tf_local_variant_rows(row, amount, maturity):
                bank_records.append({
                    "bank_name": bank,
                    "product_name": str(row.get("product_name")),
                    "variant": item.get("input_variant") or "standard",
                    "rate": item.get("profit_share_rate"),
                    "monthly": item.get("monthly_installment"),
                    "total": item.get("total_repayment"),
                    "fees": item.get("total_fees"),
                    "source_url": item.get("source_url") or _safe_text(row.get("source_url"), ""),
                    "source_kind": item.get("source_kind") or "verified_local_model",
                })
        if bank_records:
            records.extend(bank_records)
        else:
            missing_banks.append(bank)

    if not records:
        return None

    title_family = {
        "konut_finansmani": "Konut Finansmanı",
        "arac_finansmani": "Taşıt / Araç Finansmanı",
        "ihtiyac_finansmani": "İhtiyaç Finansmanı",
        "alisveris_finansmani": "Alışveriş Finansmanı",
        "arsa_finansmani": "Arsa Finansmanı",
        "isyeri_finansmani": "İş Yeri Finansmanı",
    }.get(family, "Finansman")

    lines = [
        f"### ✅ {title_family} · Doğrulanmış Hesaplama",
        f"**Senaryo:** {_fmt_money(amount)} / {maturity} ay",
        "",
        "| Banka | Ürün / Koşul | Kâr payı | Aylık taksit | Toplam geri ödeme | Doğrulanmış ücret |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for rec in records:
        variant = rec["variant"]
        label = rec["product_name"] + ((" · " + variant) if variant and variant != "standard" else "")
        fee_text = _fmt_money(rec["fees"]) if _present(rec["fees"]) else "Ücret kapsamı tam doğrulanmamış"
        lines.append(
            f"| **{rec['bank_name']}** | {label} | {_fmt_rate(rec['rate'])} | {_fmt_money(rec['monthly'])} | {_fmt_money(rec['total'])} | {fee_text} |"
        )

    # Ranking only across one concrete result per bank and with equal fee coverage.
    per_bank = {}
    for rec in records:
        per_bank.setdefault(rec["bank_name"], []).append(rec)
    if len(per_bank) >= 2 and all(len(v) == 1 for v in per_bank.values()):
        only = [v[0] for v in per_bank.values()]
        only.sort(key=lambda x: float(x["total"]) if _present(x["total"]) else math.inf)
        if len(only) >= 2 and _present(only[0]["total"]) and _present(only[1]["total"]):
            lines.append(
                f"\n**Geri ödeme toplamına göre:** {only[0]['bank_name']} daha düşük görünüyor. "
                "Ücret kapsamı bankalar arasında farklı/eksikse bu sonuç kesin toplam maliyet sıralaması olarak yorumlanmamalıdır."
            )

    if missing_banks:
        lines.append(
            "\n**Katalog desteği:** " + ", ".join(missing_banks) +
            " için bu tutar/vadede birebir doğrulanmış yerel hesaplama sonucu yok; aşağıdaki ürün karşılaştırmasında koşullar yine gösterilebilir."
        )

    sources = []
    for rec in records:
        url = rec.get("source_url") or ""
        if url and url not in sources:
            sources.append(url)
    if sources:
        lines.append("\n**Resmî hesaplama kaynakları:**")
        lines.extend(f"- {url}" for url in sources)

    # If some requested banks have no exact result, append catalog rows for those banks.
    if missing_banks:
        fallback = _catalog_compare(query, tuple(missing_banks), family, amount, maturity)
        if fallback is not None:
            lines.append("\n---\n### Diğer bankalar için doğrulanmış katalog bilgisi\n")
            lines.append(fallback.text)

    return FastRouteAnswer(
        text="\n".join(lines),
        route="finance_calculate" if len(banks) <= 1 else "finance_compare",
        answer_mode="finance",
        finance_result_count=len(records),
        reasons=("fast_exact_verified_finance", "offline_no_network"),
    )


def _scenario_rows_for_products(product_ids: Iterable[int]) -> pd.DataFrame:
    ids = {int(x) for x in product_ids if _present(x)}
    if not ids:
        return pd.DataFrame()
    frame = _scenarios()
    return frame[frame["product_id"].astype(int).isin(ids)].copy()


def _source_line(row) -> str:
    url = _safe_text(row.get("source_url"), "")
    checked = _safe_text(row.get("last_checked_at"), "")
    bits = []
    if url:
        bits.append(f"[Resmî kaynak]({url})")
    if checked:
        bits.append("Kontrol: " + checked[:10])
    return " · ".join(bits)


def _fee_value_from_product(row, attribute: str) -> str:
    # Product table stores waiver state and, for some records, a concise
    # official fee note.  Never mine an entire scraped page/navigation blob
    # for a financial fee: that produced misleading UI text in V3.
    waiver_map = {
        "allocation_fee": "allocation_fee_waived",
        "insurance_fee": "insurance_fee_waived",
    }
    waiver_column = waiver_map.get(attribute)
    if waiver_column and waiver_column in row.index and _present(row.get(waiver_column)):
        try:
            if bool(row.get(waiver_column)):
                return "Muaf / alınmıyor"
        except Exception:
            pass

    fee_text = _safe_text(row.get("fee_waiver_text"), "")
    if not fee_text:
        return "Resmî kaynakta belirtilmemiş"

    key_patterns = {
        "appraisal_fee": ("ekspertiz", "degerleme"),
        "allocation_fee": ("tahsis", "kullandirim", "dosya"),
        "mortgage_fee": ("ipotek", "rehin"),
        "insurance_fee": ("sigorta",),
    }
    keys = key_patterns.get(attribute, ())
    norm = normalize(fee_text)
    if keys and not any(k in norm for k in keys):
        return "Resmî kaynakta belirtilmemiş"

    compact = re.sub(r"\s+", " ", fee_text).strip()
    if len(compact) > 420:
        return "Resmî kaynakta belirtilmemiş"
    return compact if compact else "Resmî kaynakta belirtilmemiş"


# BANSA_COMPETITION_FEE_PROVENANCE_V4
def _structured_fee_rule(row, attribute: str) -> dict | None:
    """Return authoritative normalized fee rule for a product when available.

    Rule-level evidence has precedence over a fixed TL amount observed in one
    calculator scenario.  This prevents e.g. a 100,000 TL example's 500 TL
    allocation fee from being presented as the product's universal fee when
    the official rule is actually 0.50% of financing amount.
    """
    raw = row.get("finance_rules_json") if hasattr(row, "get") else None
    if not _present(raw):
        return None
    try:
        import json
        payload = json.loads(str(raw)) if isinstance(raw, str) else dict(raw)
    except Exception:
        return None

    type_map = {
        "allocation_fee": {"allocation"},
        "appraisal_fee": {"appraisal"},
        "mortgage_fee": {"mortgage_establishment", "mortgage"},
        "insurance_fee": {"insurance"},
    }
    wanted = type_map.get(attribute, set())
    if not wanted:
        return None
    for rule in payload.get("fee_rules") or []:
        if str(rule.get("fee_type") or "").strip() in wanted:
            return dict(rule)
    return None


def _fmt_percent_tr(value) -> str:
    try:
        number = float(value)
    except Exception:
        return str(value)
    return "%" + f"{number:.2f}".replace(".", ",")


def _structured_fee_value(row, attribute: str, *, requested_amount: float | None = None) -> tuple[str | None, str | None]:
    """Format authoritative fee rule and optional scenario-aware calculation.

    Returns (display_value, explanatory_note).  A percentage rule remains a
    percentage for generic questions; when the user explicitly supplies a
    financing amount, the corresponding TL example is calculated
    deterministically and labelled as such.
    """
    rule = _structured_fee_rule(row, attribute)
    if not rule:
        return None, None

    note = _safe_text(rule.get("note"), "")
    if bool(rule.get("waived")):
        return "Muaf / alınmıyor", note or None

    rate = rule.get("rate")
    amount = rule.get("amount")
    if _present(rate):
        pct = _fmt_percent_tr(rate)
        if requested_amount is not None:
            try:
                tl = float(requested_amount) * float(rate) / 100.0
                return f"finansman tutarının {pct}'si (bu tutarda {_fmt_money(tl)})", note or None
            except Exception:
                pass
        return f"finansman tutarının {pct}'si", note or None

    if _present(amount):
        prefix = ""
        nn = normalize(note)
        if "asgari" in nn:
            prefix = "asgari "
        return prefix + _fmt_money(amount), note or None

    if note:
        # The rule may intentionally be qualitative, e.g. appraisal charged at
        # actual third-party cost.  Use that authoritative wording rather than
        # inventing a number.
        clean = re.sub(r"\s+", " ", note).strip()
        clean = re.sub(r"\s*Kaynak(?:lar)?:.*$", "", clean, flags=re.I).strip()
        return clean[:420], note
    return None, None


def _scenario_fee(product_ids: Iterable[int], attribute: str) -> tuple[str | None, str | None]:
    scenarios = _scenario_rows_for_products(product_ids)
    if scenarios.empty:
        return None, None
    column = {
        "allocation_fee": "allocation_fee",
        "appraisal_fee": "appraisal_fee",
        "mortgage_fee": "mortgage_fee",
    }.get(attribute)
    if not column or column not in scenarios.columns:
        return None, None
    found = scenarios[scenarios[column].notna()].copy()
    if found.empty:
        return None, None
    row = found.sort_values("checked_at", ascending=False).iloc[0]
    return _fmt_money(row[column]), _safe_text(row.get("source_url"), "")


def _format_fact(query: str, banks: tuple[str, ...], family: str | None, attribute: str) -> FastRouteAnswer | None:
    if not banks:
        return None
    work = _filter_products(query, banks[:1], family)
    if work.empty:
        return None

    # Prefer the canonical product that best matches the user's wording.
    row = _best_product_row(work, query, family)
    bank = str(row.get("bank_name") or banks[0])
    product = str(row.get("product_name") or "Finansman")
    product_ids = work["id"].dropna().astype(int).tolist()

    if attribute == "minimum_maturity":
        values = pd.to_numeric(work.get("minimum_maturity_months"), errors="coerce").dropna()
        if not values.empty:
            value = int(values.min())
            text = f"### {bank} · {product}\n**Minimum vade: {value} ay.**"
        else:
            text = (
                f"### {bank} · {product}\n"
                "**Minimum vade bilgisi resmî ürün kaydında sayısal olarak doğrulanmamış.** "
                "BANSA azami vadeyi minimum vade gibi yorumlamıyor."
            )
    elif attribute == "maximum_maturity":
        values = pd.to_numeric(work.get("maximum_maturity_months"), errors="coerce").dropna()
        if not values.empty:
            value = int(values.max())
            text = f"### {bank} · {product}\n**Azami vade: {value} ay.**"
        else:
            rule = next((_safe_text(v, "") for v in work.get("maturity_rules_text", []) if _present(v)), "")
            text = f"### {bank} · {product}\n**Vade bilgisi:** {_safe_text(rule)}"
    elif attribute == "financing_ratio":
        # V21 source correction: the current Dünya Katılım vehicle evidence
        # supplied for this release establishes value-dependent maturity bands
        # but does not establish a current percentage financing ratio.  Never
        # resurrect a stale 70/50/30/20 snapshot through this fact route.
        if bank == "Dünya Katılım" and (family == "arac_finansmani" or "arac" in normalize(product)):
            text = (
                f"### {bank} · {product}\n\n"
                "**Araç değerine bağlı yüzdesel azami finansman oranı güncel kaynakta doğrulanmış değil.** "
                "Yayımlanan tutar bantları vade süresini belirliyor; BANSA bu vade bantlarından yüzdesel bir finansman oranı türetmiyor."
            )
        else:
            ratio_rules = _safe_text(row.get("financing_ratio_rules_text"), "")
            ratio = row.get("maximum_financing_ratio")
            if ratio_rules:
                text = f"### {bank} · {product}\n**Finansman oranı kuralları:** {ratio_rules}"
            elif _present(ratio):
                text = f"### {bank} · {product}\n**Azami finansman oranı: %{float(ratio):g}.**"
            else:
                text = f"### {bank} · {product}\n**Azami finansman oranı resmî kaynakta sayısal olarak doğrulanmamış.**"
    elif attribute == "profit_share_rate":
        if not _current_rate_claim_allowed(row):
            text = (
                f"### {bank} · {product}\n\n"
                "Bankanın sabit/güncel kâr payı oranını doğrulanmış bir fiyatlama olarak vermiyorum. "
                "Resmî finansman hesaplama ekranındaki **kâr oranı alanı kullanıcı tarafından belirlenebildiği** için "
                "hesaplama aracındaki veya eski hesaplama kayıtlarındaki oranları bankanın güncel oranı olarak sunmuyorum."
            )
            source = _safe_text(row.get("source_url"), "")
            if source:
                text += f"\n\n[Resmî ürün kaynağı]({source})"
            return FastRouteAnswer(
                text=text, route="finance_fact", answer_mode="finance", finance_result_count=1,
                reasons=("calculator_rate_user_controlled", "no_current_bank_rate_claim"),
            )

        scenario = _scenario_rows_for_products(product_ids)
        if not scenario.empty and scenario["profit_share_rate"].notna().any():
            s = scenario[scenario["profit_share_rate"].notna()].sort_values("checked_at", ascending=False).iloc[0]
            text = (
                f"### {bank} · {product}\n"
                f"**Doğrulanmış hesaplama örneğindeki kâr payı:** {_fmt_rate(s['profit_share_rate'])}.**\n\n"
                f"Örnek senaryo: {_fmt_money(s['input_amount'])} / {int(s['input_maturity_months'])} ay"
            )
            if _present(s.get("input_variant")):
                text += f" / {s['input_variant']}"
            source = _safe_text(s.get("source_url"), "")
            if source:
                text += f"\n\n[Resmî hesaplama kaynağı]({source})"
            return FastRouteAnswer(text=text, route="finance_fact", answer_mode="finance", finance_result_count=1,
                                   reasons=("fast_verified_finance_fact", "verified_scenario_rate"))
        text = f"### {bank} · {product}\n**Kâr payı / fiyatlama:** {_fmt_rate(row.get('profit_share_rate'), row.get('profit_share_rate_text'))}.**"
    elif attribute == "maximum_amount":
        values = pd.to_numeric(work.get("maximum_financing_amount"), errors="coerce").dropna()
        value = _fmt_money(values.max()) if not values.empty else "Resmî kaynakta sayısal limit yayımlanmamış"
        text = f"### {bank} · {product}\n**Azami finansman tutarı: {value}.**"
    elif attribute in {"allocation_fee", "appraisal_fee", "mortgage_fee", "insurance_fee"}:
        label = {
            "allocation_fee": "Tahsis ücreti",
            "appraisal_fee": "Ekspertiz ücreti",
            "mortgage_fee": "İpotek / rehin ücreti",
            "insurance_fee": "Sigorta masrafı",
        }[attribute]
        requested_amount, _ = parse_amount_and_maturity(query)
        rule_value, rule_note = _structured_fee_value(row, attribute, requested_amount=requested_amount)
        scenario_value, scenario_source = _scenario_fee(product_ids, attribute)

        if rule_value:
            text = f"### {bank} · {product}\n**{label}: {rule_value}.**"
            if rule_note:
                # Keep the user-facing explanation compact while retaining the
                # distinction between a rule and one calculator example.
                nn = normalize(rule_note)
                if "gercek maliyet" in nn or "degis" in nn or "asgari" in nn:
                    compact = re.sub(r"\s+", " ", rule_note).strip()
                    compact = re.sub(r"\s*Kaynak(?:lar)?:.*$", "", compact, flags=re.I).strip()
                    if compact and normalize(compact) not in normalize(rule_value):
                        text += "\n\n" + compact[:420]
            if scenario_value and requested_amount is None:
                text += (
                    f"\n\nBANSA'daki doğrulanmış bir hesaplama örneğinde ücret **{scenario_value}** görünür; "
                    "bu, yukarıdaki genel ücret kuralının yerine geçen sabit bir tarife değildir."
                )
        elif scenario_value:
            text = (
                f"### {bank} · {product}\n"
                f"Bu ürün için genel **{label.lower()}** kuralını sabit bir rakam olarak doğrulayamıyorum. "
                f"BANSA'daki doğrulanmış bir hesaplama örneğinde **{scenario_value}** görülüyor; "
                "bu tutarı tüm başvurular için sabit ücret olarak yorumlamıyorum."
            )
            if scenario_source:
                text += f"\n\n[Resmî hesaplama kaynağı]({scenario_source})"
        else:
            value = _fee_value_from_product(row, attribute)
            text = f"### {bank} · {product}\n**{label}: {value}.**"
    elif attribute == "fees":
        requested_amount, _ = parse_amount_and_maturity(query)
        lines = [f"### {bank} · {product} Masraf Bilgileri"]
        for key, label in (("allocation_fee", "Tahsis"), ("appraisal_fee", "Ekspertiz"), ("mortgage_fee", "İpotek / rehin"), ("insurance_fee", "Sigorta")):
            rule_value, _ = _structured_fee_value(row, key, requested_amount=requested_amount)
            scenario_value, _ = _scenario_fee(product_ids, key)
            if rule_value:
                value = rule_value
            elif scenario_value:
                value = f"doğrulanmış örnekte {scenario_value} (genel sabit tarife olarak yorumlanmaz)"
            else:
                value = _fee_value_from_product(row, key)
            lines.append(f"- **{label}:** {value}")
        text = "\n".join(lines)
    else:
        return None

    source = _source_line(row)
    if source:
        text += "\n\n" + source
    return FastRouteAnswer(text=text, route="finance_fact", answer_mode="finance", finance_result_count=1,
                           reasons=("fast_verified_finance_fact", "catalog_source_used"))


def _verified_example_for_product(product_id: int) -> str | None:
    scenarios = _scenario_rows_for_products((product_id,))
    if scenarios.empty:
        return None
    scenarios = scenarios[scenarios["scenario_status"].astype(str).str.contains("verified", case=False, na=False)].copy()
    if scenarios.empty:
        return None
    row = scenarios.sort_values("checked_at", ascending=False).iloc[0]
    amount = _fmt_money(row.get("input_amount"))
    maturity = int(row.get("input_maturity_months")) if _present(row.get("input_maturity_months")) else "?"
    rate = _fmt_rate(row.get("profit_share_rate"))
    monthly = _fmt_money(row.get("monthly_installment"))
    total = _fmt_money(row.get("total_repayment"))
    fees = _fmt_money(row.get("total_fees")) if _present(row.get("total_fees")) else "Kapsam tam doğrulanmamış"
    variant = _safe_text(row.get("input_variant"), "")
    line = f"{amount} / {maturity} ay"
    if variant and variant not in {"standard", "nan"}:
        line += f" / {variant}"
    line += f" → kâr payı {rate}, aylık {monthly}, toplam {total}, doğrulanmış ücret {fees}"
    return line


def _catalog_compare(query: str, banks: tuple[str, ...], family: str | None, amount: float | None, maturity: int | None) -> FastRouteAnswer | None:
    work = _filter_products(query, banks, family)
    if work.empty:
        return None

    # Use one best matching row per bank to keep jury output compact.
    rows = []
    for bank, group in work.groupby("bank_name", sort=False):
        group = group.copy()
        row = _best_product_row(group, query, family)
        rows.append(row)

    title_family = {
        "konut_finansmani": "Konut Finansmanı",
        "arac_finansmani": "Taşıt / Araç Finansmanı",
        "ihtiyac_finansmani": "İhtiyaç Finansmanı",
        "alisveris_finansmani": "Alışveriş Finansmanı",
        "arsa_finansmani": "Arsa Finansmanı",
        "isyeri_finansmani": "İş Yeri Finansmanı",
        "ticari_finansman": "Ticari Finansman",
    }.get(family, "Finansman")

    lines = [f"### ⚖️ {title_family} Karşılaştırması"]
    if amount is not None or maturity is not None:
        parts = []
        if amount is not None:
            parts.append(_fmt_money(amount))
        if maturity is not None:
            parts.append(f"{maturity} ay")
        lines.append("**İstenen senaryo:** " + " / ".join(parts))
    lines += ["", "| Banka | Ürün | Kâr payı / fiyatlama | Azami vade | Doğrulanmış hesaplama örneği |", "|---|---|---:|---:|---|"]

    rate_candidates = []
    for row in rows:
        rate_num = pd.to_numeric(pd.Series([row.get("profit_share_rate")]), errors="coerce").iloc[0]
        if not pd.isna(rate_num):
            rate_candidates.append((float(rate_num), str(row.get("bank_name"))))
        example = _verified_example_for_product(int(row.get("id"))) or "Bu ürün için yerel doğrulanmış hesaplama örneği bulunmuyor"
        lines.append(
            f"| **{row.get('bank_name')}** | {row.get('product_name')} | "
            f"{_fmt_rate(row.get('profit_share_rate'), row.get('profit_share_rate_text'))} | "
            f"{_fmt_maturity(row.get('maximum_maturity_months'), row.get('maturity_rules_text'))} | {example} |"
        )

    lines.append("")
    lines.append(
        "**Değerlendirme:** Kesin maliyet sıralaması yalnız aynı tutar/vade/koşul için birebir doğrulanmış hesaplama sonuçları mevcutsa yapılır. "
        "Yukarıdaki tablo, BANSA'nın resmî kaynaklardan doğruladığı ürün koşullarını ve varsa bankanın hesaplama aracından alınmış doğrulanmış örneği gösterir."
    )
    if rate_candidates:
        rate_candidates.sort()
        if len(rate_candidates) >= 2 and rate_candidates[0][0] < rate_candidates[1][0]:
            lines.append(
                f"\nYayımlanmış sayısal oranı bulunan satırlar içinde en düşük görünen oran **{rate_candidates[0][1]} %{rate_candidates[0][0]:.2f}**; "
                "bu tek başına toplam maliyet kazananı anlamına gelmez."
            )

    # Attach sources without overloading the table.
    sources = []
    for row in rows:
        url = _safe_text(row.get("source_url"), "")
        if url and url not in sources:
            sources.append(url)
    if sources:
        lines.append("\n**Resmî kaynaklar:**")
        for url in sources:
            lines.append(f"- {url}")

    return FastRouteAnswer(text="\n".join(lines), route="finance_compare", answer_mode="finance",
                           finance_result_count=len(rows), reasons=("fast_catalog_comparison", "graceful_degradation"))


def _single_finance_overview(query: str, banks: tuple[str, ...], family: str | None, amount: float | None, maturity: int | None) -> FastRouteAnswer | None:
    work = _filter_products(query, banks, family)
    if work.empty:
        return None

    # FINANCE_SINGLE_BEST_PRODUCT_V2
    # A bank+family question should answer the requested canonical product,
    # not dump every specialty product in the same family. Product hints
    # (motosiklet, eğitim, vb.) are already narrowed by _filter_products.
    if banks and family:
        selected_rows = []
        for _, group in work.groupby("bank_name", sort=False):
            selected_rows.append(_best_product_row(group, query, family))
        visible = pd.DataFrame(selected_rows) if selected_rows else work.head(1)
    else:
        visible = work.head(8)

    title = "Finansman Kataloğu"
    if banks:
        title = banks[0] + " Finansmanları"
    lines = [f"### 📋 {title}", ""]

    if amount is not None or maturity is not None:
        scenario = []
        if amount is not None:
            scenario.append(_fmt_money(amount))
        if maturity is not None:
            scenario.append(f"{maturity} ay")
        lines.append("**İstenen senaryo:** " + " / ".join(scenario))
        lines.append("")

    for _, row in visible.iterrows():
        line = (
            f"- **{row.get('product_name')}** — Kâr payı/fiyatlama: {_fmt_rate(row.get('profit_share_rate'), row.get('profit_share_rate_text'))}; "
            f"azami vade: {_fmt_maturity(row.get('maximum_maturity_months'), row.get('maturity_rules_text'))}."
        )

        # Explain only what can be proven from normalized fields.
        max_maturity = pd.to_numeric(pd.Series([row.get("maximum_maturity_months")]), errors="coerce").iloc[0]
        if maturity is not None and not pd.isna(max_maturity):
            if int(maturity) <= int(max_maturity):
                line += f"\n  - **Vade kontrolü:** {maturity} ay, yayımlanan {int(max_maturity)} aylık azami vade sınırı içindedir."
            else:
                line += f"\n  - **Vade kontrolü:** {maturity} ay, yayımlanan {int(max_maturity)} aylık azami vade sınırını aşar."

        max_amount = pd.to_numeric(pd.Series([row.get("maximum_financing_amount")]), errors="coerce").iloc[0]
        min_amount = pd.to_numeric(pd.Series([row.get("minimum_financing_amount")]), errors="coerce").iloc[0]
        if amount is not None:
            if not pd.isna(max_amount) and float(amount) > float(max_amount):
                line += f"\n  - **Tutar kontrolü:** {_fmt_money(amount)}, yayımlanan azami {_fmt_money(max_amount)} sınırını aşar."
            elif not pd.isna(min_amount) and float(amount) < float(min_amount):
                line += f"\n  - **Tutar kontrolü:** {_fmt_money(amount)}, yayımlanan asgari {_fmt_money(min_amount)} tutarın altındadır."
            elif not pd.isna(max_amount) or not pd.isna(min_amount):
                line += "\n  - **Tutar kontrolü:** İstenen tutar, BANSA'daki yayımlanmış tutar sınırlarıyla çelişmiyor."
            else:
                line += "\n  - **Tutar kontrolü:** Resmî kaynakta sayısal azami/asgari tutar yayımlanmadığı için tutar uygunluğu kesinleştirilemiyor."

        example = _verified_example_for_product(int(row.get("id")))
        if example:
            line += "\n  - Hesaplama botu doğrulanmış örneği: " + example
        url = _safe_text(row.get("source_url"), "")
        if url:
            line += f"\n  - [Resmî kaynak]({url})"
        lines.append(line)

    if not (banks and family) and len(work) > len(visible):
        lines.append(f"\nAynı filtrede **{len(work) - len(visible)} ek ürün** daha bulunuyor.")
    if amount is not None or maturity is not None:
        lines.append("\nNot: İstenen tutar/vade için birebir doğrulanmış hesaplama yoksa BANSA sayı uydurmaz; mevcut ürün koşulunu ve doğrulanmış banka hesaplama örneğini ayrı gösterir.")
    return FastRouteAnswer(text="\n".join(lines), route="finance_catalog", answer_mode="finance",
                           finance_result_count=len(visible), reasons=("fast_finance_catalog", "single_best_product_v2"))


def _campaign_benefit(row) -> str:
    parts = []
    if _present(row.get("reward_amount")):
        parts.append(_fmt_money(row.get("reward_amount")))
    if _present(row.get("shopping_points")):
        points = float(row.get("shopping_points"))
        parts.append((f"{int(points):,}".replace(",", ".")) + " puan")
    if _present(row.get("discount_rate")):
        parts.append("%" + f"{float(row.get('discount_rate')):.0f}" + " indirim")
    if _present(row.get("maximum_benefit")):
        parts.append("Azami fayda " + _fmt_money(row.get("maximum_benefit")))
    if _present(row.get("installment_count")):
        parts.append(f"{int(float(row.get('installment_count')))} taksit")
    return " · ".join(parts) if parts else "Detaylar kampanya koşullarında"


_CAMPAIGN_QUERY_STOP = {
    "kampanya", "kampanyalari", "kampanyalarini", "kampanyasi", "kampanyasinda",
    "ver", "goster", "listele", "bana", "tum", "guncel", "aktif",
    "avantaj", "avantajlari", "nedir", "neler", "ne", "kac", "var",
    "imkan", "imkani", "firsat", "firsati", "ozel", "ile", "icin",
    "vade", "farksiz", "taksit", "taksitli", "kart", "kartlari", "kredi",
    "son", "gecerlilik", "tarih", "kosul", "kosullari", "detay", "detaylari",
    "pesin", "fiyatina", "aya", "varan", "ozellik", "ozellikleri",
    "katilim", "katilimin", "katilimda", "katilimdan", "bankanin",
    "saglanan", "sunan", "nedir", "imkaninda", "imkanlari",
}


def _active_campaigns_for(banks: tuple[str, ...] = ()) -> pd.DataFrame:
    frame = _campaigns()
    if frame.empty:
        return frame.copy()
    work = frame.copy()
    if "is_active" in work.columns:
        work = work[(work["is_active"].isna()) | (work["is_active"] == 1)].copy()
    today = pd.Timestamp(date.today())
    if "campaign_start_date" in work.columns:
        starts = pd.to_datetime(work["campaign_start_date"], errors="coerce")
        work = work[starts.isna() | starts.le(today)].copy()
    if "campaign_end_date" in work.columns:
        ends = pd.to_datetime(work["campaign_end_date"], errors="coerce")
        work = work[ends.isna() | ends.ge(today)].copy()
    if banks:
        work = work[work["bank_name"].astype(str).isin(banks)].copy()
    return work


def _campaign_topic_tokens(query: str) -> tuple[str, ...]:
    stop = set(_CAMPAIGN_QUERY_STOP)
    for aliases in BANK_ALIASES.values():
        for alias in aliases:
            stop.update(_tokens(alias))
    values = []
    for token in _tokens(query):
        if token.startswith("kampany"):
            continue
        if token in stop or len(token) < 3 or token.isdigit():
            continue
        if token not in values:
            values.append(token)
    return tuple(values)


def _campaign_match_score(row, query: str, topic_tokens: tuple[str, ...]) -> tuple[float, int]:
    title = normalize(str(row.get("campaign_name") or ""))
    url = normalize(str(row.get("source_url") or ""))
    evidence = title + " " + url
    hits = sum(1 for token in topic_tokens if token in evidence)
    # Title similarity is only a tie breaker; factual topic evidence remains TITLE+URL.
    sim = SequenceMatcher(None, normalize(query), title).ratio() if title else 0.0
    return (float(hits), int(round(sim * 1000)))


def is_campaign_subject_query(query: str, banks: tuple[str, ...] = ()) -> bool:
    """Recognize a named campaign/merchant even when the word 'kampanya' is omitted."""
    topic_tokens = _campaign_topic_tokens(query)
    if not topic_tokens:
        return False
    work = _active_campaigns_for(banks)
    if work.empty:
        return False
    best_hits = 0
    for _, row in work.iterrows():
        best_hits = max(best_hits, int(_campaign_match_score(row, query, topic_tokens)[0]))
        if best_hits >= 2:
            return True
    # A distinctive single token (e.g. ShipEntegra) is enough.
    return best_hits >= 1 and any(len(t) >= 6 for t in topic_tokens)


def _campaign_answer(query: str, banks: tuple[str, ...]) -> FastRouteAnswer:
    work = _active_campaigns_for(banks)
    if work.empty:
        return smart_fallback(query, route="campaign_search")

    topic_tokens = _campaign_topic_tokens(query)
    if topic_tokens:
        scored = []
        for idx, row in work.iterrows():
            score = _campaign_match_score(row, query, topic_tokens)
            scored.append((score, idx))
        best = max((score for score, _ in scored), default=(0.0, 0))
        if best[0] > 0:
            keep = [idx for score, idx in scored if score[0] == best[0] and score[0] > 0]
            work = work.loc[keep].copy()
            work["_topic_score"] = [
                _campaign_match_score(row, query, topic_tokens)[1]
                for _, row in work.iterrows()
            ]
            work = work.sort_values("_topic_score", ascending=False)
        else:
            work = work.iloc[0:0].copy()

    if work.empty:
        bank_text = " / ".join(banks) if banks else "seçilen bankalar"
        text = (
            f"### 🎁 {bank_text} Kampanyaları\n"
            "BANSA'nın güncel yerel kampanya kayıtlarında bu başlık/konuyla eşleşen aktif kampanya bulunamadı. "
            "Kampanya süresi dolmuş veya ilgili başlık resmî kaynaktan henüz güncellenmemiş olabilir.\n\n"
            "**Öneri:** Banka adını veya kampanya/marka adını biraz daha açık yazabilirsiniz."
        )
        return FastRouteAnswer(text=text, route="campaign_search", answer_mode="campaign",
                               reasons=("campaign_no_match_graceful",))

    if "campaign_end_date" in work.columns:
        work["_end"] = pd.to_datetime(work["campaign_end_date"], errors="coerce")
        sort_cols = (["_topic_score"] if "_topic_score" in work.columns else []) + ["_end", "id"]
        ascending = ([False] if "_topic_score" in work.columns else []) + [True, False]
        work = work.sort_values(sort_cols, ascending=ascending, na_position="last")
    else:
        work = work.sort_values("id", ascending=False)

    # A named campaign/detail query should answer that campaign, not dump the whole bank catalog.
    specific_detail = bool(topic_tokens)
    if specific_detail:
        row = work.iloc[0]
        title = _safe_text(row.get("campaign_name"), "Kampanya")
        benefit = _campaign_benefit(row)
        end = _safe_text(row.get("campaign_end_date"), "Belirtilmemiş")
        condition = _safe_text(row.get("campaign_conditions"), "Resmî kaynakta koşul özeti belirtilmemiş")
        condition = re.sub(r"\s+", " ", condition)[:700]
        url = _safe_text(row.get("source_url"), "")
        installment = row.get("installment_count")
        qn = normalize(query)
        lines = [f"### 🎁 {row.get('bank_name')} · {title}", ""]
        if _present(installment) and ("kac" in qn or "taksit" in qn):
            lines.append(f"**Taksit imkânı: {int(float(installment))} taksit.**")
            lines.append("")
        lines.append(f"- **Avantaj:** {benefit}")
        lines.append(f"- **Son geçerlilik:** {end}")
        lines.append(f"- **Koşul:** {condition}")
        if url:
            lines.append(f"- [Resmî kaynak]({url})")
        return FastRouteAnswer(
            text="\n".join(lines).strip(), route="campaign_detail", answer_mode="campaign",
            reasons=("fast_campaign_detail", "title_url_topic_match", "active_date_gate"),
        )

    visible = work.head(12)
    bank_title = " / ".join(banks) if banks else "Güncel Katılım Bankası"
    lines = [f"### 🎁 {bank_title} Kampanyaları", f"**{len(work)} aktif eşleşme** bulundu. İlk {len(visible)} kayıt:", ""]
    for _, row in visible.iterrows():
        title = _safe_text(row.get("campaign_name"), "Kampanya")
        benefit = _campaign_benefit(row)
        end = _safe_text(row.get("campaign_end_date"), "Belirtilmemiş")
        condition = _safe_text(row.get("campaign_conditions"), "Resmî kaynakta koşul özeti belirtilmemiş")
        condition = re.sub(r"\s+", " ", condition)[:260]
        url = _safe_text(row.get("source_url"), "")
        lines.append(f"#### {row.get('bank_name')} · {title}")
        lines.append(f"- **Avantaj:** {benefit}")
        lines.append(f"- **Son geçerlilik:** {end}")
        lines.append(f"- **Koşul:** {condition}")
        if url:
            lines.append(f"- [Resmî kaynak]({url})")
        lines.append("")
    return FastRouteAnswer(text="\n".join(lines).strip(), route="campaign_search", answer_mode="campaign",
                           reasons=("fast_live_campaign_catalog", "active_date_gate"))


def smart_fallback(query: str, route: str = "smart_fallback") -> FastRouteAnswer:
    banks = detect_banks(query)
    bank_text = (" / ".join(banks) + " için ") if banks else ""
    text = (
        "### ℹ️ BANSA Akıllı Rehber\n"
        f"{bank_text}aradığınız finansman/kampanya kriterine ilişkin doğrudan yapılandırılmış eşleşme bulunamadı. "
        "BANSA doğrulanmamış finansal rakam üretmez.\n\n"
        "- Finansman için banka + ürün + mümkünse tutar/vade yazabilirsiniz. Örn: **100.000 TL 24 ay ihtiyaç finansmanı**.\n"
        "- Tekil bilgi için **azami vade**, **kâr payı**, **tahsis**, **ekspertiz**, **ipotek** gibi alanı belirtebilirsiniz.\n"
        "- Kampanya için banka adıyla birlikte **kampanyaları göster** veya kategori yazabilirsiniz.\n\n"
        "Sistem yerel doğrulanmış katalog, hesaplama örnekleri ve kampanya kayıtlarından yanıt üretmeye devam eder."
    )
    return FastRouteAnswer(text=text, route=route, answer_mode="guide", reasons=("smart_graceful_fallback",))


def should_replace_failure_text(text: str) -> bool:
    low = normalize(text)
    return any(normalize(marker) in low for marker in BAD_FAILURE_MARKERS)


def answer_fast(query: str) -> FastRouteAnswer | None:
    query = str(query or "").strip()
    if not query:
        return smart_fallback(query)

    banks = detect_banks(query)

    # Explicit campaign vocabulary always wins. A named merchant/campaign may
    # also win when the turn is not otherwise an explicit finance-family/fact
    # question (e.g. "Gree klimada kaç taksit?").
    if is_campaign_query(query):
        # Let the established campaign-comparison engine handle explicit
        # compare/kiyasla turns. The fast campaign search remains for list and
        # detail questions.
        if is_compare_query(query):
            return None
        return _campaign_answer(query, banks)

    family = detect_family(query)
    attribute = detect_attribute(query)
    amount, maturity = parse_amount_and_maturity(query)

    if family is None and attribute is None and amount is None and is_campaign_subject_query(query, banks):
        return _campaign_answer(query, banks)

    if not is_finance_query(query):
        return None

    if attribute and banks:
        fact = _format_fact(query, banks, family, attribute)
        if fact is not None:
            return fact

    exact = _exact_finance_answer(query, banks, family, amount, maturity)
    if exact is not None:
        return exact

    if is_compare_query(query):
        compared = _catalog_compare(query, banks, family, amount, maturity)
        if compared is not None:
            return compared

    overview = _single_finance_overview(query, banks, family, amount, maturity)
    if overview is not None:
        return overview

    return smart_fallback(query, route="finance_smart_fallback")
