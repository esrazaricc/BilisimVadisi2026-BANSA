"""BANSA amount-semantics resolver.

A finance conversation can contain several different kinds of amounts.  The
same number must never be silently reinterpreted between them.

Examples:
- "600 bin TL'lik araç" -> asset_value
- "600 bin TL finansman kullanmak istiyorum" -> requested_financing_amount
- "100 bin TL 36 ay araç finansmanlarını karşılaştır" -> requested_financing_amount
- "600 bin için?" -> ambiguous unless the resolved turn explicitly carries a
  value/financing cue.

The resolver only classifies user wording. It never calculates a financial
value.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from src.competition_fast_router import normalize


class AmountKind(str, Enum):
    ASSET_VALUE = "asset_value"
    REQUESTED_FINANCING_AMOUNT = "requested_financing_amount"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AmountSemantics:
    kind: AmountKind
    reason: str


_ASSET_MARKERS = (
    "arac degeri", "tasit degeri", "motosiklet degeri", "motor degeri",
    "fatura degeri", "kasko degeri", "satis degeri", "urun degeri",
    "arac fiyati", "araba fiyati", "motosiklet fiyati", "motor fiyati",
)

_FINANCING_MARKERS = (
    "finansman tutari", "finansman ihtiyaci", "finansman ihtiyacim",
    "finansman kullan", "finansman cek", "kredi cek", "kredi kullan",
    "kullanmak istiyorum", "kullanabilir miyim", "kullanacagim finansman",
    "istedigim finansman", "talep ettigim finansman",
)

_LIMIT_MARKERS = (
    "en fazla ne kadar finansman", "maksimum ne kadar finansman",
    "azami finansman", "finansman limiti", "kac ay vade", "kac aya kadar",
    "en fazla kac ay", "maksimum vade", "azami vade",
)

_ASSET_NOUN_FOR = (
    "arac icin", "tasit icin", "otomobil icin", "motosiklet icin", "motor icin",
)


def resolve_amount_semantics(
    query: str,
    *,
    family: str | None = None,
    amount_present: bool = True,
    compare: bool = False,
) -> AmountSemantics:
    if not amount_present:
        return AmountSemantics(AmountKind.UNKNOWN, "no_amount")

    q = normalize(query)

    if any(marker in q for marker in _ASSET_MARKERS):
        return AmountSemantics(AmountKind.ASSET_VALUE, "explicit_asset_value_wording")

    # Common Turkish shorthand: "600 bin TL'lik araç", "900 binlik araba".
    # normalize() separates apostrophes, so allow an optional scale word and
    # optional TL before the ``lik`` suffix.
    if re.search(
        r"\b\d+(?:[.,]\d+)?\s*(?:bin|milyon)?\s*(?:tl\s*)?lik\s+(?:arac|araba|tasit|otomobil|motosiklet|motor)\b",
        q,
    ):
        return AmountSemantics(AmountKind.ASSET_VALUE, "asset_value_lik_suffix")

    # "600 bin TL araç için en fazla ne kadar finansman / kaç ay?" scopes the
    # amount to the asset because the financing amount is the thing being
    # requested as the answer, not the supplied number.
    if (
        family == "arac_finansmani"
        and any(marker in q for marker in _LIMIT_MARKERS)
        and any(marker in q for marker in _ASSET_NOUN_FOR)
    ):
        return AmountSemantics(AmountKind.ASSET_VALUE, "vehicle_limit_question_scopes_amount_to_asset")

    if any(marker in q for marker in _FINANCING_MARKERS):
        return AmountSemantics(AmountKind.REQUESTED_FINANCING_AMOUNT, "explicit_financing_amount_wording")

    # A normal amount+maturity finance comparison/calculation means requested
    # principal unless the user explicitly says vehicle/property value.
    if compare and family is not None:
        return AmountSemantics(AmountKind.REQUESTED_FINANCING_AMOUNT, "comparison_scenario_amount")

    if family is not None and any(
        marker in q
        for marker in (
            "aylik taksit", "toplam geri odeme", "hesapla", "odeme plani",
            "ayda ne kadar", "ne kadar oderim",
        )
    ):
        return AmountSemantics(AmountKind.REQUESTED_FINANCING_AMOUNT, "calculation_scenario_amount")

    return AmountSemantics(AmountKind.AMBIGUOUS, "amount_role_not_explicit")
