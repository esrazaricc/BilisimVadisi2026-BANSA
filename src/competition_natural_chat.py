"""Natural, jury-facing conversation layer for BANSA.

This module sits in front of the legacy agent and the deterministic fast router.
It does *not* invent financial data.  It turns the same verified local catalog,
verified calculation snapshots and active campaign records into concise,
question-aware Turkish answers instead of dumping a fixed table for every turn.

Response policy:
1. Exact verified calculation for the requested scenario when available.
2. Product/rule interpretation for the actual question.
3. Verified calculator examples when an exact scenario is not available.
4. Compact catalog/campaign overview.
5. Let the existing RAG/Qwen/guide layers handle truly open-ended questions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Iterable

import pandas as pd

from src.competition_fast_router import (
    FastRouteAnswer,
    BANK_ALIASES,
    _active_campaigns_for,
    _best_product_row,
    _campaign_benefit,
    _exact_snapshot_rows,
    _fee_value_from_product,
    _filter_products,
    _fmt_maturity,
    _fmt_money,
    _fmt_rate,
    _present,
    _safe_text,
    _scenario_fee,
    _scenario_rows_for_products,
    _structured_fee_value,
    _tf_local_variant_rows,
    detect_attribute,
    detect_banks,
    detect_family,
    detect_product_hint,
    is_campaign_subject_query,
    is_compare_query,
    is_finance_query,
    normalize,
    parse_amount_and_maturity,
)

from src.finance_scenario_projection import (
    ScenarioProjection,
    project_row,
    project_rows,
)

from src.finance_amount_semantics import (
    AmountKind,
    resolve_amount_semantics,
)
from src.calculator_constraints import matching_constraint
from src.finance_official_calculator_service import live_records_for_row
from src.finance_user_scenario_resolver import resolve_user_scenario


ROOT = Path(__file__).resolve().parents[1]
STANDARD_PRODUCT_DIR = ROOT / "data" / "standard_products"


# ---------------------------------------------------------------------------
# Intent helpers
# ---------------------------------------------------------------------------

_CAMPAIGN_CANONICAL = (
    "kampanya",
    "kampanyalar",
    "kampanyalari",
    "kampanyasini",
    "kampanyasi",
    "kampanyasinda",
)

_CAMPAIGN_STOP = {
    "kampanya", "kampanyalar", "kampanyalari", "kampanyalarini", "kampanyasi",
    "kampanyasinda", "kampanyasinin", "kampanyasinin", "ver", "goster", "listele",
    "bana", "tum", "guncel", "aktif", "avantaj", "avantajlari", "nedir", "neler",
    "ne", "kac", "var", "imkan", "imkani", "firsat", "firsati", "ozel", "ile",
    "icin", "vade", "farksiz", "taksit", "taksitli", "kart", "kartlari", "kredi",
    "son", "gecerlilik", "tarih", "kosul", "kosullari", "detay", "detaylari",
    "bankasi", "bankasinin", "katilim", "katilimin", "katilimda", "katilimdan",
    "pesin", "fiyatina", "aya", "varan", "ozellik", "ozellikleri", "ozelligi",
    "saglanan", "sunan", "imkaninda", "imkanlari",
    "zamana", "kadar", "gecerli", "gecerlimi", "bitiyor", "bitis", "sonlaniyor",
    "hangi", "tarihe",
}


def _word_tokens(value: str) -> tuple[str, ...]:
    text = normalize(value)
    # normalize() deliberately keeps numeric punctuation for finance parsing;
    # topic tokens should not keep a trailing period/comma.
    return tuple(
        token.strip(".,:+-%")
        for token in text.split()
        if token.strip(".,:+-%")
    )


def _looks_like_campaign_word(token: str) -> bool:
    token = str(token or "").strip()
    if not token:
        return False
    if token.startswith("kampany") or token.startswith("kampan"):
        return True
    return SequenceMatcher(None, token, "kampanya").ratio() >= 0.76


def _has_explicit_campaign_word(query: str) -> bool:
    return any(_looks_like_campaign_word(token) for token in _word_tokens(query))


def is_campaign_intent(query: str, banks: tuple[str, ...] = ()) -> bool:
    if _has_explicit_campaign_word(query):
        return True
    q = normalize(query)
    # A merchant/title-style question containing "taksit" is a campaign turn
    # unless the user explicitly says finansman.  This prevents e.g.
    # "Ziraat Katılım Schafer 9 Taksit özellikleri" from falling into a random
    # finance product merely because no same-bank campaign title matched.
    if "taksit" in q and "finansman" not in q:
        return True
    # Merchant/campaign names such as "Gree" or "ShipEntegra" should still
    # route to campaigns even when the user omits the word "kampanya".
    try:
        return bool(is_campaign_subject_query(query, banks))
    except Exception:
        return False


def _campaign_topic_tokens(query: str) -> tuple[str, ...]:
    stop = set(_CAMPAIGN_STOP)
    for aliases in BANK_ALIASES.values():
        for alias in aliases:
            stop.update(_word_tokens(alias))

    output: list[str] = []
    for token in _word_tokens(query):
        if _looks_like_campaign_word(token):
            continue
        if token in stop or len(token) < 3 or token.isdigit():
            continue
        if token not in output:
            output.append(token)
    return tuple(output)


def _asks_for_advantage_or_winner(query: str) -> bool:
    q = normalize(query)
    return any(
        phrase in q
        for phrase in (
            "daha avantajli", "hangisi", "hangisi daha", "en avantajli", "en ucuz",
            "daha ucuz", "hangisi iyi", "hangisi uygun", "avantajli olan",
            "en mantikli", "en uygun", "hangisini sec", "hangisini tercih",
        )
    )


def _asks_for_recommendation(query: str) -> bool:
    """Return True when the user explicitly wants BANSA to make a choice.

    Keep this separate from generic comparisons: a request such as
    ``hangi seçenekler var`` should list options, while ``bana en mantıklı
    seçeneği öner`` should additionally interpret the verified scenario and
    surface the winners by rate, monthly payment and repayment total.
    """
    q = normalize(query)
    return any(
        phrase in q
        for phrase in (
            "oner", "oneri", "tavsiye", "en mantikli", "en uygun secenek",
            "en uygun banka", "hangisini sec", "hangisini tercih",
            "hangisi daha iyi", "hangisi daha mantikli", "hangisi daha uygun",
            "sen olsan", "bana gore en", "benim icin en",
        )
    )



def _scaled_money_value(number: str, unit: str | None) -> float | None:
    try:
        value = float(str(number).replace(".", "").replace(",", "."))
    except Exception:
        return None
    unit_n = normalize(unit or "")
    if unit_n == "bin":
        value *= 1_000.0
    elif unit_n == "milyon":
        value *= 1_000_000.0
    return value


def _money_mentions(query: str) -> list[tuple[float, int, int]]:
    """Return TL-valued mentions with spans in normalized query text."""
    q = normalize(query)
    out: list[tuple[float, int, int]] = []
    pattern = re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(bin|milyon)?\s*(?:tl|₺)\b")
    for match in pattern.finditer(q):
        value = _scaled_money_value(match.group(1), match.group(2))
        if value is not None:
            out.append((value, match.start(), match.end()))
    return out


def _extract_purchase_scenario(query: str, family: str | None) -> dict[str, float | None]:
    """Extract asset price, cash/down-payment, financing need and monthly cap.

    This is presentation-side semantic parsing only. It never creates a bank
    rate. Its job is to stop a cash amount or an asset invoice value from being
    mistaken for requested financing principal.
    """
    q = normalize(query)
    mentions = _money_mentions(query)
    asset_value = None
    cash = None
    requested = None
    monthly_cap = None

    asset_words = (
        "arac", "araba", "tasit", "otomobil", "motosiklet", "motor",
        "ev", "konut", "daire", "fatura degeri", "kasko degeri", "satis degeri",
    )
    cash_words = ("nakit", "birikim", "birikmis", "pesinat", "pesin param", "param var")
    finance_words = ("finansman", "kredi", "borclan")

    for value, start, end in mentions:
        left = q[max(0, start - 28):start]
        right = q[end:min(len(q), end + 36)]
        context = f"{left} {right}"
        if "aylik" in left or ("aylik" in context and any(x in context for x in ("fazla odem", "gecmek istem", "butce", "odemem"))):
            monthly_cap = value
            continue
        immediate_right = right[:20]
        if " lik " in immediate_right or any(word in immediate_right for word in asset_words):
            asset_value = value
            continue
        if any(word in context for word in cash_words):
            cash = value
            continue
        if any(word in context for word in asset_words):
            asset_value = value
            continue
        if any(word in context for word in finance_words):
            requested = value

    # If two purchase amounts are explicit and one is cash, the other is the
    # asset price even when Turkish word order made the local window ambiguous.
    values = [m[0] for m in mentions if m[0] != monthly_cap]
    if cash is not None and asset_value is None:
        others = [v for v in values if abs(v - cash) > 0.001]
        if others:
            asset_value = max(others)

    financing_need = None
    if requested is not None:
        financing_need = requested
    elif asset_value is not None and cash is not None:
        financing_need = max(0.0, asset_value - cash)

    return {
        "asset_value": asset_value,
        "cash": cash,
        "requested_financing": requested,
        "financing_need": financing_need,
        "monthly_cap": monthly_cap,
    }


def _extract_monthly_payment_cap(query: str) -> float | None:
    return _extract_purchase_scenario(query, None).get("monthly_cap")


def _prefers_low_monthly(query: str) -> bool:
    q = normalize(query)
    return any(
        phrase in q
        for phrase in (
            "aylik odemem mumkun oldugunca dusuk", "aylik odeme mumkun oldugunca dusuk",
            "aylik taksit mumkun oldugunca dusuk", "en dusuk aylik", "aylik odemesi en dusuk",
            "aylik taksiti en dusuk", "aylik odemem dusuk",
        )
    )


def _generic_finance_family_clarification(amount: float | None, maturity: int | None) -> FastRouteAnswer:
    scenario = []
    if amount is not None:
        scenario.append(_fmt_money(amount))
    if maturity is not None:
        scenario.append(f"{int(maturity)} ay")
    prefix = " / ".join(scenario)
    lead = f"**{prefix}** için " if prefix else ""
    return FastRouteAnswer(
        text=(
            f"{lead}en uygun seçeneği doğru karşılaştırabilmem için **finansman türünü** belirtmem gerekiyor. "
            "Konut, taşıt veya ihtiyaç finansmanı arasında oran, vade ve uygunluk kuralları farklıdır.\n\n"
            "Örneğin **“100 bin TL, 36 ay ihtiyaç finansmanı; aylık ödemesi en düşük olanı öner”** diyebilirsiniz."
        ),
        route="finance_family_clarification",
        answer_mode="finance",
        finance_result_count=0,
        reasons=("generic_finance_topic_reset", "family_required_for_recommendation"),
    )


def _vehicle_purchase_recommendation_answer(
    query: str,
    family: str | None,
    maturity: int | None,
) -> FastRouteAnswer | None:
    if family != "arac_finansmani" or not _asks_for_recommendation(query):
        return None
    scenario = _extract_purchase_scenario(query, family)
    asset_value = scenario.get("asset_value")
    if asset_value is None:
        return None

    work = _filter_products(query, tuple(), family)
    if work.empty:
        return None
    direct_rows: list[tuple[pd.Series, bool]] = []
    for _, group in work.groupby("bank_name", sort=False):
        row, is_direct = _direct_family_product(group, family, query)
        if row is not None and is_direct:
            direct_rows.append((_enrich_row(row), is_direct))

    band_info: list[tuple[pd.Series, VehicleBand, float]] = []
    unknown_banks: list[str] = []
    for row, _ in direct_rows:
        band = _band_for_value(_vehicle_bands(row), float(asset_value))
        if band is None or band.ratio is None or band.ratio <= 0 or band.maturity <= 0:
            unknown_banks.append(str(row.get("bank_name") or ""))
            continue
        band_info.append((row, band, float(asset_value) * float(band.ratio)))

    if not band_info:
        return None

    financing_need = scenario.get("financing_need")
    cash = scenario.get("cash")
    if financing_need is None:
        # Asset value is known but principal is not. Do not repeat the V46 bug
        # of sending the full invoice price to the bank calculators.
        max_values = sorted({round(x[2], 2) for x in band_info})
        max_terms = sorted({int(x[1].maturity) for x in band_info})
        if len(max_values) == 1 and len(max_terms) == 1:
            rule = (
                f"Doğrulanmış araç-değer kurallarında bu değer için azami finansman yaklaşık "
                f"**{_fmt_money(max_values[0])}**, azami vade **{max_terms[0]} ay**."
            )
        else:
            rule = "Bankaların doğrulanmış araç-değer kurallarında azami finansman/vade farklılaşabildiği için tek bir finansman tutarı varsaymıyorum."
        return FastRouteAnswer(
            text=(
                f"### {_fmt_money(asset_value)} araç değeri\n\n"
                f"Buradaki {_fmt_money(asset_value)} tutarı **araç/fatura değeri**; bunu finansman tutarı olarak hesaplamaya göndermiyorum. {rule}\n\n"
                "Size gerçekten banka önerisi yapabilmem için **nakit/peşinatınızı veya kullanmak istediğiniz finansman tutarını** da belirtin."
            ),
            route="vehicle_asset_value_recommendation_clarification",
            answer_mode="finance",
            finance_result_count=0,
            reasons=("asset_value_not_principal", "vehicle_band_first", "recommendation_needs_financing_amount"),
        )

    eligible: list[tuple[pd.Series, VehicleBand, float]] = []
    for item in band_info:
        row, band, maximum = item
        if float(financing_need) <= maximum + 0.01 and (maturity is None or int(maturity) <= int(band.maturity)):
            eligible.append(item)

    if not eligible:
        max_verified = max(x[2] for x in band_info)
        term_at_max = max(int(x[1].maturity) for x in band_info if abs(x[2] - max_verified) < 0.01)
        cash_needed = max(0.0, float(asset_value) - max_verified)
        budget_note = ""
        if scenario.get("monthly_cap") is not None:
            budget_note = f" Aylık **{_fmt_money(scenario['monthly_cap'])}** sınırını değerlendirmeden önce finansman tutarı uygunluk sınırına takılıyor."
        unknown_note = ""
        if any(x for x in unknown_banks if x):
            unknown_note = " Sayısal araç-değer oranı doğrulanamayan bankaları bu sonuca zorla dahil etmiyorum; onlar için banka değerlendirmesi gerekir."
        return FastRouteAnswer(
            text=(
                "### BANSA önerisi\n\n"
                f"{_fmt_money(asset_value)} araç için {_fmt_money(cash or 0)} nakitiniz varsa finansman ihtiyacınız **{_fmt_money(financing_need)}**. "
                f"Doğrulanmış araç-değer bantlarında karşılaştırılabilir azami finansman en fazla yaklaşık **{_fmt_money(max_verified)}** ve bu bantta azami vade **{term_at_max} ay**.\n\n"
                f"Bu nedenle **{_fmt_money(financing_need)} talebiyle doğrulanmış seçeneklerden birini 'uygun' diye önermem doğru olmaz**. "
                f"Bu kurala göre en az yaklaşık **{_fmt_money(cash_needed)}** nakit/peşinat gerekir veya araç bütçesini düşürmek gerekir.{budget_note}{unknown_note}"
            ),
            route="vehicle_recommendation_ineligible",
            answer_mode="finance",
            finance_result_count=0,
            reasons=("asset_cash_semantics", "vehicle_ltv_gate", "no_false_recommendation"),
        )

    effective_maturity = int(maturity) if maturity is not None else min(int(x[1].maturity) for x in eligible)
    base = _multi_bank_options_answer(query, family, float(financing_need), effective_maturity)
    if base is None:
        return None
    intro = (
        f"**Senaryoyu şöyle yorumladım:** araç değeri {_fmt_money(asset_value)}"
        + (f", nakit/peşinat {_fmt_money(cash)}" if cash is not None else "")
        + f", ihtiyaç duyulan finansman **{_fmt_money(financing_need)}**. Araç değerine bağlı uygunluk nedeniyle karşılaştırmayı **{effective_maturity} ay** üzerinden yaptım."
    )
    return FastRouteAnswer(
        text=intro + "\n\n" + base.text,
        route="vehicle_purchase_recommendation",
        answer_mode="finance",
        finance_result_count=base.finance_result_count,
        reasons=tuple(base.reasons) + ("asset_cash_semantics", "vehicle_band_maturity"),
    )



def _phone_purchase_recommendation_answer(query: str) -> FastRouteAnswer | None:
    """Handle phone purchases as purchase-purpose finance, not generic 36m need finance.

    Phone purchases have category-specific maturity constraints.  A generic
    need-finance maximum maturity must therefore not be presented as if it
    applied to the phone itself.
    """
    qn = normalize(query)
    if "telefon" not in qn or not _asks_for_recommendation(query):
        return None

    amount, _ = parse_amount_and_maturity(query)
    work = _filter_products(query, tuple(), "alisveris_finansmani")
    if work.empty:
        return None

    wanted = [
        ("Kuveyt Türk", "Teknosa Alışveriş Finansmanı"),
        ("Hayat Finans", "Bana Bunu Al"),
        ("Albaraka Türk", "Bayide Finansman"),
    ]
    selected: list[pd.Series] = []
    for bank, product in wanted:
        m = work[
            work["bank_name"].astype(str).eq(bank)
            & work["product_name"].astype(str).eq(product)
        ]
        if not m.empty:
            selected.append(_enrich_row(m.iloc[0]))

    if not selected:
        return None

    amount_text = _fmt_money(amount) if amount is not None else "belirttiğiniz tutar"
    lines = [
        "### Telefon alımı için BANSA önerisi",
        f"{amount_text} tutarındaki telefon alımını otomatik olarak **36 ay genel ihtiyaç finansmanı** saymıyorum. "
        "Cep telefonu alımlarında kategoriye özel vade sınırı bulunduğu için önce alışveriş/teknoloji amaçlı ürünleri değerlendiriyorum.",
    ]

    if amount is not None and float(amount) > 20000:
        lines.append(
            "Doğrulanmış ürün metinlerinde **20.000 TL üzerindeki cep telefonu alımlarında azami 3 taksit** kuralı açıkça yer alıyor. "
            "Bu nedenle 40.000 TL gibi bir telefon alımını 36 aya yayılmış gibi göstermiyorum."
        )

    for row in selected:
        bank = str(row.get("bank_name") or "")
        product = str(row.get("product_name") or "")
        text = normalize(str(row.get("clean_text") or ""))
        if bank == "Kuveyt Türk":
            fit = "Telefon alımını açıkça kapsıyor; Teknosa alışverişleri için."
        elif bank == "Hayat Finans":
            fit = "Elektronik/cep telefonu alımını açıkça kapsıyor; mağaza ve internet alışverişlerinde kullanılabiliyor."
        else:
            fit = "Elektronik ve cep telefonu alımını açıkça kapsıyor; anlaşmalı işyerlerinde kullanılabiliyor."
        lines.append(f"- **{bank} · {product}:** {fit}")
        url = _source_url(row)
        if url:
            lines.append(f"  [Resmî ürün sayfası]({url})")

    lines.append(
        "**Maliyet önerisi:** Bu ürünlerin aynı telefon tutarı ve aynı geçerli vadede güncel kâr payı/taksitleri birlikte doğrulanmadan birini **en ucuz** ilan etmiyorum. "
        "Teknosa'dan alacaksanız Kuveyt Türk Teknosa Alışveriş Finansmanı; daha geniş alışveriş kullanımında Hayat Finans Bana Bunu Al ve Albaraka Bayide Finansman ilk bakılacak ürünlerdir."
    )
    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="phone_purchase_recommendation",
        answer_mode="finance",
        finance_result_count=len(selected),
        reasons=("phone_purchase_semantics", "category_maturity_guard", "purpose_fit_before_cost_rank"),
    )


def _commercial_purpose_recommendation_answer(
    query: str,
    family: str | None,
    amount: float | None,
    maturity: int | None,
) -> FastRouteAnswer | None:
    """Recommend commercial products by verified purpose fit when price is unavailable.

    Cost ranking is intentionally not attempted without comparable current
    pricing.  For a machine/equipment purchase, however, official product text
    can still prove that a product is designed for that use case.
    """
    if family != "ticari_finansman" or not _asks_for_recommendation(query):
        return None
    q = normalize(query)
    purpose_tokens = [t for t in ("makine", "techizat", "ekipman") if t in q]
    if not purpose_tokens:
        return None

    work = _filter_products(query, tuple(), family)
    if work.empty:
        return None

    candidates: list[tuple[int, pd.Series, str]] = []
    for _, row in work.iterrows():
        row = _enrich_row(row)
        source = _source_record_lookup(
            str(row.get("bank_name") or ""),
            str(row.get("product_name") or ""),
            _source_url(row),
        )
        clean = normalize(source.get("clean_text") or row.get("clean_text") or "")
        hits = sum(1 for token in ("makine", "techizat", "ekipman") if token in clean)
        if hits <= 0:
            continue
        product_n = normalize(row.get("product_name") or "")
        score = hits * 10 + (4 if "taksitli ticari" in product_n else 0)
        try:
            max_maturity = int(float(row.get("maximum_maturity_months")))
        except Exception:
            max_maturity = None
        if maturity is not None and max_maturity is not None and max_maturity < int(maturity):
            continue
        candidates.append((score, row, clean))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], str(item[1].get("bank_name") or "")))
    visible = candidates[:3]

    scenario_bits = []
    if amount is not None:
        scenario_bits.append(_fmt_money(amount))
    if maturity is not None:
        scenario_bits.append(f"{int(maturity)} ay")
    scenario = " / ".join(scenario_bits)

    lines = ["### BANSA önerisi"]
    if scenario:
        lines.append(f"**{scenario}** senaryosunda güncel ve karşılaştırılabilir ticari kâr payı/taksit verisi yayımlanmadığı için maliyet açısından sahte bir sıralama yapmıyorum.")
    else:
        lines.append("Güncel ve karşılaştırılabilir ticari kâr payı/taksit verisi yayımlanmadığı için maliyet açısından sahte bir sıralama yapmıyorum.")
    lines.append("Ancak **makine/teçhizat/ekipman alımına uygunluğu resmî ürün metninde açıkça doğrulanan** seçenekler arasında şunlar öne çıkıyor:")

    for _, row, _clean in visible:
        bank = str(row.get("bank_name") or "")
        product = str(row.get("product_name") or "")
        lines.append(f"- **{bank} · {product}:** resmî ürün açıklamasında makine/teçhizat/ekipman finansmanı açıkça kapsama alınıyor.")
        url = _source_url(row)
        if url:
            lines.append(f"  [Resmî ürün sayfası]({url})")

    first = visible[0][1]
    lines.append(
        f"**Ürün uyumu açısından ilk bakacağım seçenek {first.get('bank_name')} · {first.get('product_name')} olur.** "
        "Fakat 'en ucuz' diyebilmek için aynı tutar/vadede güncel oran ve taksitlerin bankalardan doğrulanması gerekir."
    )
    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="commercial_purpose_recommendation",
        answer_mode="finance",
        finance_result_count=len(visible),
        reasons=("commercial_purpose_fit", "official_product_text", "no_fake_cost_ranking"),
    )


def _asks_for_information(query: str) -> bool:
    q = normalize(query)
    return any(
        phrase in q
        for phrase in (
            "hakkinda bilgi", "bilgi ver", "nedir", "ne sunuyor", "ne sunuluyor",
            "ozellik", "avantaj", "detay", "kullanabilir miyim", "uygun mu",
        )
    )


def _asks_scenario_calculation(query: str) -> bool:
    q = normalize(query)
    return any(
        phrase in q
        for phrase in (
            "aylik taksit", "taksit hesapla", "taksiti hesapla", "hesapla",
            "toplam geri odeme", "geri odeme ne kadar", "ayda ne kadar",
            "ne kadar oderim", "odeme plani",
        )
    )


def _is_superlative_maturity(query: str) -> bool:
    q = normalize(query)
    return (
        any(x in q for x in ("en uzun vade", "en uzun vadeli", "en fazla vade", "en yuksek vade"))
        or ("hangi bankada" in q and "vade" in q)
    )


# ---------------------------------------------------------------------------
# Rich source-record enrichment
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _source_records() -> tuple[dict, ...]:
    records: list[dict] = []
    if not STANDARD_PRODUCT_DIR.exists():
        return tuple()
    for path in sorted(STANDARD_PRODUCT_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = payload.get("products", []) if isinstance(payload, dict) else []
        for item in items:
            if isinstance(item, dict):
                records.append(item)
    return tuple(records)


@lru_cache(maxsize=512)
def _source_record_lookup(bank_name: str, product_name: str, source_url: str) -> dict:
    bank_n = normalize(bank_name)
    product_n = normalize(product_name)
    url = str(source_url or "").strip()

    best = None
    best_score = -1
    for item in _source_records():
        if normalize(item.get("bank_name")) != bank_n:
            continue
        score = 0
        if normalize(item.get("product_name")) == product_n:
            score += 100
        elif product_n and product_n in normalize(item.get("product_name")):
            score += 40
        if url and str(item.get("url") or "").strip() == url:
            score += 120
        if score > best_score:
            best = item
            best_score = score
    return dict(best or {})


def _enrich_row(row) -> pd.Series:
    enriched = row.copy()
    source = _source_record_lookup(
        str(row.get("bank_name") or ""),
        str(row.get("product_name") or ""),
        str(row.get("source_url") or ""),
    )
    for key, value in source.items():
        if key not in enriched.index or not _present(enriched.get(key)):
            if _present(value):
                enriched[key] = value
    return enriched


def _clean_source_text(row) -> str:
    enriched = _enrich_row(row)
    return re.sub(r"\s+", " ", str(enriched.get("clean_text") or "")).strip()


def _source_url(row) -> str:
    return str(_enrich_row(row).get("source_url") or row.get("source_url") or "").strip()


# ---------------------------------------------------------------------------
# Generic source-text extraction helpers
# ---------------------------------------------------------------------------


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    # The scraped bank pages often contain heading boundaries without periods;
    # punctuation split is still the safest high-precision source extraction.
    chunks = re.split(r"(?<=[.!?])\s+", text)
    return [chunk.strip() for chunk in chunks if 15 <= len(chunk.strip()) <= 520]


def _sentence_with(text: str, required: Iterable[str], *, reject: Iterable[str] = ()) -> str | None:
    req = tuple(normalize(x) for x in required)
    rej = tuple(normalize(x) for x in reject)
    matches = []
    for sentence in _sentences(text):
        sn = normalize(sentence)
        if all(token in sn for token in req) and not any(token in sn for token in rej):
            matches.append(sentence)
    if not matches:
        return None
    # Navigation-heavy scraped sentences are usually much longer than the
    # actual explanatory sentence. Prefer the shortest high-confidence match.
    return min(matches, key=len)


def _noisy_scrape_sentence(sentence: str, *, mode: str = "generic") -> bool:
    """High-precision guard for headings/navigation accidentally captured as copy.

    False negatives are preferable to rendering a menu item or FAQ question as
    product truth.  The deterministic numeric fields are unaffected.
    """
    raw = re.sub(r"\s+", " ", str(sentence or "")).strip()
    q = normalize(raw)
    if not raw:
        return True

    noisy = (
        "sikca sorulan sorular",
        "diger finansman turleri",
        "basvuru kanallari",
        "ana menu",
        "urun ve hizmet ucretleri",
        "hesaplama araclari",
        "sube ve atm",
    )
    if any(marker in q for marker in noisy):
        return True

    # Scraped FAQ/accordion headings such as "Taşıt Finansmanı Kullanmalıyım?"
    # or "Kredi Notu Önemli mi?" are not product descriptions.
    if mode == "description" and raw.endswith("?"):
        return True

    if mode == "application":
        # A valid application sentence may contain one natural question only in
        # rare cases; navigation/FAQ blends usually expose several menu tokens.
        if raw.count("?") >= 1:
            return True
        if any(x in q for x in ("kasko degerinin tamamini", "ile ilgili sikca")):
            return True

    return False


def _short_product_description(row) -> str | None:
    text = _clean_source_text(row)
    if not text:
        return None
    product = normalize(row.get("product_name"))
    hint = detect_product_hint(str(row.get("product_name") or ""))

    candidates: list[tuple[str, ...]] = []
    if hint == "motosiklet" or "motosiklet" in product:
        candidates += [("motosiklet finansmani", "sifir"), ("motosiklet", "satin alma")]
    if "konut" in product:
        candidates += [("konut finansmani", "ev"), ("konut", "finansman")]
    if "ihtiyac" in product:
        candidates += [("ihtiyac finansmani",), ("ihtiyac", "finansman")]
    candidates += [(str(row.get("product_name") or ""),)]

    for required in candidates:
        sentence = _sentence_with(
            text,
            required,
            reject=("cerez", "ana sayfa", "menu", "kvkk", "nakit olarak"),
        )
        if sentence:
            if _noisy_scrape_sentence(sentence, mode="description"):
                continue
            # If a scraped sentence still contains menu/navigation before the
            # real product copy, trim from the last product-name occurrence.
            product_raw = str(row.get("product_name") or "").strip()
            bank_product_raw = (str(row.get("bank_name") or "").strip() + " " + product_raw).strip()
            for needle in (bank_product_raw, product_raw):
                if not needle:
                    continue
                pos = sentence.casefold().rfind(needle.casefold())
                if pos > 0 and len(sentence) - pos >= 28:
                    sentence = sentence[pos:].strip()
                    break
            # A generic Taşıt/Araç page sometimes contains a navigation or
            # teaser sentence for a different specialty product.  Do not use
            # that sentence as the selected product's description.
            sn = normalize(sentence)
            selected = normalize(product_raw)
            if selected in {"tasit finansmani", "arac finansmani"} and any(
                other in sn for other in ("cevreci arac finansmani", "yesil arac finansmani")
            ):
                continue
            if len(sentence) > 300:
                sentence = sentence[:297].rstrip() + "…"
            return sentence
    return None


def _application_feature(row) -> str | None:
    text = _clean_source_text(row)
    if not text:
        return None
    navigation_markers = (
        "cerez", "ana menu", "english", "arabic", "sube ve atm",
        "internet subesi", "dijital sifre", "urun ve hizmet ucretleri",
        "hesaplama araclari",
    )
    for required in (("basvuru", "mobil"), ("basvuru", "sube"), ("basvuru", "web")):
        sentence = _sentence_with(text, required, reject=("cerez", "menu"))
        if not sentence:
            continue
        sn = normalize(sentence)
        if _noisy_scrape_sentence(sentence, mode="application"):
            continue
        if sum(1 for marker in navigation_markers if marker in sn) >= 2:
            continue
        if len(sentence) > 360:
            continue
        return sentence.strip()
    return None


def _eligibility_feature(row) -> str | None:
    text = _clean_source_text(row)
    if not text:
        return None
    patterns = (
        ("sifir ve ikinci el",),
        ("sifir motosiklet",),
        ("bireysel muster",),
        ("yeni muster",),
    )
    for required in patterns:
        sentence = _sentence_with(text, required, reject=("cerez", "menu"))
        if sentence:
            return sentence[:280].rstrip() + ("…" if len(sentence) > 280 else "")
    return None


def _product_benefit_sentences(row, *, limit: int = 5) -> tuple[str, ...]:
    """Extract the bank's own benefits section without turning nav into facts.

    Many product pages contain an explicit ``... Avantajları Nelerdir?`` block.
    The old generic renderer ignored it and answered an advantage question with
    maturity/fee fields instead.  This helper keeps the bank's own wording as
    evidence, then lets the response layer summarize it naturally.
    """
    text = _clean_source_text(row)
    if not text:
        return tuple()

    n = normalize(text)
    starts = (
        "avantajlari nelerdir",
        "avantajlari",
        "avantajlar nelerdir",
        "avantajlar",
    )
    start_pos = -1
    start_len = 0
    for marker in starts:
        pos = n.find(marker)
        if pos >= 0 and (start_pos < 0 or pos < start_pos):
            start_pos = pos
            start_len = len(marker)
    if start_pos < 0:
        return tuple()

    # normalize() and source text have the same rough ordering but not byte
    # offsets. Locate the real heading in the original text instead.
    m = re.search(r"[^.!?]{0,100}Avantaj(?:lar|ları|lari)[^.!?]{0,80}\?", text, flags=re.I)
    if m:
        segment = text[m.end():]
    else:
        # High-recall fallback: cut after first visible advantage heading word.
        m2 = re.search(r"Avantaj(?:lar|ları|lari)", text, flags=re.I)
        segment = text[m2.end():] if m2 else text

    # Stop at the next common section heading.
    stop_patterns = (
        r"\bEğitim Finansmanına Nasıl Başvurulur\?",
        r"\bEgitim Finansmanina Nasil Basvurulur\?",
        r"\bNasıl Başvurulur\?",
        r"\bNasil Basvurulur\?",
        r"\bBaşvuru İçin Gerekli Belgeler",
        r"\bBasvuru Icin Gerekli Belgeler",
        r"\bKimler Yararlanabilir\?",
        r"\bSıkça Sorulan Sorular",
    )
    cut = len(segment)
    for pattern in stop_patterns:
        sm = re.search(pattern, segment, flags=re.I)
        if sm:
            cut = min(cut, sm.start())
    segment = segment[:cut]

    values: list[str] = []
    for sentence in _sentences(segment):
        if _noisy_scrape_sentence(sentence):
            continue
        sn = normalize(sentence)
        if any(x in sn for x in ("cerez", "ana sayfa", "mobil indir", "musteri ol")):
            continue
        if len(sentence) > 360:
            continue
        if normalize(sentence).endswith("finansmanina") or normalize(sentence).endswith("finansmani"):
            continue
        if sentence not in values:
            values.append(sentence)
        if len(values) >= limit:
            break
    return tuple(values)


def _asks_product_benefits(query: str) -> bool:
    q = normalize(query)
    return "avantaj" in q or "faydasi" in q or "faydalari" in q


def _asks_product_overview(query: str) -> bool:
    q = normalize(query)
    return any(x in q for x in ("nasil", "ozellik", "nedir", "hakkinda", "bilgi", "ne sunuyor"))



def _natural_fee_overview(row) -> str | None:
    allocation, _ = _structured_fee_value(row, "allocation_fee")
    appraisal, _ = _structured_fee_value(row, "appraisal_fee")
    mortgage, _ = _structured_fee_value(row, "mortgage_fee")

    if allocation and appraisal and mortgage:
        combined_norm = normalize(" ".join((str(appraisal), str(mortgage))))
        if "gercek maliyet" in combined_norm:
            sentence = f"Masraflarda tahsis ücreti **{allocation}**"
            sentence += "; ekspertiz ve ipotek/rehin ücretleri üçüncü kişilere ödenen gerçek maliyete göre değişiyor"
            if "bsmv muaftir" in combined_norm:
                sentence += " ve bu kalemlerde BSMV muafiyeti belirtiliyor"
            return sentence + "."

    summary = _fee_summary(row)
    if not summary:
        return None
    # Remove scraper-like double punctuation without changing the facts.
    summary = re.sub(r"\.\s*;", ";", summary)
    summary = re.sub(r"\.\.+", ".", summary)
    return summary


def _simple_rate_overview(row) -> str | None:
    """User-facing pricing summary for broad product questions.

    Detailed evidence caveats belong to explicit rate questions, not at the top
    of every product overview.
    """
    row = _enrich_row(row)
    if _present(row.get("profit_share_rate")):
        return f"Yayımlanmış kâr payı {_fmt_rate(row.get('profit_share_rate'))}."
    metadata = _display_metadata(row)
    if metadata.get("calculator_rate_user_controlled"):
        return "Kâr payı, başvuru senaryosunda hesaplama aşamasında belirleniyor."
    text = normalize(row.get("profit_share_rate_text") or "")
    clean = normalize(_clean_source_text(row))
    if "dinamik" in text or "hesaplama" in text or "hesaplama araci" in clean:
        return "Kâr payı, seçilen tutar ve vadeye göre hesaplama aracında belirleniyor."
    return None


def _vehicle_overview_summary(row, query: str) -> tuple[str, ...]:
    bands = tuple(b for b in _vehicle_bands(row) if b.ratio > 0 and b.maturity > 0)
    if not bands:
        return tuple()
    asset = "motosiklet" if (detect_product_hint(query) == "motosiklet" or "motosiklet" in normalize(row.get("product_name"))) else "araç"
    max_term = max(b.maturity for b in bands)
    lines = [
        f"**{max_term} aya varan vade** imkânı bulunuyor. Kullanılabilecek finansman oranı ve azami vade, {'motosikletin' if asset == 'motosiklet' else 'aracın'} fatura/kasko değerine göre değişiyor."
    ]

    # Deterministic example from a non-boundary band. Prefer the second band
    # when available because it creates an illustrative mid-market scenario.
    candidates = [b for b in bands if b.maximum is not None and b.maximum > b.minimum]
    if candidates:
        band = candidates[1] if len(candidates) > 1 else candidates[0]
        value = (float(band.minimum) + float(band.maximum)) / 2.0
        max_financing = value * float(band.ratio)
        lines.append(
            f"**Örnek senaryo (BANSA hesaplaması):** {_fmt_money(value)} değerinde bir {asset} için bu bantta azami finansman yaklaşık "
            f"**{_fmt_money(max_financing)}**, azami vade **{band.maturity} ay** olur."
        )
    return tuple(lines)


def _amount_clarification_answer(row, amount: float, query: str) -> FastRouteAnswer:
    bank = str(row.get("bank_name") or "Katılım Bankası")
    product = str(row.get("product_name") or "Finansman")
    asset = "motosiklet" if (detect_product_hint(query) == "motosiklet" or "motosiklet" in normalize(product)) else "araç"
    lines = [
        f"### {bank} · {product}",
        f"**{_fmt_money(amount)} ile {'motosikletin' if asset == 'motosiklet' else 'aracın'} fatura/kasko değerini mi, yoksa kullanmak istediğiniz finansman tutarını mı kastediyorsunuz?** "
        "İkisi farklı kurallara göre değerlendiriliyor.",
        f"{asset.capitalize()} değerini söylüyorsanız değer bandına göre azami finansman ve vadeyi; finansman tutarını söylüyorsanız hesaplama aracındaki tutar/vade uygunluğunu kontrol ederim.",
    ]
    url = _source_url(row)
    if url:
        lines.append(f"[Resmî ürün kaynağı]({url})")
    return FastRouteAnswer(
        text="\n\n".join(lines), route="finance_amount_clarification",
        answer_mode="finance", finance_result_count=0,
        reasons=("amount_semantics_ambiguous", "asset_value_not_assumed"),
    )


def _requested_financing_amount_guard(
    row,
    amount: float,
    query: str,
    maturity: int | None = None,
) -> FastRouteAnswer:
    bank = str(row.get("bank_name") or "Katılım Bankası")
    product = str(row.get("product_name") or "Finansman")
    family = str(row.get("product_family_key") or row.get("family_key") or "arac_finansmani")
    asset = "motosiklet" if (detect_product_hint(query) == "motosiklet" or "motosiklet" in normalize(product)) else "araç"
    lines = [
        f"### {bank} · {product}",
        f"**{_fmt_money(amount)} finansman talebini**, {asset} değerine bağlı oran tablosuna doğrudan uygulamıyorum. "
        f"Bu tablonun sınırları {'motosikletin' if asset == 'motosiklet' else 'aracın'} fatura/kasko değerine göre çalışıyor.",
    ]

    constraint = matching_constraint(bank, family, query, require_variant_evidence=True)
    if constraint is not None:
        if constraint.amount_limit_applies(maturity):
            if constraint.max_financing_amount is not None and float(amount) > float(constraint.max_financing_amount):
                term_text = f"{maturity} ay" if maturity is not None else "bu ürün"
                lines.append(
                    f"Ayrıca bankanın resmî hesaplama aracında **{constraint.calculator_product}** için {term_text} senaryosunda "
                    f"hesaplanabilen finansman tutarı **{_fmt_money(constraint.max_financing_amount)}** ile sınırlı görünüyor. "
                    f"Bu nedenle **{_fmt_money(amount)}** talep bu hesaplama sınırını aşıyor."
                )
            elif constraint.max_financing_amount is not None:
                lines.append(
                    f"Bankanın resmî hesaplama aracında **{constraint.calculator_product}** için doğrulanmış üst finansman tutarı "
                    f"**{_fmt_money(constraint.max_financing_amount)}**. Talep ettiğiniz tutar bu hesaplama sınırının içinde."
                )
        elif constraint.amount_limit_mode == "term_scoped_observation" and constraint.max_financing_amount is not None:
            observed = constraint.observed_maturity_months
            if maturity is None:
                lines.append(
                    f"Hesaplama aracında **{constraint.calculator_product}** için gözlenen **{observed} ay** senaryosunda "
                    f"üst hesaplama tutarı **{_fmt_money(constraint.max_financing_amount)}**. Banka ekranda bu sınırı 'seçilen vade için' verdiğinden, "
                    "vadenizi bilmeden aynı limiti diğer vadelere genellemiyorum."
                )
            elif observed is not None and int(maturity) != int(observed):
                lines.append(
                    f"Hesaplama aracındaki **{_fmt_money(constraint.max_financing_amount)}** üst sınırı **{observed} ay** senaryosunda doğrulandı. "
                    f"{maturity} ay için aynı sınırı varsaymıyorum; güncel hesaplama aracı doğrulaması gerekir."
                )

        if maturity is not None and constraint.min_maturity_months is not None and int(maturity) < int(constraint.min_maturity_months):
            lines.append(f"Hesaplama aracında doğrulanan vade aralığı **{constraint.min_maturity_months}–{constraint.max_maturity_months} ay**; {maturity} ay bu aralığın altında.")
        elif maturity is not None and constraint.max_maturity_months is not None and int(maturity) > int(constraint.max_maturity_months):
            lines.append(f"Hesaplama aracında doğrulanan vade aralığı **{constraint.min_maturity_months}–{constraint.max_maturity_months} ay**; {maturity} ay bu aralığın üstünde.")

    lines.append(
        f"{_fmt_money(amount)} finansmanın ürün kuralları açısından uygunluğunu netleştirmek için "
        f"{'motosikletin' if asset == 'motosiklet' else 'aracın'} fatura/kasko değerini de bilmem gerekiyor; "
        "hesaplama aracının ürün/varyant/vade sınırı bundan ayrı kontrol edilir."
    )
    url = _source_url(row)
    if url:
        lines.append(f"[Resmî ürün kaynağı]({url})")
    return FastRouteAnswer(
        text="\n\n".join(lines), route="finance_requested_amount_guard",
        answer_mode="finance", finance_result_count=0,
        reasons=("requested_financing_amount_not_asset_value", "eligibility_vs_calculator_separated", "calculator_constraints_separate"),
    )


def _calculator_constraint_scenario_guard(
    row, amount: float, maturity: int, query: str
) -> FastRouteAnswer | None:
    """Fail closed when a verified calculator UI constraint rejects a scenario."""
    bank = str(row.get("bank_name") or "Katılım Bankası")
    product = str(row.get("product_name") or "Finansman")
    family = str(row.get("product_family_key") or row.get("family_key") or "arac_finansmani")
    constraint = matching_constraint(bank, family, query, require_variant_evidence=True)
    if constraint is None:
        return None

    reasons = []
    lines = [f"### {bank} · {product}"]
    if constraint.min_maturity_months is not None and int(maturity) < int(constraint.min_maturity_months):
        reasons.append("below_calculator_min_maturity")
        lines.append(
            f"**{maturity} ay**, resmî hesaplama aracında **{constraint.calculator_product}** için doğrulanan "
            f"**{constraint.min_maturity_months}–{constraint.max_maturity_months} ay** aralığının altında."
        )
    if constraint.max_maturity_months is not None and int(maturity) > int(constraint.max_maturity_months):
        reasons.append("above_calculator_max_maturity")
        lines.append(
            f"**{maturity} ay**, resmî hesaplama aracında **{constraint.calculator_product}** için doğrulanan "
            f"**{constraint.min_maturity_months}–{constraint.max_maturity_months} ay** aralığının üstünde."
        )
    if constraint.amount_limit_applies(int(maturity)) and constraint.max_financing_amount is not None and float(amount) > float(constraint.max_financing_amount):
        reasons.append("above_calculator_max_amount")
        lines.append(
            f"**{_fmt_money(amount)} finansman tutarı**, resmî hesaplama aracında **{constraint.calculator_product}** için bu kapsamda doğrulanan "
            f"**{_fmt_money(constraint.max_financing_amount)}** üst hesaplama tutarını aşıyor."
        )
    if not reasons:
        return None

    if constraint.amount_limit_mode == "term_scoped_observation":
        lines.append(
            "Bu tutar sınırı yalnız doğrulandığı seçili vade senaryosuna uygulanıyor; diğer vadelere otomatik genellemiyorum."
        )
    lines.append(
        "Bu kontrol, araç değerine bağlı azami finansman oranından ayrıdır: biri bankanın hesaplama aracının kabul ettiği senaryoyu, diğeri fatura/kasko değerine bağlı ürün sınırını ifade eder."
    )
    if constraint.source_url:
        lines.append(f"[Resmî hesaplama kaynağı]({constraint.source_url})")
    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="finance_calculator_constraint",
        answer_mode="finance",
        finance_result_count=0,
        reasons=tuple(reasons) + ("calculator_constraint_precheck",),
    )


def _generic_financing_product_clarification(bank: str, amount: float | None) -> FastRouteAnswer:
    amount_text = f" **{_fmt_money(amount)}**" if amount is not None else ""
    return FastRouteAnswer(
        text=(
            f"### {bank} · Finansman seçimi\n\n"
            f"{amount_text.strip() + ' tutarında ' if amount_text else ''}hangi finansman ürününü kastettiğinizi netleştirelim. "
            "**Taşıt, konut, ihtiyaç, eğitim** gibi ürünlerin tutar/vade kuralları ve hesaplama araçları farklı çalışıyor. "
            "Ürünü söylerseniz talep ettiğiniz finansman tutarını o ürünün doğrulanmış koşulları ve varsa resmî hesaplama aracıyla kontrol ederim."
        ),
        route="finance_product_clarification",
        answer_mode="finance",
        finance_result_count=0,
        reasons=("generic_financing_amount_needs_product", "no_random_product_fallback"),
    )


def _albaraka_motorcycle_scope_answer(row, query: str) -> FastRouteAnswer | None:
    """Explain Albaraka's verified 125 cc motorcycle scope.

    Albaraka does not expose a separate generic motorcycle product row in the
    local catalog, but the official vehicle-finance evidence explicitly says
    that motorcycles at/above 125 cc follow vehicle-finance conditions while
    lower-displacement motorcycles fall under need finance.
    """
    metadata = _display_metadata(row)
    if metadata.get("motorcycle_rule") != "125cc_and_above_vehicle_finance_below_125_need_finance":
        return None
    bank = str(row.get("bank_name") or "Albaraka Türk")
    product = str(row.get("product_name") or "Taşıt Finansmanı")
    qn = normalize(query)
    match = re.search(r"\b(\d{2,4})\s*cc\b", qn)
    lines = [f"### {bank} · {product}"]
    if match:
        cc = int(match.group(1))
        if cc >= 125:
            lines.append(
                f"**{cc} cc motosiklet**, resmî ürün koşuluna göre **125 cc ve üzeri** grupta; "
                "bu nedenle taşıt finansmanı koşullarında değerlendiriliyor."
            )
        else:
            lines.append(
                f"**{cc} cc motosiklet**, **125 cc altı** grupta. Resmî ürün koşuluna göre bu durumda "
                "taşıt finansmanı yerine **ihtiyaç finansmanı** koşulları uygulanıyor."
            )
    else:
        lines.append(
            "Albaraka Türk'te motosiklet için finansman türü motor hacmine göre ayrılıyor: "
            "**125 cc ve üzeri** motosikletler taşıt finansmanı koşullarında, **125 cc altı** motosikletler ise "
            "ihtiyaç finansmanı koşullarında değerlendiriliyor. Motor hacmini söylerseniz ilgili ürüne göre devam edebilirim."
        )
    url = _source_url(row)
    if url:
        lines.append(f"[Resmî ürün kaynağı]({url})")
    return FastRouteAnswer(
        text="\n\n".join(lines), route="finance_motorcycle_cc_scope",
        answer_mode="finance", finance_result_count=1,
        reasons=("verified_motorcycle_cc_scope", "no_generic_motorcycle_assumption"),
    )


# ---------------------------------------------------------------------------
# Vehicle/motorcycle rule interpretation
# ---------------------------------------------------------------------------

def _display_metadata(row) -> dict:
    raw = _enrich_row(row).get("finance_rules_json")
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


def _historical_snapshot_rankable(row) -> bool:
    return bool(_display_metadata(row).get("historical_snapshot_rankable", True))


def _vehicle_rule_boundary_status(row, amount: float) -> str | None:
    metadata = _display_metadata(row)
    value = float(amount)
    for raw in metadata.get("vehicle_ambiguous_values") or []:
        try:
            if abs(value - float(raw)) < 0.005:
                return "ambiguous"
        except Exception:
            pass
    for raw in metadata.get("vehicle_unknown_ranges") or []:
        try:
            low, high = float(raw[0]), float(raw[1])
        except Exception:
            continue
        if low < value < high:
            return "unknown"
    try:
        blocked = metadata.get("vehicle_blocked_above")
        if blocked is not None and value > float(blocked):
            return "blocked"
    except Exception:
        pass
    return None


@dataclass(frozen=True)
class VehicleBand:
    minimum: float
    maximum: float | None
    ratio: float | None
    maturity: int


def _parse_tl_number(raw: str) -> float:
    return float(str(raw).replace(".", "").replace(",", "."))


def _vehicle_bands(row) -> tuple[VehicleBand, ...]:
    # Prefer normalized deterministic rules already extracted into
    # finance_rules_json.  Page-text regex is only a backward-compatible
    # fallback.  This fixes pages whose HTML spacing/dashes make a valid
    # 48/36/24/12 table look like a single last-row match.
    bands: list[VehicleBand] = []

    raw_rules = row.get("finance_rules_json")
    if isinstance(raw_rules, dict):
        rules = raw_rules
    elif isinstance(raw_rules, str) and raw_rules.strip():
        try:
            rules = json.loads(raw_rules)
        except Exception:
            rules = {}
    else:
        rules = {}

    metadata = rules.get("display_metadata") if isinstance(rules, dict) else {}
    structured = metadata.get("vehicle_value_rules") if isinstance(metadata, dict) else None
    if isinstance(structured, list):
        for item in structured:
            if not isinstance(item, dict):
                continue
            try:
                minimum = float(item.get("min_value") or 0.0)
                maximum = item.get("max_value")
                maximum = float(maximum) if maximum is not None else None
                raw_ratio = item.get("max_financing_ratio")
                ratio = None if raw_ratio is None or str(raw_ratio).strip() in {"", "None", "nan", "<NA>"} else float(raw_ratio)
                if ratio is not None and ratio > 1:
                    ratio /= 100.0
                maturity = int(item.get("max_maturity_months"))
            except Exception:
                continue
            ratio_ok = ratio is None or 0 <= ratio <= 1
            if ratio_ok and 0 <= maturity <= 120 and (maximum is None or maximum >= minimum):
                bands.append(VehicleBand(minimum, maximum, ratio, maturity))

        blocked_above = metadata.get("vehicle_blocked_above") if isinstance(metadata, dict) else None
        if blocked_above is not None:
            try:
                blocked = float(blocked_above)
                bands.append(VehicleBand(blocked, None, 0.0, 0))
            except Exception:
                pass

    if bands:
        unique: list[VehicleBand] = []
        seen = set()
        for band in bands:
            key = (band.minimum, band.maximum, band.ratio, band.maturity)
            if key not in seen:
                unique.append(band)
                seen.add(key)
        return tuple(unique)

    text = _clean_source_text(row)
    if not text:
        return tuple()

    # Covers Vakıf/Kuveyt style: 0 TL - 400.000 TL 70% 48
    pattern = re.compile(
        r"(\d[\d.]*)\s*TL\s*-\s*(\d[\d.]*)\s*TL\s*%?\s*(\d{1,3})\s*%?\s*(\d{1,3})(?:\s|$)",
        flags=re.I,
    )
    for m in pattern.finditer(text):
        try:
            minimum = _parse_tl_number(m.group(1))
            maximum = _parse_tl_number(m.group(2))
            ratio = float(m.group(3)) / 100.0
            maturity = int(m.group(4))
        except Exception:
            continue
        if 0 <= ratio <= 1 and 0 <= maturity <= 120 and maximum >= minimum:
            bands.append(VehicleBand(minimum, maximum, ratio, maturity))

    # Covers: 2.000.000 TL ve üzeri 0% 0
    upper_pattern = re.compile(
        r"(\d[\d.]*)\s*TL\s*ve\s*(?:uzeri|üzeri)\s*%?\s*(\d{1,3})\s*%?\s*(\d{1,3})",
        flags=re.I,
    )
    for m in upper_pattern.finditer(text):
        try:
            minimum = _parse_tl_number(m.group(1))
            ratio = float(m.group(2)) / 100.0
            maturity = int(m.group(3))
        except Exception:
            continue
        if 0 <= ratio <= 1 and 0 <= maturity <= 120:
            bands.append(VehicleBand(minimum, None, ratio, maturity))

    # Deduplicate exact bands while preserving order.
    unique: list[VehicleBand] = []
    seen = set()
    for band in bands:
        key = (band.minimum, band.maximum, band.ratio, band.maturity)
        if key not in seen:
            unique.append(band)
            seen.add(key)
    return tuple(unique)


def _band_for_value(bands: tuple[VehicleBand, ...], value: float) -> VehicleBand | None:
    for band in bands:
        lower_ok = value >= band.minimum
        upper_ok = band.maximum is None or value <= band.maximum
        if lower_ok and upper_ok:
            return band
    return None


def _vehicle_rule_answer(row, amount: float | None, maturity: int | None, query: str) -> list[str]:
    bands = _vehicle_bands(row)
    if not bands:
        return []

    lines: list[str] = []
    moto_query = detect_product_hint(query) == "motosiklet"
    moto_product = "motosiklet" in normalize(row.get("product_name"))
    generic_vehicle_for_moto = moto_query and not moto_product
    asset_label = "motosiklet" if (moto_query or moto_product) else "araç"

    if generic_vehicle_for_moto:
        # V15 evidence boundary: a generic automobile/vehicle eligibility table
        # is not proof that the same bank applies those ratios to motorcycles.
        # Never transfer the %70/%50/... bands to a motorcycle unless a
        # motorcycle-specific official product record exists.
        return [
            "BANSA'nın doğrulanmış kayıtlarında bu banka için ayrı bir **Motosiklet Finansmanı** koşulu bulamadım. "
            "Genel **Araç Finansmanı** değer/vade tablosunu motosiklete otomatik uygulamıyorum."
        ]

    if amount is None:
        # Give a useful compact rule summary, not a raw scraped table.
        examples = []
        for band in bands[:4]:
            if band.maximum is None:
                label = f"{_fmt_money(band.minimum)} ve üzeri"
            else:
                label = f"{_fmt_money(band.minimum)}–{_fmt_money(band.maximum)}"
            if band.ratio is None:
                examples.append(f"{label}: azami vade {band.maturity} ay")
            elif band.ratio <= 0 or band.maturity <= 0:
                examples.append(f"{label}: kullandırım yok")
            else:
                examples.append(f"{label}: en çok %{band.ratio*100:.0f} finansman, {band.maturity} ay")
        if examples:
            ratio_available = any(b.ratio is not None for b in bands[:4])
            if ratio_available:
                label = "Motosiklet değerine göre azami finansman/vade sınırları" if (moto_query or moto_product) else "Araç değerine göre azami finansman/vade sınırları"
            else:
                label = "Araç/kasko değerine göre azami vade bantları"
            lines.append(f"**{label}:** " + "; ".join(examples) + ".")
        return lines

    q = normalize(query)
    explicit_vehicle_value = any(
        phrase in q
        for phrase in (
            "fatura degeri", "satis degeri", "kasko degeri", "motosiklet fiyati",
            "motor fiyati", "arac degeri", "urun tutari",
        )
    )

    band = _band_for_value(bands, float(amount))
    if not band:
        return lines

    max_financing = (float(amount) * float(band.ratio)) if band.ratio is not None else None
    range_text = (
        f"{_fmt_money(band.minimum)} ve üzeri"
        if band.maximum is None
        else f"{_fmt_money(band.minimum)}–{_fmt_money(band.maximum)}"
    )

    if explicit_vehicle_value:
        if band.ratio is None:
            lines.append(
                f"{_fmt_money(amount)} {asset_label} **fatura/kasko değeri**, resmî tabloda {range_text} bandına giriyor. "
                f"Bu bant için **azami vade {band.maturity} ay**. Kaynak bu değer aralıklarının yalnızca vade süresini belirlemek için kullanıldığını söylüyor; "
                "yüzdesel azami finansman oranı yayımlamadığı için araç değerinden bir finansman tutarı türetmiyorum."
            )
        elif band.ratio <= 0 or band.maturity <= 0:
            lines.append(
                f"Verdiğiniz {_fmt_money(amount)} araç/fatura değeri, resmî tabloda **{range_text}** bandına giriyor ve bu bantta finansman kullandırımı bulunmuyor."
            )
            return lines
        else:
            lines.append(
                f"{_fmt_money(amount)} {asset_label} **fatura/satış değeri** ise resmî tabloda {range_text} bandına giriyor: "
                f"azami finansman oranı **%{band.ratio*100:.0f}** (yaklaşık **{_fmt_money(max_financing)}**) ve azami vade **{band.maturity} ay**."
            )
    else:
        # A user saying "600 bin TL motosiklet finansmanı" normally means the
        # desired financing amount, while official motorcycle rules are based
        # on vehicle invoice/kasko value. Explain both meanings instead of
        # silently applying the wrong interpretation.
        if band.ratio is None:
            lines.append(
                f"Eğer {_fmt_money(amount)} {asset_label} fatura/kasko değeri ise bu değer bandında azami vade **{band.maturity} ay**. "
                "Resmî kaynak yüzdesel finansman oranı yayımlamadığı için bu değerden azami finansman tutarı hesaplamıyorum."
            )
        elif band.ratio <= 0 or band.maturity <= 0:
            lines.append(
                f"Eğer {_fmt_money(amount)} {asset_label} fatura/satış değeri ise bu değer resmî tabloda finansman kullandırılmayan banda giriyor."
            )
        else:
            lines.append(
                (
                    "Burada önemli bir ayrım var: resmî Araç Finansmanı değer tablosu **istenen finansman tutarına değil, taşıtın fatura/kasko değerine** göre çalışıyor. "
                    if generic_vehicle_for_moto
                    else (
                        "Burada önemli bir ayrım var: bankanın motosiklet kuralı **istenen finansman tutarına değil, motosikletin fatura/kasko değerine** göre çalışıyor. "
                        if moto_product
                        else "Burada önemli bir ayrım var: resmî taşıt değer tablosu **istenen finansman tutarına değil, aracın fatura/kasko değerine** göre çalışıyor. "
                    )
                )
                + f"Eğer {_fmt_money(amount)} {asset_label} değeri ise azami oran **%{band.ratio*100:.0f}**, yani yaklaşık **{_fmt_money(max_financing)}** finansman ve en fazla **{band.maturity} ay** vade uygulanıyor."
            )
            lines.append(
                f"Eğer {_fmt_money(amount)} doğrudan **kullanmak istediğiniz finansman tutarı** ise, uygunluğu net hesaplamak için {asset_label} fatura/kasko değerini de bilmem gerekiyor."
            )

    if maturity is not None and band.maturity > 0:
        if int(maturity) <= int(band.maturity):
            lines.append(f"**{maturity} ay vade**, bu değer bandındaki **{band.maturity} aylık** üst sınırın içinde kalıyor.")
        else:
            lines.append(f"**{maturity} ay vade**, bu değer bandındaki **{band.maturity} aylık** üst sınırı aşıyor.")
    return lines


def _vehicle_value_fact_answer(
    query: str,
    banks: tuple[str, ...],
    family: str | None,
    amount: float | None,
    maturity: int | None,
) -> FastRouteAnswer | None:
    """Answer amount-aware vehicle-value rules before generic max-vade facts.

    A product-level ``maximum_maturity_months=48`` is only the broad ceiling.
    For vehicle products the official table can reduce that ceiling to 36/24/12
    months as the invoice/kasko value rises.  If the conversational resolver has
    identified the number as an asset value, this rule is the authoritative
    answer and must beat the generic product field.
    """

    if family != "arac_finansmani" or amount is None or len(banks) != 1:
        return None

    semantics = resolve_amount_semantics(
        query, family=family, amount_present=True, compare=is_compare_query(query)
    )
    if semantics.kind != AmountKind.ASSET_VALUE:
        return None

    work = _filter_products(query, banks, family)
    if work.empty:
        return None

    row = _enrich_row(_best_product_row(work, query, family))

    if detect_product_hint(query) == "motosiklet" and "motosiklet" not in normalize(row.get("product_name")):
        bank = str(row.get("bank_name") or banks[0])
        lines = [f"### {bank} · {row.get('product_name') or 'Araç Finansmanı'}",
                 "BANSA'nın doğrulanmış kayıtlarında bu banka için ayrı bir **Motosiklet Finansmanı** ürünü/kapsamı bulamadım. Genel **Araç Finansmanı** değer/vade tablosunu motosiklete otomatik uygulamıyorum."]
        url = _source_url(row)
        if url:
            lines.append(f"[Resmî ürün kaynağı]({url})")
        return FastRouteAnswer(text="\n\n".join(lines), route="finance_motorcycle_scope_guard", answer_mode="finance", finance_result_count=0, reasons=("motorcycle_scope_not_verified", "no_vehicle_rule_transplant"))

    boundary = _vehicle_rule_boundary_status(row, float(amount))
    if boundary in {"ambiguous", "unknown"}:
        bank = str(row.get("bank_name") or banks[0])
        detail = ("Resmî kaynakta bu tam sınır değeri iki kuralla çakışıyor; komşu banttan tahmin yapmıyorum." if boundary == "ambiguous" else "Resmî tabloda bu değer aralığı açıkça tanımlanmamış; komşu banttan tahmin yapmıyorum.")
        lines=[f"### {bank} · {row.get('product_name') or 'Taşıt Finansmanı'}", f"{_fmt_money(amount)} araç değeri için {detail} Güncel banka hesaplama aracı/şube doğrulaması gerekir."]
        url=_source_url(row)
        if url:
            lines.append(f"[Resmî ürün kaynağı]({url})")
        return FastRouteAnswer(text="\n\n".join(lines), route="finance_vehicle_boundary_guard", answer_mode="finance", finance_result_count=0, reasons=("official_rule_boundary_ambiguous", "no_inference"))
    if detect_product_hint(query) == "motosiklet" and "motosiklet" not in normalize(row.get("product_name")):
        bank = str(row.get("bank_name") or banks[0])
        url = _source_url(row)
        lines = [f"### {bank} · Motosiklet finansmanı"]
        lines.append(
            "Bu banka için ayrı doğrulanmış motosiklet finansmanı kuralı bulamadım. "
            "Genel araç finansmanı oran/vade tablosunu motosiklete taşımıyorum."
        )
        if url:
            lines.append(f"[Genel araç finansmanı kaynağı]({url})")
        return FastRouteAnswer(
            text="\n\n".join(lines), route="finance_motorcycle_evidence_gap",
            answer_mode="finance", finance_result_count=0,
            reasons=("motorcycle_requires_product_specific_evidence", "no_cross_product_rule_transfer"),
        )
    bands = _vehicle_bands(row)
    band = _band_for_value(bands, float(amount)) if bands else None
    if band is None:
        return None

    bank = str(row.get("bank_name") or banks[0])
    product = str(row.get("product_name") or "Taşıt Finansmanı")
    asset_label = "motosiklet" if detect_product_hint(query) == "motosiklet" else "araç"
    url = _source_url(row)

    lines = [f"### {bank} · {product}"]
    if band.ratio is None:
        lines.append(
            f"{_fmt_money(amount)} {asset_label} değeri, resmî vade tablosunda bu banda giriyor; **azami vade {band.maturity} ay**. "
            "Bu kaynak yüzdesel bir azami finansman oranı yayımlamıyor ve tutar aralıklarının yalnızca vade süresinin belirlenmesinde esas alındığını belirtiyor. "
            "Bu nedenle BANSA araç değerinden yüzdesel bir finansman oranı veya buna bağlı türetilmiş bir azami finansman tutarı üretmiyor."
        )
        constraint = matching_constraint(bank, family, query, require_variant_evidence=True)
        if constraint is not None and constraint.max_financing_amount is not None and constraint.amount_limit_applies(maturity):
            lines.append(
                f"Ayrı olarak, resmî hesaplama aracında **{constraint.calculator_product}** için giriş alanının doğrulanmış üst sınırı "
                f"**{_fmt_money(constraint.max_financing_amount)}**. Bu değer bir **calculator giriş sınırıdır**; araç değerine bağlı yüzdesel finansman oranı olarak yorumlanmaz."
            )
    elif band.ratio <= 0 or band.maturity <= 0:
        lines.append(
            f"{_fmt_money(amount)} {asset_label} değeri, resmî tabloda **finansman kullandırılmayan** banda giriyor."
        )
    else:
        max_financing = float(amount) * float(band.ratio)
        lines.append(
            f"{_fmt_money(amount)} {asset_label} değeri için azami finansman oranı **%{band.ratio*100:.0f}**; "
            f"bu da değer kuralına göre yaklaşık **{_fmt_money(max_financing)}** finansmana kadar çıkılabildiği anlamına geliyor. "
            f"Bu değer bandında azami vade **{band.maturity} ay**."
        )

        # V18 keeps calculator UI limits separate from the invoice/kasko-value
        # rule. Apply a calculator ceiling only when the query identifies the
        # exact verified variant and the constraint's term scope is satisfied.
        constraint = matching_constraint(bank, family, query, require_variant_evidence=True)
        if constraint is not None and constraint.max_financing_amount is not None:
            if constraint.amount_limit_applies(maturity):
                effective = min(float(max_financing), float(constraint.max_financing_amount))
                lines.append(
                    f"Resmî hesaplama aracında **{constraint.calculator_product}** için doğrulanmış hesaplama üst sınırı "
                    f"**{_fmt_money(constraint.max_financing_amount)}**. Bu senaryoda efektif üst sınır iki kuralın düşüğü olan "
                    f"**{_fmt_money(effective)}**."
                )
            elif constraint.amount_limit_mode == "term_scoped_observation" and constraint.observed_maturity_months is not None:
                lines.append(
                    f"Hesaplama aracında **{constraint.calculator_product}** için **{constraint.observed_maturity_months} ay** senaryosunda "
                    f"**{_fmt_money(constraint.max_financing_amount)}** üst hesaplama tutarı gözlendi; banka bunu seçilen vadeye bağlı verdiği için "
                    "bu limiti burada farklı vadeye genellemiyorum."
                )

        if maturity is not None:
            if int(maturity) <= int(band.maturity):
                lines.append(
                    f"**{maturity} ay vade** olur. İstediğiniz vade **{band.maturity} aylık** üst sınırın içinde."
                )
            else:
                lines.append(
                    f"**{maturity} ay vade** olmaz. Bu değer bandında azami vade {band.maturity} ay."
                )

    if url:
        lines.append(f"[Resmî ürün kaynağı]({url})")
    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="finance_vehicle_value_rule",
        answer_mode="finance",
        finance_result_count=1,
        reasons=("vehicle_value_band_precedence", "verified_structured_rules"),
    )


# ---------------------------------------------------------------------------
# Calculation and product helpers
# ---------------------------------------------------------------------------



def _live_records_for_row(row, amount: float, maturity: int, query: str = "") -> list[dict]:
    """Shared live-first official calculator resolver.

    Only exact VERIFIED bank-calculator outputs are returned.  Network or
    parser failures remain non-numeric and the caller may then use the existing
    V43 deterministic projection/fallback path.
    """
    try:
        return live_records_for_row(row, amount, maturity)
    except Exception:
        return []


def _exact_records_for_row(row, amount: float, maturity: int) -> list[dict]:
    row = _enrich_row(row)
    # Do not reject all historical rows up front: a current official static
    # rate table may independently confirm that the exact calculator scenario
    # still uses the same rate. The gate below performs that reconciliation.
    exact = _exact_snapshot_rows((int(row.get("id")),), amount, maturity)
    output: list[dict] = []

    # V15 freshness gate. Historical calculator snapshots are audit evidence,
    # not current pricing. If a current official pricing tier exists it owns
    # the scenario. Otherwise a portable snapshot is accepted only for 72h.
    tiers_for_term = [t for t in _pricing_tiers(row) if int(t.get("maturity_months") or 0) == int(maturity)]
    if tiers_for_term and not exact.empty:
        # A historical exact calculator row may remain usable only when its
        # rate is independently confirmed by the CURRENT official price table
        # for the same maturity. This preserves calculator-derived payment math
        # without letting a changed rate (e.g. Vakıf %3.19 -> %3.40) survive.
        current_rates = {round(float(t.get("profit_share_rate")), 8) for t in tiers_for_term if _present(t.get("profit_share_rate"))}
        exact_rates = pd.to_numeric(exact["profit_share_rate"], errors="coerce")
        exact = exact[exact_rates.round(8).isin(current_rates)].copy()
    elif not exact.empty and "checked_at" in exact.columns:
        checked = pd.to_datetime(exact["checked_at"], utc=True, errors="coerce")
        now = pd.Timestamp.now(tz="UTC")
        exact = exact[(now - checked) <= pd.Timedelta(hours=72)].copy()

    if not exact.empty:
        for _, srow in exact.iterrows():
            output.append({
                "bank_name": str(row.get("bank_name")),
                "product_name": str(row.get("product_name")),
                "variant": _safe_text(srow.get("input_variant"), "standard"),
                "rate": srow.get("profit_share_rate"),
                "monthly": srow.get("monthly_installment"),
                "total": srow.get("total_repayment"),
                "fees": srow.get("total_fees"),
                "allocation_fee": srow.get("allocation_fee"),
                "appraisal_fee": srow.get("appraisal_fee"),
                "mortgage_fee": srow.get("mortgage_fee"),
                "source_url": _safe_text(srow.get("source_url"), "") or _source_url(row),
            })
        return output

    for item in _tf_local_variant_rows(row, amount, maturity):
        output.append({
            "bank_name": str(row.get("bank_name")),
            "product_name": str(row.get("product_name")),
            "variant": str(item.get("input_variant") or "standard"),
            "rate": item.get("profit_share_rate"),
            "monthly": item.get("monthly_installment"),
            "total": item.get("total_repayment"),
            "fees": item.get("total_fees"),
            "source_url": item.get("source_url") or _source_url(row),
        })
    return output


def _verified_example(row) -> dict | None:
    row = _enrich_row(row)
    if not _historical_snapshot_rankable(row):
        return None
    scenarios = _scenario_rows_for_products((int(row.get("id")),))
    if scenarios.empty:
        return None
    good = scenarios[
        scenarios["scenario_status"].astype(str).str.contains("verified", case=False, na=False)
    ].copy()
    if good.empty:
        return None
    s = good.sort_values("checked_at", ascending=False).iloc[0]

    # Do not surface an older calculator snapshot as the representative
    # example when a newer official pricing table has already been verified.
    # The current table is authoritative for rate questions and scenario math.
    try:
        scenario_ts = pd.to_datetime(s.get("checked_at"), utc=True, errors="coerce")
        tier_times = []
        for tier in _pricing_tiers(row):
            ts = pd.to_datetime(
                tier.get("verified_checked_at") or tier.get("checked_at"),
                utc=True, errors="coerce",
            )
            if not pd.isna(ts):
                tier_times.append(ts)
        if tier_times and (pd.isna(scenario_ts) or max(tier_times) > scenario_ts):
            return None
    except Exception:
        pass

    return {
        "amount": s.get("input_amount"),
        "maturity": s.get("input_maturity_months"),
        "variant": _safe_text(s.get("input_variant"), "standard"),
        "rate": s.get("profit_share_rate"),
        "monthly": s.get("monthly_installment"),
        "total": s.get("total_repayment"),
        "fees": s.get("total_fees"),
        "source_url": _safe_text(s.get("source_url"), "") or _source_url(row),
    }


def _rate_sentence(row) -> str:
    row = _enrich_row(row)
    metadata = _display_metadata(row)
    if metadata.get("calculator_rate_user_controlled"):
        return (
            "Bankanın sabit/güncel kâr payı oranını doğrulanmış bir fiyatlama olarak vermiyorum. "
            "Resmî finansman hesaplama ekranındaki kâr oranı alanı kullanıcı tarafından belirlenebildiği için "
            "bu alanı bankanın güncel oranı olarak kabul etmiyorum."
        )
    if _present(row.get("profit_share_rate")):
        return f"Yayımlanmış kâr payı oranı {_fmt_rate(row.get('profit_share_rate'))}."
    text = str(row.get("profit_share_rate_text") or "").strip()
    clean = normalize(_clean_source_text(row))
    if text:
        if "dinamik" in normalize(text) or "hesaplama" in normalize(text):
            return "Sabit bir kâr payı oranı yayımlanmıyor; oran bankanın hesaplama aracında seçilen tutar/vadeye göre belirleniyor."
        return f"Fiyatlama bilgisi: {text}."
    if "hesaplama araci" in clean or "finansman hesapla" in clean:
        return "Sabit bir kâr payı oranı yayımlanmıyor; ürün sayfasında hesaplama aracı bulunuyor ve oran senaryoya göre belirleniyor."
    return "Resmî ürün kaydında sabit sayısal kâr payı oranı yayımlanmamış."


def _fee_summary(row) -> str | None:
    """Natural fee summary with source-rule precedence.

    Calculator scenario fees are examples.  Normalized authoritative fee rules
    are the product policy.  Never reverse that precedence.
    """
    row = _enrich_row(row)
    product_id = int(row.get("id"))
    parts = []
    for key, label in (
        ("allocation_fee", "tahsis"),
        ("appraisal_fee", "ekspertiz"),
        ("mortgage_fee", "ipotek/rehin"),
        ("insurance_fee", "sigorta"),
    ):
        rule_value, _ = _structured_fee_value(row, key)
        if rule_value:
            parts.append(f"{label}: {rule_value}")
            continue

        # A scenario-only fee is explicitly labelled as an example, never as
        # the universal product tariff.
        scenario_value, _ = _scenario_fee((product_id,), key)
        if scenario_value:
            parts.append(f"{label}: doğrulanmış örnekte {scenario_value}")
            continue

        value = _fee_value_from_product(row, key)
        if value and value != "Resmî kaynakta belirtilmemiş":
            vn = normalize(value)
            if any(marker in vn for marker in ("ucret", "masraf", "muaf", "tl", "%", "komisyon", "alinm")):
                parts.append(f"{label}: {value}")

    if parts:
        return "Masraf tarafında " + "; ".join(parts) + "."
    return None




def _pricing_tiers(row) -> list[dict]:
    raw = row.get("finance_rules_json")
    if isinstance(raw, dict):
        rules = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            rules = json.loads(raw)
        except Exception:
            rules = {}
    else:
        rules = {}
    return [x for x in (rules.get("pricing_tiers") or []) if isinstance(x, dict)]


def _tier_matches_query(tier: dict, query: str) -> bool:
    q = normalize(query)
    variant = normalize(tier.get("pricing_variant") or "")

    # Explicit conditions always narrow; absent conditions keep all variants.
    if "sigortasiz" in q and "sigortasiz" not in variant:
        return False
    if "sigortali" in q and "sigortasiz" not in q and "sigortali" not in variant:
        return False
    if any(x in q for x in ("2 el", "ikinci el", "2.el")) and not any(x in variant for x in ("2 el", "ikinci el")):
        return False
    if any(x in q for x in ("0 km", "sifir km", "sifir arac")) and not any(x in variant for x in ("0 km", "sifir")):
        return False
    if "ilk konut" in q and "ilk konut" not in variant:
        return False
    if any(x in q for x in ("mevcut konut", "ikinci konut", "2 konut")) and "mevcut konut" not in variant:
        return False
    return True


def _variant_matches_query(variant_value: str, query: str) -> bool:
    """Apply the same explicit variant narrowing to calculated records."""
    q = normalize(query)
    variant = normalize(variant_value or "")
    if "sigortasiz" in q and "sigortasiz" not in variant:
        return False
    if "sigortali" in q and "sigortasiz" not in q and "sigortali" not in variant:
        return False
    if any(x in q for x in ("2 el", "ikinci el", "2.el")) and not any(x in variant for x in ("2 el", "ikinci el")):
        return False
    if any(x in q for x in ("0 km", "sifir km", "sifir arac")) and not any(x in variant for x in ("0 km", "sifir")):
        return False
    if "ilk konut" in q and "ilk konut" not in variant:
        return False
    if any(x in q for x in ("mevcut konut", "ikinci konut", "2 konut")) and "mevcut konut" not in variant:
        return False
    return True


def _pricing_rate_answer(query: str, row, maturity: int | None) -> FastRouteAnswer | None:
    tiers = [t for t in _pricing_tiers(row) if _tier_matches_query(t, query)]
    if not tiers:
        return None

    if maturity is not None:
        tiers = [t for t in tiers if int(t.get("maturity_months") or 0) == int(maturity)]
        if not tiers:
            return FastRouteAnswer(
                text=(
                    f"### {row.get('bank_name')} · {row.get('product_name')}\n\n"
                    f"Resmî fiyatlama tablosunda **{maturity} ay** için bu koşulla eşleşen bir oran satırı göremiyorum. "
                    "Başka bir vade veya sigorta/araç durumunu belirtirseniz mevcut tabloyu ona göre kontrol edebilirim."
                ),
                route="finance_fact", answer_mode="finance",
                reasons=("official_pricing_table_no_exact_maturity",),
            )

    # Deduplicate variants whose maturity/rate curves are identical (e.g. TF
    # 0 km and 2.el vehicle tables).  This keeps the answer conversational.
    groups: dict[tuple, list[dict]] = {}
    for tier in tiers:
        key_variant = normalize(tier.get("pricing_variant") or "standard")
        if maturity is not None:
            signature = (int(tier.get("maturity_months") or 0), float(tier.get("profit_share_rate") or 0))
        else:
            base = re.sub(r"\b(?:0 km|2 el|ikinci el)\b", "", key_variant).strip()
            signature = (base,)
        groups.setdefault(signature, []).append(tier)

    bank = str(row.get("bank_name") or "Katılım Bankası")
    product = str(row.get("product_name") or "Finansman")
    checked = str(row.get("last_checked_at") or "").split("T")[0]
    source = _source_url(row)

    if maturity is not None:
        # If the user only asked for an insurance condition + maturity, 0 km
        # and 2.el rows that publish the same rate are one conversational fact.
        # Preserve the vehicle status only when the user explicitly asks for it
        # or when the values actually differ.
        qn = normalize(query)
        explicit_vehicle_status = any(
            marker in qn
            for marker in ("0 km", "sifir km", "sifir arac", "2 el", "ikinci el", "2.el")
        )
        unique: list[tuple[dict, str]] = []
        seen = set()
        for tier in tiers:
            raw_variant = str(tier.get("pricing_variant") or "Standart")
            display_variant = raw_variant
            if not explicit_vehicle_status:
                base = re.sub(
                    r"\s*[·|/-]?\s*(?:0\s*km|2\.?\s*el|ikinci\s*el)\s*$",
                    "", raw_variant, flags=re.I,
                ).strip(" ·|/-")
                if base:
                    display_variant = base
            key = (normalize(display_variant), float(tier.get("profit_share_rate") or 0))
            if key in seen:
                continue
            seen.add(key)
            unique.append((tier, display_variant))
        lines = [f"### {bank} · {product}"]
        for tier, display_variant in unique:
            lines.append(
                f"**{display_variant} · {maturity} ay:** kâr payı **{_fmt_rate(tier.get('profit_share_rate'))}**, "
                f"tahsis ücreti **%0,50**."
            )
        lines.append("Bu oranlar BANSA'nın hesaplama örneğinden değil, bankanın **resmî vade/fiyatlama tablosundan** alınır.")
    else:
        # Build one compact rate curve per insurance/condition family.
        buckets: dict[str, list[dict]] = {}
        for tier in tiers:
            v = normalize(tier.get("pricing_variant") or "Standart")
            if "sigortasiz" in v:
                label = "Sigortasız"
            elif "sigortali" in v:
                label = "Sigortalı"
            elif "ilk konut" in v:
                label = str(tier.get("pricing_variant"))
            else:
                label = str(tier.get("pricing_variant") or "Standart")
            buckets.setdefault(label, []).append(tier)
        lines = [
            f"### {bank} · {product}",
            "Kâr payı oranı **tek bir sabit oran değil; vadeye ve seçilen koşula göre değişiyor**.",
        ]
        for label, items in buckets.items():
            by_m = {}
            for t in items:
                by_m[int(t.get("maturity_months") or 0)] = float(t.get("profit_share_rate") or 0)
            pairs = ", ".join(f"{m} ay %{str(r).replace('.', ',')}" for m, r in sorted(by_m.items()))
            lines.append(f"- **{label}:** {pairs}.")
        lines.append("Tahsis ücreti resmî tabloda finansman tutarının **%0,50'si** olarak yer alıyor.")

    if checked:
        lines.append(f"**BANSA güncel kaynak kontrolü:** {checked}")
    if source:
        lines.append(f"[Resmî fiyatlama kaynağı]({source})")
    return FastRouteAnswer(
        text="\n\n".join(lines), route="finance_fact", answer_mode="finance",
        finance_result_count=len(tiers),
        reasons=("current_official_pricing_table", "rate_intent_precedence"),
    )

def _direct_family_product(group: pd.DataFrame, family: str | None, query: str):
    if group.empty:
        return None, False
    if family != "ihtiyac_finansmani":
        return _best_product_row(group, query, family), True

    direct_scores = []
    for idx, row in group.iterrows():
        name = normalize(row.get("product_name"))
        score = 0
        if name == "ihtiyac finansmani":
            score = 120
        elif "dijital ihtiyac finansmani" in name:
            score = 110
        elif name == "bireysel finansman":
            score = 100
        elif name in {"aninda finansman", "hizli fon finansmani", "kolay fon finansmani"}:
            score = 90
        elif "ihtiyac finansmani" in name and not any(
            special in name for special in ("egitim", "enerya", "hac", "umre", "seyahat")
        ):
            score = 80
        direct_scores.append((score, idx))

    direct_scores.sort(reverse=True)
    if direct_scores and direct_scores[0][0] > 0:
        return group.loc[direct_scores[0][1]], True
    return _best_product_row(group, query, family), False


def _maturity_fit(row, maturity: int | None) -> str | None:
    if maturity is None:
        return None
    max_m = pd.to_numeric(pd.Series([row.get("maximum_maturity_months")]), errors="coerce").iloc[0]
    if pd.isna(max_m):
        return "Resmî kayıtta sayısal azami vade yayımlanmadığı için vade uygunluğu kesinleştirilemiyor."
    if int(maturity) <= int(max_m):
        return f"{maturity} ay, yayımlanmış {int(max_m)} aylık azami vade sınırı içinde."
    return f"{maturity} ay, yayımlanmış {int(max_m)} aylık azami vade sınırını aşıyor."


# ---------------------------------------------------------------------------
# Finance natural responses
# ---------------------------------------------------------------------------


def _single_product_answer(
    query: str,
    banks: tuple[str, ...],
    family: str | None,
    amount: float | None,
    maturity: int | None,
) -> FastRouteAnswer | None:
    work = _filter_products(query, banks, family)
    if work.empty:
        return None

    if not banks and not detect_product_hint(query):
        return None

    row = _enrich_row(_best_product_row(work, query, family))
    bank = str(row.get("bank_name"))
    product = str(row.get("product_name"))
    description = _short_product_description(row)
    qn = normalize(query)

    generic_moto_gap = (
        detect_product_hint(query) == "motosiklet"
        and "motosiklet" not in normalize(product)
    )

    # A motorcycle request must never be routed through generic vehicle amount
    # semantics when the bank has no verified motorcycle scope. Albaraka is the
    # explicit exception because its official vehicle page publishes a 125 cc
    # split; handle that rule directly.
    if generic_moto_gap:
        albaraka_scope = _albaraka_motorcycle_scope_answer(row, query)
        if albaraka_scope is not None:
            return albaraka_scope
        lines = [f"### {bank} · {product}"]
        lines.append(
            f"BANSA'nın doğrulanmış kayıtlarında {bank} için ayrı bir **Motosiklet Finansmanı** ürünü/kapsamı bulamadım. "
            "Genel araç finansmanı kurallarını motosiklete otomatik uygulamıyorum."
        )
        url = _source_url(row)
        if url:
            lines.append(f"[Resmî ürün kaynağı]({url})")
        return FastRouteAnswer(
            text="\n\n".join(lines), route="finance_motorcycle_scope_guard",
            answer_mode="finance", finance_result_count=0,
            reasons=("motorcycle_scope_not_verified", "no_vehicle_rule_transplant"),
        )

    # V17 amount semantics: a bare numeric follow-up is not silently treated as
    # the vehicle value. Ask one short clarification instead.
    if family == "arac_finansmani" and amount is not None and not is_compare_query(query):
        semantics = resolve_amount_semantics(
            query, family=family, amount_present=True, compare=False
        )
        if semantics.kind == AmountKind.AMBIGUOUS and maturity is None:
            return _amount_clarification_answer(row, float(amount), query)
        if (
            semantics.kind == AmountKind.REQUESTED_FINANCING_AMOUNT
            and maturity is None
            and not _asks_scenario_calculation(query)
        ):
            return _requested_financing_amount_guard(row, float(amount), query, maturity)

    lines = [f"### {bank} · {product}"]

    # Intent-aware benefit questions use the bank's own benefit section rather
    # than the generic product/fee renderer.
    if _asks_product_benefits(query):
        benefits = _product_benefit_sentences(row)
        if benefits:
            lead = f"{bank} {product} için öne çıkan avantajlar şöyle:"
            lines.append(lead)
            for benefit in benefits:
                lines.append(f"- {benefit}")
            max_m = row.get("maximum_maturity_months")
            if _present(max_m) and not any(str(int(float(max_m))) in b for b in benefits):
                lines.append(f"**Azami vade:** {int(float(max_m))} ay.")
            url = _source_url(row)
            if url:
                lines.append(f"[Resmî ürün kaynağı]({url})")
            return FastRouteAnswer(
                text="\n\n".join(lines), route="finance_product_benefits",
                answer_mode="finance", finance_result_count=1,
                reasons=("intent_aware_product_benefits", "official_benefit_section"),
            )

    # Broad overview: answer like an assistant, not a database dump. Put the
    # useful decision facts first and keep detailed pricing caveats for explicit
    # rate questions.
    if description:
        lines.append(description)

    if family == "arac_finansmani" and _vehicle_bands(row) and amount is None:
        lines.extend(_vehicle_overview_summary(row, query))
    else:
        if maturity is not None:
            fit = _maturity_fit(row, maturity)
            if fit:
                lines.append("**Vade açısından:** " + fit)
        elif _present(row.get("maximum_maturity_months")):
            lines.append(f"**Azami vade:** {int(float(row.get('maximum_maturity_months')))} ay.")

    rate_summary = _simple_rate_overview(row)
    if rate_summary:
        lines.append(rate_summary)

    # Fees are useful for an "özellikler" question, but not every casual
    # "nasıl?" turn. This keeps the first answer short and decision-oriented.
    if "ozellik" in qn or "masraf" in qn or "ucret" in qn:
        fee = _natural_fee_overview(row)
        if fee:
            lines.append(fee)

    eligibility = _eligibility_feature(row)
    if eligibility and ("kimler" in qn or "kaps" in qn or "ozellik" in qn):
        lines.append("**Kimler/neyi kapsıyor?** " + eligibility)

    application = _application_feature(row)
    if application and any(x in qn for x in ("basvuru", "nasil", "ozellik")):
        lines.append("**Başvuru:** " + application)

    # Historical examples are intentionally omitted from broad product
    # overviews. They belong to a scenario/calculation question and otherwise
    # make the answer look like a database record.

    url = _source_url(row)
    if url:
        lines.append(f"[Resmî ürün kaynağı]({url})")

    return FastRouteAnswer(
        text="\n\n".join(x for x in lines if str(x).strip()),
        route="finance_product_conversation",
        answer_mode="finance",
        finance_result_count=1,
        reasons=("intent_aware_product_overview", "critical_facts_first", "no_historical_example_dump"),
    )


def _variant_label(value: str) -> str:
    key = normalize(value).replace(" ", "_")
    labels = {
        "sigortali": "Sigortalı",
        "sigortasiz": "Sigortasız",
        "ilk_konut_sigortali": "İlk konut · sigortalı",
        "ilk_konut_sigortasiz": "İlk konut · sigortasız",
        "2el_konut": "İkinci el konut",
        "sifir_konut": "Sıfır konut",
        "0km": "0 km",
        "0_km": "0 km",
        "2el": "2. el",
        "2_el": "2. el",
        "2el_binek": "2. el",
        "yeni_binek": "0 km",
        "0km_sigortali": "0 km · Sigortalı",
        "0km_sigortasiz": "0 km · Sigortasız",
        "2el_sigortali": "2. el · Sigortalı",
        "2el_sigortasiz": "2. el · Sigortasız",
        "standard": "Standart",
        "standart": "Standart",
        "ilk_ev": "İlk ev",
        "mevcut_konut": "Mevcut konut",
    }
    return labels.get(key, str(value or "standart").replace("_", " ").strip().title())


def _single_bank_exact_answer(query: str, row, records: list[dict], amount: float, maturity: int) -> FastRouteAnswer:
    row = _enrich_row(row)
    bank = str(row.get("bank_name"))
    product = str(row.get("product_name"))
    qn = normalize(query)
    explicit_vehicle_status = any(
        marker in qn
        for marker in ("0 km", "sifir km", "sifir arac", "2 el", "ikinci el", "2.el")
    )

    # Collapse 0 km / 2.el rows when the user did not ask for vehicle status
    # and the verified financial result is identical.  Türkiye Finans, for
    # example, publishes the same insured curve for both vehicle statuses.
    # Showing both and then calling one a "winner" with 0 TL difference is
    # deterministic but conversationally wrong.
    display_records: list[tuple[dict, str]] = []
    seen = set()
    for rec in records:
        raw_variant = str(rec.get("variant") or "standard")
        label = _variant_label(raw_variant) if raw_variant not in {"", "standard", "nan"} else "Standart"
        if not explicit_vehicle_status:
            label = re.sub(
                r"\b(?:0\s*km|2\.?\s*el|ikinci\s*el|yeni\s*binek)\b",
                "",
                label,
                flags=re.I,
            ).strip(" ·|/-") or "Standart"
            if normalize(label) == "sigortali":
                label = "Sigortalı"
            elif normalize(label) == "sigortasiz":
                label = "Sigortasız"
        key = (
            normalize(label),
            str(rec.get("rate")),
            str(rec.get("monthly")),
            str(rec.get("total")),
            str(rec.get("fees")),
        )
        if key in seen:
            continue
        seen.add(key)
        display_records.append((rec, label))

    lines = [
        f"### {bank} · {product}",
        f"{_fmt_money(amount)} için **{maturity} ay** vadede BANSA'nın birebir doğruladığı hesaplama "
        + ("sonuçları şöyle:" if len(display_records) > 1 else "sonucu şöyle:"),
    ]
    for rec, label in display_records:
        variant_label = "" if label == "Standart" else f" **{label}** seçenekte"
        fee = _fmt_money(rec.get("fees")) if _present(rec.get("fees")) else "ücret kapsamı tam doğrulanmamış"
        lines.append(
            f"- {variant_label.strip() + ': ' if variant_label else ''}kâr payı **{_fmt_rate(rec.get('rate'))}**, "
            f"aylık taksit **{_fmt_money(rec.get('monthly'))}**, toplam geri ödeme **{_fmt_money(rec.get('total'))}**; {fee}."
        )

    if len(display_records) >= 2:
        sortable = [r for r, _label in display_records if _present(r.get("total"))]
        sortable.sort(key=lambda r: float(r.get("total")))
        if len(sortable) >= 2 and abs(float(sortable[1]["total"]) - float(sortable[0]["total"])) > 0.01:
            best = sortable[0]
            diff = float(sortable[1]["total"]) - float(best["total"])
            lines.append(
                f"Bu doğrulanmış seçenekler içinde toplam geri ödemesi daha düşük olan **{_variant_label(str(best.get('variant') or 'standart'))}** seçenek; "
                f"fark yaklaşık **{_fmt_money(diff)}**. Ücret/sigorta kapsamı farklıysa bunu nihai toplam maliyet farkı olarak yorumlamamak gerekir."
            )

    sources = []
    for rec in records:
        url = str(rec.get("source_url") or "").strip()
        if url and url not in sources:
            sources.append(url)
    if sources:
        lines.append("\n" + " · ".join(f"[Resmî hesaplama kaynağı]({url})" for url in sources))

    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="finance_calculate",
        answer_mode="finance",
        finance_result_count=len(records),
        reasons=("natural_exact_verified_finance", "no_llm_required"),
    )



def _projection_mode_label(rec: ScenarioProjection) -> str:
    if rec.mode == "official_pricing_table_model":
        return "resmî fiyatlama tablosu"
    if rec.mode == "verified_same_maturity_projection":
        return "aynı vadede doğrulanmış resmî hesaplama aracı sonucu"
    if rec.mode == "bansa_managed_calculator_model":
        return "BANSA resmî kaynak modeli"
    if rec.mode == "official_calculator_snapshot_model":
        return "resmî hesaplama ekranı snapshotı"
    if rec.mode == "official_visible_calculator_rate_model":
        return "resmî hesaplama ekranındaki görünür oran"
    if rec.mode == "calculator_input_rate_model":
        return "resmî hesaplama aracındaki senaryo oranı"
    if rec.mode == "official_calculator_reference_model":
        return "resmî hesaplama aracı kaynak modeli"
    return "BANSA hesaplama modeli"


def _projection_fee_text(rec: ScenarioProjection) -> str:
    parts: list[str] = []
    if rec.allocation_fee_rate is not None:
        parts.append(
            f"tahsis %{str(rec.allocation_fee_rate).replace('.', ',')} → {_fmt_money(rec.allocation_fee)}"
        )
    elif rec.allocation_fee is not None:
        parts.append(f"tahsis {_fmt_money(rec.allocation_fee)}")
    if rec.appraisal_fee is not None:
        parts.append(f"ekspertiz referansı/asgarisi {_fmt_money(rec.appraisal_fee)}")
    if rec.mortgage_fee is not None:
        parts.append(f"ipotek referansı/asgarisi {_fmt_money(rec.mortgage_fee)}")
    return " · ".join(parts)


def _dedupe_projection_records(records: Iterable[ScenarioProjection]) -> list[tuple[ScenarioProjection, list[str]]]:
    grouped: dict[tuple[str, str, str], tuple[ScenarioProjection, list[str]]] = {}
    for rec in records:
        key = (
            str(rec.profit_share_rate),
            str(rec.monthly_installment),
            str(rec.installment_total),
        )
        label = _variant_label(rec.variant)
        if key not in grouped:
            grouped[key] = (rec, [label])
        elif label not in grouped[key][1]:
            grouped[key][1].append(label)
    return list(grouped.values())


def _single_bank_projection_answer(
    row,
    records: Iterable[ScenarioProjection],
    amount: float,
    maturity: int,
) -> FastRouteAnswer:
    row = _enrich_row(row)
    bank = str(row.get("bank_name"))
    product = str(row.get("product_name"))
    deduped = _dedupe_projection_records(records)

    lines = [
        f"### {bank} · {product}",
        f"**{_fmt_money(amount)} / {maturity} ay** için birebir kaydedilmiş bir hesaplama satırı yok; "
        "ancak BANSA aynı vade için bankanın doğrulanmış hesaplama verisini veya resmî fiyatlama tablosunu kullanarak "
        "bu senaryoyu deterministik olarak hesaplayabiliyor.",
    ]

    for rec, labels in deduped:
        variant = " / ".join(labels)
        method = _projection_mode_label(rec)
        sentence = (
            f"- **{variant}:** kâr payı **{_fmt_rate(rec.profit_share_rate)}**, "
            f"hesaplanan aylık taksit **{_fmt_money(rec.monthly_installment)}**, "
            f"{maturity} aylık taksit toplamı **{_fmt_money(rec.installment_total)}**. "
            f"Dayanak: {method}."
        )
        fees = _projection_fee_text(rec)
        if fees:
            sentence += " Masraf kuralı: " + fees + "."
        lines.append(sentence)

    if any(rec.mode in {"bansa_managed_calculator_model", "official_calculator_snapshot_model", "official_visible_calculator_rate_model", "calculator_input_rate_model", "official_calculator_reference_model"} for rec, _ in deduped):
        lines.append(
            "**Not:** BANSA hesapladı; bu bir canlı banka teklifi değildir. Resmî kaynak/hesaplama ekranı arka planda "
            "dayanak olarak tutulur, kâr payı oranına göre aylık taksit ve toplam ödeme içeride hesaplanır. "
            "V43 oran kalibrasyonunda banka ekran görüntüsü/snapshotı esas alınan kayıtlar açıkça snapshot olarak etiketlenir; nihai oran, masraf, belge ve onay koşulları banka değerlendirmesine göre değişebilir."
        )
    elif any(rec.mode == "verified_same_maturity_projection" for rec, _ in deduped):
        lines.append(
            "**Not:** Bu bir canlı banka teklifi değildir. Aynı vadede resmî hesaplama aracından doğrulanmış oran/taksit yapısı "
            "istenen tutara uygulanmıştır; banka tutara göre fiyatlamayı değiştirirse başvuru anındaki sonuç farklılaşabilir."
        )
    elif any(rec.mode == "official_pricing_table_model" for rec, _ in deduped):
        lines.append(
            "**Not:** Hesap, bankanın resmî fiyatlama tablosunda bu vade için yayımladığı kâr payı oranıyla yapılmıştır; "
            "sigorta/ekspertiz gibi başvuruya özel maliyetler ayrıca değişebilir."
        )

    urls: list[str] = []
    for rec, _ in deduped:
        if rec.source_url and rec.source_url not in urls:
            urls.append(rec.source_url)
    if not urls:
        url = _source_url(row)
        if url:
            urls.append(url)
    if urls:
        lines.append("\n" + " · ".join(f"[Resmî dayanak]({url})" for url in urls))

    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="finance_scenario_projection",
        answer_mode="finance",
        finance_result_count=len(deduped),
        reasons=("same_maturity_verified_projection", "official_table_or_calculator_evidence", "no_llm_required"),
    )


def _projection_compare_answer(
    rows: list,
    projection_by_bank: dict[str, tuple[ScenarioProjection, ...]],
    amount: float,
    maturity: int,
    family_title: str,
    exact_by_bank: dict[str, list[dict]] | None = None,
) -> FastRouteAnswer:
    """Render one mixed exact + official-table comparison.

    V16 rule:
    A bank with an exact/live calculator result must never disappear merely
    because another bank is being answered from a current official pricing
    table.  Housing comparisons commonly mix these evidence modes.
    """
    exact_by_bank = exact_by_bank or {}

    lines = [
        f"### {family_title} karşılaştırması",
        f"İstediğiniz senaryo: **{_fmt_money(amount)} / {maturity} ay**.",
        "Bankaları aynı tutar ve vadede karşılaştırıyorum. Önce bankanın kendi hesaplama aracından doğrulanan sonucu kullanıyorum; "
        "bu mümkün değilse yalnız güncel resmî oranı bulunan ürünlerde BANSA hesabını açıkça etiketleyerek gösteriyorum.",
    ]

    # Ranking pool is normalized to dictionaries so exact live-calculator and
    # official-table projections can coexist without dropping either source.
    best_candidates: list[dict] = []

    for row in rows:
        bank = str(row.get("bank_name"))
        live_records = exact_by_bank.get(bank, [])
        projections = projection_by_bank.get(bank, tuple())
        if not live_records and not projections:
            continue

        lines.append(f"**{bank}:**")
        bank_candidates: list[dict] = []

        if live_records:
            for rec in _comparison_display_records(live_records):
                label = str(rec.get("display_variant") or _variant_label(str(rec.get("variant") or "standard")))
                sentence = (
                    f"- {label}: kâr payı **{_fmt_rate(rec.get('rate'))}**, aylık **{_fmt_money(rec.get('monthly'))}**, "
                    f"toplam geri ödeme **{_fmt_money(rec.get('total'))}** "
                    "**(resmî canlı/birebir hesaplama)**."
                )
                fee_parts = []
                if _present(rec.get("allocation_fee")):
                    fee_parts.append("tahsis " + _fmt_money(rec.get("allocation_fee")))
                if _present(rec.get("appraisal_fee")):
                    fee_parts.append("ekspertiz " + _fmt_money(rec.get("appraisal_fee")))
                if _present(rec.get("mortgage_fee")):
                    fee_parts.append("ipotek " + _fmt_money(rec.get("mortgage_fee")))
                if _present(rec.get("fees")):
                    fee_parts.append("ücretler toplamı " + _fmt_money(rec.get("fees")))
                if fee_parts:
                    sentence += " " + " · ".join(fee_parts) + "."
                lines.append(sentence)

                if _present(rec.get("monthly")) and _present(rec.get("total")):
                    bank_candidates.append({
                        "bank_name": bank,
                        "variant": label,
                        "monthly": float(rec.get("monthly")),
                        "total": float(rec.get("total")),
                        "source_mode": "live_exact",
                    })

        if projections:
            for rec, labels in _dedupe_projection_records(projections):
                variant = " / ".join(labels)
                method = _projection_mode_label(rec)
                sentence = (
                    f"- {variant}: kâr payı **{_fmt_rate(rec.profit_share_rate)}**, aylık **{_fmt_money(rec.monthly_installment)}**, "
                    f"taksit toplamı **{_fmt_money(rec.installment_total)}** ({method})."
                )
                fees = _projection_fee_text(rec)
                if fees:
                    sentence += " " + fees + "."
                lines.append(sentence)
                bank_candidates.append({
                    "bank_name": bank,
                    "variant": variant,
                    "monthly": float(rec.monthly_installment),
                    "total": float(rec.installment_total),
                    "source_mode": rec.mode,
                })

        if bank_candidates:
            best_candidates.append(min(bank_candidates, key=lambda x: x["total"]))

    resolved_banks = set(exact_by_bank) | set(projection_by_bank)
    missing = [
        str(row.get("bank_name"))
        for row in rows
        if str(row.get("bank_name")) not in resolved_banks
    ]
    if missing:
        lines.append(
            "**Bu senaryoda güncel sayısal sonucu doğrulayamadığım bankalar:** "
            + ", ".join(missing)
            + ". Bu bankaları eski snapshot veya başka tutardaki örnekle doldurmuyorum."
        )

    if len(best_candidates) >= 2:
        best_candidates.sort(key=lambda x: x["total"])
        best = best_candidates[0]
        second = best_candidates[1]
        diff = second["total"] - best["total"]
        lines.append(
            f"**Senaryo yorumu:** mevcut güncel ve doğrulanmış varyantlar içinde toplam geri ödemesi en düşük görünen "
            f"**{best['bank_name']} · {_fmt_money(best['total'])}**. En yakın banka sonucuyla fark yaklaşık "
            f"**{_fmt_money(diff)}**."
        )
        lines.append(
            "Ürün varyantı, sigorta/kasko, masraf ve bankaya özel değerlendirme koşulları değişebildiği için "
            "bu yorumu yalnız yukarıda açıkça gösterilen varyantlar arasında okuyorum."
        )

    urls: list[str] = []
    for records in exact_by_bank.values():
        for rec in records:
            url = str(rec.get("source_url") or "").strip()
            if url and url not in urls:
                urls.append(url)
    for recs in projection_by_bank.values():
        for rec in recs:
            if rec.source_url and rec.source_url not in urls:
                urls.append(rec.source_url)
    if urls:
        lines.append(
            "**Resmî hesaplama/fiyatlama dayanakları:** "
            + " · ".join(f"[Kaynak {i+1}]({url})" for i, url in enumerate(urls))
        )

    count = sum(len(_comparison_display_records(v)) for v in exact_by_bank.values())
    count += sum(len(_dedupe_projection_records(v)) for v in projection_by_bank.values())

    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="finance_compare",
        answer_mode="finance",
        finance_result_count=count,
        reasons=("mixed_live_and_projection_compare", "calculator_or_official_table", "graceful_numeric_answer"),
    )


def _verified_maturity_for_row(row) -> int | None:
    """Bir ürün için doğrulanmış (verified) bir senaryonun bulunduğu bir vade
    döner (varsa). Kullanıcı vade belirtmediğinde, azami vadeye kör bir
    şekilde düşmek yerine, gerçek bir hesaplama yapabileceğimiz bir vadeyi
    tercih etmek için kullanılır.
    """
    try:
        from src.finance_scenario_projection import get_verified_finance_scenarios
    except Exception:
        return None
    try:
        product_id = int(row.get("id"))
    except (TypeError, ValueError):
        return None
    scenarios = get_verified_finance_scenarios()
    work = scenarios[scenarios["product_id"].eq(product_id)].copy()
    if work.empty:
        return None
    status = work["scenario_status"].astype(str).str.casefold()
    work = work[status.str.contains("verified", na=False)]
    if work.empty:
        return None
    maturities = pd.to_numeric(work["input_maturity_months"], errors="coerce").dropna()
    if maturities.empty:
        return None
    return int(maturities.iloc[0])


def _common_default_maturity(direct_rows: list[tuple[pd.Series, bool]], family: str) -> int | None:
    """Choose one common comparison maturity when the user omitted maturity.

    V45 fixes a critical presentation bug where each bank silently used a
    different historical verified maturity while the heading displayed one
    bank's maximum term.  We now choose a single, derived family maturity and
    send that exact term to every bank.
    """
    from collections import Counter

    values: list[int] = []
    for row, is_direct in direct_rows:
        if family == "ihtiyac_finansmani" and not is_direct:
            continue
        raw = row.get("maximum_maturity_months")
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            continue
        if value > 0:
            values.append(value)
    if not values:
        return None
    counts = Counter(values)
    # Most commonly published maximum term; if tied, prefer the longer term.
    return max(counts, key=lambda value: (counts[value], value))


def _scenario_recommendation_block(
    query: str,
    exact_blocks: list[tuple[pd.Series, list[dict]]],
    projected_blocks: list[tuple[pd.Series, tuple[ScenarioProjection, ...]]],
    amount: float | None,
    maturity: int | None,
) -> list[str]:
    """Build an explainable recommendation from *comparable verified* rows only.

    Recommendation is deliberately presentation-only.  It never manufactures a
    rate or payment and never lets a stale/unverified bank enter the ranking.
    The three core metrics are shown separately so the user can see whether the
    same bank actually wins on rate, monthly payment and repayment total.
    """
    if not _asks_for_recommendation(query) or amount is None or maturity is None:
        return []

    candidates: list[dict] = []

    for row, records in exact_blocks:
        bank = str(row.get("bank_name") or "Banka")
        for rec in records:
            if not all(_present(rec.get(k)) for k in ("rate", "monthly", "total")):
                continue
            candidates.append({
                "bank_name": bank,
                "variant": str(rec.get("variant") or "standard"),
                "rate": float(rec.get("rate")),
                "monthly": float(rec.get("monthly")),
                "total": float(rec.get("total")),
                "source_mode": "live" if str(rec.get("freshness_mode") or "") == "live_calculator" else "exact",
            })

    for row, projections in projected_blocks:
        bank = str(row.get("bank_name") or "Banka")
        for rec in projections:
            if rec.profit_share_rate is None or rec.monthly_installment is None or rec.installment_total is None:
                continue
            candidates.append({
                "bank_name": bank,
                "variant": str(rec.variant or "standard"),
                "rate": float(rec.profit_share_rate),
                "monthly": float(rec.monthly_installment),
                "total": float(rec.installment_total),
                "source_mode": "official_table",
            })

    if len(candidates) < 2:
        return [
            "### BANSA önerisi",
            "Bu senaryoda en az iki bankanın aynı tutar/vadede güncel ve karşılaştırılabilir sayısal sonucu olmadığı için tek bir bankayı **en mantıklı seçenek** diye önermiyorum."
        ] if candidates else []

    # Collapse duplicate financial variants so an identical 0 km / 2. el row
    # does not count as two separate recommendation candidates.
    unique: dict[tuple, dict] = {}
    for c in candidates:
        key = (
            normalize(c["bank_name"]),
            round(c["rate"], 8), round(c["monthly"], 2), round(c["total"], 2),
        )
        if key not in unique:
            unique[key] = c
    candidates = list(unique.values())

    monthly_cap = _extract_monthly_payment_cap(query)
    rankable = candidates
    if monthly_cap is not None:
        affordable = [c for c in candidates if c["monthly"] <= float(monthly_cap) + 0.01]
        if not affordable:
            closest = min(candidates, key=lambda c: (c["monthly"], c["total"], c["rate"]))
            excess = max(0.0, float(closest["monthly"]) - float(monthly_cap))
            return [
                "### BANSA önerisi",
                f"Aylık ödeme sınırınız **{_fmt_money(monthly_cap)}**. Aynı tutar/vadede doğrulanabilen seçeneklerin hiçbiri bu sınırın altında kalmıyor.",
                f"**Sınıra en yakın seçenek:** **{closest['bank_name']}** — aylık **{_fmt_money(closest['monthly'])}**; bütçenizi yaklaşık **{_fmt_money(excess)}** aşıyor.",
                "Bu nedenle bütçe sınırınızı aşan bir bankayı 'en uygun' diye önermiyorum; daha uzun uygun bir vade varsa onu veya daha düşük finansman tutarını değerlendirmek gerekir.",
            ]
        rankable = affordable

    lowest_rate = min(rankable, key=lambda c: (c["rate"], c["total"], c["monthly"]))
    lowest_monthly = min(rankable, key=lambda c: (c["monthly"], c["total"], c["rate"]))
    lowest_total = min(rankable, key=lambda c: (c["total"], c["monthly"], c["rate"]))

    def plain_label(c: dict) -> str:
        variant = str(c.get("variant") or "standard")
        suffix = "" if normalize(variant) in {"", "standard", "standart", "nan"} else f" ({_variant_label(variant)})"
        return f"{c['bank_name']}{suffix}"

    def label(c: dict) -> str:
        return f"**{plain_label(c)}**"

    metric_wins: dict[str, int] = {}
    for winner in (lowest_rate, lowest_monthly, lowest_total):
        key = str(winner["bank_name"])
        metric_wins[key] = metric_wins.get(key, 0) + 1

    # Respect the user's stated decision criterion. If monthly payment is the
    # explicit goal, monthly payment owns the recommendation; otherwise total
    # repayment remains the default overall-cost criterion.
    recommendation = lowest_monthly if _prefers_low_monthly(query) else lowest_total
    same_bank_all = len({lowest_rate["bank_name"], lowest_monthly["bank_name"], lowest_total["bank_name"]}) == 1

    source_note = {
        "live": "banka hesaplama aracından doğrulanan sonuç",
        "exact": "aynı tutar ve vadede doğrulanan sonuç",
        "official_table": "resmî banka oranına göre BANSA hesabı",
    }.get(str(recommendation.get("source_mode")), "kaynağı doğrulanmış sonuç")

    lines = ["### BANSA önerisi"]
    if monthly_cap is not None:
        lines.append(f"Aylık **{_fmt_money(monthly_cap)}** bütçe sınırınıza uyan doğrulanmış seçenekleri kendi içinde karşılaştırdım.")
    lines.append(
        f"- **En düşük kâr payı:** {label(lowest_rate)} — **{_fmt_rate(lowest_rate['rate'])}**."
    )
    lines.append(
        f"- **En düşük aylık taksit:** {label(lowest_monthly)} — **{_fmt_money(lowest_monthly['monthly'])}**."
    )
    lines.append(
        f"- **En düşük toplam geri ödeme:** {label(lowest_total)} — **{_fmt_money(lowest_total['total'])}**."
    )

    if same_bank_all:
        lines.append(
            f"**Bu nedenle, yalnız doğrulanmış sayısal maliyetleri esas alırsam benim ilk tercihim {plain_label(recommendation)} olur.** "
            f"Bu seçenek üç temel ölçütte de öne çıkıyor ve sonucu **{source_note}** ile destekleniyor."
        )
    else:
        wins = metric_wins.get(str(recommendation["bank_name"]), 0)
        if _prefers_low_monthly(query):
            lines.append(
                f"**Aylık ödeme önceliğinize göre ilk tercihim {plain_label(recommendation)} olur**, çünkü {_fmt_money(amount)} / {maturity} ay senaryosunda "
                f"doğrulanmış seçenekler içindeki en düşük aylık taksiti veriyor. Bu banka üç temel ölçütün **{wins}/3** tanesinde lider."
            )
        else:
            lines.append(
                f"**Genel maliyet açısından ilk tercihim {plain_label(recommendation)} olur**, çünkü {_fmt_money(amount)} / {maturity} ay senaryosunda "
                f"doğrulanmış seçenekler içindeki en düşük toplam geri ödemeyi veriyor. Bu banka üç temel ölçütün **{wins}/3** tanesinde lider."
            )

    family = detect_family(query)
    if family == "konut_finansmani":
        caveat = "Ekspertiz, ipotek, sigorta, tahsis ücreti, konutun niteliği ve müşteri profiline göre değişen ek maliyetler nihai tercihi değiştirebilir."
    elif family == "arac_finansmani":
        caveat = "Araç değeri, sıfır/ikinci el durumu, sigorta, rehin/tahsis ücretleri ve müşteri profiline göre nihai maliyet değişebilir."
    elif family == "ihtiyac_finansmani":
        caveat = "Tahsis ücreti, sigorta, ürün koşulları ve müşteri profiline göre nihai maliyet değişebilir."
    else:
        caveat = "Ürün masrafları ve müşteri profiline göre nihai maliyet değişebilir."
    lines.append(
        "**Not:** Bu öneri aynı tutar/vadede doğrulanabilen sayısal sonuçlara dayanır. " + caveat
    )
    return lines


def _multi_bank_options_answer(query: str, family: str, amount: float | None, maturity: int | None) -> FastRouteAnswer | None:
    work = _filter_products(query, tuple(), family)
    if work.empty:
        return None

    direct_rows: list[tuple[pd.Series, bool]] = []
    for _, group in work.groupby("bank_name", sort=False):
        row, is_direct = _direct_family_product(group, family, query)
        if row is not None:
            direct_rows.append((_enrich_row(row), is_direct))

    exact_blocks: list[tuple[pd.Series, list[dict]]] = []
    projected_blocks: list[tuple[pd.Series, tuple[ScenarioProjection, ...]]] = []
    live_unavailable_banks: set[str] = set()
    common_default_maturity = _common_default_maturity(direct_rows, family) if maturity is None else None
    if amount is not None:
        for row, is_direct in direct_rows:
            if not is_direct and family == "ihtiyac_finansmani":
                continue

            # BANSA_CALC_DEFAULT_MATURITY_V1: kullanıcı vade belirtmediyse
            # (örn. "500 bin TL araba almak istiyorum, finansman öner"),
            # hesaplamayı tamamen atlayıp "dinamik" demek yerine, o bankanın
            # bu ürün için yayımladığı azami vadeyi varsayılan alıp projeksiyon
            # dener. Bu, banka taahhüdü olarak DEĞİL, açıkça "varsayılan vade"
            # notuyla sunulur; kullanıcı isterse farklı bir vade belirtebilir.
            effective_maturity = maturity if maturity is not None else common_default_maturity
            if effective_maturity is None:
                continue

            # V45: one shared authoritative resolver for both dashboard + chatbot.
            # A live-mapped bank must return an exact current calculator result;
            # otherwise BANSA does not expose an older rate as "current".
            resolution = resolve_user_scenario(
                row, float(amount), int(effective_maturity)
            )
            if resolution.mode == "live":
                exact_blocks.append((row, list(resolution.live_records)))
                continue
            if resolution.mode == "model":
                projected_blocks.append((row, tuple(resolution.projections)))
                continue
            if resolution.mode == "live_unavailable":
                live_unavailable_banks.add(str(row.get("bank_name")))
                continue

            # Legacy exact snapshots are allowed only for products without an
            # authoritative live mapping and only through the freshness gate.
            records = _exact_records_for_row(row, amount, effective_maturity)
            if records:
                exact_blocks.append((row, records))

    family_title = {
        "ihtiyac_finansmani": "ihtiyaç finansmanı",
        "konut_finansmani": "konut finansmanı",
        "arac_finansmani": "taşıt/araç finansmanı",
        "alisveris_finansmani": "alışveriş finansmanı",
    }.get(family, "finansman")

    lines = []
    effective_maturity_for_title = maturity if maturity is not None else common_default_maturity

    if amount is not None and (maturity is not None or exact_blocks or projected_blocks):
        maturity_label = (
            f"{maturity} ay"
            if maturity is not None
            else (
                f"{effective_maturity_for_title} ay (varsayılan azami vade)"
                if effective_maturity_for_title is not None
                else "vade belirtilmedi"
            )
        )
        lines.append(
            f"### {_fmt_money(amount)} · {maturity_label} {family_title} seçenekleri"
        )
        if maturity is None and common_default_maturity is not None:
            lines.append(
                f"Vade belirtmediğiniz için bankaları **aynı senaryoda** karşılaştırabilmek adına bu ürün grubunda en yaygın yayımlanmış azami vade olan **{common_default_maturity} ayı** varsayılan aldım. "
                "Her sayısal sonuç gerçekten bu vade için hesaplanmıştır; farklı bir vade isterseniz belirtebilirsiniz."
            )
        if exact_blocks or projected_blocks:
            recommendation_maturity = maturity if maturity is not None else common_default_maturity
            recommendation_lines = _scenario_recommendation_block(
                query, exact_blocks, projected_blocks, amount, recommendation_maturity
            )
            if recommendation_lines:
                lines.extend(recommendation_lines)

            parts = []
            live_block_count = sum(
                1 for _, records in exact_blocks
                if any(str(rec.get("freshness_mode") or "") == "live_calculator" for rec in records)
            )
            snapshot_block_count = len(exact_blocks) - live_block_count
            if live_block_count:
                parts.append(f"{live_block_count} bankadan doğrudan hesaplama sonucu")
            if snapshot_block_count:
                parts.append(f"{snapshot_block_count} bankada aynı tutar/vadede doğrulanmış sonuç")
            if projected_blocks:
                parts.append(f"{len(projected_blocks)} bankada resmî oranlarla BANSA hesabı")
            lines.append(
                "Bu senaryoda " + " ve ".join(parts) + " bulunuyor. "
                "Sonuçların hangi kaynaktan üretildiğini her bankanın yanında belirtiyorum."
            )
            for row, records in exact_blocks:
                bank = str(row.get("bank_name"))
                for rec in records:
                    variant = str(rec.get("variant") or "standard")
                    variant_text = "" if variant in {"", "standard", "nan"} else f" ({_variant_label(variant)})"
                    source_label = (
                        "banka hesaplama aracından doğrulandı"
                        if str(rec.get("freshness_mode") or "") == "live_calculator"
                        else "aynı tutar ve vadede doğrulandı"
                    )
                    lines.append(
                        f"- **{bank}{variant_text}:** kâr payı {_fmt_rate(rec.get('rate'))}, aylık {_fmt_money(rec.get('monthly'))}, toplam {_fmt_money(rec.get('total'))} **({source_label})**."
                    )
            for row, projections in projected_blocks:
                bank = str(row.get("bank_name"))
                for rec, labels in _dedupe_projection_records(projections):
                    variant = " / ".join(labels)
                    variant_suffix = "" if normalize(variant) in {"standard", "standart"} else f" ({variant})"
                    lines.append(
                        f"- **{bank}{variant_suffix}:** kâr payı {_fmt_rate(rec.profit_share_rate)}, aylık {_fmt_money(rec.monthly_installment)}, "
                        f"toplam geri ödeme {_fmt_money(rec.installment_total)} **(resmî banka verisine göre BANSA hesapladı)**."
                    )
        else:
            lines.append(
                "Bu tutar ve vade için karşılaştırılabilir güncel sayısal sonuç doğrulanamadı. "
                "Tahmini taksit üretmek yerine bankaların yayımladığı ürün koşullarını gösteriyorum."
            )
    else:
        lines.append(f"### {family_title.title()} seçenekleri")

    direct_other = []
    specialized = []
    exact_banks = {str(row.get("bank_name")) for row, _ in exact_blocks}
    exact_banks.update(str(row.get("bank_name")) for row, _ in projected_blocks)
    exact_banks.update(live_unavailable_banks)
    for row, is_direct in direct_rows:
        bank = str(row.get("bank_name"))
        if bank in exact_banks:
            continue
        if not is_direct and family == "ihtiyac_finansmani":
            specialized.append(bank)
            continue
        direct_other.append(row)

    if live_unavailable_banks:
        lines.append(
            "**Resmî hesaplama aracı bulunan ancak bu çalıştırmada anlık sonuç doğrulanamayan bankalar:** "
            + ", ".join(sorted(live_unavailable_banks))
            + ". Bu bankaların hesaplama aracı BANSA'da eşleştirilmiştir; yalnızca o anki exact tutar/vade sonucu doğrulanamadığı için yanlış veya eski rakam göstermeden sayısal sıralamanın dışında tutuyorum."
        )

    if direct_other:
        lines.append("**Diğer doğrudan seçenekler:**")
        for row in direct_other:
            maturity_text = _fmt_maturity(row.get("maximum_maturity_months"), row.get("maturity_rules_text"))
            rate_text = _fmt_rate(row.get("profit_share_rate"), row.get("profit_share_rate_text"))
            fit = _maturity_fit(row, maturity)

            maturity_norm = normalize(str(maturity_text or ""))
            if any(x in maturity_norm for x in ("sayisal vade yayimlanmamis", "sayisal vade yayinlanmamis", "belirtilmemis")):
                maturity_public = "banka sayfasında net vade belirtilmiyor"
            else:
                maturity_public = str(maturity_text).strip()

            pricing_text = str(rate_text or "").strip()
            pricing_norm = normalize(pricing_text)
            if pricing_norm.startswith("fiyatlama "):
                pricing_text = pricing_text[len("Fiyatlama "):].strip()
                pricing_norm = normalize(pricing_text)
            if "hesaplama aracinda dinamik" in pricing_norm or "hesaplama aracinda senaryoya gore" in pricing_norm:
                pricing_public = "banka hesaplama aracında belirleniyor"
            elif "sayisal oran yayimlanmamis" in pricing_norm or "sayisal oran yayinlanmamis" in pricing_norm:
                pricing_public = "güncel oran için bankadan teklif alınmalı"
            elif "kisiye ozel" in pricing_norm:
                pricing_public = "kişiye özel teklif"
            else:
                pricing_public = pricing_text

            sentence = (
                f"- **{row.get('bank_name')} – {row.get('product_name')}:** "
                f"vade: {maturity_public}; kâr payı/fiyatlama: {pricing_public}."
            )
            if fit and "içinde" in fit:
                sentence += f" {fit}"
            # Do not show a 100k/36-month reference under a different user
            # scenario. It is technically useful for QA but confuses end users.
            lines.append(sentence)

    if specialized:
        lines.append(
            "**Amaç bazlı ürünler:** " + ", ".join(sorted(set(specialized))) +
            " tarafında ihtiyaç ailesinde eğitim, seyahat, teknoloji vb. özel amaçlı ürünler bulunuyor. "
            "Genel ihtiyaç finansmanı ile birebir aynı ürün olmadığı için bunları doğrudan maliyet rakibi gibi sıralamıyorum."
        )

    if amount is not None and maturity is not None:
        lines.append(
            "**Not:** Sayısal karşılaştırmaya yalnız seçtiğiniz tutar ve vadeyle uyumlu, kaynağı doğrulanmış sonuçlar dahil edilir."
        )

    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="finance_options",
        answer_mode="finance",
        finance_result_count=len(direct_rows),
        reasons=("natural_finance_options", "tiered_exact_then_catalog", "no_invented_numbers"),
    )


def _superlative_maturity_answer(query: str, family: str | None) -> FastRouteAnswer | None:
    work = _filter_products(query, tuple(), family)
    if work.empty:
        return None
    vals = pd.to_numeric(work["maximum_maturity_months"], errors="coerce")
    known = work[vals.notna()].copy()
    if known.empty:
        return None
    known["_m"] = pd.to_numeric(known["maximum_maturity_months"], errors="coerce")
    maximum = int(known["_m"].max())
    leaders = known[known["_m"].eq(maximum)].copy()

    # Keep one relevant product per bank.
    selected = []
    for _, group in leaders.groupby("bank_name", sort=False):
        selected.append(_enrich_row(_best_product_row(group, query, family)))

    names = ", ".join(str(r.get("bank_name")) for r in selected)
    hint = detect_product_hint(query)
    product_label = "motosiklet finansmanında" if hint == "motosiklet" else "bu finansman grubunda"
    lines = [
        f"### En uzun vade: {maximum} ay",
        f"BANSA'daki yayımlanmış ürün koşullarına göre {product_label} en yüksek genel vade **{maximum} ay**. "
        f"Bu üst sınırı **{names}** sunuyor.",
    ]

    if hint == "motosiklet":
        lines.append(
            "Buradaki **48 ay genel üst sınırdır**; motosikletin fatura/kasko değeri yükseldikçe bazı bankalarda azami vade 36, 24 veya 12 aya düşebilir. "
            "Bu nedenle belirli bir motosiklet için fiyatı yazarsanız gerçek banda göre ayrıca kontrol ederim."
        )

    sources = []
    for row in selected:
        url = _source_url(row)
        if url and url not in sources:
            sources.append(url)
    if sources:
        lines.append("\n" + " · ".join(f"[Kaynak {i+1}]({url})" for i, url in enumerate(sources)))

    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="finance_superlative",
        answer_mode="finance",
        finance_result_count=len(selected),
        reasons=("natural_superlative", "catalog_numeric_comparison"),
    )


def _comparison_clarification(
    query: str,
    banks: tuple[str, ...],
    family: str | None,
    *,
    amount: float | None = None,
    maturity: int | None = None,
) -> FastRouteAnswer:
    family_label = {
        "konut_finansmani": "konut finansmanını",
        "ihtiyac_finansmani": "ihtiyaç finansmanını",
        "arac_finansmani": "taşıt finansmanını",
    }.get(family, "finansmanı")
    bank_text = " ile ".join(banks)
    missing = []
    if amount is None:
        missing.append("**finansman tutarı**")
    if maturity is None:
        missing.append("**vade**")
    if len(missing) == 2:
        need = "finansman tutarı ve vade"
    else:
        need = missing[0].replace("**", "") if missing else "senaryo bilgileri"
    lines = [
        f"Elbette. **{bank_text}** için {family_label} aynı şartlarda karşılaştırabilirim. Önce **{need}** bilgisini yazmanız gerekiyor.",
        "Kâr payı, aylık taksit ve toplam geri ödeme senaryoya göre değişebildiği için bu bilgileri varsaymıyorum. "
        "Örneğin **500.000 TL / 36 ay** yazabilirsiniz; ardından iki bankayı aynı senaryoda güncel ve doğrulanmış sonuçlarla karşılaştırırım.",
    ]
    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="finance_compare_clarify",
        answer_mode="finance",
        finance_result_count=0,
        reasons=("natural_compare_clarification", "missing_amount_or_maturity"),
    )


def _vehicle_rules_compact(row) -> str | None:
    """Return verified vehicle-value limits without treating finance amount as asset value."""
    bands = [
        band for band in _vehicle_bands(row)
        if band.maximum is not None and band.ratio > 0 and band.maturity > 0
    ]
    if not bands:
        return None

    parts: list[str] = []
    for band in bands:
        ratio_pct = int(round(float(band.ratio) * 100))
        if band.minimum <= 0:
            value_text = f"{_fmt_money(band.maximum)}'ye kadar"
        else:
            value_text = f"{_fmt_money(band.minimum)}–{_fmt_money(band.maximum)}"
        parts.append(f"{value_text} %{ratio_pct}/{band.maturity} ay")
    return "; ".join(parts)


def _comparison_display_records(records: list[dict]) -> list[dict]:
    """Collapse financially identical status variants for human-readable tables.

    Verification rows remain untouched upstream.  This affects presentation
    only: e.g. 0 km and 2. el rows with the same rate/installment/fees become
    one row, while insured vs uninsured pricing stays separate.
    """
    groups: dict[tuple, list[dict]] = {}
    for rec in records:
        signature = tuple(
            None if not _present(rec.get(key)) else round(float(rec.get(key)), 8)
            for key in (
                "rate", "monthly", "total", "allocation_fee",
                "appraisal_fee", "mortgage_fee", "fees",
            )
        )
        groups.setdefault(signature, []).append(rec)

    output: list[dict] = []
    for grouped in groups.values():
        base = dict(grouped[0])
        labels = []
        norm_variants = [normalize(x.get("variant") or "standard") for x in grouped]

        insured = [v for v in norm_variants if "sigortali" in v and "sigortasiz" not in v]
        uninsured = [v for v in norm_variants if "sigortasiz" in v]
        if insured and len(insured) == len(norm_variants):
            display = "Sigortalı"
        elif uninsured and len(uninsured) == len(norm_variants):
            display = "Sigortasız"
        elif len(grouped) > 1:
            for rec in grouped:
                label = _variant_label(str(rec.get("variant") or "standard"))
                if label not in labels:
                    labels.append(label)
            display = " / ".join(labels)
        else:
            variant = str(base.get("variant") or "standard")
            display = "Standart" if variant in {"", "standard", "nan"} else _variant_label(variant)

        base["display_variant"] = display
        base["collapsed_variant_count"] = len(grouped)
        output.append(base)

    return output


def _compare_answer(
    query: str,
    banks: tuple[str, ...],
    family: str | None,
    amount: float | None,
    maturity: int | None,
) -> FastRouteAnswer | None:
    work = _filter_products(query, banks, family)
    if work.empty:
        return None

    # When the user asks a winner between named banks, do not pretend that
    # unlike calculator examples are a fair comparison. Ask for the scenario.
    if len(banks) >= 2 and (amount is None or maturity is None):
        return _comparison_clarification(
            query, banks, family, amount=amount, maturity=maturity
        )

    rows = []
    for _, group in work.groupby("bank_name", sort=False):
        row, _ = _direct_family_product(group, family, query)
        if row is not None:
            rows.append(_enrich_row(row))

    exact_by_bank: dict[str, list[dict]] = {}
    projection_by_bank: dict[str, tuple[ScenarioProjection, ...]] = {}
    if amount is not None and maturity is not None:
        # V17 calculator-first comparison. The same requested financing amount
        # and maturity are sent to each mapped official calculator. A calculator
        # result is accepted only when it is exact and verified.
        for row in rows:
            bank_name = str(row.get("bank_name"))

            resolution = resolve_user_scenario(row, float(amount), int(maturity))
            if resolution.mode == "live":
                exact_by_bank[bank_name] = list(resolution.live_records)
                continue
            if resolution.mode == "model":
                projection_by_bank[bank_name] = tuple(resolution.projections)
                continue
            if resolution.mode == "live_unavailable":
                # Fail closed: do not rank a stale calculator snapshot against
                # another bank's current live quote.
                continue

            records = _exact_records_for_row(row, amount, maturity)
            if records:
                exact_by_bank[bank_name] = records

    family_title = {
        "konut_finansmani": "Konut finansmanı",
        "ihtiyac_finansmani": "İhtiyaç finansmanı",
        "arac_finansmani": "Taşıt finansmanı",
        "alisveris_finansmani": "Alışveriş finansmanı",
    }.get(family, "Finansman")

    # V15 conversational comparison state: the resolved query contains the
    # original scenario plus the current short follow-up. Rank only fresh/live
    # or current official-table records; never stale snapshots.
    qn = normalize(query)
    ranking_records: list[dict] = []
    for bank, records in exact_by_bank.items():
        numeric = [r for r in records if _present(r.get("monthly")) and _present(r.get("total"))]
        if numeric:
            ranking_records.append(min(numeric, key=lambda r: float(r.get("total"))))
    for bank, projections in projection_by_bank.items():
        if bank in exact_by_bank:
            continue
        valid = [p for p in projections if p.monthly_installment is not None and p.installment_total is not None]
        if valid:
            p = min(valid, key=lambda x: float(x.installment_total))
            ranking_records.append({
                "bank_name": bank, "product_name": p.product_name, "variant": p.variant,
                "rate": p.profit_share_rate, "monthly": p.monthly_installment,
                "total": p.installment_total, "source_url": p.source_url,
                "freshness_mode": p.mode,
            })

    if amount is not None and maturity is not None and ranking_records:
        by_total = sorted(ranking_records, key=lambda r: float(r.get("total")))
        by_monthly = sorted(ranking_records, key=lambda r: float(r.get("monthly")))

        if "ikinci en dusuk" in qn or "ikinci en iyi" in qn:
            if len(by_total) >= 2:
                r = by_total[1]
                text=(f"### {family_title} · ikinci en düşük geri ödeme\n\n"
                      f"{_fmt_money(amount)} / {maturity} ay senaryosunda ikinci en düşük doğrulanmış güncel geri ödeme "
                      f"**{r['bank_name']}** tarafında: **{_fmt_money(r['total'])}**.")
            else:
                text=(f"### {family_title} · ikinci sıra\n\n"
                      "Şu anda bu senaryoda yalnız **bir bankanın** güncel fiyatlaması sayısal olarak doğrulanabildiği için "
                      "ikinci sırayı güvenilir biçimde söylemiyorum. Canlı hesaplayıcı sonucu gelmeyen bankaları eski snapshot ile doldurmuyorum.")
            return FastRouteAnswer(
                text=text, route="finance_compare_second", answer_mode="finance",
                finance_result_count=len(by_total), reasons=("comparison_followup_second", "fresh_pricing_only"),
            )

        if "en dusuk aylik" in qn or "aylik taksit hang" in qn:
            if len(by_monthly) < 2:
                return FastRouteAnswer(
                    text=(f"### {family_title} · aylık taksit karşılaştırması\n\n"
                          "Şu anda bu senaryoda yalnız **bir bankanın** güncel aylık taksiti sayısal olarak doğrulanabildiği için "
                          "'en düşük' diye kazanan ilan etmiyorum. Diğer bankaların canlı/güncel sonucu gelmeden eski snapshot ile kıyas yapmıyorum."),
                    route="finance_compare_monthly_unavailable", answer_mode="finance",
                    finance_result_count=len(by_monthly), reasons=("comparison_followup_monthly", "fresh_pricing_only", "insufficient_comparable_banks"),
                )
            r = by_monthly[0]
            return FastRouteAnswer(
                text=(f"### {family_title} · en düşük aylık taksit\n\n"
                      f"{_fmt_money(amount)} / {maturity} ay senaryosunda güncel doğrulanmış sonuçlar içinde en düşük aylık taksit "
                      f"**{r['bank_name']}** tarafında: **{_fmt_money(r['monthly'])}**. Toplam geri ödeme **{_fmt_money(r['total'])}**."),
                route="finance_compare_monthly_winner", answer_mode="finance",
                finance_result_count=len(by_monthly), reasons=("comparison_followup_monthly", "fresh_pricing_only"),
            )

        asks_top3 = any(x in qn for x in (
            "ilk uc", "ilk 3", "en iyi 3", "en mantikli 3", "3 secenek", "uc secenek",
            "3 banka", "uc banka", "ilk ucu", "ilk üçü"
        ))
        if asks_top3:
            top = by_total[:3]
            body_lines = []
            for i, r in enumerate(top, 1):
                reason = "doğrulanmış seçenekler içinde toplam geri ödemesi daha düşük" if i == 1 else "aynı tutar/vadede doğrulanmış sayısal karşılaştırmaya girebildiği için"
                body_lines.append(
                    f"{i}. **{r['bank_name']}** — aylık {_fmt_money(r['monthly'])}, toplam {_fmt_money(r['total'])}. "
                    f"**Neden:** {reason}."
                )
            body = "\n".join(body_lines)
            if len(top) < 3:
                body += (
                    f"\n\n**Neden 3'e tamamlamadım?** Bu senaryoda yalnız **{len(top)} bankanın** güncel ve aynı "
                    "tutar/vadeye ait sayısal fiyatlaması doğrulanabildi. Üçüncü sırayı farklı tutar, eski oran veya tahmini "
                    "hesapla doldurmak doğruluğu düşürürdü; bu yüzden uydurmuyorum."
                )
            return FastRouteAnswer(
                text=f"### {family_title} · güncel doğrulanmış öneri sıralaması\n\n{body}",
                route="finance_compare_top3", answer_mode="finance",
                finance_result_count=len(top), reasons=("comparison_followup_top3", "fresh_pricing_only", "no_forced_third_place"),
            )

        if any(x in qn for x in ("aradaki fark", "fark ne kadar", "farki ne kadar")) and len(banks) >= 2:
            bank_norms = {normalize(b) for b in banks}
            selected = [r for r in by_total if normalize(r.get("bank_name")) in bank_norms]
            if len(selected) >= 2:
                a, b = selected[0], selected[1]
                total_diff = abs(float(a['total']) - float(b['total']))
                monthly_diff = abs(float(a['monthly']) - float(b['monthly']))
                return FastRouteAnswer(
                    text=(f"### {family_title} · fark\n\n"
                          f"**{a['bank_name']}** ile **{b['bank_name']}** arasında toplam geri ödeme farkı yaklaşık "
                          f"**{_fmt_money(total_diff)}**, aylık taksit farkı ise yaklaşık **{_fmt_money(monthly_diff)}**."),
                    route="finance_compare_difference", answer_mode="finance",
                    finance_result_count=2, reasons=("comparison_followup_difference", "fresh_pricing_only"),
                )
            available_names = {normalize(r.get("bank_name")): r.get("bank_name") for r in selected}
            missing = [b for b in banks if normalize(b) not in available_names]
            available = [str(r.get("bank_name")) for r in selected]
            available_text = ", ".join(available) if available else "seçtiğiniz bankalarda"
            missing_text = ", ".join(missing) if missing else "diğer bankada"
            return FastRouteAnswer(
                text=(f"### {family_title} · fark\n\n"
                      f"Bu iki banka arasındaki farkı güvenilir biçimde hesaplayabilmek için ikisinin de aynı senaryoda güncel sayısal sonucu gerekiyor. "
                      f"Şu anda **{available_text}** için güncel sayısal sonuç var; **{missing_text}** için aynı senaryoda güncel aylık taksit/toplam geri ödeme doğrulanamadı. "
                      "Eski snapshot kullanarak fark üretmiyorum."),
                route="finance_compare_difference_unavailable", answer_mode="finance",
                finance_result_count=len(selected), reasons=("comparison_followup_difference", "fresh_pricing_only", "safe_abstention"),
            )

        asks_repayment_winner = (
            "geri odeme" in qn and any(marker in qn for marker in ("en dusuk", "hangisi", "hangi banka", "daha iyi"))
        ) or "hangisinin toplam" in qn
        if asks_repayment_winner:
            if len(by_total) < 2:
                return FastRouteAnswer(
                    text=(f"### {family_title} · geri ödeme karşılaştırması\n\n"
                          "Şu anda bu senaryoda yalnız **bir bankanın** güncel toplam geri ödemesi sayısal olarak doğrulanabildiği için "
                          "'en düşük' diye kazanan ilan etmiyorum. Diğer bankaların canlı/güncel sonucu doğrulanmadan eski snapshot ile sıralama yapmıyorum."),
                    route="finance_compare_winner_unavailable", answer_mode="finance",
                    finance_result_count=len(by_total), reasons=("comparison_followup_winner", "fresh_pricing_only", "insufficient_comparable_banks"),
                )
            winner = by_total[0]
            lines = [
                f"### {family_title} · en düşük güncel doğrulanmış geri ödeme",
                f"{_fmt_money(amount)} / {maturity} ay senaryosunda en düşük doğrulanmış güncel geri ödeme "
                f"**{winner['bank_name']}** tarafında: **{_fmt_money(winner['total'])}**.",
            ]
            second = by_total[1]
            diff = float(second.get("total")) - float(winner.get("total"))
            lines.append(f"İkinci sırada **{second['bank_name']}** var; fark yaklaşık **{_fmt_money(diff)}**.")
            return FastRouteAnswer(
                text="\n\n".join(lines), route="finance_compare_winner", answer_mode="finance",
                finance_result_count=len(by_total), reasons=("comparison_followup_winner", "fresh_pricing_only"),
            )

    # V5 numeric graceful degradation: when the strict exact store has no
    # amount match, use official pricing tables or a verified calculator result
    # from the same maturity to calculate the *requested* amount.
    if (
        amount is not None
        and maturity is not None
        and projection_by_bank
    ):
        return _projection_compare_answer(
            rows,
            projection_by_bank,
            float(amount),
            int(maturity),
            family_title,
            exact_by_bank=exact_by_bank,
        )

    lines = [f"### {family_title} karşılaştırması"]
    if amount is not None or maturity is not None:
        scenario = []
        if amount is not None:
            scenario.append(_fmt_money(amount))
        if maturity is not None:
            scenario.append(f"{maturity} ay")
        lines.append("İstediğiniz senaryo: **" + " / ".join(scenario) + "**.")

    if exact_by_bank and amount is not None and maturity is not None:
        lines.append(
            "Aynı tutar ve vadede **güncel sayısal sonucunu doğrulayabildiğim seçenekler** şöyle:"
        )
        lines += [
            "",
            "| Banka | Koşul | Kâr payı | Aylık taksit | Toplam geri ödeme | Masraf notu |",
            "|---|---|---:|---:|---:|---|",
        ]

        all_records = []
        for bank, records in exact_by_bank.items():
            for rec in _comparison_display_records(records):
                variant_label = str(rec.get("display_variant") or "Standart")
                fee_parts = []
                if _present(rec.get("allocation_fee")):
                    fee_parts.append("tahsis " + _fmt_money(rec.get("allocation_fee")))
                if _present(rec.get("appraisal_fee")):
                    fee_parts.append("ekspertiz " + _fmt_money(rec.get("appraisal_fee")))
                if _present(rec.get("mortgage_fee")):
                    fee_parts.append("ipotek " + _fmt_money(rec.get("mortgage_fee")))
                if _present(rec.get("fees")):
                    fee_parts.append("toplam " + _fmt_money(rec.get("fees")))
                fee_text = " · ".join(fee_parts) if fee_parts else "Ayrıntı eksik"
                lines.append(
                    f"| **{bank}** | {variant_label} | {_fmt_rate(rec.get('rate'))} | "
                    f"{_fmt_money(rec.get('monthly'))} | {_fmt_money(rec.get('total'))} | {fee_text} |"
                )
                if _present(rec.get("total")):
                    all_records.append(rec)

        # Bank-level best case is used only to summarize the observed verified
        # rows.  It is explicitly labelled as such and never called final cost.
        best_by_bank = []
        for bank, records in exact_by_bank.items():
            numeric = [r for r in records if _present(r.get("total"))]
            if numeric:
                best = min(numeric, key=lambda r: float(r.get("total")))
                best_by_bank.append(best)
        if len(best_by_bank) >= 2:
            best_by_bank.sort(key=lambda r: float(r.get("total")))
            winner = best_by_bank[0]
            second = best_by_bank[1]
            diff = float(second.get("total")) - float(winner.get("total"))
            lines.append(
                f"\n**Yorum:** Mevcut doğrulanmış varyantlar içinde geri ödeme toplamı en düşük görünen sonuç "
                f"**{winner['bank_name']} · {_fmt_money(winner['total'])}**. En yakın sonraki banka sonucuna göre fark yaklaşık "
                f"**{_fmt_money(diff)}**. Bu ifade yalnız geri ödeme toplamını karşılaştırır; ekspertiz, ipotek, sigorta ve "
                "varyant kapsamı eksik/farklıysa bunu kesin nihai maliyet kazananı olarak sunmuyorum."
            )

        missing_exact = [
            str(row.get("bank_name")) for row in rows
            if str(row.get("bank_name")) not in exact_by_bank
            and str(row.get("bank_name")) not in projection_by_bank
        ]
        if missing_exact:
            lines.append(
                "\n**Henüz aynı senaryoda güncel sayısal sonucu alamadığım bankalar:** "
                + ", ".join(missing_exact)
                + ". Eski hesap örneklerini veya araç-değeri tablolarını aylık taksitmiş gibi kullanmıyorum."
            )
    else:
        if amount is not None and maturity is not None:
            lines.append(
                "Bu tutar ve vade için seçilen bankalarda karşılaştırılabilir güncel sayısal sonuç bulunamadı. "
                "Başka bir tutara ait örnek ödemeyi sizin senaryonuza uyarlamak yerine yalnız doğrulanmış ürün koşullarını gösteriyorum."
            )
        else:
            lines.append(
                "Genel ürün koşullarını karşılaştırıyorum. Hesaplama örnekleri farklı tutar/varyantlara ait olabileceği için bunlardan doğrudan 'kazanan banka' çıkarmıyorum."
            )

    # Two banks read more naturally as short prose; broad comparisons can use
    # a compact table because the user is explicitly comparing a set.
    if len(rows) <= 2:
        for row in rows:
            bank = str(row.get("bank_name"))
            max_m = _fmt_maturity(row.get("maximum_maturity_months"), row.get("maturity_rules_text"))
            rate = _fmt_rate(row.get("profit_share_rate"), row.get("profit_share_rate_text"))
            sentence = f"- **{bank}:** {row.get('product_name')}; azami vade **{max_m}**, fiyatlama **{rate}**."
            fit = _maturity_fit(row, maturity)
            if fit:
                sentence += " " + fit
            example = _verified_example(row)
            if example and bank not in exact_by_bank:
                sentence += (
                    f" Bankanın BANSA'daki doğrulanmış örneği {_fmt_money(example['amount'])}/{int(float(example['maturity']))} ay: "
                    f"oran {_fmt_rate(example['rate'])}, aylık {_fmt_money(example['monthly'])}, toplam {_fmt_money(example['total'])}. "
                    "Bu örnek istenen senaryo değildir."
                )
            lines.append(sentence)
    elif not exact_by_bank:
        lines += [
            "",
            "| Banka | Ürün | Azami vade | Fiyatlama | Doğrulanmış örnek |",
            "|---|---|---:|---|---|",
        ]
        for row in rows:
            example = _verified_example(row)
            example_text = "—"
            if example:
                example_text = (
                    f"{_fmt_money(example['amount'])}/{int(float(example['maturity']))} ay · "
                    f"{_fmt_rate(example['rate'])} · aylık {_fmt_money(example['monthly'])}"
                )
            lines.append(
                f"| **{row.get('bank_name')}** | {row.get('product_name')} | "
                f"{_fmt_maturity(row.get('maximum_maturity_months'), row.get('maturity_rules_text'))} | "
                f"{_fmt_rate(row.get('profit_share_rate'), row.get('profit_share_rate_text'))} | {example_text} |"
            )


    sources = []
    for row in rows:
        url = _source_url(row)
        if url and url not in sources:
            sources.append(url)
    if sources:
        lines.append("\n**Resmî ürün kaynakları:** " + " · ".join(f"[Kaynak {i+1}]({url})" for i, url in enumerate(sources)))

    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="finance_compare",
        answer_mode="finance",
        finance_result_count=len(rows),
        reasons=("natural_finance_compare", "exact_when_available", "catalog_graceful_degradation"),
    )


# ---------------------------------------------------------------------------
# Campaign natural responses
# ---------------------------------------------------------------------------


def _campaign_score(row, topic_tokens: tuple[str, ...], query: str) -> tuple[int, int]:
    title = normalize(str(row.get("campaign_name") or ""))
    url = normalize(str(row.get("source_url") or ""))
    evidence = title + " " + url
    hits = sum(1 for token in topic_tokens if token in evidence)
    sim = int(SequenceMatcher(None, normalize(query), title).ratio() * 1000) if title else 0
    return hits, sim


def _clean_campaign_conditions(value: str, *, limit: int = 440) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    # Ziraat pages may include the entire campaign category navigation before
    # the actual content.  Never expose those menu counters to the user.
    text = re.sub(r"^Tüm Kampanyalar\b.*?\bArşiv\b\s*", "", text, flags=re.I)
    text = re.sub(
        r"^Kampanya Tarihleri\s+\d{1,2}[./-]\d{1,2}[./-]\d{4}\s*-\s*\d{1,2}[./-]\d{1,2}[./-]\d{4}\s+Kampanyayı Paylaş\s*",
        "", text, flags=re.I,
    )
    # If a scraper captured title/date/sector before a clear conditions block,
    # keep only the actual conditions.
    m = re.search(r"Kampanya Koşulları\s*:\s*", text, flags=re.I)
    if m:
        text = text[m.end():]
    else:
        text = re.sub(r"Kampanya Dönemi\s+\d{1,2}[-./]\d{1,2}[-./]\d{4}\s*-\s*\d{1,2}[-./]\d{1,2}[-./]\d{4}", "", text, flags=re.I)
        text = re.sub(r"Sektör\s*:\s*[^.]{1,80}", "", text, count=1, flags=re.I)
    # Related-campaign cards often follow the genuine text.
    if " Detaylar " in text:
        text = text.split(" Detaylar ", 1)[0]
    text = re.sub(r"\s+", " ", text).strip(" -:;.")
    if len(text) <= limit:
        return text
    short = text[:limit]
    cut = max(short.rfind(". "), short.rfind("; "))
    if cut >= 180:
        short = short[: cut + 1]
    return short.rstrip() + "…"


def _campaign_detail_answer(row, query: str) -> FastRouteAnswer:
    bank = str(row.get("bank_name") or "Katılım Bankası")
    title = _safe_text(row.get("campaign_name"), "Kampanya")
    benefit = _campaign_benefit(row)
    end = _safe_text(row.get("campaign_end_date"), "Belirtilmemiş")
    condition = _clean_campaign_conditions(
        _safe_text(row.get("campaign_conditions"), "Resmî kaynakta koşul özeti belirtilmemiş")
    )
    url = _safe_text(row.get("source_url"), "")
    installment = row.get("installment_count")
    # V15 campaign extraction guard: the detail-page title is stronger than
    # navigation/related-card numerics.  "Vatan’da 3 Taksit" must never render
    # as 5 taksit because a neighbouring campaign card contained the number 5.
    title_match = re.search(r"(?<!\d)(\d{1,2})\s*taksit", normalize(title))
    if title_match:
        installment = int(title_match.group(1))

    # Follow-up turns are resolved as:
    #   "<original campaign query> - <current short follow-up>"
    # Use only the tail to decide which field the user is asking now, while
    # keeping the original part for bank/merchant matching.
    followup_tail = ""
    if " - " in str(query or ""):
        followup_tail = normalize(str(query).rsplit(" - ", 1)[-1])

    if followup_tail:
        asks_end = any(
            marker in followup_tail
            for marker in (
                "ne zamana kadar", "zamana kadar", "gecerli", "son tarih",
                "bitis tarihi", "ne zaman bitiyor", "ne zaman sona eriyor",
            )
        )
        asks_condition = any(
            marker in followup_tail
            for marker in (
                "sarti", "sartlari", "kosulu", "kosullari", "nasil yararlan",
                "kimler yararlan", "ne yapmam gerek", "ne gerekiyor",
            )
        )
        asks_installment = "taksit" in followup_tail and any(
            marker in followup_tail for marker in ("kac", "ne kadar", "var mi")
        )

        lines = [f"### {bank} · {title}"]
        if asks_end:
            if end == "Belirtilmemiş":
                lines.append("Yerel doğrulanmış kayıtta kampanyanın bitiş tarihi belirtilmemiş.")
            else:
                lines.append(f"Kampanya **{end}** tarihine kadar geçerli görünüyor.")
        elif asks_condition:
            lines.append("**Yararlanma koşulları:** " + condition)
        elif asks_installment and _present(installment):
            lines.append(f"Bu kampanyada **{int(float(installment))} taksit** imkânı var.")
        else:
            lines = []

        if lines:
            if url:
                lines.append(f"[Resmî kampanya sayfası]({url})")
            return FastRouteAnswer(
                text="\n\n".join(lines),
                route="campaign_detail",
                answer_mode="campaign",
                reasons=("natural_campaign_followup_field", "title_url_topic_match", "active_date_gate"),
            )

    # A direct single-field campaign question should get a concise field answer.
    # Do not expose a long marketing/conditions paragraph when the user only asks
    # "kaç taksit?" or "ne zamana kadar?".
    query_norm = normalize(query)
    direct_asks_installment = (
        "taksit" in query_norm
        and any(marker in query_norm for marker in ("kac", "ne kadar", "var mi"))
        and not any(marker in query_norm for marker in ("sart", "kosul", "nasil yararlan", "kimler"))
    )
    direct_asks_end = any(
        marker in query_norm
        for marker in ("ne zamana kadar", "zamana kadar", "son tarih", "bitis tarihi", "ne zaman bitiyor", "ne zaman sona eriyor")
    )

    if direct_asks_installment and _present(installment):
        lines = [
            f"### {bank} · {title}",
            f"Bu kampanyada **{int(float(installment))} taksit** imkânı var.",
        ]
        if end != "Belirtilmemiş":
            lines.append(f"Son tarih: **{end}**.")
        if url:
            lines.append(f"[Resmî kampanya sayfası]({url})")
        return FastRouteAnswer(
            text="\n\n".join(lines),
            route="campaign_detail",
            answer_mode="campaign",
            reasons=("natural_campaign_direct_field", "installment", "active_date_gate"),
        )

    if direct_asks_end:
        lines = [f"### {bank} · {title}"]
        if end == "Belirtilmemiş":
            lines.append("Yerel doğrulanmış kayıtta kampanyanın bitiş tarihi belirtilmemiş.")
        else:
            lines.append(f"Kampanya **{end}** tarihine kadar geçerli görünüyor.")
        if url:
            lines.append(f"[Resmî kampanya sayfası]({url})")
        return FastRouteAnswer(
            text="\n\n".join(lines),
            route="campaign_detail",
            answer_mode="campaign",
            reasons=("natural_campaign_direct_field", "end_date", "active_date_gate"),
        )

    lines = [f"### {bank} · {title}"]
    if _present(installment):
        inst_n = int(float(installment))
        benefit_norm = normalize(benefit)
        conflicting_taksit_benefit = ("taksit" in benefit_norm and benefit_norm != normalize(f"{inst_n} taksit"))
        extra_benefit = "" if conflicting_taksit_benefit else (
            "Taksit dışında öne çıkan avantaj: **" + benefit + "**."
            if benefit != f"{inst_n} taksit" else ""
        )
        lines.append(
            f"Bu kampanyada **{inst_n} taksit** imkânı var."
            + (" " + extra_benefit if extra_benefit else "")
        )
    else:
        lines.append(f"Kampanyanın öne çıkan avantajı **{benefit}**.")
    if condition:
        lines.append("**Kimler/nasıl yararlanabilir?** " + condition)
    if end == "Belirtilmemiş":
        lines.append("Yerel doğrulanmış kayıtta kampanyanın bitiş tarihi belirtilmemiş.")
    else:
        lines.append(f"Kampanya **{end}** tarihine kadar aktif görünüyor.")
    if url:
        lines.append(f"[Resmî kampanya sayfası]({url})")

    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="campaign_detail",
        answer_mode="campaign",
        reasons=("natural_campaign_detail", "title_url_topic_match", "active_date_gate"),
    )


def _campaign_answer(query: str, banks: tuple[str, ...]) -> FastRouteAnswer | None:
    work = _active_campaigns_for(banks)
    if work.empty:
        return None

    topics = _campaign_topic_tokens(query)
    if topics:
        scored = [(_campaign_score(row, topics, query), idx) for idx, row in work.iterrows()]
        best = max((score for score, _ in scored), default=(0, 0))
        if best[0] > 0:
            candidates = [idx for score, idx in scored if score[0] == best[0]]
            ranked = []
            for idx in candidates:
                row = work.loc[idx]
                ranked.append((_campaign_score(row, topics, query), idx))
            ranked.sort(reverse=True)
            return _campaign_detail_answer(work.loc[ranked[0][1]], query)

        # Never replace a missing named campaign with an unrelated campaign
        # from the requested bank.  If the same merchant/title is strongly
        # verified at another participation bank, say so explicitly.
        subject = " ".join(topics)
        bank_text = " / ".join(banks) if banks else "BDDK kapsamındaki katılım bankaları"
        alternatives = []
        if banks:
            all_work = _active_campaigns_for(tuple())
            ranked_all = []
            for idx, row in all_work.iterrows():
                score = _campaign_score(row, topics, query)
                if score[0] > 0 and str(row.get("bank_name")) not in banks:
                    ranked_all.append((score, idx))
            ranked_all.sort(reverse=True)
            for score, idx in ranked_all[:3]:
                row = all_work.loc[idx]
                # A distinctive topic token must actually occur in TITLE/URL.
                title_ev = normalize(str(row.get("campaign_name") or "") + " " + str(row.get("source_url") or ""))
                generic = {"paraf", "bankkart", "world", "troy", "saglam", "bonus", "maximum"}
                distinctive = [
                    t for t in topics
                    if len(t) >= 5 and t not in generic and t in title_ev
                ]
                if distinctive:
                    alternatives.append((str(row.get("bank_name")), str(row.get("campaign_name"))))
        extra = ""
        if alternatives:
            seen=[]
            for b,t in alternatives:
                item=f"**{b} · {t}**"
                if item not in seen: seen.append(item)
            extra = " BANSA'da benzer başlık " + "; ".join(seen) + " olarak görünüyor; banka adı karışmış olabilir."
        return FastRouteAnswer(
            text=(
                f"**{bank_text}** için “{subject}” ile yeterince güçlü eşleşen aktif kampanya bulamadım. "
                "Bu nedenle aynı bankadan alakasız bir kampanyayı cevap olarak vermiyorum." + extra
            ),
            route="campaign_search", answer_mode="campaign",
            reasons=("natural_campaign_no_match", "no_unrelated_campaign_fallback", "graceful_degradation"),
        )

    # Plain bank campaign listing: answer like a chatbot, not a raw 12-card dump.
    if "campaign_end_date" in work.columns:
        work = work.assign(_end=pd.to_datetime(work["campaign_end_date"], errors="coerce"))
        work = work.sort_values(["_end", "id"], ascending=[True, False], na_position="last")
    else:
        work = work.sort_values("id", ascending=False)

    visible = work.head(6)
    bank_text = " / ".join(banks) if banks else "Katılım bankalarında"
    lines = [
        f"### {bank_text} güncel kampanyalar",
        f"Şu anda **{len(work)} aktif kampanya** görüyorum. Hepsini uzun uzun dökmek yerine ilk bakışta en faydalı **{len(visible)} seçeneği** özetliyorum:",
    ]
    for _, row in visible.iterrows():
        title = _safe_text(row.get("campaign_name"), "Kampanya")
        benefit = _campaign_benefit(row)
        end = _safe_text(row.get("campaign_end_date"), "Belirtilmemiş")
        url = _safe_text(row.get("source_url"), "")
        title_md = f"[{title}]({url})" if url else title
        lines.append(f"- **{title_md}** — {benefit}; son tarih **{end}**.")
    lines.append(
        "İstersen **market, teknoloji, seyahat, akaryakıt, eğitim** gibi bir kategori ya da kampanya adını yaz; o zaman yalnız ilgili fırsatın koşullarını çıkarırım."
    )
    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="campaign_search",
        answer_mode="campaign",
        finance_result_count=0,
        reasons=("natural_campaign_list", "active_date_gate", "compact_jury_output"),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------




def _enerya_karz_hasen_answer(query: str) -> FastRouteAnswer | None:
    """High-precision answer for Dünya Katılım's Enerya vade-farksız finance campaign.

    The user may call this surface "Karz-ı Hasen".  BANSA's official record is
    the Enerya finance campaign page.  Keep it separate from the distinct
    standard product "Enerya İhtiyaç Finansmanı" (36 months / 250k ceiling).
    """
    qn = normalize(query)
    if "enerya" not in qn:
        return None
    if not any(marker in qn for marker in ("karz", "hasen", "vade farksiz")):
        return None

    try:
        from src.repository import get_campaigns
        frame = get_campaigns()
    except Exception:
        return None
    if frame is None or frame.empty:
        return None

    names = frame.get("campaign_name", pd.Series(index=frame.index, dtype=object)).fillna("").astype(str)
    urls = frame.get("source_url", pd.Series(index=frame.index, dtype=object)).fillna("").astype(str)
    mask = names.map(lambda x: "enerya" in normalize(x)) & urls.str.contains("/kampanyalar/enerya-finansmani", regex=False)
    rows = frame[mask].copy()
    if rows.empty:
        return None
    row = rows.iloc[0]
    text = re.sub(r"\s+", " ", str(row.get("campaign_conditions") or "")).strip()

    def _money_from(pattern: str) -> float | None:
        m = re.search(pattern, text, flags=re.I)
        if not m:
            return None
        raw = m.group(1).replace(".", "").replace(",", ".")
        try:
            return float(raw)
        except Exception:
            return None

    def _int_from(pattern: str) -> int | None:
        m = re.search(pattern, text, flags=re.I)
        return int(m.group(1)) if m else None

    min_amount = _money_from(r"minimum\s+([0-9][0-9.,]*)\s*TL")
    max_amount = _money_from(r"maksimum\s+([0-9][0-9.,]*)\s*TL")
    min_term = _int_from(r"minimum\s+(\d+)\s*ay")
    max_term = _int_from(r"maksimum\s+(\d+)\s*ay")
    source = str(row.get("source_url") or "").strip()

    lines = ["### Dünya Katılım · Enerya vade farksız finansmanı"]

    asks_min_term = any(x in qn for x in ("minimum kac ay", "minimum vade", "en az kac ay", "asgari vade"))
    asks_max_term = any(x in qn for x in ("maksimum kac ay", "maksimum vade", "en fazla kac ay", "azami vade"))
    if asks_min_term:
        if min_term is not None:
            lines.append(f"**Minimum vade {min_term} ay.**")
        else:
            lines.append("Resmî Enerya kampanya kaydında minimum vade sayısal olarak doğrulanamadı; değer uydurmuyorum.")
    elif asks_max_term:
        if max_term is not None:
            lines.append(f"**Maksimum vade {max_term} ay.**")
        else:
            lines.append("Resmî Enerya kampanya kaydında maksimum vade sayısal olarak doğrulanamadı; değer uydurmuyorum.")
    else:
        lines.append(
            "Bu kayıt, Dünya Katılım'ın Enerya yeni doğal gaz abonelikleri için sunduğu **vade farksız finansman** kampanyasıdır. "
            "Ayrı bir standart ürün olan **Enerya İhtiyaç Finansmanı** ile karıştırılmaz."
        )
        facts = []
        if min_amount is not None and max_amount is not None:
            facts.append(f"finansman tutarı **{_fmt_money(min_amount)}–{_fmt_money(max_amount)}**")
        if min_term is not None and max_term is not None:
            facts.append(f"vade **{min_term}–{max_term} ay**")
        if facts:
            lines.append("Öne çıkan doğrulanmış koşullar: " + "; ".join(facts) + ".")
        if any(city in normalize(text) for city in ("antalya", "aydin", "denizli", "konya")):
            lines.append("Kapsam, resmî metinde **Antalya, Aydın, Denizli ve Konya** illerindeki yeni abonelik işlemleri için belirtiliyor.")
        if "abonelik" in normalize(text) and "tesisat" in normalize(text):
            lines.append("Finansman; Enerya abonelik bedeli ile doğal gaz dönüşümünde ihtiyaç duyulan konut içi tesisat giderleri için kullanılabiliyor.")

    if source:
        lines.append(f"[Resmî kampanya kaynağı]({source})")
    return FastRouteAnswer(
        text="\n\n".join(lines),
        route="enerya_karz_hasen_finance_campaign",
        answer_mode="finance",
        finance_result_count=1,
        reasons=("explicit_enerya_karz_hasen_alias", "official_campaign_finance_detail"),
    )


def answer_natural(query: str) -> FastRouteAnswer | None:
    query = str(query or "").strip()
    if not query:
        return None

    # V47: explicit card-product questions must be resolved before campaign
    # matching or stale finance context. A card name may also appear in an
    # active campaign title, but questions about fee/contactless/NFC/etc.
    # belong to the verified card catalog.
    try:
        from src.card_query_service import answer_card_query
        card_answer = answer_card_query(query)
        if card_answer is not None:
            return card_answer
    except Exception:
        pass

    phone_purchase = _phone_purchase_recommendation_answer(query)
    if phone_purchase is not None:
        return phone_purchase

    # V25.1 accuracy-first surface.  These handlers distinguish catalog/list
    # requests and attribute-only comparisons from scenario pricing, and they
    # use only the verified local catalog + manually re-checked official facts.
    try:
        from src.v25_accuracy_layer import answer_accuracy_first
        accuracy = answer_accuracy_first(query)
        if accuracy is not None and str(accuracy.text or "").strip():
            return accuracy
    except Exception:
        pass

    # V21: branded Enerya Karz-ı Hasen wording is an explicit finance-campaign
    # surface and must beat stale conversation state / generic campaign search.
    enerya = _enerya_karz_hasen_answer(query)
    if enerya is not None:
        return enerya

    banks = detect_banks(query)
    family = detect_family(query)
    attribute = detect_attribute(query)
    amount, maturity = parse_amount_and_maturity(query)

    # V47: purchase scenarios may contain both the asset price and cash/down
    # payment.  The calculator principal is the financing need, not simply the
    # first TL number in the sentence.
    purchase_scenario = _extract_purchase_scenario(query, family)
    if _asks_for_recommendation(query) and family in {"konut_finansmani", "arac_finansmani"}:
        financing_need = purchase_scenario.get("financing_need")
        if financing_need is not None and financing_need > 0:
            amount = float(financing_need)

    # Explicit campaign wording (including common typos such as "kampnya")
    # always wins. Merchant-only campaign recognition is used only when the
    # turn does not already contain an explicit finance family/attribute; this
    # prevents a financing question from being hijacked by a campaign whose
    # title happens to contain "ihtiyaç finansmanı" or "taşıt".
    if _has_explicit_campaign_word(query):
        # Campaign comparisons already have a mature deterministic comparison
        # engine in the legacy BANSA core. Do not collapse a compare request
        # into one "best matching" campaign detail in the natural layer.
        if is_compare_query(query):
            return None
        campaign = _campaign_answer(query, banks)
        if campaign is not None:
            return campaign

    # Merchant/title-style installment questions are campaign questions even
    # when a parser happens to infer a numeric field or a bank.  Explicit
    # finance-family wording still wins.
    finance_numeric_surface = bool(
        amount is not None
        and (maturity is not None or any(x in normalize(query) for x in ("aylik taksit", "geri odeme", "kar payi", "finansman")))
    )
    finance_product_surface = bool(
        any(token in normalize(query) for token in ("finansman", "kredi"))
        and not _has_explicit_campaign_word(query)
    )
    if (
        family is None
        and is_campaign_intent(query, banks)
        and not finance_numeric_surface
        and not finance_product_surface
    ):
        campaign = _campaign_answer(query, banks)
        if campaign is not None:
            return campaign

    # V47: a fresh generic finance recommendation must not inherit the previous
    # conversation's family.  Without a product family, comparing 100k/36m as
    # housing vs vehicle vs need finance is not meaningful.
    if (
        family is None
        and amount is not None
        and _asks_for_recommendation(query)
        and "finansman" in normalize(query)
    ):
        return _generic_finance_family_clarification(amount, maturity)

    if family is None and attribute is None and amount is None:
        if not is_finance_query(query):
            return None

    if not is_finance_query(query):
        return None

    # V18: a bank + requested amount without a product is not enough evidence
    # to choose an arbitrary catalog row (for example SÖİK).  In a real
    # conversation the follow-up resolver may inherit the recent product; if it
    # did not, ask one short product clarification instead of guessing.
    if family is None and len(banks) == 1 and amount is not None:
        semantics = resolve_amount_semantics(
            query, family=None, amount_present=True, compare=False
        )
        qn_generic = normalize(query)
        specific_product_markers = (
            "tasit", "arac", "otomobil", "motosiklet", "motor", "konut",
            "ihtiyac", "egitim", "arsa", "isyeri", "is yeri", "ticari",
            "tarim", "hac", "umre", "alisveris", "saglik", "soik", "kobi",
        )
        if (
            semantics.kind == AmountKind.REQUESTED_FINANCING_AMOUNT
            and not any(marker in qn_generic for marker in specific_product_markers)
        ):
            return _generic_financing_product_clarification(banks[0], float(amount))

    # V4 routing precedence: a comparison/superlative request owns the turn.
    # Numeric maturity text such as "100 bin TL 36 ay vade için ... kıyasla"
    # must not be mistaken for a single-bank "maximum maturity" fact query.
    if _is_superlative_maturity(query):
        result = _superlative_maturity_answer(query, family)
        if result is not None:
            return result

    # V47: vehicle purchase recommendations first resolve asset value,
    # down-payment and value-band eligibility. This prevents a 500k invoice
    # value from being sent to calculators as a 500k finance principal and
    # enforces the correct vehicle-value maturity band.
    vehicle_purchase = _vehicle_purchase_recommendation_answer(query, family, maturity)
    if vehicle_purchase is not None:
        return vehicle_purchase

    commercial_fit = _commercial_purpose_recommendation_answer(query, family, amount, maturity)
    if commercial_fit is not None:
        return commercial_fit

    # V46: an all-bank recommendation is a scenario decision request, not a
    # raw comparison table. Route it through the multi-bank scenario builder so
    # it can choose a common default maturity when the user omitted one and then
    # explain the winners by rate, monthly payment and repayment total.
    if _asks_for_recommendation(query) and not banks and family is not None and amount is not None:
        result = _multi_bank_options_answer(query, family, amount, maturity)
        if result is not None:
            return result

    if is_compare_query(query):
        result = _compare_answer(query, banks, family, amount, maturity)
        if result is not None:
            return result

    # Published pricing tables are stronger than a one-off calculator
    # snapshot for rate questions.  They also understand "sigortalı" as a
    # pricing variant instead of misrouting it to insurance-fee intent.
    if attribute == "profit_share_rate" and banks:
        work = _filter_products(query, banks, family)
        if not work.empty:
            row = _enrich_row(_best_product_row(work, query, family))
            priced = _pricing_rate_answer(query, row, maturity)
            if priced is not None:
                return priced

    # V17 amount semantics. The same 600,000 TL can be the asset value or the
    # requested financing principal; never silently swap those meanings.
    if family == "arac_finansmani" and amount is not None and len(banks) == 1 and not is_compare_query(query):
        semantics = resolve_amount_semantics(
            query, family=family, amount_present=True, compare=False
        )
        work_for_amount = _filter_products(query, banks, family)
        if not work_for_amount.empty:
            amount_row = _enrich_row(_best_product_row(work_for_amount, query, family))
            generic_moto_gap = (
                detect_product_hint(query) == "motosiklet"
                and "motosiklet" not in normalize(amount_row.get("product_name"))
            )
            if generic_moto_gap:
                albaraka_scope = _albaraka_motorcycle_scope_answer(amount_row, query)
                if albaraka_scope is not None:
                    return albaraka_scope
                bank_name = str(amount_row.get("bank_name") or "Katılım Bankası")
                product_name = str(amount_row.get("product_name") or "Araç Finansmanı")
                lines = [
                    f"### {bank_name} · {product_name}",
                    f"BANSA'nın doğrulanmış kayıtlarında {bank_name} için ayrı bir **Motosiklet Finansmanı** ürünü/kapsamı bulamadım. "
                    "Genel araç finansmanı kurallarını motosiklete otomatik uygulamıyorum.",
                ]
                url = _source_url(amount_row)
                if url:
                    lines.append(f"[Resmî ürün kaynağı]({url})")
                return FastRouteAnswer(
                    text="\n\n".join(lines), route="finance_motorcycle_scope_guard",
                    answer_mode="finance", finance_result_count=0,
                    reasons=("motorcycle_scope_not_verified", "no_vehicle_rule_transplant"),
                )
            if semantics.kind == AmountKind.AMBIGUOUS and maturity is None:
                return _amount_clarification_answer(amount_row, float(amount), query)
            if (
                semantics.kind == AmountKind.REQUESTED_FINANCING_AMOUNT
                and maturity is None
                and not _asks_scenario_calculation(query)
            ):
                return _requested_financing_amount_guard(amount_row, float(amount), query, maturity)
            if semantics.kind == AmountKind.REQUESTED_FINANCING_AMOUNT and maturity is not None:
                constraint_guard = _calculator_constraint_scenario_guard(
                    amount_row, float(amount), int(maturity), query
                )
                if constraint_guard is not None:
                    return constraint_guard

    # Vehicle finance has value-dependent legal/product bands.  Only an amount
    # classified as asset value may enter those bands.
    vehicle_value_fact = _vehicle_value_fact_answer(
        query, banks, family, amount, maturity
    )
    if vehicle_value_fact is not None:
        return vehicle_value_fact

    # Simple single-field facts are concise and high quality in the
    # deterministic router; use them only after comparison intents are ruled out.
    if attribute and banks:
        from src.competition_fast_router import answer_fast
        fact = answer_fast(query)
        if fact is not None and fact.route == "finance_fact":
            return fact

    # A no-bank scenario such as "75.000 TL 24 ay ihtiyaç finansmanı için hangi
    # seçenekler var?" means "show me options", not "dump the whole family".
    if not banks and family is not None and (
        amount is not None or maturity is not None or any(x in normalize(query) for x in ("hangi secenek", "secenekler", "neler var"))
    ):
        result = _multi_bank_options_answer(query, family, amount, maturity)
        if result is not None:
            return result

    if (
        banks and family is not None and amount is not None and maturity is None
        and (attribute in {"monthly_installment", "total_repayment"} or _asks_scenario_calculation(query))
    ):
        # BANSA_CALC_DEFAULT_MATURITY_V1: kullanıcı vade belirtmeden "aylık
        # ödeme ne kadar / toplam ne öderim" diye sorduğunda (banka zaten
        # bağlamdan belli), hesaplamayı tamamen atlamak yerine bu bankanın
        # doğrulanmış bir senaryosu olan vadeyi (yoksa azami vadeyi)
        # varsayılan alıp devam ediyoruz.
        _probe_work = _filter_products(query, banks, family)
        if not _probe_work.empty:
            _probe_row = _enrich_row(_best_product_row(_probe_work, query, family))
            _default_maturity = None
            _default_m = _probe_row.get("maximum_maturity_months")
            if pd.notna(_default_m) and float(_default_m) > 0:
                _default_maturity = int(_default_m)
            if _default_maturity is not None:
                maturity = _default_maturity

    if banks and family is not None and amount is not None and maturity is not None:
        work = _filter_products(query, banks, family)
        if not work.empty:
            row = _enrich_row(_best_product_row(work, query, family))

            resolution = resolve_user_scenario(row, float(amount), int(maturity))
            if resolution.mode == "live":
                live_records = [
                    rec for rec in resolution.live_records
                    if _variant_matches_query(str(rec.get("variant") or ""), query)
                ]
                if live_records:
                    return _single_bank_exact_answer(query, row, live_records, amount, maturity)

            if resolution.mode == "model":
                projected = tuple(
                    rec for rec in resolution.projections
                    if _variant_matches_query(rec.variant, query)
                )
                if projected:
                    return _single_bank_projection_answer(row, projected, amount, maturity)

            if resolution.mode == "live_unavailable":
                bank = str(row.get("bank_name") or "Banka")
                return FastRouteAnswer(
                    text=(
                        f"**{bank}** için {_fmt_money(amount)} / {maturity} ay senaryosunda resmî hesaplama aracı şu anda birebir doğrulanamadı. "
                        "Eski bir oranı güncelmiş gibi kullanmadığım için sayısal taksit göstermiyorum; lütfen kısa süre sonra tekrar deneyin veya resmî hesaplama aracını açın."
                    ),
                    route="finance_live_unavailable",
                    answer_mode="finance",
                    reasons=("live_calculator_authoritative", "stale_fallback_blocked"),
                )

            records = _exact_records_for_row(row, amount, maturity)
            records = [
                rec for rec in records
                if _variant_matches_query(str(rec.get("variant") or ""), query)
            ]
            if records:
                return _single_bank_exact_answer(query, row, records, amount, maturity)

            if _asks_scenario_calculation(query):
                bank = str(row.get("bank_name") or banks[0])
                product = str(row.get("product_name") or "Finansman")
                lines = [
                    f"### {bank} · {product}",
                    f"**{_fmt_money(amount)} / {maturity} ay** için BANSA'nın şu anda birebir doğrulayabildiği güncel bir kâr payı/taksit satırı yok. "
                    "Bu yüzden aylık taksit veya toplam geri ödeme uydurmuyorum.",
                ]
                current_tiers = [
                    t for t in _pricing_tiers(row)
                    if int(t.get("maturity_months") or 0) == int(maturity)
                    and _tier_matches_query(t, query)
                    and _present(t.get("profit_share_rate"))
                ]
                if current_tiers:
                    rate_items = []
                    seen_rates = set()
                    for tier in current_tiers:
                        variant = str(tier.get("pricing_variant") or "Standart")
                        rate = float(tier.get("profit_share_rate"))
                        key = (normalize(variant), round(rate, 8))
                        if key in seen_rates:
                            continue
                        seen_rates.add(key)
                        rate_items.append(f"{variant}: **{_fmt_rate(rate)}**")
                    if rate_items:
                        lines.append(
                            f"Bununla birlikte bankanın **güncel resmî fiyatlama tablosunda {maturity} ay** için kâr payı "
                            + "; ".join(rate_items)
                            + " olarak yayımlanıyor. Bu oranı biliyorum; yalnız banka hesaplama matematiğini doğrulamadan bu orandan aylık taksit türetmiyorum."
                        )
                if family == "arac_finansmani" and _vehicle_bands(row):
                    lines.append(
                        "Ürün sayfasındaki **araç değeri → azami finansman oranı/vade** tablosu uygunluk sınırını belirler; "
                        "kâr payı oranını vermediği için o tablo tek başına aylık taksit hesabı yapmak için yeterli değildir."
                    )
                example = _verified_example(row)
                if example:
                    lines.append(
                        f"BANSA'daki en yakın doğrulanmış örnek **{_fmt_money(example['amount'])} / {int(float(example['maturity']))} ay**, "
                        f"kâr payı **{_fmt_rate(example['rate'])}**, aylık **{_fmt_money(example['monthly'])}**. "
                        "Vade farklı olduğu için bu örneği sizin senaryonuza ölçeklemiyorum."
                    )
                url = _source_url(row)
                if url:
                    lines.append(f"[Resmî ürün kaynağı]({url})")
                return FastRouteAnswer(
                    text="\n\n".join(lines),
                    route="finance_scenario_not_exact",
                    answer_mode="finance",
                    finance_result_count=0,
                    reasons=("no_exact_rate_for_requested_scenario", "no_invented_installment"),
                )

    if banks or detect_product_hint(query):
        result = _single_product_answer(query, banks, family, amount, maturity)
        if result is not None:
            return result

    # Family-only turns such as "ilk konut için" should receive a compact,
    # interpreted options answer instead of falling through to the raw catalog
    # renderer with dozens of links.
    if family is not None and not banks:
        result = _multi_bank_options_answer(query, family, amount, maturity)
        if result is not None:
            return result

    return None
