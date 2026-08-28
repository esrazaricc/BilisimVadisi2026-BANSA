from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import sqlite3
import unicodedata
from typing import Iterable


@dataclass(frozen=True)
class CampaignCandidate:
    campaign_id: int
    bank_name: str
    campaign_name: str
    campaign_category: str
    start_date: str | None
    end_date: str | None
    source_url: str | None

    reward_amount: Decimal | None
    discount_rate: Decimal | None
    cashback_value: Decimal | None
    shopping_points: Decimal | None
    campaign_installment_count: Decimal | None
    minimum_spending: Decimal | None
    maximum_benefit: Decimal | None

    minimum_transaction_amount: Decimal | None
    maximum_transaction_amount: Decimal | None
    card_installment_count: Decimal | None
    installment_cost_rate: Decimal | None
    installment_cost_text: str | None

    search_text: str = ""


@dataclass(frozen=True)
class CampaignCriterionWinner:
    criterion: str
    direction: str
    campaign_ids: tuple[int, ...]
    value: Decimal


@dataclass(frozen=True)
class CampaignComparisonResult:
    campaign_category: str
    requested_banks: tuple[str, ...]
    spend_amount: Decimal | None
    candidates: tuple[CampaignCandidate, ...]
    criterion_winners: tuple[CampaignCriterionWinner, ...]
    overall_winner_campaign_ids: tuple[int, ...]
    overall_metric: str | None
    reasons: tuple[str, ...]

    @property
    def may_claim_overall_winner(self) -> bool:
        return bool(
            self.overall_winner_campaign_ids
            and self.overall_metric
        )


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_campaign_db_path() -> Path:
    return (
        _project_root()
        / "data"
        / "campaigns.db"
    )


def _normalize(value: object) -> str:
    text = str(value or "").casefold()

    text = text.replace(
        "\u0131",
        "i",
    )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _bank_key(value: object) -> str:
    return re.sub(
        r"[^a-z0-9]",
        "",
        _normalize(value),
    )


def _to_decimal(
    value: object,
) -> Decimal | None:

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        return Decimal(text)

    except (
        InvalidOperation,
        ValueError,
    ):
        return None


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
        or requested in candidate
        or candidate in requested
    )


_TOPIC_STOPWORDS = {
    "kampanya",
    "kampanyasi",
    "kampanyalari",
    "kampanyalar",
    "karsilastir",
    "karsilastirma",
    "hangisi",
    "hangi",
    "banka",
    "bankalar",
    "bankalarin",
    "avantajli",
    "avantaj",
    "daha",
    "icin",
    "olan",
    "var",
    "mi",
    "mu",
    "harcama",
    "harcamasi",
    "alisveris",
}



def _topic_terms(
    question: str | None,
    *,
    bank_names: Iterable[str] | None = None,
) -> tuple[str, ...]:

    normalized = _normalize(
        question
    )

    bank_tokens = set()

    for bank_name in (
        bank_names
        or ()
    ):

        bank_tokens.update(
            _normalize(
                bank_name
            ).split()
        )

    stopwords = set(
        _TOPIC_STOPWORDS
    )

    stopwords.update(
        {
            "tl",
            "try",
            "turk",
            "katilim",
            "finans",
            "kart",
            "kredi",
            "banka",
            "bankasi",
            "bankasinin",
            "karsilastir",
            "karsilastirir",
            "karsilastirma",
            "kampanya",
            "kampanyasi",
            "kampanyalarini",
            "avantajli",
            "avantajlisi",
            "iyi",
            "iyisi",
            "harcama",
            "harcamada",
            "harcamalarinda",
            "tutar",
            "tutarinda",
        }
    )

    stopwords.update(
        bank_tokens
    )

    terms = []

    for term in normalized.split():

        if len(term) < 3:
            continue

        if term in stopwords:
            continue

        if term.isdigit():
            continue

        terms.append(
            term
        )

    return tuple(
        dict.fromkeys(
            terms
        )
    )




def _topic_score(
    candidate: CampaignCandidate,
    terms: tuple[str, ...],
) -> int:

    if not terms:
        return 0

    alias_groups = (
        frozenset(
            {
                "egitim",
                "egitime",
                "okul",
                "okulu",
                "okullari",
                "universite",
                "universitesi",
                "kirtasiye",
                "kurs",
                "kolej",
            }
        ),
        frozenset(
            {
                "market",
                "markette",
                "marketlerde",
                "supermarket",
            }
        ),
        frozenset(
            {
                "akaryakit",
                "benzin",
                "motorin",
                "petrol",
            }
        ),
        frozenset(
            {
                "seyahat",
                "tatil",
                "otel",
                "ucak",
                "ucus",
                "bilet",
                "turizm",
            }
        ),
        frozenset(
            {
                "restoran",
                "restaurant",
                "yemek",
                "kafe",
                "cafe",
                "gastro",
            }
        ),
        frozenset(
            {
                "eticaret",
                "ecommerce",
                "amazon",
                "hepsiburada",
                "trendyol",
                "n11",
                "idefix",
            }
        ),
    )

    title = _normalize(
        candidate.campaign_name
    )

    url = _normalize(
        candidate.source_url
    )

    title_tokens = tuple(
        title.split()
    )

    url_tokens = tuple(
        url.split()
    )

    query_terms = set(
        terms
    )

    concepts = []
    consumed = set()

    for term in terms:

        if term in consumed:
            continue

        matched_group = None

        for group in alias_groups:

            if term in group:
                matched_group = group
                break

        if matched_group is None:

            concepts.append(
                frozenset(
                    {term}
                )
            )

            consumed.add(
                term
            )

        else:

            concepts.append(
                matched_group
            )

            consumed.update(
                matched_group
            )

    def token_matches(
        token,
        wanted,
    ):

        if token == wanted:
            return True

        if (
            len(wanted) >= 5
            and
            token.startswith(
                wanted
            )
        ):
            return True

        return False

    score = 0

    for concept in concepts:

        # Plain "market" means grocery/supermarket in this
        # comparison context. Do not treat "yapi marketi" as
        # the same topic unless the user actually says yapi,
        # mobilya or dekorasyon.
        if "market" in concept:

            asks_for_hardware_market = bool(
                query_terms
                & {
                    "yapi",
                    "mobilya",
                    "dekorasyon",
                }
            )

            if not asks_for_hardware_market:

                combined = (
                    " "
                    + title
                    + " "
                    + url
                    + " "
                )

                if (
                    " yapi market" in combined
                    or " mobilya " in combined
                    or " dekorasyon " in combined
                ):
                    continue

        title_match = any(
            token_matches(
                token,
                wanted,
            )
            for token in title_tokens
            for wanted in concept
        )

        url_match = any(
            token_matches(
                token,
                wanted,
            )
            for token in url_tokens
            for wanted in concept
        )

        # Each semantic concept contributes only once per
        # field. Aliases cannot artificially multiply score.
        if title_match:
            score += 100

        if url_match:
            score += 50

    return score


def _row_to_candidate(
    row: sqlite3.Row,
) -> CampaignCandidate:

    return CampaignCandidate(
        campaign_id=int(
            row["campaign_id"]
        ),
        bank_name=str(
            row["bank_name"] or ""
        ),
        campaign_name=str(
            row["campaign_name"] or ""
        ),
        campaign_category=str(
            row["campaign_category"] or ""
        ),
        start_date=(
            str(row["start_date"])
            if row["start_date"]
            else None
        ),
        end_date=(
            str(row["end_date"])
            if row["end_date"]
            else None
        ),
        source_url=(
            str(row["source_url"])
            if row["source_url"]
            else None
        ),
        reward_amount=_to_decimal(
            row["reward_amount"]
        ),
        discount_rate=_to_decimal(
            row["discount_rate"]
        ),
        cashback_value=_to_decimal(
            row["cashback_value"]
        ),
        shopping_points=_to_decimal(
            row["shopping_points"]
        ),
        campaign_installment_count=_to_decimal(
            row["campaign_installment_count"]
        ),
        minimum_spending=_to_decimal(
            row["minimum_spending"]
        ),
        maximum_benefit=_to_decimal(
            row["maximum_benefit"]
        ),
        minimum_transaction_amount=_to_decimal(
            row["minimum_transaction_amount"]
        ),
        maximum_transaction_amount=_to_decimal(
            row["maximum_transaction_amount"]
        ),
        card_installment_count=_to_decimal(
            row["card_installment_count"]
        ),
        installment_cost_rate=_to_decimal(
            row["installment_cost_rate"]
        ),
        installment_cost_text=(
            str(row["installment_cost_text"])
            if row["installment_cost_text"]
            else None
        ),
        search_text=str(
            row["clean_text"] or ""
        ),
    )


def load_campaign_candidates(
    campaign_category: str,
    *,
    bank_names: Iterable[str] | None = None,
    question: str | None = None,
    as_of: date | None = None,
    db_path: str | Path | None = None,
) -> tuple[
    tuple[CampaignCandidate, ...],
    tuple[str, ...],
]:

    if not campaign_category:
        return (), (
            "campaign_category_missing",
        )

    path = Path(
        db_path
        or default_campaign_db_path()
    )

    if not path.exists():
        return (), (
            "campaign_database_missing",
        )

    comparison_date = (
        as_of
        or date.today()
    ).isoformat()

    uri = (
        path.resolve().as_uri()
        + "?mode=ro"
    )

    con = sqlite3.connect(
        uri,
        uri=True,
    )

    con.row_factory = sqlite3.Row

    try:

        rows = con.execute(
            """
            SELECT
                v.campaign_id,
                v.bank_name,
                v.campaign_name,
                v.campaign_category,
                v.start_date,
                v.end_date,
                v.source_url,

                v.reward_amount,
                v.discount_rate,
                v.cashback_value,
                v.shopping_points,
                v.campaign_installment_count,
                v.minimum_spending,
                v.maximum_benefit,

                v.minimum_transaction_amount,
                v.maximum_transaction_amount,
                v.card_installment_count,
                v.installment_cost_rate,
                v.installment_cost_text,

                c.clean_text

            FROM live_campaign_comparison v

            JOIN live_campaigns c
                ON c.id = v.campaign_id

            WHERE
                c.is_current = 1

                AND COALESCE(
                    c.comparison_eligible,
                    0
                ) = 1

                AND v.campaign_category = ?

                AND (
                    v.start_date IS NULL
                    OR TRIM(v.start_date) = ''
                    OR DATE(v.start_date) <= DATE(?)
                )

                AND (
                    v.end_date IS NULL
                    OR TRIM(v.end_date) = ''
                    OR DATE(v.end_date) >= DATE(?)
                )

                AND LOWER(
                    COALESCE(
                        v.current_status,
                        ''
                    )
                ) NOT IN (
                    'expired',
                    'removed',
                    'inactive'
                )

            ORDER BY
                LOWER(v.bank_name),
                LOWER(v.campaign_name),
                v.campaign_id
            """,
            (
                campaign_category,
                comparison_date,
                comparison_date,
            ),
        ).fetchall()

    finally:
        con.close()

    candidates = tuple(
        _row_to_candidate(
            row
        )
        for row in rows
    )

    requested = tuple(
        str(name).strip()
        for name in (
            bank_names
            or ()
        )
        if str(name).strip()
    )

    reasons: list[str] = []

    if requested:

        candidates = tuple(
            item
            for item in candidates
            if any(
                _bank_matches(
                    item.bank_name,
                    requested_bank,
                )
                for requested_bank
                in requested
            )
        )

        for requested_bank in requested:

            if not any(
                _bank_matches(
                    item.bank_name,
                    requested_bank,
                )
                for item in candidates
            ):
                reasons.append(
                    "requested_bank_without_candidate:"
                    + requested_bank
                )

    terms = _topic_terms(
        question,
        bank_names=requested,
    )

    if terms and candidates:

        scored = [
            (
                _topic_score(
                    item,
                    terms,
                ),
                item,
            )
            for item in candidates
        ]

        positive = [
            (
                score,
                item,
            )
            for score, item
            in scored
            if score > 0
        ]

        if positive:

            # Candidate selection is a semantic eligibility
            # decision, not a relevance ranking.
            #
            # Keep every campaign with a genuine title/URL
            # match. Do not discard a correct campaign merely
            # because another title contains a stronger alias.
            candidates = tuple(
                item
                for score, item
                in positive
            )

            reasons.append(
                "topic_filter_title_url_lock"
            )

        else:

            candidates = ()

            reasons.append(
                "topic_filter_no_primary_match"
            )

    return (
        candidates,
        tuple(reasons),
    )


def _criterion_value(
    item: CampaignCandidate,
    field_name: str,
) -> Decimal | None:

    if field_name == "installment_count":

        return (
            item.card_installment_count
            if item.card_installment_count
            is not None
            else
            item.campaign_installment_count
        )

    return getattr(
        item,
        field_name,
    )


def _criterion_definitions(
    campaign_category: str,
) -> tuple[
    tuple[str, str, str],
    ...,
]:

    if campaign_category == "card_campaign":

        return (
            (
                "installment_count",
                "installment_count",
                "max",
            ),
            (
                "installment_cost_rate",
                "installment_cost_rate",
                "min",
            ),
            (
                "maximum_transaction_amount",
                "maximum_transaction_amount",
                "max",
            ),
            (
                "minimum_transaction_amount",
                "minimum_transaction_amount",
                "min",
            ),
        )

    return (
        (
            "reward_amount",
            "reward_amount",
            "max",
        ),
        (
            "discount_rate",
            "discount_rate",
            "max",
        ),
        (
            "cashback_value",
            "cashback_value",
            "max",
        ),
        (
            "shopping_points",
            "shopping_points",
            "max",
        ),
        (
            "maximum_benefit",
            "maximum_benefit",
            "max",
        ),
        (
            "minimum_spending",
            "minimum_spending",
            "min",
        ),
        (
            "installment_count",
            "installment_count",
            "max",
        ),
    )


def evaluate_criterion_winners(
    candidates: Iterable[CampaignCandidate],
    campaign_category: str,
) -> tuple[CampaignCriterionWinner, ...]:

    items = tuple(
        candidates
    )

    if len(items) < 2:
        return ()

    winners = []

    for (
        criterion,
        field_name,
        direction,
    ) in _criterion_definitions(
        campaign_category
    ):

        values = [
            _criterion_value(
                item,
                field_name,
            )
            for item in items
        ]

        if any(
            value is None
            for value in values
        ):
            continue

        target = (
            max(values)
            if direction == "max"
            else min(values)
        )

        campaign_ids = tuple(
            item.campaign_id
            for item, value
            in zip(
                items,
                values,
            )
            if value == target
        )

        winners.append(
            CampaignCriterionWinner(
                criterion=criterion,
                direction=direction,
                campaign_ids=campaign_ids,
                value=target,
            )
        )

    return tuple(
        winners
    )


def _effective_monetary_benefit(
    item: CampaignCandidate,
    spend_amount: Decimal,
) -> Decimal | None:

    if spend_amount < 0:
        return None

    if (
        item.minimum_spending
        is not None
        and
        spend_amount
        < item.minimum_spending
    ):
        return Decimal("0")

    possible = []

    if item.reward_amount is not None:
        possible.append(
            item.reward_amount
        )

    if item.cashback_value is not None:
        possible.append(
            item.cashback_value
        )

    if item.discount_rate is not None:
        possible.append(
            spend_amount
            * item.discount_rate
            / Decimal("100")
        )

    if not possible:
        return None

    benefit = max(
        possible
    )

    if item.maximum_benefit is not None:
        benefit = min(
            benefit,
            item.maximum_benefit,
        )

    return benefit


def compare_campaigns(
    campaign_category: str,
    *,
    bank_names: Iterable[str] | None = None,
    spend_amount: Decimal | int | float | str | None = None,
    question: str | None = None,
    as_of: date | None = None,
    db_path: str | Path | None = None,
) -> CampaignComparisonResult:

    requested = tuple(
        str(name).strip()
        for name in (
            bank_names
            or ()
        )
        if str(name).strip()
    )

    spend = _to_decimal(
        spend_amount
    )

    candidates, load_reasons = (
        load_campaign_candidates(
            campaign_category,
            bank_names=requested,
            question=question,
            as_of=as_of,
            db_path=db_path,
        )
    )

    reasons = list(
        load_reasons
    )

    if not candidates:
        reasons.append(
            "no_comparable_campaign_candidates"
        )

    criterion_winners = (
        evaluate_criterion_winners(
            candidates,
            campaign_category,
        )
    )

    overall_ids: tuple[int, ...] = ()
    overall_metric = None

    if (
        len(candidates) >= 2
        and spend is not None
        and campaign_category
        not in {
            "card_campaign",
            "finance_campaign",
        }
    ):

        effective = [
            _effective_monetary_benefit(
                item,
                spend,
            )
            for item in candidates
        ]

        if all(
            value is not None
            for value in effective
        ):

            target = max(
                effective
            )

            overall_ids = tuple(
                item.campaign_id
                for item, value
                in zip(
                    candidates,
                    effective,
                )
                if value == target
            )

            overall_metric = (
                "effective_monetary_benefit_at_requested_spend"
            )

            if len(
                overall_ids
            ) > 1:
                reasons.append(
                    "overall_campaign_tie"
                )

        else:
            reasons.append(
                "overall_ranking_blocked_incomplete_monetary_benefit"
            )

    elif spend is None:
        reasons.append(
            "overall_ranking_requires_spend_amount"
        )

    elif campaign_category in {
        "card_campaign",
        "finance_campaign",
    }:
        reasons.append(
            "overall_ranking_blocked_for_campaign_category"
        )

    return CampaignComparisonResult(
        campaign_category=campaign_category,
        requested_banks=requested,
        spend_amount=spend,
        candidates=candidates,
        criterion_winners=criterion_winners,
        overall_winner_campaign_ids=overall_ids,
        overall_metric=overall_metric,
        reasons=tuple(
            dict.fromkeys(
                reasons
            )
        ),
    )

# ============================================================
# CAMPAIGN_TOPIC_DISCOURSE_GUARD_V1
# ============================================================

_topic_terms_before_discourse_guard_v1 = (
    _topic_terms
)


_CAMPAIGN_TOPIC_NON_SEMANTIC_TERMS_V1 = frozenset(
    (
        "peki",
        "sadece",
        "yalniz",
        "yalnizca",

        # Campaign time/scope words are not semantic topics.
        "guncel",
        "gecerli",
        "aktif",
        "bugun",
        "bugunku",
        "su",
        "anda",

        "ile",
        "olan",
        "olanlar",
    )
)


def _topic_terms(
    question,
    *args,
    **kwargs,
):

    terms = (
        _topic_terms_before_discourse_guard_v1(
            question,
            *args,
            **kwargs,
        )
    )

    safe_terms = []

    for term in terms:

        normalized_term = _normalize(
            str(
                term
                or ""
            )
        )

        if (
            normalized_term
            in _CAMPAIGN_TOPIC_NON_SEMANTIC_TERMS_V1
        ):

            continue

        safe_terms.append(
            term
        )

    return tuple(
        dict.fromkeys(
            safe_terms
        )
    )
