# CHATBOT_FINANCE_RENDERER_V1

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.chatbot_answer_contract import (
    GroundedAnswerContext,
)


@dataclass(frozen=True)
class FinanceRenderedAnswer:

    text: str

    ranking_claimed: bool

    ranking_metric: str | None

    numeric_product_ids: tuple[
        int,
        ...
    ]

    unresolved_product_ids: tuple[
        int,
        ...
    ]

    ineligible_product_ids: tuple[
        int,
        ...
    ]


def _status(
    item,
) -> str:

    return (
        str(
            item.status
            or ""
        )
        .strip()
        .casefold()
    )


def _money(
    value: Decimal,
) -> str:

    value = Decimal(
        str(value)
    )

    formatted = (
        f"{value:,.2f}"
        .replace(
            ",",
            "_",
        )
        .replace(
            ".",
            ",",
        )
        .replace(
            "_",
            ".",
        )
    )

    return (
        formatted
        + " TL"
    )


def _rate(
    value: Decimal,
) -> str:

    value = Decimal(
        str(value)
    )

    text = format(
        value.normalize(),
        "f",
    )

    return (
        "%"
        + text.replace(
            ".",
            ",",
        )
    )


def _candidate_label(
    item,
) -> str:

    return (
        item.bank_name
        + " - "
        + item.product_name
    )


def _verified_lines(
    verified,
) -> list[str]:

    lines = []

    for item in verified:

        lines.append(
            "- "
            + _candidate_label(
                item
            )
        )

        if (
            item.profit_share_rate
            is not None
        ):

            lines.append(
                "  K\u00e2r pay\u0131 oran\u0131: "
                + _rate(
                    item.profit_share_rate
                )
            )

        if (
            item.monthly_installment
            is not None
        ):

            lines.append(
                "  Ayl\u0131k taksit: "
                + _money(
                    item.monthly_installment
                )
            )

        if (
            item.total_repayment
            is not None
        ):

            lines.append(
                "  Geri \u00f6denecek toplam: "
                + _money(
                    item.total_repayment
                )
            )

        if (
            item.allocation_fee
            is not None
        ):

            lines.append(
                "  Tahsis \u00fccreti: "
                + _money(
                    item.allocation_fee
                )
            )

        minimum_appraisal_fee = (
            getattr(
                item,
                "minimum_appraisal_fee",
                None,
            )
        )

        minimum_mortgage_fee = (
            getattr(
                item,
                "minimum_mortgage_establishment_fee",
                None,
            )
        )

        minimum_verified_fees_total = (
            getattr(
                item,
                "minimum_verified_fees_total",
                None,
            )
        )


        if (
            item.appraisal_fee is None
            and minimum_appraisal_fee
            is not None
        ):

            lines.append(
                "  Ekspertiz \u00fccreti: Asgari "
                + _money(
                    minimum_appraisal_fee
                )
            )


        if (
            item.mortgage_fee is None
            and minimum_mortgage_fee
            is not None
        ):

            lines.append(
                "  \u0130potek tesis \u00fccreti: Asgari "
                + _money(
                    minimum_mortgage_fee
                )
            )


        if (
            item.total_fees is None
            and minimum_verified_fees_total
            is not None
        ):

            lines.append(
                "  Asgari do\u011frulanm\u0131\u015f "
                "\u00fccretler toplam\u0131: "
                + _money(
                    minimum_verified_fees_total
                )
            )


        if (
            item.mortgage_fee
            is not None
        ):

            lines.append(
                "  \u0130potek \u00fccreti: "
                + _money(
                    item.mortgage_fee
                )
            )

        if (
            item.appraisal_fee
            is not None
        ):

            lines.append(
                "  Ekspertiz \u00fccreti: "
                + _money(
                    item.appraisal_fee
                )
            )

        if (
            item.total_fees
            is not None
        ):

            lines.append(
                "  A\u00e7\u0131k\u00e7a do\u011frulanm\u0131\u015f "
                "toplam \u00fccret: "
                + _money(
                    item.total_fees
                )
            )

        if item.source_url:

            lines.append(
                "  Kaynak: "
                + str(
                    item.source_url
                )
            )

        if item.checked_at:

            lines.append(
                "  Kontrol tarihi: "
                + str(
                    item.checked_at
                )
            )

    return lines


def _render_finance_answer_legacy(
    context: GroundedAnswerContext,
) -> FinanceRenderedAnswer:
    """
    Deterministic finance response.

    No LLM is called here.

    Safety:
    - UNVERIFIED values are never rendered.
    - Non-exact values are never rendered.
    - Global ranking requires the permission
      issued by Grounded Answer Contract V2.
    - Ranking is metric-specific:
      total_repayment only.
    - Generic "best bank" claims are avoided.
    """

    if context.route not in {
        "finance_compare",
        "hybrid",
    }:

        raise ValueError(
            "Finance renderer received "
            "a non-finance route."
        )

    if context.missing_fields:

        fields = ", ".join(
            context.missing_fields
        )

        return FinanceRenderedAnswer(
            text=(
                "Finansman kar\u015f\u0131la\u015ft\u0131rmas\u0131 "
                "i\u00e7in gerekli bilgiler eksik: "
                + fields
                + "."
            ),
            ranking_claimed=False,
            ranking_metric=None,
            numeric_product_ids=tuple(),
            unresolved_product_ids=tuple(),
            ineligible_product_ids=tuple(),
        )

    finance = tuple(
        context.finance_results
    )

    verified = tuple(
        item
        for item in finance
        if (
            item.verified
            and
            item.exact_match
            and
            item.rankable
        )
    )

    unresolved = tuple(
        item
        for item in finance
        if (
            not item.rankable
            and
            _status(item)
            != "ineligible"
        )
    )

    ineligible = tuple(
        item
        for item in finance
        if (
            _status(item)
            == "ineligible"
        )
    )

    numeric_product_ids = tuple(
        int(
            item.product_id
        )
        for item in verified
    )

    unresolved_product_ids = tuple(
        int(
            item.product_id
        )
        for item in unresolved
    )

    ineligible_product_ids = tuple(
        int(
            item.product_id
        )
        for item in ineligible
    )


    # ========================================================
    # NO VERIFIED EXACT RESULT
    # ========================================================

    if not verified:

        lines = [
            (
                "Bu senaryo i\u00e7in "
                "do\u011frulanm\u0131\u015f ve birebir e\u015fle\u015fen "
                "hesaplama sonucu bulunmad\u0131\u011f\u0131ndan "
                "bankalar\u0131 g\u00fcvenilir bi\u00e7imde "
                "s\u0131ralayam\u0131yorum."
            )
        ]

        if unresolved:

            lines.append("")
            lines.append(
                "Do\u011frulama bekleyen adaylar:"
            )

            for item in unresolved:

                lines.append(
                    "- "
                    + _candidate_label(
                        item
                    )
                    + " ("
                    + str(
                        item.status
                    )
                    + ")"
                )

        if ineligible:

            lines.append("")
            lines.append(
                "Talep edilen senaryoya uygun olmayan "
                "\u00fcr\u00fcnler:"
            )

            for item in ineligible:

                lines.append(
                    "- "
                    + _candidate_label(
                        item
                    )
                )

        return FinanceRenderedAnswer(
            text="\n".join(
                lines
            ),
            ranking_claimed=False,
            ranking_metric=None,
            numeric_product_ids=tuple(),
            unresolved_product_ids=(
                unresolved_product_ids
            ),
            ineligible_product_ids=(
                ineligible_product_ids
            ),
        )


    # ========================================================
    # VERIFIED RESULTS EXIST
    # ========================================================

    lines = [
        (
            "Ayn\u0131 tutar ve vade i\u00e7in "
            "birebir do\u011frulanm\u0131\u015f sonu\u00e7lar:"
        ),
        "",
    ]

    lines.extend(
        _verified_lines(
            verified
        )
    )


    # ========================================================
    # GLOBAL RANKING
    # ========================================================

    ranking_claimed = False
    ranking_metric = None

    all_have_total = (
        bool(verified)
        and
        all(
            item.total_repayment
            is not None
            for item in verified
        )
    )

    if (
        context.may_claim_finance_ranking
        and
        len(verified) >= 2
        and
        all_have_total
    ):

        ordered = sorted(
            verified,
            key=lambda item:
                Decimal(
                    str(
                        item.total_repayment
                    )
                ),
        )

        winner = ordered[0]

        lines.append("")
        lines.append(
            (
                "Do\u011frulanm\u0131\u015f geri \u00f6deme "
                "toplam\u0131 metri\u011fine g\u00f6re en d\u00fc\u015f\u00fck "
                "sonu\u00e7 "
                + _candidate_label(
                    winner
                )
                + " i\u00e7in "
                + _money(
                    winner.total_repayment
                )
                + "."
            )
        )

        lines.append(
            (
                "Bu s\u0131ralama yaln\u0131zca ayn\u0131 tutar "
                "ve vadedeki do\u011frulanm\u0131\u015f "
                "geri \u00f6deme toplamlar\u0131na dayan\u0131r."
            )
        )

        ranking_claimed = True
        ranking_metric = (
            "total_repayment"
        )

    else:

        lines.append("")

        if unresolved:

            lines.append(
                (
                    "Di\u011fer adaylar\u0131n bir k\u0131sm\u0131 "
                    "hen\u00fcz do\u011frulanmad\u0131\u011f\u0131 i\u00e7in "
                    "bankalar aras\u0131nda genel bir "
                    "\"en uygun\" sonucu vermiyorum."
                )
            )

        elif len(verified) < 2:

            lines.append(
                (
                    "Yaln\u0131zca bir do\u011frulanm\u0131\u015f sonu\u00e7 "
                    "bulundu\u011fu i\u00e7in bankalar aras\u0131nda "
                    "s\u0131ralama yapm\u0131yorum."
                )
            )

        elif not all_have_total:

            lines.append(
                (
                    "Do\u011frulanm\u0131\u015f sonu\u00e7larda ortak "
                    "geri \u00f6deme toplam\u0131 metri\u011fi eksik "
                    "oldu\u011fu i\u00e7in s\u0131ralama yapm\u0131yorum."
                )
            )

        else:

            lines.append(
                (
                    "Kar\u015f\u0131la\u015ft\u0131rma kontrat\u0131 "
                    "s\u0131ralama izni vermedi\u011fi i\u00e7in "
                    "genel bir banka s\u0131ralamas\u0131 yapm\u0131yorum."
                )
            )


    if unresolved:

        lines.append("")
        lines.append(
            "Hen\u00fcz do\u011frulanmam\u0131\u015f adaylar:"
        )

        for item in unresolved:

            lines.append(
                "- "
                + _candidate_label(
                    item
                )
            )


    if ineligible:

        lines.append("")
        lines.append(
            (
                "Talep edilen tutar/vade i\u00e7in "
                "kural motorunun uygun bulmad\u0131\u011f\u0131 "
                "\u00fcr\u00fcnler:"
            )
        )

        for item in ineligible:

            lines.append(
                "- "
                + _candidate_label(
                    item
                )
            )


    return FinanceRenderedAnswer(
        text="\n".join(
            lines
        ),
        ranking_claimed=(
            ranking_claimed
        ),
        ranking_metric=(
            ranking_metric
        ),
        numeric_product_ids=(
            numeric_product_ids
        ),
        unresolved_product_ids=(
            unresolved_product_ids
        ),
        ineligible_product_ids=(
            ineligible_product_ids
        ),
    )


# ============================================================
# UNIVERSAL FINANCE EXPLAINABLE COMPARISON V2
# ============================================================

def _comparison_format_tl(
    value,
) -> str:

    from decimal import Decimal


    value = Decimal(
        str(
            value
        )
    )


    text = (
        f"{value:,.2f}"
        .replace(
            ",",
            "_",
        )
        .replace(
            ".",
            ",",
        )
        .replace(
            "_",
            ".",
        )
    )


    return (
        text
        + " TL"
    )


def _comparison_format_percent(
    value,
) -> str:

    from decimal import Decimal


    value = Decimal(
        str(
            value
        )
    )


    text = (
        format(
            value,
            "f",
        )
        .rstrip(
            "0"
        )
        .rstrip(
            "."
        )
    )


    return (
        "%"
        + text.replace(
            ".",
            ",",
        )
    )


def _comparison_winner_text(
    labels,
) -> str:

    values = tuple(
        str(
            value
        ).strip()
        for value
        in labels
        if str(
            value
        ).strip()
    )


    return ", ".join(
        values
    )


def _comparison_value_text(
    criterion,
) -> str:

    if (
        criterion.field
        == "profit_share_rate"
    ):

        return (
            _comparison_format_percent(
                criterion.best_value
            )
        )


    return (
        _comparison_format_tl(
            criterion.best_value
        )
    )


def _strip_legacy_ranking_tail(
    text: str,
) -> str:
    """
    Remove only the old final ranking paragraph.

    The verified candidate details remain intact.
    """

    text = str(
        text
        or ""
    ).rstrip()


    marker = (
        "Do\u011frulanm\u0131\u015f geri \u00f6deme "
        "toplam\u0131 metri\u011fine g\u00f6re"
    )


    index = text.find(
        marker
    )


    if index < 0:

        return text


    return (
        text[:index]
        .rstrip()
    )


def _build_finance_comparison_analysis(
    context,
):
    """
    Build explanatory text only after the legacy
    renderer has already authorized ranking.
    """

    from src.finance_comparison_evaluator import (
        evaluate_finance_results,
    )


    evaluation = (
        evaluate_finance_results(
            getattr(
                context,
                "finance_results",
                (),
            ),
            allow_ranking=True,
        )
    )


    if not evaluation.ranking_allowed:

        return (
            "",
            evaluation,
        )


    lines = [
        "Kriter bazl\u0131 de\u011ferlendirme:",
    ]


    safe_results = tuple(
        item
        for item
        in (
            getattr(
                context,
                "finance_results",
                (),
            )
            or ()
        )
        if (
            getattr(
                item,
                "verified",
                False,
            )
            and
            getattr(
                item,
                "exact_match",
                False,
            )
            and
            getattr(
                item,
                "rankable",
                False,
            )
        )
    )


    maturity_values = {
        int(
            item.requested_maturity_months
        )
        for item
        in safe_results
        if getattr(
            item,
            "requested_maturity_months",
            None,
        )
        is not None
    }


    if len(
        maturity_values
    ) == 1:

        maturity = next(
            iter(
                maturity_values
            )
        )


        lines.append(
            (
                "- Talep edilen vade: "
                f"{maturity} ay. "
                "Do\u011frulanm\u0131\u015f birebir "
                "adaylar bu vadeyi kar\u015f\u0131l\u0131yor."
            )
        )


    for criterion in evaluation.criteria:

        winner_text = (
            _comparison_winner_text(
                criterion.winner_labels
            )
        )

        value_text = (
            _comparison_value_text(
                criterion
            )
        )


        if len(
            criterion.winner_labels
        ) == 1:

            lines.append(
                (
                    f"- {criterion.label}: "
                    f"{winner_text} daha avantajl\u0131 "
                    f"({value_text})."
                )
            )

        else:

            lines.append(
                (
                    f"- {criterion.label}: "
                    f"{winner_text} ayn\u0131 en d\u00fc\u015f\u00fck "
                    f"de\u011fere sahip ({value_text})."
                )
            )


    winner_text = (
        _comparison_winner_text(
            evaluation.winner_labels
        )
    )


    lines.extend(
        (
            "",
            "Genel de\u011ferlendirme:",
        )
    )


    if len(
        evaluation.winner_labels
    ) == 1:

        lines.append(
            (
                "- Do\u011frulanm\u0131\u015f ve birebir "
                "e\u015fle\u015fen adaylar aras\u0131nda "
                f"{winner_text} daha mant\u0131kl\u0131 "
                "g\u00f6r\u00fcn\u00fcyor."
            )
        )

        lines.append(
            (
                "- Gerek\u00e7e: "
                f"{evaluation.overall_metric_label} "
                "bu adayda en d\u00fc\u015f\u00fck "
                f"({_comparison_format_tl(evaluation.overall_best_value)})."
            )
        )


    else:

        lines.append(
            (
                "- "
                f"{winner_text} "
                f"{evaluation.overall_metric_label} "
                "a\u00e7\u0131s\u0131ndan e\u015fit en d\u00fc\u015f\u00fck "
                "sonuca sahip."
            )
        )


    if (
        evaluation.overall_metric
        == "overall_total_cost"
    ):

        lines.append(
            (
                "- Genel maliyet hesab\u0131nda "
                "toplam geri \u00f6deme ile "
                "do\u011frulanm\u0131\u015f toplam \u00fccret "
                "birlikte dikkate al\u0131nd\u0131."
            )
        )


    elif (
        evaluation.overall_metric
        == "total_repayment"
    ):

        lines.append(
            (
                "- Baz\u0131 adaylarda toplam \u00fccret "
                "bilgisi eksiksiz olmad\u0131\u011f\u0131 i\u00e7in "
                "genel sonu\u00e7ta toplam geri \u00f6deme "
                "esas al\u0131nd\u0131."
            )
        )


    return (
        "\n".join(
            lines
        ),
        evaluation,
    )


def _render_finance_answer_scoped_base(
    context,
):

    from dataclasses import replace


    legacy = (
        _render_finance_answer_legacy(
            context
        )
    )


    # The old renderer remains the primary
    # grounding authority.
    if not bool(
        getattr(
            context,
            "may_claim_finance_ranking",
            False,
        )
    ):

        return legacy


    # Even if context permission is true,
    # require the existing renderer itself
    # to have accepted ranking.
    if not bool(
        getattr(
            legacy,
            "ranking_claimed",
            False,
        )
    ):

        return legacy


    analysis, evaluation = (
        _build_finance_comparison_analysis(
            context
        )
    )


    if (
        not analysis
        or
        not evaluation.ranking_allowed
    ):

        return legacy


    base_text = (
        _strip_legacy_ranking_tail(
            legacy.text
        )
    )


    combined = (
        base_text
        + "\n\n"
        + analysis
    ).strip()


    return replace(
        legacy,

        text=combined,

        ranking_claimed=True,

        ranking_metric=(
            evaluation.overall_metric
        ),
    )


# ============================================================
# SCOPED_PARTIAL_UNRESOLVED_DISCLOSURE_V1
# ============================================================

def _scoped_unresolved_finance_items(
    context,
):

    # ========================================================
    # FINANCE_SCOPED_UNRESOLVED_VERIFIED_FLAG_V2
    #
    # Grounded finance items expose verification in two ways:
    #
    #   item.status
    #   item.verified
    #
    # HV4 condition rendering intentionally trusts the grounded
    # boolean `verified` flag together with exact_match.
    #
    # The unresolved renderer must therefore honor that same
    # verification boundary. Otherwise a condition-specific,
    # verified product can also appear as "unverified".
    # ========================================================

    finance_results = tuple(
        getattr(
            context,
            "finance_results",
            (),
        )
        or ()
    )


    def _is_verified(
        item,
        status,
    ):

        return (
            bool(
                getattr(
                    item,
                    "verified",
                    False,
                )
            )
            or
            status == "verified"
            or
            status.endswith(
                ".verified"
            )
        )


    def _is_ineligible(
        status,
    ):

        return (
            status == "ineligible"
            or
            status.endswith(
                ".ineligible"
            )
        )


    verified_product_ids = set()


    for item in finance_results:

        status = (
            str(
                getattr(
                    item,
                    "status",
                    "",
                )
                or ""
            )
            .strip()
            .casefold()
        )


        if not _is_verified(
            item,
            status,
        ):
            continue


        try:

            product_id = int(
                getattr(
                    item,
                    "product_id",
                )
            )

        except Exception:

            continue


        if product_id > 0:

            verified_product_ids.add(
                product_id
            )


    items = []


    for item in finance_results:

        if bool(
            getattr(
                item,
                "rankable",
                False,
            )
        ):

            continue


        status = (
            str(
                getattr(
                    item,
                    "status",
                    "",
                )
                or ""
            )
            .strip()
            .casefold()
        )


        if (
            _is_verified(
                item,
                status,
            )
            or
            _is_ineligible(
                status
            )
        ):

            continue


        try:

            product_id = int(
                getattr(
                    item,
                    "product_id",
                )
            )

        except Exception:

            product_id = None


        if (
            product_id is not None
            and
            product_id > 0
            and
            product_id
            in verified_product_ids
        ):

            continue


        items.append(
            item
        )


    return tuple(
        items
    )




def _scoped_finance_label(
    item,
):

    bank = str(
        getattr(
            item,
            "bank_name",
            "",
        )
        or ""
    ).strip()


    product = str(
        getattr(
            item,
            "product_name",
            "",
        )
        or ""
    ).strip()


    if bank and product:

        return (
            bank
            + " - "
            + product
        )


    return (
        bank
        or
        product
        or
        "Do\u011frulanmam\u0131\u015f finansman aday\u0131"
    )


def _scoped_product_ids(
    items,
):

    ids = []


    for item in items:

        try:

            product_id = int(
                getattr(
                    item,
                    "product_id",
                )
            )

        except Exception:

            continue


        if (
            product_id > 0
            and
            product_id not in ids
        ):

            ids.append(
                product_id
            )


    return tuple(
        ids
    )


def render_finance_answer(
    context,
):
    """
    Preserve the universal criterion evaluator.

    In scoped partial-ranking mode, explicitly disclose
    unresolved candidates after the verified-subset
    recommendation.
    """

    rendered = (
        _render_finance_answer_scoped_base(
            context
        )
    )


    reasons = {
        str(
            value
        )

        for value
        in tuple(
            getattr(
                context,
                "reasons",
                (),
            )
            or ()
        )
    }


    scoped = (
        "partial_verified_finance_ranking_allowed"
        in reasons
        and
        "ranking_scope_verified_candidates_only"
        in reasons
    )


    if not scoped:

        return rendered


    unresolved = (
        _scoped_unresolved_finance_items(
            context
        )
    )


    if not unresolved:

        return rendered


    unresolved_ids = (
        _scoped_product_ids(
            unresolved
        )
    )


    text = str(
        rendered.text
        or ""
    ).rstrip()


    heading = (
        "Hen\u00fcz do\u011frulanmam\u0131\u015f adaylar:"
    )


    if heading not in text:

        lines = [
            text,
            "",
            "Kapsam notu:",
            (
                "- Bu \u00f6neri yaln\u0131zca "
                "do\u011frulanm\u0131\u015f ve birebir "
                "e\u015fle\u015fen adaylar aras\u0131ndad\u0131r."
            ),
            (
                "- A\u015fa\u011f\u0131daki adaylar hen\u00fcz "
                "do\u011frulanmad\u0131\u011f\u0131 i\u00e7in bu sonu\u00e7 "
                "t\u00fcm bankalar i\u00e7in kesin birincilik "
                "anlam\u0131na gelmez."
            ),
            "",
            heading,
        ]


        for item in unresolved:

            lines.append(
                "- "
                + _scoped_finance_label(
                    item
                )
            )


        text = "\n".join(
            lines
        )


    return FinanceRenderedAnswer(
        text=text,

        ranking_claimed=(
            rendered.ranking_claimed
        ),

        ranking_metric=(
            rendered.ranking_metric
        ),

        numeric_product_ids=(
            rendered.numeric_product_ids
        ),

        unresolved_product_ids=(
            unresolved_ids
        ),

        ineligible_product_ids=(
            rendered.ineligible_product_ids
        ),
    )

# ============================================================
# FINANCE_RENDERER_VISUAL_FORMAT_V1
# UI-ONLY. NO FINANCIAL DECISION LOGIC.
# ============================================================

from dataclasses import replace as _finance_visual_replace_v1
from datetime import datetime as _finance_visual_datetime_v1


_render_finance_answer_before_visual_format_v1 = (
    render_finance_answer
)


_FINANCE_VISUAL_MONTHS_V1 = {
    1: "Ocak",
    2: "\u015eubat",
    3: "Mart",
    4: "Nisan",
    5: "May\u0131s",
    6: "Haziran",
    7: "Temmuz",
    8: "A\u011fustos",
    9: "Eyl\u00fcl",
    10: "Ekim",
    11: "Kas\u0131m",
    12: "Aral\u0131k",
}


_FINANCE_VERIFIED_HEADER_V1 = (
    "Ayn\u0131 tutar ve vade i\u00e7in "
    "birebir do\u011frulanm\u0131\u015f sonu\u00e7lar:"
)


_FINANCE_SECTION_BOUNDARIES_V1 = (
    "Di\u011fer adaylar\u0131n",
    "Hen\u00fcz do\u011frulanmam\u0131\u015f adaylar:",
    "Do\u011frulama bekleyen adaylar:",
    "Kriter bazl\u0131 de\u011ferlendirme:",
    "Genel de\u011ferlendirme:",
    "Kapsam notu:",
)


def _finance_visual_date_v1(
    value: str,
) -> str:

    raw = str(
        value
        or ""
    ).strip()

    if not raw:

        return raw

    try:

        parsed = (
            _finance_visual_datetime_v1.fromisoformat(
                raw.replace(
                    "Z",
                    "+00:00",
                )
            )
        )

    except Exception:

        return raw

    month = (
        _FINANCE_VISUAL_MONTHS_V1.get(
            parsed.month,
            str(
                parsed.month
            ),
        )
    )

    return (
        f"{parsed.day} "
        f"{month} "
        f"{parsed.year}"
    )


def _finance_visual_table_v1(
    details,
):

    if not details:

        return []

    lines = [
        "| Kriter | De\u011fer |",
        "|---|---:|",
    ]

    for label, value in details:

        lines.append(
            "| "
            + label
            + " | "
            + value
            + " |"
        )

    return lines


def _finance_visual_section_heading_v1(
    line: str,
) -> str:

    stripped = str(
        line
        or ""
    ).strip()

    heading_map = {
        "Kriter bazl\u0131 de\u011ferlendirme:":
            "### Kriter bazl\u0131 de\u011ferlendirme",

        "Genel de\u011ferlendirme:":
            "### Genel de\u011ferlendirme",

        "Kapsam notu:":
            "### Kapsam notu",

        "Hen\u00fcz do\u011frulanmam\u0131\u015f adaylar:":
            "### Hen\u00fcz do\u011frulanmam\u0131\u015f adaylar",

        "Do\u011frulama bekleyen adaylar:":
            "### Do\u011frulama bekleyen adaylar",
    }

    return heading_map.get(
        stripped,
        line,
    )


def _beautify_finance_text_v1(
    text: str,
) -> str:

    original = str(
        text
        or ""
    )

    if (
        _FINANCE_VERIFIED_HEADER_V1
        not in original
    ):

        return original

    lines = original.splitlines()

    output = []

    i = 0
    in_verified_results = False

    while i < len(
        lines
    ):

        raw = lines[i]

        stripped = raw.strip()

        if (
            stripped
            == _FINANCE_VERIFIED_HEADER_V1
        ):

            output.append(
                "### "
                + _FINANCE_VERIFIED_HEADER_V1[
                    :-1
                ]
            )

            output.append(
                ""
            )

            in_verified_results = True

            i += 1

            continue


        if (
            in_verified_results
            and any(
                stripped.startswith(
                    boundary
                )
                for boundary
                in _FINANCE_SECTION_BOUNDARIES_V1
            )
        ):

            in_verified_results = False


        if (
            in_verified_results
            and raw.startswith(
                "- "
            )
        ):

            title = raw[
                2:
            ].strip()

            details = []

            source_line = None
            date_line = None

            i += 1

            while i < len(
                lines
            ):

                detail_raw = lines[i]

                if not detail_raw.startswith(
                    "  "
                ):

                    break

                detail = (
                    detail_raw.strip()
                )

                if detail.startswith(
                    "Kaynak:"
                ):

                    source_line = detail

                elif detail.startswith(
                    "Kontrol tarihi:"
                ):

                    raw_date = (
                        detail.split(
                            ":",
                            1,
                        )[1].strip()
                    )

                    date_line = (
                        "Kontrol tarihi: "
                        + _finance_visual_date_v1(
                            raw_date
                        )
                    )

                elif ":" in detail:

                    label, value = (
                        detail.split(
                            ":",
                            1,
                        )
                    )

                    details.append(
                        (
                            label.strip(),
                            value.strip(),
                        )
                    )

                else:

                    details.append(
                        (
                            "Bilgi",
                            detail,
                        )
                    )

                i += 1


            output.append(
                "#### "
                + title
            )

            output.append(
                ""
            )

            output.extend(
                _finance_visual_table_v1(
                    details
                )
            )

            if details:

                output.append(
                    ""
                )

            if source_line:

                output.append(
                    source_line
                )

            if date_line:

                output.append(
                    date_line
                )

            output.append(
                ""
            )

            continue


        formatted = (
            _finance_visual_section_heading_v1(
                raw
            )
        )

        # Avoid excessive vertical gaps after the
        # newly generated finance cards.
        if (
            not stripped
            and
            output
            and
            output[-1] == ""
        ):

            i += 1
            continue

        output.append(
            formatted
        )

        i += 1


    return "\n".join(
        output
    ).strip()


def render_finance_answer(
    context,
):

    rendered = (
        _render_finance_answer_before_visual_format_v1(
            context
        )
    )

    pretty_text = (
        _beautify_finance_text_v1(
            rendered.text
        )
    )

    if (
        pretty_text
        == rendered.text
    ):

        return rendered

    return _finance_visual_replace_v1(
        rendered,
        text=pretty_text,
    )


# ============================================================
# HOUSING_CONDITION_DISPLAY_V1_2
#
# Condition-aware housing finance presentation.
#
# Important:
# - Raw input_variant values stay unchanged.
# - Database/schema stay unchanged.
# - Finance calculations stay unchanged.
# - Condition-specific results are not promoted into the
#   generic cross-bank ranking.
# ============================================================

from dataclasses import replace as _hc_replace_v12
from decimal import Decimal as _HCDecimalV12
from decimal import InvalidOperation as _HCInvalidOperationV12
from datetime import datetime as _HCDatetimeV12


_render_finance_answer_before_hc_v12 = (
    render_finance_answer
)


_HC_LABELS_V12 = {
    "yeni_konut":
        "Yeni / s\u0131f\u0131r konut",

    "sifir_konut":
        "Yeni / s\u0131f\u0131r konut",

    "2el_konut":
        "\u0130kinci el konut",

    "ilk_ev":
        "\u0130lk konut",

    "ilk_konut":
        "\u0130lk konut",

    "mevcut_konut":
        "\u0130kinci ve sonraki konut",

    "ilk_konut_sigortali":
        "\u0130lk konut + sigortal\u0131",

    "ilk_konut_sigortasiz":
        "\u0130lk konut + sigortas\u0131z",

    "mevcut_konut_sigortali":
        (
            "Halihaz\u0131rda konutu bulunan "
            "+ sigortal\u0131"
        ),

    "mevcut_konut_sigortasiz":
        (
            "Halihaz\u0131rda konutu bulunan "
            "+ sigortas\u0131z"
        ),
}


# Product 242 is calculated through a new-housing mapping.
# It must be presented as a condition-specific result instead
# of a generic housing result.
_HC_LIVE_SPECIAL_V12 = {
    242: "yeni_konut",
}


# Historical Albaraka housing snapshots are audit-only after
# the provenance guard and must not reappear through this
# presentation layer.
_HC_BLOCKED_IDS_V12 = {
    97,
}


def _hc_text_v12(
    value,
):

    if value is None:
        return ""

    return str(
        value
    ).strip()


def _hc_decimal_v12(
    value,
):

    if value is None:
        return None

    text = str(
        value
    ).strip()

    if (
        not text
        or
        text.casefold()
        in {
            "none",
            "nan",
            "<na>",
        }
    ):

        return None

    try:

        number = _HCDecimalV12(
            text
        )

    except (
        _HCInvalidOperationV12,
        ValueError,
        TypeError,
    ):

        return None

    if not number.is_finite():
        return None

    return number


def _hc_int_v12(
    value,
):

    number = _hc_decimal_v12(
        value
    )

    if number is None:
        return None

    return int(
        number
    )


def _hc_money_v12(
    value,
):

    number = _hc_decimal_v12(
        value
    )

    if number is None:
        return "\u2014"

    raw = format(
        number,
        ",.2f",
    )

    return (
        raw
        .replace(",", "\u00a7")
        .replace(".", ",")
        .replace("\u00a7", ".")
        + " TL"
    )


def _hc_rate_v12(
    value,
):

    number = _hc_decimal_v12(
        value
    )

    if number is None:
        return "\u2014"

    return (
        "%"
        + format(
            number,
            ".2f",
        ).replace(
            ".",
            ",",
        )
    )


def _hc_date_v12(
    value,
):

    text = _hc_text_v12(
        value
    )

    if not text:
        return ""

    try:

        parsed = (
            _HCDatetimeV12.fromisoformat(
                text.replace(
                    "Z",
                    "+00:00",
                )
            )
        )

    except Exception:

        return text

    months = {
        1: "Ocak",
        2: "\u015eubat",
        3: "Mart",
        4: "Nisan",
        5: "May\u0131s",
        6: "Haziran",
        7: "Temmuz",
        8: "A\u011fustos",
        9: "Eyl\u00fcl",
        10: "Ekim",
        11: "Kas\u0131m",
        12: "Aral\u0131k",
    }

    return (
        f"{parsed.day} "
        f"{months[parsed.month]} "
        f"{parsed.year}"
    )


def _hc_variant_v12(
    value,
):

    return (
        _hc_text_v12(
            value
        )
        .casefold()
    )


def _hc_label_v12(
    value,
):

    key = _hc_variant_v12(
        value
    )

    if (
        not key
        or
        key
        in {
            "standard",
            "none",
            "nan",
            "<na>",
        }
    ):

        return None

    return (
        _HC_LABELS_V12.get(
            key
        )
    )


def _hc_is_housing_v12(
    context,
):

    results = tuple(
        getattr(
            context,
            "finance_results",
            (),
        )
        or ()
    )

    for item in results:

        product_name = (
            _hc_text_v12(
                getattr(
                    item,
                    "product_name",
                    "",
                )
            )
            .casefold()
        )

        if "konut" in product_name:
            return True

    return False


def _hc_item_map_v12(
    context,
):

    result = {}

    for item in tuple(
        getattr(
            context,
            "finance_results",
            (),
        )
        or ()
    ):

        try:

            product_id = int(
                getattr(
                    item,
                    "product_id",
                )
            )

        except Exception:

            continue

        result[
            product_id
        ] = item

    return result


def _hc_dimensions_v12(
    context,
):

    for item in tuple(
        getattr(
            context,
            "finance_results",
            (),
        )
        or ()
    ):

        amount = (
            _hc_decimal_v12(
                getattr(
                    item,
                    "requested_amount",
                    None,
                )
            )
        )

        maturity = (
            _hc_int_v12(
                getattr(
                    item,
                    "requested_maturity_months",
                    None,
                )
            )
        )

        if (
            amount is not None
            and
            maturity is not None
        ):

            return (
                amount,
                maturity,
            )

    return (
        None,
        None,
    )


def _hc_snapshot_rows_v12(
    context,
):

    try:

        from src.finance_runtime_repository import (
            get_verified_finance_scenarios,
        )

    except Exception:

        return []

    item_map = (
        _hc_item_map_v12(
            context
        )
    )

    amount, maturity = (
        _hc_dimensions_v12(
            context
        )
    )

    if (
        not item_map
        or
        amount is None
        or
        maturity is None
    ):

        return []

    try:

        rows = (
            get_verified_finance_scenarios(
                product_ids=sorted(
                    item_map
                )
            )
        )

    except Exception:

        return []

    if (
        rows is None
        or
        rows.empty
    ):

        return []

    result = []

    for _index, row in rows.iterrows():

        try:

            product_id = int(
                row.get(
                    "product_id"
                )
            )

        except Exception:

            continue

        if (
            product_id
            in
            _HC_BLOCKED_IDS_V12
        ):

            continue

        item = item_map.get(
            product_id
        )

        if item is None:
            continue

        product_name = (
            _hc_text_v12(
                getattr(
                    item,
                    "product_name",
                    "",
                )
            )
        )

        if (
            "konut"
            not in
            product_name.casefold()
        ):

            continue

        row_amount = (
            _hc_decimal_v12(
                row.get(
                    "input_amount"
                )
            )
        )

        row_maturity = (
            _hc_int_v12(
                row.get(
                    "input_maturity_months"
                )
            )
        )

        if (
            row_amount != amount
            or
            row_maturity != maturity
        ):

            continue

        status = (
            _hc_text_v12(
                row.get(
                    "scenario_status"
                )
            )
            .casefold()
        )

        if not status.startswith(
            "verified"
        ):

            continue

        condition = (
            _hc_label_v12(
                row.get(
                    "input_variant"
                )
            )
        )

        if condition is None:
            continue

        result.append(
            {
                "product_id":
                    product_id,

                "bank_name":
                    _hc_text_v12(
                        getattr(
                            item,
                            "bank_name",
                            "",
                        )
                    ),

                "product_name":
                    product_name,

                "condition":
                    condition,

                "profit_share_rate":
                    row.get(
                        "profit_share_rate"
                    ),

                "monthly_installment":
                    row.get(
                        "monthly_installment"
                    ),

                "total_repayment":
                    row.get(
                        "total_repayment"
                    ),

                "source_url":
                    _hc_text_v12(
                        row.get(
                            "source_url"
                        )
                    ),

                "checked_at":
                    _hc_text_v12(
                        row.get(
                            "checked_at"
                        )
                    ),

                "origin":
                    "portable_snapshot",
            }
        )

    return result


def _hc_live_rows_v12(
    context,
):

    result = []

    for item in tuple(
        getattr(
            context,
            "finance_results",
            (),
        )
        or ()
    ):

        try:

            product_id = int(
                getattr(
                    item,
                    "product_id",
                )
            )

        except Exception:

            continue

        variant = (
            _HC_LIVE_SPECIAL_V12.get(
                product_id
            )
        )

        if variant is None:
            continue

        if not (
            bool(
                getattr(
                    item,
                    "verified",
                    False,
                )
            )
            and
            bool(
                getattr(
                    item,
                    "exact_match",
                    False,
                )
            )
        ):

            continue

        condition = (
            _hc_label_v12(
                variant
            )
        )

        if condition is None:
            continue

        result.append(
            {
                "product_id":
                    product_id,

                "bank_name":
                    _hc_text_v12(
                        getattr(
                            item,
                            "bank_name",
                            "",
                        )
                    ),

                "product_name":
                    _hc_text_v12(
                        getattr(
                            item,
                            "product_name",
                            "",
                        )
                    ),

                "condition":
                    condition,

                "profit_share_rate":
                    getattr(
                        item,
                        "profit_share_rate",
                        None,
                    ),

                "monthly_installment":
                    getattr(
                        item,
                        "monthly_installment",
                        None,
                    ),

                "total_repayment":
                    getattr(
                        item,
                        "total_repayment",
                        None,
                    ),

                "source_url":
                    _hc_text_v12(
                        getattr(
                            item,
                            "source_url",
                            "",
                        )
                    ),

                "checked_at":
                    _hc_text_v12(
                        getattr(
                            item,
                            "checked_at",
                            "",
                        )
                    ),

                "origin":
                    "live_condition_result",
            }
        )

    return result


def _hc_dedupe_v12(
    rows,
):

    ordered = sorted(
        rows,
        key=lambda row:
            (
                0
                if row.get(
                    "origin"
                )
                == "live_condition_result"
                else 1
            ),
    )

    seen = set()
    result = []

    for row in ordered:

        key = (
            int(
                row[
                    "product_id"
                ]
            ),

            row[
                "condition"
            ],

            _hc_decimal_v12(
                row.get(
                    "profit_share_rate"
                )
            ),

            _hc_decimal_v12(
                row.get(
                    "monthly_installment"
                )
            ),

            _hc_decimal_v12(
                row.get(
                    "total_repayment"
                )
            ),
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        result.append(
            row
        )

    return result


def _hc_safe_context_v12(
    context,
):

    safe_results = []
    changed = False

    for item in tuple(
        getattr(
            context,
            "finance_results",
            (),
        )
        or ()
    ):

        try:

            product_id = int(
                getattr(
                    item,
                    "product_id",
                )
            )

        except Exception:

            safe_results.append(
                item
            )
            continue

        if (
            product_id
            not in
            _HC_LIVE_SPECIAL_V12
        ):

            safe_results.append(
                item
            )
            continue

        if not (
            bool(
                getattr(
                    item,
                    "verified",
                    False,
                )
            )
            and
            bool(
                getattr(
                    item,
                    "exact_match",
                    False,
                )
            )
        ):

            safe_results.append(
                item
            )
            continue

        changed = True

        safe_results.append(
            _hc_replace_v12(
                item,

                status="UNVERIFIED",

                verified=False,
                exact_match=False,
                rankable=False,

                profit_share_rate=None,
                monthly_installment=None,
                total_repayment=None,

                allocation_fee=None,
                mortgage_fee=None,
                appraisal_fee=None,
                total_fees=None,

                source_kind=None,
                source_url=None,
                checked_at=None,

                reason=(
                    "condition_specific_housing_result: "
                    "This exact value belongs to a specific "
                    "housing condition and is displayed "
                    "separately."
                ),
            )
        )

    if not changed:
        return context

    rankable_count = sum(
        1
        for item in safe_results
        if bool(
            getattr(
                item,
                "rankable",
                False,
            )
        )
    )

    return _hc_replace_v12(
        context,

        finance_results=tuple(
            safe_results
        ),

        may_claim_finance_ranking=(
            bool(
                getattr(
                    context,
                    "may_claim_finance_ranking",
                    False,
                )
            )
            and
            rankable_count >= 2
        ),
    )


def _hc_sort_v12(
    row,
):

    condition_order = {
        "Yeni / s\u0131f\u0131r konut":
            10,

        "\u0130kinci el konut":
            20,

        "\u0130lk konut":
            30,

        "\u0130lk konut + sigortal\u0131":
            31,

        "\u0130lk konut + sigortas\u0131z":
            32,

        "\u0130kinci ve sonraki konut":
            40,

        (
            "Halihaz\u0131rda konutu bulunan "
            "+ sigortal\u0131"
        ):
            41,

        (
            "Halihaz\u0131rda konutu bulunan "
            "+ sigortas\u0131z"
        ):
            42,
    }

    return (
        _hc_text_v12(
            row[
                "bank_name"
            ]
        ).casefold(),

        _hc_text_v12(
            row[
                "product_name"
            ]
        ).casefold(),

        condition_order.get(
            row[
                "condition"
            ],
            999,
        ),
    )


def _hc_section_v12(
    rows,
):

    if not rows:
        return ""

    rows = sorted(
        rows,
        key=_hc_sort_v12,
    )

    output = [
        (
            "### Ko\u015fula g\u00f6re "
            "do\u011frulanm\u0131\u015f konut "
            "se\u00e7enekleri"
        ),
        "",
        (
            "A\u015fa\u011f\u0131daki sonu\u00e7lar "
            "yaln\u0131zca belirtilen konut ko\u015fulu "
            "i\u00e7in ge\u00e7erlidir. Ko\u015fula "
            "\u00f6zel sonu\u00e7lar genel banka "
            "s\u0131ralamas\u0131na kar\u0131\u015ft\u0131r\u0131lmaz."
        ),
        "",
    ]

    groups = {}

    for row in rows:

        key = (
            int(
                row[
                    "product_id"
                ]
            ),
            row[
                "bank_name"
            ],
            row[
                "product_name"
            ],
        )

        groups.setdefault(
            key,
            [],
        ).append(
            row
        )

    for (
        _product_id,
        bank_name,
        product_name,
    ), group in groups.items():

        output.extend(
            [
                (
                    "#### "
                    + bank_name
                    + " - "
                    + product_name
                ),
                "",
                (
                    "| Ko\u015ful | K\u00e2r pay\u0131 | "
                    "Ayl\u0131k taksit | "
                    "Geri \u00f6denecek toplam |"
                ),
                (
                    "| --- | ---: | ---: | ---: |"
                ),
            ]
        )

        for row in group:

            output.append(
                "| "
                + row[
                    "condition"
                ]
                + " | "
                + _hc_rate_v12(
                    row.get(
                        "profit_share_rate"
                    )
                )
                + " | "
                + _hc_money_v12(
                    row.get(
                        "monthly_installment"
                    )
                )
                + " | "
                + _hc_money_v12(
                    row.get(
                        "total_repayment"
                    )
                )
                + " |"
            )

        output.append(
            ""
        )

        labels = {
            row[
                "condition"
            ]
            for row in group
        }

        signatures = {
            (
                _hc_decimal_v12(
                    row.get(
                        "profit_share_rate"
                    )
                ),
                _hc_decimal_v12(
                    row.get(
                        "monthly_installment"
                    )
                ),
                _hc_decimal_v12(
                    row.get(
                        "total_repayment"
                    )
                ),
            )
            for row in group
        }

        if (
            labels
            ==
            {
                "Yeni / s\u0131f\u0131r konut",
            }
        ):

            output.append(
                (
                    "Bu do\u011frulama yaln\u0131zca "
                    "**yeni/s\u0131f\u0131r konut** "
                    "ko\u015fulu i\u00e7indir; ikinci el "
                    "konuta otomatik olarak genellenmez."
                )
            )

            output.append(
                ""
            )

        elif (
            {
                "Yeni / s\u0131f\u0131r konut",
                "\u0130kinci el konut",
            }
            .issubset(
                labels
            )
            and
            len(
                signatures
            )
            == 1
        ):

            output.append(
                (
                    "Bu tutar ve vadede "
                    "**s\u0131f\u0131r ve ikinci el konut** "
                    "i\u00e7in do\u011frulanm\u0131\u015f finansal "
                    "sonu\u00e7 ayn\u0131d\u0131r."
                )
            )

            output.append(
                ""
            )

        if any(
            (
                "sigortal\u0131"
                in label.casefold()
                or
                "sigortas\u0131z"
                in label.casefold()
            )
            for label in labels
        ):

            output.append(
                (
                    "Bu bankada sonu\u00e7lar konut "
                    "sahipli\u011fi ve sigorta se\u00e7imine "
                    "g\u00f6re de\u011fi\u015fmektedir."
                )
            )

            output.append(
                ""
            )

        source_url = next(
            (
                _hc_text_v12(
                    row.get(
                        "source_url"
                    )
                )
                for row in group
                if _hc_text_v12(
                    row.get(
                        "source_url"
                    )
                )
            ),
            "",
        )

        checked_at = next(
            (
                _hc_text_v12(
                    row.get(
                        "checked_at"
                    )
                )
                for row in group
                if _hc_text_v12(
                    row.get(
                        "checked_at"
                    )
                )
            ),
            "",
        )

        if source_url:

            source_line = (
                "Kaynak: "
                "[Resm\u00ee hesaplama kayna\u011f\u0131]"
                "("
                + source_url
                + ")"
            )

            human_date = (
                _hc_date_v12(
                    checked_at
                )
            )

            if human_date:

                source_line += (
                    " \u00b7 Kontrol: "
                    + human_date
                )

            output.append(
                source_line
            )

            output.append(
                ""
            )

    return "\n".join(
        output
    ).rstrip()


def _hc_insert_section_v12(
    text,
    section,
):

    if not section:
        return text

    anchors = (
        (
            "### Kriter bazl\u0131 "
            "de\u011ferlendirme"
        ),
        (
            "Kriter bazl\u0131 "
            "de\u011ferlendirme:"
        ),
    )

    for anchor in anchors:

        if anchor in text:

            return text.replace(
                anchor,
                section
                + "\n\n"
                + anchor,
                1,
            )

    return (
        text.rstrip()
        + "\n\n"
        + section
    )



def _hc_remove_condition_verified_unresolved_v13(
    text,
    condition_rows,
):

    # ========================================================
    # HC_CONDITION_VERIFIED_UNRESOLVED_DEDUP_V1
    #
    # HC condition rows are already verified/exact evidence.
    #
    # _hc_safe_context_v12 intentionally demotes special
    # condition-only results before calling the generic
    # renderer so they cannot enter generic ranking.
    #
    # Side effect:
    # the generic renderer may list the same product under
    # "Hen?z do?rulanmam?? adaylar".
    #
    # Remove only that duplicate bullet from the unresolved
    # section. Do not promote it into generic ranking.
    # ========================================================

    value = str(
        text
        or ""
    )


    labels = set()


    for row in tuple(
        condition_rows
        or ()
    ):

        bank = str(
            row.get(
                "bank_name"
            )
            or ""
        ).strip()

        product = str(
            row.get(
                "product_name"
            )
            or ""
        ).strip()


        if (
            bank
            and
            product
        ):

            labels.add(
                bank
                + " - "
                + product
            )


    if not labels:

        return value


    heading = (
        "### Hen\u00fcz "
        "do\u011frulanmam\u0131\u015f adaylar"
    )


    lines = value.splitlines()

    output = []

    inside_unresolved = False


    for line in lines:

        stripped = (
            line.strip()
        )


        if stripped == heading:

            inside_unresolved = True

            output.append(
                line
            )

            continue


        if (
            inside_unresolved
            and
            stripped.startswith(
                "### "
            )
        ):

            inside_unresolved = False


        if (
            inside_unresolved
            and
            stripped.startswith(
                "- "
            )
        ):

            candidate = (
                stripped[2:]
                .strip()
            )


            if candidate in labels:

                continue


        output.append(
            line
        )


    return "\n".join(
        output
    )


def render_finance_answer(
    context,
):

    if not _hc_is_housing_v12(
        context
    ):

        return (
            _render_finance_answer_before_hc_v12(
                context
            )
        )

    condition_rows = (
        _hc_live_rows_v12(
            context
        )
    )

    condition_rows.extend(
        _hc_snapshot_rows_v12(
            context
        )
    )

    condition_rows = (
        _hc_dedupe_v12(
            condition_rows
        )
    )

    safe_context = (
        _hc_safe_context_v12(
            context
        )
    )

    rendered = (
        _render_finance_answer_before_hc_v12(
            safe_context
        )
    )

    text = rendered.text

    text = (
        _hc_remove_condition_verified_unresolved_v13(
            text,
            condition_rows,
        )
    )

    text = text.replace(
        (
            "### Ayn\u0131 tutar ve vade i\u00e7in "
            "birebir do\u011frulanm\u0131\u015f sonu\u00e7lar"
        ),
        (
            "### Genel kar\u015f\u0131la\u015ft\u0131rmaya "
            "uygun do\u011frulanm\u0131\u015f sonu\u00e7lar"
        ),
        1,
    )

    text = text.replace(
        (
            "Ayn\u0131 tutar ve vade i\u00e7in "
            "birebir do\u011frulanm\u0131\u015f sonu\u00e7lar:"
        ),
        (
            "Genel kar\u015f\u0131la\u015ft\u0131rmaya "
            "uygun do\u011frulanm\u0131\u015f sonu\u00e7lar:"
        ),
        1,
    )

    section = (
        _hc_section_v12(
            condition_rows
        )
    )

    text = (
        _hc_insert_section_v12(
            text,
            section,
        )
    )

    numeric_ids = set(
        rendered.numeric_product_ids
    )

    numeric_ids.update(
        int(
            row[
                "product_id"
            ]
        )
        for row in condition_rows
    )

    return _hc_replace_v12(
        rendered,

        text=text,

        numeric_product_ids=tuple(
            sorted(
                numeric_ids
            )
        ),
    )


# ============================================================
# FINANCE_CONDITION_SCOPE_WORDING_V2
#
# Presentation only.
#
# A finance item may be unresolved for generic ranking while
# already carrying a separately verified condition-specific
# housing result.
#
# Only when ALL unresolved product ids are also represented in
# numeric_product_ids and a condition-specific housing section
# is present do we relabel the unresolved section.
#
# Genuine UNVERIFIED candidates retain the original wording.
# ============================================================

from dataclasses import replace as _scope_replace_v2


_render_finance_answer_before_condition_scope_wording_v2 = (
    render_finance_answer
)


_SCOPE_CONDITION_SECTION_V2 = (
    "### Ko\u015fula g\u00f6re "
    "do\u011frulanm\u0131\u015f konut se\u00e7enekleri"
)

_SCOPE_OLD_HEADING_V2 = (
    "### Hen\u00fcz "
    "do\u011frulanmam\u0131\u015f adaylar"
)

_SCOPE_NEW_HEADING_V2 = (
    "### Genel s\u0131ralamaya dahil edilmeyen "
    "ko\u015fula \u00f6zel adaylar"
)

_SCOPE_OLD_NOTE_V2 = (
    "- A\u015fa\u011f\u0131daki adaylar hen\u00fcz "
    "do\u011frulanmad\u0131\u011f\u0131 i\u00e7in bu sonu\u00e7 "
    "t\u00fcm bankalar i\u00e7in kesin birincilik "
    "anlam\u0131na gelmez."
)

_SCOPE_NEW_NOTE_V2 = (
    "- A\u015fa\u011f\u0131daki adaylar i\u00e7in bu tutar "
    "ve vadede ko\u015fula \u00f6zel sonu\u00e7lar "
    "do\u011frulanm\u0131\u015ft\u0131r; ancak ko\u015ful "
    "belirtilmeden genel s\u0131ralamaya uygun tekil bir "
    "sonu\u00e7 bulunmad\u0131\u011f\u0131ndan bu adaylar "
    "genel s\u0131ralamaya dahil edilmemi\u015ftir."
)


def _scope_id_set_v2(
    values,
):

    return {
        str(value).strip()

        for value
        in tuple(
            values
            or ()
        )

        if str(
            value
        ).strip()
    }


def render_finance_answer(
    context,
):

    rendered = (
        _render_finance_answer_before_condition_scope_wording_v2(
            context
        )
    )


    text = str(
        rendered.text
        or ""
    )


    if (
        _SCOPE_CONDITION_SECTION_V2
        not in text
    ):

        return rendered


    unresolved_ids = (
        _scope_id_set_v2(
            getattr(
                rendered,
                "unresolved_product_ids",
                (),
            )
        )
    )

    numeric_ids = (
        _scope_id_set_v2(
            getattr(
                rendered,
                "numeric_product_ids",
                (),
            )
        )
    )


    if not unresolved_ids:

        return rendered


    # Critical semantic guard:
    #
    # If even one unresolved candidate does NOT already have
    # condition-specific numeric evidence in the rendered
    # answer, the original UNVERIFIED wording remains.
    if not unresolved_ids.issubset(
        numeric_ids
    ):

        return rendered


    if (
        _SCOPE_OLD_HEADING_V2
        not in text
    ):

        return rendered


    if (
        _SCOPE_OLD_NOTE_V2
        not in text
    ):

        return rendered


    updated = text.replace(
        _SCOPE_OLD_NOTE_V2,
        _SCOPE_NEW_NOTE_V2,
        1,
    )


    updated = updated.replace(
        _SCOPE_OLD_HEADING_V2,
        _SCOPE_NEW_HEADING_V2,
        1,
    )


    return _scope_replace_v2(
        rendered,
        text=updated,
    )


# ============================================================
# HOUSING_VARIANT_METADATA_BRIDGE_V4
#
# Reads ONLY GroundedFinanceResult.presentation_variants.
#
# The values reached this point only through the
# verified+exact grounding gate.
#
# Ranking candidate count and calculations are untouched.
# ============================================================

from dataclasses import (
    replace as _hv4_replace,
)


_render_finance_answer_before_hv4 = (
    render_finance_answer
)


_HV4_CONDITION_HEADING = (
    "### Ko\u015fula g\u00f6re "
    "do\u011frulanm\u0131\u015f konut se\u00e7enekleri"
)

_HV4_CRITERIA_HEADING = (
    "### Kriter bazl\u0131 de\u011ferlendirme"
)


_HV4_CONTRACT = {

    3: {
        "bank":
            "D\u00fcnya Kat\u0131l\u0131m",

        "required":
            (
                "yeni_konut",
                "2el_konut",
            ),

        "labels": {
            "yeni_konut":
                "Yeni / s\u0131f\u0131r konut",

            "2el_konut":
                "\u0130kinci el konut",
        },

        "note":
            (
                "Bu tutar ve vadede "
                "**yeni/s\u0131f\u0131r ve ikinci el konut** "
                "se\u00e7enekleri ayr\u0131 ayr\u0131 "
                "do\u011frulanm\u0131\u015f ve ayn\u0131 finansal "
                "sonucu vermi\u015ftir."
            ),
    },

    97: {
        "bank":
            "Albaraka T\u00fcrk",

        "required":
            (
                "ilk_ev",
                "mevcut_konut",
            ),

        "labels": {
            "ilk_ev":
                "\u0130lk Evim",

            "mevcut_konut":
                "2. ve sonraki konut",
        },

        "note":
            (
                "Bu tutar ve vadede "
                "**\u0130lk Evim ve 2. ve sonraki konut** "
                "se\u00e7enekleri ayr\u0131 ayr\u0131 "
                "do\u011frulanm\u0131\u015f ve ayn\u0131 finansal "
                "sonucu vermi\u015ftir."
            ),
    },
}


def _hv4_money(
    value,
):

    if value is None:
        return "-"

    try:
        number = float(value)

    except Exception:
        return "-"

    return (
        f"{number:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
        + " TL"
    )


def _hv4_rate(
    value,
):

    if value is None:
        return "-"

    try:
        number = float(value)

    except Exception:
        return "-"

    return (
        "%"
        +
        f"{number:.2f}"
        .replace(".", ",")
    )


def _hv4_items(
    context,
):

    output = []


    for item in tuple(
        getattr(
            context,
            "finance_results",
            (),
        )
        or ()
    ):

        try:
            product_id = int(
                item.product_id
            )

        except Exception:
            continue


        contract = (
            _HV4_CONTRACT.get(
                product_id
            )
        )


        if contract is None:
            continue


        if not bool(
            getattr(
                item,
                "verified",
                False,
            )
        ):
            continue


        if not bool(
            getattr(
                item,
                "exact_match",
                False,
            )
        ):
            continue


        variants = tuple(
            getattr(
                item,
                "presentation_variants",
                (),
            )
            or ()
        )


        required = tuple(
            contract[
                "required"
            ]
        )


        if (
            len(variants)
            !=
            len(required)
        ):
            continue


        if set(
            variants
        ) != set(
            required
        ):
            continue


        # All financial numbers used below already crossed
        # the verified/exact numeric grounding boundary.
        if any(
            getattr(
                item,
                name,
                None,
            )
            is None

            for name in (
                "profit_share_rate",
                "monthly_installment",
                "total_repayment",
            )
        ):
            continue


        output.append(
            (
                item,
                contract,
                required,
            )
        )


    return tuple(
        output
    )


def _hv4_section(
    item,
    contract,
    variants,
):

    lines = [
        (
            "#### "
            + contract[
                "bank"
            ]
            + " - Konut Finansman\u0131"
        ),
        "",
        (
            "| Ko\u015ful | K\u00e2r pay\u0131 | "
            "Ayl\u0131k taksit | "
            "Geri \u00f6denecek toplam |"
        ),
        "| --- | ---: | ---: | ---: |",
    ]


    for variant in variants:

        lines.append(
            (
                "| "
                + contract[
                    "labels"
                ][variant]
                + " | "
                + _hv4_rate(
                    item.profit_share_rate
                )
                + " | "
                + _hv4_money(
                    item.monthly_installment
                )
                + " | "
                + _hv4_money(
                    item.total_repayment
                )
                + " |"
            )
        )


    lines.extend(
        (
            "",
            contract[
                "note"
            ],
        )
    )


    source_url = str(
        getattr(
            item,
            "source_url",
            "",
        )
        or ""
    )


    checked_at = str(
        getattr(
            item,
            "checked_at",
            "",
        )
        or ""
    )


    if source_url:

        source_line = (
            "Kaynak: "
            "[Resm\u00ee hesaplama kayna\u011f\u0131]"
            "("
            + source_url
            + ")"
        )


        if checked_at:

            try:

                date_part = (
                    checked_at[:10]
                )

                year, month, day = (
                    date_part.split(
                        "-"
                    )
                )

                months = {
                    "01": "Ocak",
                    "02": "\u015eubat",
                    "03": "Mart",
                    "04": "Nisan",
                    "05": "May\u0131s",
                    "06": "Haziran",
                    "07": "Temmuz",
                    "08": "A\u011fustos",
                    "09": "Eyl\u00fcl",
                    "10": "Ekim",
                    "11": "Kas\u0131m",
                    "12": "Aral\u0131k",
                }

                source_line += (
                    " \u00b7 Kontrol: "
                    + str(
                        int(
                            day
                        )
                    )
                    + " "
                    + months.get(
                        month,
                        month,
                    )
                    + " "
                    + year
                )

            except Exception:

                pass


        lines.extend(
            (
                "",
                source_line,
            )
        )


    return "\n".join(
        lines
    )


def _hv4_insert(
    text,
    sections,
):

    value = str(
        text
        or ""
    )


    if not sections:
        return value


    addition = (
        "\n\n".join(
            sections
        )
    )


    if (
        _HV4_CONDITION_HEADING
        in value
    ):

        if (
            _HV4_CRITERIA_HEADING
            in value
        ):

            return value.replace(
                _HV4_CRITERIA_HEADING,
                (
                    addition
                    + "\n\n"
                    + _HV4_CRITERIA_HEADING
                ),
                1,
            )


        return (
            value.rstrip()
            + "\n\n"
            + addition
        )


    condition_intro = (
        _HV4_CONDITION_HEADING
        + "\n\n"
        + (
            "A\u015fa\u011f\u0131daki sonu\u00e7lar bankalar\u0131n "
            "resm\u00ee hesaplama ara\u00e7lar\u0131nda ayr\u0131 "
            "konut ko\u015fullar\u0131 olarak do\u011frulanm\u0131\u015ft\u0131r. "
            "Ayn\u0131 finansal sonucu veren ko\u015fullar genel "
            "banka s\u0131ralamas\u0131nda ikinci kez aday olarak "
            "say\u0131lmaz."
        )
        + "\n\n"
        + addition
    )


    if (
        _HV4_CRITERIA_HEADING
        in value
    ):

        return value.replace(
            _HV4_CRITERIA_HEADING,
            (
                condition_intro
                + "\n\n"
                + _HV4_CRITERIA_HEADING
            ),
            1,
        )


    return (
        value.rstrip()
        + "\n\n"
        + condition_intro
    )


def render_finance_answer(
    context,
):

    rendered = (
        _render_finance_answer_before_hv4(
            context
        )
    )


    items = (
        _hv4_items(
            context
        )
    )


    if not items:
        return rendered


    sections = [
        _hv4_section(
            item,
            contract,
            variants,
        )

        for (
            item,
            contract,
            variants,
        )
        in items
    ]


    current = str(
        rendered.text
        or ""
    )


    updated = (
        _hv4_insert(
            current,
            sections,
        )
    )


    if updated == current:
        return rendered


    return _hv4_replace(
        rendered,
        text=updated,
    )


# ============================================================
# FINANCE_CONDITIONAL_VERIFIED_VARIANTS_V1
#
# Generic renderer for independently verified pricing
# conditions such as:
#
# - insured / uninsured
# - future explicitly modeled condition pairs
#
# This wrapper intentionally runs AFTER the existing housing
# and HV4 renderer stack. Existing housing behavior remains
# untouched.
# ============================================================

from dataclasses import (
    replace as _cv_dataclass_replace_v1,
)


_render_finance_answer_before_cv_v1 = (
    render_finance_answer
)


def _cv_label_v1(
    value,
):

    key = str(
        value
        or ""
    ).strip().casefold()

    labels = {
        "sigortali":
            "Sigortal\u0131",

        "sigortasiz":
            "Sigortas\u0131z",
    }

    return labels.get(
        key,
        str(
            value
            or ""
        ).strip(),
    )


def _cv_items_v1(
    context,
):

    output = []

    for item in tuple(
        getattr(
            context,
            "finance_results",
            (),
        )
        or ()
    ):

        variants = tuple(
            getattr(
                item,
                "conditional_verified_variants",
                (),
            )
            or ()
        )

        if not variants:
            continue

        safe = []

        seen = set()

        for row in variants:

            if not isinstance(
                row,
                dict,
            ):
                continue

            variant = str(
                row.get(
                    "variant"
                )
                or ""
            ).strip()

            if not variant:
                continue

            normalized = (
                variant.casefold()
            )

            if normalized in seen:
                continue

            if any(
                row.get(
                    key
                )
                is None

                for key in (
                    "profit_share_rate",
                    "monthly_installment",
                    "total_repayment",
                )
            ):
                continue

            seen.add(
                normalized
            )

            safe.append(
                row
            )

        if safe:

            output.append(
                (
                    item,
                    tuple(
                        safe
                    ),
                )
            )

    return tuple(
        output
    )


def _cv_section_v1(
    items,
):

    if not items:
        return ""

    lines = [
        "### Ko\u015fula g\u00f6re do\u011frulanm\u0131\u015f se\u00e7enekler",
        "",
        (
            "A\u015fa\u011f\u0131daki sonu\u00e7lar ayn\u0131 tutar ve vade "
            "i\u00e7in birebir do\u011frulanm\u0131\u015ft\u0131r; ancak fiyatlama "
            "ko\u015fullar\u0131 farkl\u0131 oldu\u011fu i\u00e7in kullan\u0131c\u0131 bir "
            "ko\u015ful se\u00e7meden genel s\u0131ralamaya otomatik olarak "
            "dahil edilmez."
        ),
    ]

    for (
        item,
        variants,
    ) in items:

        bank = str(
            getattr(
                item,
                "bank_name",
                "",
            )
            or ""
        ).strip()

        product = str(
            getattr(
                item,
                "product_name",
                "",
            )
            or ""
        ).strip()

        lines.extend(
            (
                "",
                (
                    "#### "
                    + bank
                    + " - "
                    + product
                ),
                "",
                (
                    "| Ko\u015ful | K\u00e2r pay\u0131 | "
                    "Ayl\u0131k taksit | "
                    "Geri \u00f6denecek toplam |"
                ),
                "| --- | ---: | ---: | ---: |",
            )
        )

        source_rows = []

        for row in variants:

            lines.append(
                (
                    "| "
                    + _cv_label_v1(
                        row.get(
                            "variant"
                        )
                    )
                    + " | "
                    + _hv4_rate(
                        row.get(
                            "profit_share_rate"
                        )
                    )
                    + " | "
                    + _hv4_money(
                        row.get(
                            "monthly_installment"
                        )
                    )
                    + " | "
                    + _hv4_money(
                        row.get(
                            "total_repayment"
                        )
                    )
                    + " |"
                )
            )

            source_url = str(
                row.get(
                    "source_url"
                )
                or ""
            ).strip()

            if source_url:
                pair = (
                    _cv_label_v1(
                        row.get(
                            "variant"
                        )
                    ),
                    source_url,
                )

                if pair not in source_rows:
                    source_rows.append(
                        pair
                    )

        if source_rows:

            lines.append("")

            for (
                label,
                source_url,
            ) in source_rows:

                lines.append(
                    (
                        "Kaynak ("
                        + label
                        + "): "
                        + "[Resm\u00ee fiyatlama kayna\u011f\u0131]"
                        + "("
                        + source_url
                        + ")"
                    )
                )

    return "\n".join(
        lines
    )


def _cv_remove_unresolved_v1(
    text,
    items,
):

    labels = set()

    for (
        item,
        _,
    ) in items:

        bank = str(
            getattr(
                item,
                "bank_name",
                "",
            )
            or ""
        ).strip()

        product = str(
            getattr(
                item,
                "product_name",
                "",
            )
            or ""
        ).strip()

        if bank and product:

            labels.add(
                bank
                + " - "
                + product
            )

    if not labels:
        return str(
            text
            or ""
        )

    lines = str(
        text
        or ""
    ).splitlines()

    output = []

    inside = False

    headings = {
        "### Hen\u00fcz do\u011frulanmam\u0131\u015f adaylar",
        "Hen\u00fcz do\u011frulanmam\u0131\u015f adaylar:",
    }

    for line in lines:

        stripped = (
            line.strip()
        )

        if stripped in headings:

            inside = True

            output.append(
                line
            )

            continue

        if (
            inside
            and
            stripped.startswith(
                "### "
            )
            and
            stripped not in headings
        ):

            inside = False

        if (
            inside
            and
            stripped.startswith(
                "- "
            )
        ):

            candidate = (
                stripped[2:]
                .strip()
            )

            if candidate in labels:
                continue

        output.append(
            line
        )

    return "\n".join(
        output
    )


def _cv_insert_v1(
    text,
    section,
):

    value = str(
        text
        or ""
    ).rstrip()

    section = str(
        section
        or ""
    ).strip()

    if not section:
        return value

    candidates = (
        "\n### Hen\u00fcz do\u011frulanmam\u0131\u015f adaylar",
        "\nHen\u00fcz do\u011frulanmam\u0131\u015f adaylar:",
    )

    indexes = [
        value.find(
            candidate
        )
        for candidate in candidates
        if value.find(
            candidate
        ) >= 0
    ]

    if indexes:

        index = min(
            indexes
        )

        return (
            value[:index]
            .rstrip()
            + "\n\n"
            + section
            + "\n\n"
            + value[index:]
            .lstrip()
        )

    if not value:
        return section

    return (
        value
        + "\n\n"
        + section
    )


def render_finance_answer(
    context,
):

    rendered = (
        _render_finance_answer_before_cv_v1(
            context
        )
    )

    items = (
        _cv_items_v1(
            context
        )
    )

    if not items:
        return rendered

    section = (
        _cv_section_v1(
            items
        )
    )

    text = (
        _cv_remove_unresolved_v1(
            rendered.text,
            items,
        )
    )

    text = (
        _cv_insert_v1(
            text,
            section,
        )
    )

    condition_ids = {
        int(
            getattr(
                item,
                "product_id",
            )
        )
        for (
            item,
            _,
        )
        in items
    }

    numeric_ids = set(
        getattr(
            rendered,
            "numeric_product_ids",
            (),
        )
        or ()
    )

    numeric_ids.update(
        condition_ids
    )

    unresolved_ids = set(
        getattr(
            rendered,
            "unresolved_product_ids",
            (),
        )
        or ()
    )

    unresolved_ids.difference_update(
        condition_ids
    )

    return _cv_dataclass_replace_v1(
        rendered,

        text=text,

        numeric_product_ids=tuple(
            sorted(
                numeric_ids
            )
        ),

        unresolved_product_ids=tuple(
            sorted(
                unresolved_ids
            )
        ),
    )


# ============================================================
# EM_LAK_HOUSING_SCOPE_NOTE_V14
#
# Product 242's official calculator mapping is scoped to
# new/zero housing.  If the live endpoint is temporarily
# unreachable, keep that verified *scope* fact visible without
# inventing or replaying a numeric result from another maturity.
# ============================================================

from dataclasses import replace as _emlak_scope_replace_v14

_render_finance_answer_before_emlak_scope_note_v14 = render_finance_answer


def render_finance_answer(context):
    rendered = _render_finance_answer_before_emlak_scope_note_v14(context)
    text = str(getattr(rendered, "text", "") or "")

    try:
        unresolved = {
            int(value)
            for value in tuple(getattr(rendered, "unresolved_product_ids", ()) or ())
        }
    except Exception:
        unresolved = set()

    heading = "### Koşula göre doğrulanmış konut seçenekleri"
    criteria = "### Kriter bazlı değerlendirme"
    scope_sentence = (
        "Bu ürün için BANSA'daki resmî hesaplayıcı eşlemesi yalnızca "
        "**yeni/sıfır konut** koşulu içindir; ikinci el konuta otomatik "
        "olarak genellenmez."
    )

    if (
        242 in unresolved
        and heading in text
        and "Türkiye Emlak Katılım - Konut Finansmanı" in text
        and "yalnızca **yeni/sıfır konut** koşulu içindir" not in text
    ):
        note = (
            "#### Türkiye Emlak Katılım - Konut Finansmanı\n\n"
            + scope_sentence
            + " Bu senaryoda canlı hesap sonucu doğrulanamadığı için sayısal "
              "değer genel sıralamaya eklenmiyor.\n\n"
        )
        if criteria in text:
            text = text.replace(criteria, note + criteria, 1)
        else:
            text = text.rstrip() + "\n\n" + note.rstrip()

        return _emlak_scope_replace_v14(rendered, text=text)

    return rendered
