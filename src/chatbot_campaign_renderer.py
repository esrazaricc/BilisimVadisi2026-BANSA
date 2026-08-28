from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.source_link_resolver import resolve_campaign_detail_url


@dataclass(frozen=True)
class CampaignRenderedAnswer:
    text: str
    ranking_claimed: bool
    ranking_metric: str | None
    campaign_ids: tuple[int, ...]
    bank_names: tuple[str, ...]
    reasons: tuple[str, ...] = ()


_LABELS = {
    "reward_amount":
        "En y\u00fcksek \u00f6d\u00fcl",

    "discount_rate":
        "En y\u00fcksek indirim / iade oran\u0131",

    "cashback_value":
        "En y\u00fcksek nakit iade",

    "shopping_points":
        "En y\u00fcksek al\u0131\u015fveri\u015f puan\u0131",

    "maximum_benefit":
        "En y\u00fcksek maksimum fayda",

    "minimum_spending":
        "En d\u00fc\u015f\u00fck minimum harcama",

    "installment_count":
        "En fazla taksit",

    "installment_cost_rate":
        "En d\u00fc\u015f\u00fck ek maliyet oran\u0131",

    "maximum_transaction_amount":
        "En y\u00fcksek i\u015flem limiti",

    "minimum_transaction_amount":
        "En d\u00fc\u015f\u00fck minimum i\u015flem tutar\u0131",
}


_TL_FIELDS = {
    "reward_amount",
    "cashback_value",
    "maximum_benefit",
    "minimum_spending",
    "maximum_transaction_amount",
    "minimum_transaction_amount",
}


_PERCENT_FIELDS = {
    "discount_rate",
    "installment_cost_rate",
}


def _fmt(
    value,
) -> str:

    if value is None:

        return "-"

    try:

        number = Decimal(
            str(value)
        )

    except Exception:

        return str(
            value
        )

    text = f"{number:,.2f}"

    text = (
        text
        .replace(
            ",",
            "X",
        )
        .replace(
            ".",
            ",",
        )
        .replace(
            "X",
            ".",
        )
    )

    if text.endswith(
        ",00"
    ):

        text = text[:-3]

    return text


def _criterion_text(
    criterion,
    value,
):

    text = _fmt(
        value
    )

    if criterion in _TL_FIELDS:

        return (
            text
            + " TL"
        )

    if criterion in _PERCENT_FIELDS:

        return (
            "%"
            + text
        )

    if criterion == "shopping_points":

        return (
            text
            + " puan"
        )

    if criterion == "installment_count":

        return (
            text
            + " taksit"
        )

    return text


def _details(
    candidate,
):

    result = []

    if candidate.reward_amount is not None:

        result.append(
            "\u00d6d\u00fcl: "
            + _fmt(
                candidate.reward_amount
            )
            + " TL"
        )

    if candidate.discount_rate is not None:

        result.append(
            "\u0130ndirim / iade: %"
            + _fmt(
                candidate.discount_rate
            )
        )

    if candidate.cashback_value is not None:

        result.append(
            "Nakit iade: "
            + _fmt(
                candidate.cashback_value
            )
            + " TL"
        )

    if candidate.shopping_points is not None:

        result.append(
            "Puan: "
            + _fmt(
                candidate.shopping_points
            )
        )

    installments = (
        candidate.card_installment_count
        if (
            candidate.card_installment_count
            is not None
        )
        else
        candidate.campaign_installment_count
    )

    if installments is not None:

        result.append(
            "Taksit: "
            + _fmt(
                installments
            )
        )

    if candidate.minimum_spending is not None:

        result.append(
            "Minimum harcama: "
            + _fmt(
                candidate.minimum_spending
            )
            + " TL"
        )

    if candidate.maximum_benefit is not None:

        result.append(
            "Maksimum fayda: "
            + _fmt(
                candidate.maximum_benefit
            )
            + " TL"
        )

    if candidate.end_date:

        result.append(
            "Biti\u015f: "
            + str(
                candidate.end_date
            )
        )

    return result


def render_campaign_answer(
    comparison,
) -> CampaignRenderedAnswer:

    if comparison is None:

        return CampaignRenderedAnswer(
            text=(
                "Kampanya kar\u015f\u0131la\u015ft\u0131rmas\u0131 "
                "i\u00e7in konuyu biraz daha net belirtin."
            ),
            ranking_claimed=False,
            ranking_metric=None,
            campaign_ids=(),
            bank_names=(),
            reasons=(
                "campaign_comparison_missing",
            ),
        )

    candidates = tuple(
        getattr(
            comparison,
            "candidates",
            (),
        )
    )

    if not candidates:

        return CampaignRenderedAnswer(
            text=(
                "Bu kapsamda kar\u015f\u0131la\u015ft\u0131r\u0131labilir "
                "aktif kampanya bulunamad\u0131. "
                "Eksik veya e\u015fitlenemeyen veriler "
                "i\u00e7in de\u011fer \u00fcretmedim."
            ),
            ranking_claimed=False,
            ranking_metric=None,
            campaign_ids=(),
            bank_names=(),
            reasons=(
                "no_campaign_candidates_rendered",
            ),
        )

    universe_key = str(
        getattr(
            comparison,
            "universe_key",
            "",
        )
        or ""
    ).strip()

    display_candidates = (
        candidates[:12]
    )

    if universe_key == "all_active":

        requested_banks = tuple(
            str(value).strip()
            for value
            in getattr(
                comparison,
                "requested_banks",
                (),
            )
            if str(value).strip()
        )

        if not requested_banks:

            requested_banks = tuple(
                dict.fromkeys(
                    item.bank_name
                    for item
                    in candidates
                )
            )

        buckets = {
            bank: [
                item
                for item
                in candidates
                if item.bank_name == bank
            ]
            for bank
            in requested_banks
        }

        balanced = []
        row_index = 0

        while len(balanced) < 12:

            added = False

            for bank in requested_banks:

                bucket = buckets.get(
                    bank,
                    (),
                )

                if row_index >= len(bucket):
                    continue

                balanced.append(
                    bucket[row_index]
                )

                added = True

                if len(balanced) >= 12:
                    break

            if not added:
                break

            row_index += 1

        if balanced:

            display_candidates = tuple(
                balanced
            )

    lines = [
        "Kar\u015f\u0131la\u015ft\u0131r\u0131labilir aktif kampanyalar:",
        "",
    ]

    for candidate in display_candidates:

        lines.append(
            "- "
            + candidate.bank_name
            + " - "
            + candidate.campaign_name
        )

        details = _details(
            candidate
        )

        if details:

            lines.append(
                "  "
                + " | ".join(
                    details
                )
            )

        resolved_source = resolve_campaign_detail_url(
            candidate.bank_name, candidate.campaign_name, candidate.source_url
        )
        if resolved_source:

            lines.append(
                "  Kaynak: "
                + resolved_source
            )

    if len(candidates) > 12:

        lines.extend(
            [
                "",
                (
                    "Toplam "
                    + str(
                        len(candidates)
                    )
                    + " uygun kampanya bulundu; "
                    "ilk 12 kay\u0131t g\u00f6sterildi."
                ),
            ]
        )

    candidate_map = {
        item.campaign_id:
            item
        for item
        in candidates
    }

    winners = tuple(
        getattr(
            comparison,
            "criterion_winners",
            (),
        )
    )

    if winners:

        lines.extend(
            [
                "",
                "Kriter baz\u0131nda:",
            ]
        )

        for winner in winners:

            matched = [
                candidate_map[
                    campaign_id
                ]
                for campaign_id
                in winner.campaign_ids
                if campaign_id
                in candidate_map
            ]

            if not matched:

                continue

            names = ", ".join(
                (
                    item.bank_name
                    + " - "
                    + item.campaign_name
                )
                for item in matched
            )

            lines.append(
                "- "
                + _LABELS.get(
                    winner.criterion,
                    winner.criterion,
                )
                + ": "
                + names
                + " ("
                + _criterion_text(
                    winner.criterion,
                    winner.value,
                )
                + ")"
            )

    ranking_claimed = bool(
        getattr(
            comparison,
            "may_claim_overall_winner",
            False,
        )
    )

    reasons = tuple(
        str(value)
        for value
        in getattr(
            comparison,
            "reasons",
            (),
        )
    )

    winner_banks = tuple(
        getattr(
            comparison,
            "overall_winner_bank_names",
            (),
        )
    )

    lines.extend(
        [
            "",
            "Genel de\u011ferlendirme:",
        ]
    )

    if ranking_claimed:

        representatives = {
            item.bank_name:
                item
            for item in getattr(
                comparison,
                "bank_representatives",
                (),
            )
        }

        spend = getattr(
            comparison,
            "spend_amount",
            None,
        )

        if len(winner_banks) == 1:

            bank = winner_banks[0]

            representative = (
                representatives.get(
                    bank
                )
            )

            sentence = "- "

            if spend is not None:

                sentence += (
                    _fmt(
                        spend
                    )
                    + " TL harcama i\u00e7in "
                )

            sentence += (
                "hesaplanabilen parasal fayda "
                "bak\u0131m\u0131ndan "
                + bank
                + " \u00f6ne \u00e7\u0131k\u0131yor"
            )

            if representative is not None:

                sentence += (
                    " ("
                    + _fmt(
                        representative.effective_monetary_benefit
                    )
                    + " TL)"
                )

            sentence += "."

            lines.append(
                sentence
            )

        else:

            lines.append(
                "- E\u015fit sonu\u00e7: "
                + ", ".join(
                    winner_banks
                )
                + "."
            )

    elif (
        "overall_ranking_requires_multiple_banks"
        in reasons
    ):

        banks = tuple(
            dict.fromkeys(
                item.bank_name
                for item
                in candidates
            )
        )

        if len(banks) == 1:

            lines.append(
                "- Kar\u015f\u0131la\u015ft\u0131r\u0131labilir "
                "kampanyalar \u015fu anda yaln\u0131z "
                + banks[0]
                + " taraf\u0131nda bulundu. "
                "Bu nedenle bankalar aras\u0131 "
                "genel kazanan belirtmiyorum."
            )

        else:

            lines.append(
                "- Bankalar aras\u0131 genel kazanan "
                "belirtmek i\u00e7in en az iki "
                "kar\u015f\u0131la\u015ft\u0131r\u0131labilir "
                "banka gerekiyor."
            )

    elif (
        "overall_ranking_blocked_incomplete_monetary_benefit"
        in reasons
    ):

        lines.append(
            "- T\u00fcm bankalar i\u00e7in parasal fayda "
            "ayn\u0131 g\u00fcvenli kuralla hesaplanamad\u0131\u011f\u0131 "
            "i\u00e7in genel kazanan belirtmiyorum."
        )

    elif (
        "overall_ranking_blocked_requested_bank_missing"
        in reasons
        or any(
            value.startswith(
                "requested_bank_without_candidate:"
            )
            for value
            in reasons
        )
    ):

        lines.append(
            "- Se\u00e7ilen bankalar\u0131n tamam\u0131nda "
            "uygun kar\u015f\u0131la\u015ft\u0131r\u0131labilir "
            "kampanya bulunmad\u0131\u011f\u0131 i\u00e7in "
            "genel kazanan belirtmiyorum."
        )

    elif universe_key == "all_active":

        lines.append(
            "- Kampanyalar farkl\u0131 t\u00fcrlerde oldu\u011fu "
            "i\u00e7in tek bir genel 'en iyi' banka "
            "belirtmiyorum; aktif kampanyalar\u0131 "
            "banka baz\u0131nda yan yana g\u00f6steriyorum."
        )

    elif (
        "overall_ranking_blocked_for_campaign_universe"
        in reasons
    ):

        lines.append(
            "- Bu kampanya t\u00fcr\u00fcnde tek bir "
            "genel 'en iyi' sonucu vermiyorum; "
            "ortak say\u0131sal kriterleri ayr\u0131 "
            "ayr\u0131 kar\u015f\u0131la\u015ft\u0131r\u0131yorum."
        )

    else:

        lines.append(
            "- Mevcut veriler tek bir genel kazanan "
            "s\u00f6ylemek i\u00e7in yeterli de\u011fil."
        )

    return CampaignRenderedAnswer(
        text="\n".join(
            lines
        ),
        ranking_claimed=ranking_claimed,
        ranking_metric=getattr(
            comparison,
            "overall_metric",
            None,
        ),
        campaign_ids=tuple(
            item.campaign_id
            for item
            in candidates
        ),
        bank_names=tuple(
            dict.fromkeys(
                item.bank_name
                for item
                in candidates
            )
        ),
        reasons=(),
    )

# ============================================================
# CAMPAIGN_INSTALLMENT_RENDER_NOTE_V1_1
# ============================================================

_render_campaign_answer_before_installment_note_v1_1 = (
    render_campaign_answer
)


def render_campaign_answer(
    comparison,
) -> CampaignRenderedAnswer:

    rendered = (
        _render_campaign_answer_before_installment_note_v1_1(
            comparison
        )
    )

    if comparison is None:

        return rendered

    if (
        str(
            getattr(
                comparison,
                "universe_key",
                "",
            )
            or ""
        ).strip()
        == "all_active"
    ):

        return rendered

    comparison_reasons = tuple(
        str(value)
        for value
        in getattr(
            comparison,
            "reasons",
            (),
        )
    )

    blocked_ids = tuple(
        value.split(
            ":",
            1,
        )[1]
        for value
        in comparison_reasons
        if value.startswith(
            "installment_consistency_blocked:"
        )
    )

    if not blocked_ids:

        return rendered

    note = (
        "\n\n"
        "Veri do\u011frulama notu:\n"
        "- Baz\u0131 kampanyalar\u0131n yap\u0131land\u0131r\u0131lm\u0131\u015f "
        "taksit bilgisi ile resmi ba\u015fl\u0131k/URL "
        "birbiriyle \u00e7eli\u015fti\u011fi i\u00e7in bu kay\u0131tlar\u0131n "
        "taksit de\u011feri g\u00f6sterilmedi ve taksit "
        "s\u0131ralamas\u0131nda kullan\u0131lmad\u0131."
    )

    return CampaignRenderedAnswer(
        text=(
            rendered.text
            + note
        ),
        ranking_claimed=(
            rendered.ranking_claimed
        ),
        ranking_metric=(
            rendered.ranking_metric
        ),
        campaign_ids=(
            rendered.campaign_ids
        ),
        bank_names=(
            rendered.bank_names
        ),
        reasons=(
            rendered.reasons
            + (
                "installment_consistency_guard_applied",
            )
        ),
    )
