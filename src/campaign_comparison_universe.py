from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import sqlite3
from typing import Iterable

from src.campaign_compare import (
    CampaignCandidate,
    CampaignCriterionWinner,
    _effective_monetary_benefit,
    _normalize,
    default_campaign_db_path,
    evaluate_criterion_winners,
    load_campaign_candidates,
)


CAMPAIGN_COMPARISON_UNIVERSES = {
    "shopping_benefit": (
        "discount_campaign",
        "points_campaign",
    ),
    "card_installment": (
        "card_campaign",
    ),
    "new_customer": (
        "new_customer_campaign",
    ),
    "all_active": (
        "card_campaign",
        "discount_campaign",
        "points_campaign",
        "new_customer_campaign",
        "finance_campaign",
        "other_campaign",
        "insurance_campaign",
    ),
}


@dataclass(frozen=True)
class CampaignBankRepresentative:
    bank_name: str
    campaign_ids: tuple[int, ...]
    effective_monetary_benefit: Decimal


@dataclass(frozen=True)
class CampaignUniverseComparisonResult:
    universe_key: str
    categories: tuple[str, ...]
    requested_banks: tuple[str, ...]
    spend_amount: Decimal | None

    candidates: tuple[
        CampaignCandidate,
        ...
    ]

    criterion_winners: tuple[
        CampaignCriterionWinner,
        ...
    ]

    bank_representatives: tuple[
        CampaignBankRepresentative,
        ...
    ]

    overall_winner_bank_names: tuple[
        str,
        ...
    ]

    overall_winner_campaign_ids: tuple[
        int,
        ...
    ]

    overall_metric: str | None
    reasons: tuple[str, ...]

    @property
    def may_claim_overall_winner(self) -> bool:
        return bool(
            self.overall_winner_bank_names
            and
            self.overall_winner_campaign_ids
            and
            self.overall_metric
        )


def resolve_campaign_comparison_universe(
    universe_key: str,
) -> tuple[str, ...]:

    return tuple(
        CAMPAIGN_COMPARISON_UNIVERSES.get(
            str(
                universe_key
                or ""
            ).strip(),
            (),
        )
    )


def _to_decimal(
    value: object,
) -> Decimal | None:

    if value is None:
        return None

    text = str(
        value
    ).strip()

    if not text:
        return None

    try:
        return Decimal(
            text
        )

    except (
        InvalidOperation,
        ValueError,
    ):
        return None


def _bank_key(
    value: object,
) -> str:

    text = str(
        value
        or ""
    ).casefold()

    for old, new in (
        ("\u0131", "i"),
        ("\u015f", "s"),
        ("\u011f", "g"),
        ("\u00fc", "u"),
        ("\u00f6", "o"),
        ("\u00e7", "c"),
    ):
        text = text.replace(
            old,
            new,
        )

    return "".join(
        char
        for char in text
        if char.isalnum()
    )


def _bank_matches(
    candidate_bank: str,
    requested_bank: str,
) -> bool:

    candidate = _bank_key(
        candidate_bank
    )

    requested = _bank_key(
        requested_bank
    )

    if not candidate or not requested:
        return False

    return (
        candidate == requested
        or candidate in requested
        or requested in candidate
    )


def _deduplicate_candidates(
    candidates: Iterable[
        CampaignCandidate
    ],
) -> tuple[
    CampaignCandidate,
    ...
]:

    seen = set()
    result = []

    for candidate in candidates:

        if candidate.campaign_id in seen:
            continue

        seen.add(
            candidate.campaign_id
        )

        result.append(
            candidate
        )

    return tuple(
        result
    )


def _criterion_category(
    universe_key: str,
) -> str:

    if universe_key == "card_installment":
        return "card_campaign"

    return "discount_campaign"


def _may_attempt_monetary_ranking(
    universe_key: str,
) -> bool:

    return universe_key in {
        "shopping_benefit",
        "new_customer",
    }


def _build_bank_representatives(
    candidates: tuple[
        CampaignCandidate,
        ...
    ],
    spend: Decimal,
) -> tuple[
    tuple[
        CampaignBankRepresentative,
        ...
    ],
    bool,
]:

    if not candidates:
        return (), False

    grouped = {}

    for candidate in candidates:

        grouped.setdefault(
            candidate.bank_name,
            [],
        ).append(
            candidate
        )

    representatives = []

    for bank_name, bank_candidates in grouped.items():

        values = []

        for candidate in bank_candidates:

            value = (
                _effective_monetary_benefit(
                    candidate,
                    spend,
                )
            )

            values.append(
                (
                    candidate,
                    value,
                )
            )

        # Strict grounding:
        #
        # If even one applicable candidate for a bank
        # has an unknown monetary equivalent, we cannot
        # safely claim that we know that bank's best
        # monetary campaign.
        if any(
            value is None
            for _, value in values
        ):
            return (), False

        best_value = max(
            value
            for _, value
            in values
        )

        best_ids = tuple(
            candidate.campaign_id
            for candidate, value
            in values
            if value == best_value
        )

        representatives.append(
            CampaignBankRepresentative(
                bank_name=bank_name,
                campaign_ids=best_ids,
                effective_monetary_benefit=(
                    best_value
                ),
            )
        )

    representatives.sort(
        key=lambda item: (
            _bank_key(
                item.bank_name
            ),
            item.campaign_ids,
        )
    )

    return (
        tuple(
            representatives
        ),
        True,
    )



_BUSINESS_SCOPE_TERMS = frozenset(
    {
        "ticari",
        "isletme",
        "isletmeler",
        "kobi",
        "kobiler",
        "esnaf",
        "kurumsal",
        "business",
        "pos",
        "satici",
        "saticilar",
        "toptanci",
        "toptancilar",
    }
)


def _detect_customer_scope(
    question: str | None,
) -> str:

    tokens = set(
        _normalize(
            question
        ).split()
    )

    if (
        tokens
        & _BUSINESS_SCOPE_TERMS
    ):
        return "business"

    return "individual"


def _topic_question_without_scope(
    question: str | None,
) -> str | None:

    normalized = _normalize(
        question
    )

    if not normalized:
        return question

    tokens = [
        token
        for token
        in normalized.split()
        if token
        not in _BUSINESS_SCOPE_TERMS
    ]

    return " ".join(
        tokens
    )


def _load_source_groups(
    candidates: tuple[
        CampaignCandidate,
        ...
    ],
    *,
    db_path: str | Path | None,
) -> dict[int, str]:

    if not candidates:
        return {}

    path = Path(
        db_path
        or default_campaign_db_path()
    )

    if not path.exists():
        return {}

    try:

        uri = (
            path.resolve().as_uri()
            + "?mode=ro"
        )

        con = sqlite3.connect(
            uri,
            uri=True,
        )

        try:

            columns = {
                row[1]
                for row in con.execute(
                    "PRAGMA table_info(live_campaigns)"
                ).fetchall()
            }

            if "source_group" not in columns:
                return {}

            ids = tuple(
                candidate.campaign_id
                for candidate in candidates
            )

            placeholders = ",".join(
                "?"
                for _ in ids
            )

            rows = con.execute(
                f"""
                SELECT
                    id,
                    source_group
                FROM live_campaigns
                WHERE id IN (
                    {placeholders}
                )
                """,
                ids,
            ).fetchall()

            return {
                int(
                    campaign_id
                ): str(
                    source_group
                    or ""
                )
                for campaign_id, source_group
                in rows
            }

        finally:
            con.close()

    except sqlite3.Error:
        return {}


def _is_business_candidate(
    candidate: CampaignCandidate,
    source_group: str = "",
) -> bool:

    raw_url = str(
        candidate.source_url
        or ""
    ).casefold()

    normalized_url = _normalize(
        raw_url
    )

    normalized_title = _normalize(
        candidate.campaign_name
    )

    normalized_group = _normalize(
        source_group
    )

    # Strong official navigation/source signals.
    if any(
        signal in raw_url
        for signal in (
            "/isim-icin/",
            "/ticari/",
            "/kurumsal/",
            "/business/",
            "/kobi/",
            "/pos-kampanyalari/",
        )
    ):
        return True

    if any(
        phrase in normalized_group
        for phrase in (
            "ticari",
            "business",
            "kurumsal",
            "kobi",
            "pos kampanyalari",
        )
    ):
        return True

    # Strong title-level commercial audience signals.
    title_tokens = set(
        normalized_title.split()
    )

    if (
        title_tokens
        & {
            "ticari",
            "business",
            "kobi",
            "esnaf",
            "toptanci",
            "toptancilar",
            "satici",
            "saticilar",
        }
    ):
        return True

    if (
        "taksitli pos" in normalized_title
        or
        "pos kampanyasi" in normalized_title
        or
        "pos kampanyalari" in normalized_title
    ):
        return True

    # URL fallback for normalized forms.
    if any(
        phrase in normalized_url
        for phrase in (
            "ticari kampanya",
            "business campaign",
            "pos kampanyalari",
        )
    ):
        return True

    return False


def _apply_customer_scope(
    candidates: tuple[
        CampaignCandidate,
        ...
    ],
    *,
    question: str | None,
    db_path: str | Path | None,
) -> tuple[
    tuple[
        CampaignCandidate,
        ...
    ],
    str,
    int,
]:

    scope = _detect_customer_scope(
        question
    )

    source_groups = (
        _load_source_groups(
            candidates,
            db_path=db_path,
        )
    )

    kept = []

    for candidate in candidates:

        is_business = (
            _is_business_candidate(
                candidate,
                source_groups.get(
                    candidate.campaign_id,
                    "",
                ),
            )
        )

        if scope == "business":

            if is_business:
                kept.append(
                    candidate
                )

        else:

            if not is_business:
                kept.append(
                    candidate
                )

    return (
        tuple(
            kept
        ),
        scope,
        (
            len(candidates)
            - len(kept)
        ),
    )




def compare_campaign_universe(
    universe_key: str,
    *,
    bank_names: Iterable[str] | None = None,
    spend_amount: Decimal | int | float | str | None = None,
    question: str | None = None,
    as_of: date | None = None,
    db_path: str | Path | None = None,
) -> CampaignUniverseComparisonResult:

    categories = (
        resolve_campaign_comparison_universe(
            universe_key
        )
    )

    normalized_question = (
        _normalize(
            question
        )
    )

    market_listing_bridge = (
        universe_key == "shopping_benefit"
        and
        "market" in normalized_question
        and
        "kampanya" in normalized_question
        and
        "karsilastir" in normalized_question
        and
        spend_amount is None
        and
        not any(
            marker in normalized_question
            for marker
            in (
                "indirim",
                "iade",
                "odul",
                "puan",
                "cashback",
                "parasal fayda",
                "kazanc",
                "daha avantajli",
                "en avantajli",
                "hangisi daha",
                "daha uygun",
                "en uygun",
                "daha iyi",
                "en iyi",
            )
        )
    )

    if (
        market_listing_bridge
        and
        "card_campaign"
        not in categories
    ):

        categories = (
            tuple(
                categories
            )
            + (
                "card_campaign",
            )
        )

    requested = tuple(
        str(
            name
        ).strip()
        for name in (
            bank_names
            or ()
        )
        if str(
            name
        ).strip()
    )

    spend = _to_decimal(
        spend_amount
    )

    if not categories:

        return CampaignUniverseComparisonResult(
            universe_key=universe_key,
            categories=(),
            requested_banks=requested,
            spend_amount=spend,
            candidates=(),
            criterion_winners=(),
            bank_representatives=(),
            overall_winner_bank_names=(),
            overall_winner_campaign_ids=(),
            overall_metric=None,
            reasons=(
                "unknown_campaign_comparison_universe",
            ),
        )

    all_candidates = []
    reasons = []

    topic_question = (
        _topic_question_without_scope(
            question
        )
    )

    customer_scope = (
        _detect_customer_scope(
            question
        )
    )

    for category in categories:

        candidates, category_reasons = (
            load_campaign_candidates(
                category,
                bank_names=requested,
                question=topic_question,
                as_of=as_of,
                db_path=db_path,
            )
        )

        all_candidates.extend(
            candidates
        )

        for reason in category_reasons:

            reasons.append(
                category
                + ":"
                + reason
            )

    candidates = (
        _deduplicate_candidates(
            all_candidates
        )
    )

    all_active_scope_tokens = set(
        _normalize(
            question
        ).split()
    )

    all_active_individual_terms = frozenset(
        {
            "bireysel",
            "kisisel",
            "kendim",
            "ferdi",
            "sahsi",
        }
    )

    all_active_has_explicit_scope = bool(
        all_active_scope_tokens
        & (
            _BUSINESS_SCOPE_TERMS
            |
            all_active_individual_terms
        )
    )

    if (
        (
            universe_key == "all_active"
            or
            market_listing_bridge
        )
        and
        not all_active_has_explicit_scope
    ):

        customer_scope = (
            "unspecified"
        )

        scope_filtered_count = 0

    else:

        (
            candidates,
            customer_scope,
            scope_filtered_count,
        ) = _apply_customer_scope(
            candidates,
            question=question,
            db_path=db_path,
        )

    if market_listing_bridge:

        reasons.append(
            "market_card_campaign_bridge"
        )

    reasons.append(
        "customer_scope:"
        + customer_scope
    )

    if scope_filtered_count:

        reasons.append(
            "customer_scope_filtered:"
            + str(
                scope_filtered_count
            )
        )

    if not candidates:

        reasons.append(
            "no_comparable_campaign_candidates"
        )

    missing_requested_bank = False

    if requested:

        for requested_bank in requested:

            matched = any(
                _bank_matches(
                    candidate.bank_name,
                    requested_bank,
                )
                for candidate
                in candidates
            )

            if not matched:

                missing_requested_bank = True

                reasons.append(
                    "requested_bank_without_candidate:"
                    + requested_bank
                )

    if universe_key == "all_active":

        criterion_winners = ()

        reasons.append(
            "criterion_ranking_blocked_for_all_active"
        )

    else:

        criterion_winners = (
            evaluate_criterion_winners(
                candidates,
                _criterion_category(
                    universe_key
                ),
            )
        )

    bank_representatives = ()
    overall_bank_names = ()
    overall_campaign_ids = ()
    overall_metric = None

    if not _may_attempt_monetary_ranking(
        universe_key
    ):

        reasons.append(
            "overall_ranking_blocked_for_campaign_universe"
        )

    elif spend is None:

        reasons.append(
            "overall_ranking_requires_spend_amount"
        )

    elif missing_requested_bank:

        reasons.append(
            "overall_ranking_blocked_requested_bank_missing"
        )

    elif not candidates:

        reasons.append(
            "overall_ranking_requires_campaign_candidates"
        )

    else:

        (
            bank_representatives,
            complete,
        ) = _build_bank_representatives(
            candidates,
            spend,
        )

        if not complete:

            reasons.append(
                "overall_ranking_blocked_incomplete_monetary_benefit"
            )

        elif len(
            bank_representatives
        ) < 2:

            reasons.append(
                "overall_ranking_requires_multiple_banks"
            )

        else:

            best_value = max(
                item.effective_monetary_benefit
                for item
                in bank_representatives
            )

            winning_representatives = tuple(
                item
                for item
                in bank_representatives
                if (
                    item.effective_monetary_benefit
                    == best_value
                )
            )

            overall_bank_names = tuple(
                item.bank_name
                for item
                in winning_representatives
            )

            overall_campaign_ids = tuple(
                campaign_id
                for item
                in winning_representatives
                for campaign_id
                in item.campaign_ids
            )

            overall_metric = (
                "best_bank_effective_monetary_benefit_at_requested_spend"
            )

            if len(
                overall_bank_names
            ) > 1:

                reasons.append(
                    "overall_bank_tie"
                )

    return CampaignUniverseComparisonResult(
        universe_key=universe_key,
        categories=categories,
        requested_banks=requested,
        spend_amount=spend,
        candidates=candidates,
        criterion_winners=criterion_winners,
        bank_representatives=(
            bank_representatives
        ),
        overall_winner_bank_names=(
            overall_bank_names
        ),
        overall_winner_campaign_ids=(
            overall_campaign_ids
        ),
        overall_metric=overall_metric,
        reasons=tuple(
            dict.fromkeys(
                reasons
            )
        ),
    )

# ============================================================
# CAMPAIGN_INSTALLMENT_CONSISTENCY_GUARD_V1_1
# ============================================================

from dataclasses import replace as _installment_replace_v1_1


_compare_campaign_universe_before_installment_guard_v1_1 = (
    compare_campaign_universe
)


def _installment_int_v1_1(
    value,
):

    if value is None:
        return None

    try:

        number = Decimal(
            str(value)
        )

    except Exception:
        return None

    if (
        number
        != number.to_integral_value()
    ):
        return None

    result = int(
        number
    )

    if (
        result < 2
        or result > 36
    ):
        return None

    return result


def _explicit_installment_numbers_v1_1(
    candidate,
) -> tuple[int, ...]:

    values = set()

    texts = (
        str(
            candidate.campaign_name
            or ""
        ),
        str(
            candidate.source_url
            or ""
        ),
    )

    patterns = (
        r"(?<!\d)(\d{1,2})\s+taksit\b",
        r"\+(\d{1,2})\s+taksit\b",
        r"(?<!\d)(\d{1,2})\s+aya\s+kadar\s+.*?taksit\b",
        r"(?<!\d)(\d{1,2})\s+aya\s+varan\s+.*?taksit\b",
        r"(?<!\d)(\d{1,2})\s+ay\s+.*?taksit\b",
    )

    for raw_text in texts:

        text = _normalize(
            raw_text
        )

        for pattern in patterns:

            for match in re.finditer(
                pattern,
                text,
            ):

                value = int(
                    match.group(1)
                )

                if (
                    2
                    <= value
                    <= 36
                ):

                    values.add(
                        value
                    )

    return tuple(
        sorted(
            values
        )
    )


def _sanitize_installment_candidate_v1_1(
    candidate,
):

    official_numbers = set(
        _explicit_installment_numbers_v1_1(
            candidate
        )
    )

    # No explicit number in title/URL.
    # Structured data may originate from page body,
    # therefore keep it.
    if not official_numbers:

        return (
            candidate,
            False,
        )

    card_value = (
        _installment_int_v1_1(
            candidate.card_installment_count
        )
    )

    campaign_value = (
        _installment_int_v1_1(
            candidate.campaign_installment_count
        )
    )

    structured_numbers = {
        value
        for value in (
            card_value,
            campaign_value,
        )
        if value is not None
    }

    if not structured_numbers:

        return (
            candidate,
            False,
        )

    # Safe only if title/URL gives exactly one
    # installment number and all structured
    # installment values agree with it.
    if (
        len(
            official_numbers
        ) == 1
        and
        structured_numbers
        == official_numbers
    ):

        return (
            candidate,
            False,
        )

    sanitized = (
        _installment_replace_v1_1(
            candidate,
            card_installment_count=None,
            campaign_installment_count=None,
        )
    )

    return (
        sanitized,
        True,
    )


def _apply_installment_consistency_guard_v1_1(
    candidates,
):

    safe_candidates = []
    blocked_ids = []

    for candidate in candidates:

        (
            safe_candidate,
            blocked,
        ) = (
            _sanitize_installment_candidate_v1_1(
                candidate
            )
        )

        safe_candidates.append(
            safe_candidate
        )

        if blocked:

            blocked_ids.append(
                candidate.campaign_id
            )

    return (
        tuple(
            safe_candidates
        ),
        tuple(
            blocked_ids
        ),
    )


def compare_campaign_universe(
    universe_key: str,
    *,
    bank_names: Iterable[str] | None = None,
    spend_amount: Decimal | int | float | str | None = None,
    question: str | None = None,
    as_of: date | None = None,
    db_path: str | Path | None = None,
) -> CampaignUniverseComparisonResult:

    result = (
        _compare_campaign_universe_before_installment_guard_v1_1(
            universe_key,
            bank_names=bank_names,
            spend_amount=spend_amount,
            question=question,
            as_of=as_of,
            db_path=db_path,
        )
    )

    (
        safe_candidates,
        blocked_ids,
    ) = (
        _apply_installment_consistency_guard_v1_1(
            result.candidates
        )
    )

    if not blocked_ids:

        return result

    if universe_key == "all_active":

        safe_criterion_winners = ()

    else:

        safe_criterion_winners = (
            evaluate_criterion_winners(
                safe_candidates,
                _criterion_category(
                    universe_key
                ),
            )
        )

    reasons = list(
        result.reasons
    )

    reasons.append(
        "installment_consistency_conflicts_present"
    )

    for campaign_id in blocked_ids:

        reasons.append(
            "installment_consistency_blocked:"
            + str(
                campaign_id
            )
        )

    return _installment_replace_v1_1(
        result,
        candidates=safe_candidates,
        criterion_winners=(
            safe_criterion_winners
        ),
        reasons=tuple(
            dict.fromkeys(
                reasons
            )
        ),
    )
