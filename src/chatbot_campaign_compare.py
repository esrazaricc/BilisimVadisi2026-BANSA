from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

from src.campaign_compare import (
    _normalize,
)

from src.campaign_comparison_universe import (
    CampaignUniverseComparisonResult,
    compare_campaign_universe,
)


@dataclass(frozen=True)
class CampaignCompareRunResult:
    universe_key: str | None
    comparison: CampaignUniverseComparisonResult | None
    missing_fields: tuple[str, ...]
    reasons: tuple[str, ...]


_BANK_ALIASES = (
    (
        "Adil Katilim",
        (
            "adil katilim",
        ),
    ),
    (
        "Albaraka Turk",
        (
            "albaraka turk",
            "albaraka",
        ),
    ),
    (
        "Dunya Katilim",
        (
            "dunya katilim",
        ),
    ),
    (
        "Hayat Finans",
        (
            "hayat finans",
        ),
    ),
    (
        "Kuveyt Turk",
        (
            "kuveyt turk",
            "kuveyt",
        ),
    ),
    (
        "T.O.M. Katilim",
        (
            "tom katilim",
            "tom bank",
        ),
    ),
    (
        "Turkiye Emlak Katilim",
        (
            "turkiye emlak katilim",
            "emlak katilim",
        ),
    ),
    (
        "Turkiye Finans",
        (
            "turkiye finans",
        ),
    ),
    (
        "Vakif Katilim",
        (
            "vakif katilim",
        ),
    ),
    (
        "Ziraat Katilim",
        (
            "ziraat katilim",
        ),
    ),
)


def resolve_campaign_universe_key(
    question: str,
) -> str | None:

    text = _normalize(
        question
    )

    tokens = set(
        text.split()
    )

    if (
        "yeni musteri" in text
        or
        "musteri ol" in text
        or
        "davet et" in text
        or
        "arkadasini getir" in text
    ):

        return "new_customer"

    if (
        tokens
        & {
            "egitim",
            "egitime",
            "okul",
            "kirtasiye",
            "universite",
            "kolej",
            "kurs",
        }
    ):

        return "card_installment"

    if (
        "taksit" in text
        or
        "vade farksiz" in text
        or
        "kar paysiz taksit" in text
    ):

        return "card_installment"

    if (
        tokens
        & {
            "market",
            "supermarket",
            "alisveris",
            "indirim",
            "iade",
            "odul",
            "puan",
            "parafpara",
            "worldpuan",
            "cashback",
            "akaryakit",
            "benzin",
            "motorin",
            "seyahat",
            "tatil",
            "otel",
            "restoran",
            "restaurant",
            "yemek",
            "eticaret",
            "amazon",
            "hepsiburada",
            "trendyol",
            "idefix",
        }
    ):

        return "shopping_benefit"

    if "kart kampany" in text:

        return "card_installment"

    # CAMPAIGN_ALL_ACTIVE_V2
    #
    # Existing semantic universes above still win first.
    #
    # Any remaining explicit campaign comparison uses the
    # broad active-campaign universe. If the user supplied a
    # real topic, the downstream TITLE + URL topic lock will
    # filter this universe.
    if (
        "kampanya" in text
        and any(
            marker in text
            for marker in (
                "karsilastir",
                "karsilastirma",
                "hangisi",
            )
        )
    ):

        return "all_active"

    return None


def _decision_bank_names(
    route_decision,
    question: str,
) -> tuple[str, ...]:

    values = getattr(
        route_decision,
        "bank_names",
        (),
    )

    if values:

        return tuple(
            str(value).strip()
            for value in values
            if str(value).strip()
        )

    text = _normalize(
        question
    )

    found = []

    for canonical, aliases in (
        _BANK_ALIASES
    ):

        if any(
            alias in text
            for alias in aliases
        ):

            found.append(
                canonical
            )

    return tuple(
        dict.fromkeys(
            found
        )
    )


def _parse_question_amount(
    question: str,
) -> Decimal | None:

    match = re.search(
        r"(?<!\d)"
        r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?"
        r"|\d+(?:,\d+)?)"
        r"\s*(?:tl|try)\b",
        str(
            question
            or ""
        ).casefold(),
    )

    if match is None:

        return None

    text = (
        match.group(1)
        .replace(
            ".",
            "",
        )
        .replace(
            ",",
            ".",
        )
    )

    try:

        return Decimal(
            text
        )

    except Exception:

        return None


def _decision_spend_amount(
    route_decision,
    question: str,
) -> Decimal | None:

    value = getattr(
        route_decision,
        "amount",
        None,
    )

    if value is not None:

        try:

            return Decimal(
                str(value)
            )

        except Exception:

            pass

    return _parse_question_amount(
        question
    )


def run_campaign_compare(
    question: str,
    *,
    route_decision=None,
    db_path=None,
) -> CampaignCompareRunResult:

    question = str(
        question
        or ""
    ).strip()

    universe_key = (
        resolve_campaign_universe_key(
            question
        )
    )

    if universe_key is None:

        return CampaignCompareRunResult(
            universe_key=None,
            comparison=None,
            missing_fields=(
                "campaign_topic",
            ),
            reasons=(
                "campaign_universe_unresolved",
            ),
        )

    bank_names = (
        _decision_bank_names(
            route_decision,
            question,
        )
    )

    spend_amount = (
        _decision_spend_amount(
            route_decision,
            question,
        )
    )

    comparison = (
        compare_campaign_universe(
            universe_key,
            bank_names=(
                bank_names
                or None
            ),
            spend_amount=spend_amount,
            question=question,
            db_path=db_path,
        )
    )

    reasons = [
        "deterministic_campaign_engine_executed",
        (
            "campaign_universe:"
            + universe_key
        ),
    ]

    reasons.extend(
        str(value)
        for value
        in comparison.reasons
    )

    return CampaignCompareRunResult(
        universe_key=universe_key,
        comparison=comparison,
        missing_fields=tuple(),
        reasons=tuple(
            dict.fromkeys(
                reasons
            )
        ),
    )
