# CHATBOT_FINANCE_FACT_LOOKUP_V1

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import re
import unicodedata

import pandas as pd

from src.finance_runtime_repository import (
    get_standard_products,
)


@dataclass(frozen=True)
class FinanceFactLookupResult:

    status: str
    attribute: str | None

    bank_name: str | None
    product_name: str | None

    text: str

    source_url: str | None = None
    checked_at: str | None = None


def _normalize(value) -> str:

    text = str(
        value
        or ""
    ).strip().casefold()

    text = (
        text
        .replace("\u0131", "i")
        .replace("\u015f", "s")
        .replace("\u011f", "g")
        .replace("\u00fc", "u")
        .replace("\u00f6", "o")
        .replace("\u00e7", "c")
    )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        ch
        for ch in text
        if not unicodedata.combining(
            ch
        )
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


def _present(value) -> bool:

    if value is None:
        return False

    try:

        if bool(
            pd.isna(
                value
            )
        ):
            return False

    except Exception:
        pass

    return str(
        value
    ).strip() != ""


def _as_decimal(
    value,
) -> Decimal | None:

    if not _present(
        value
    ):
        return None

    try:

        return Decimal(
            str(
                value
            )
            .replace(
                ",",
                ".",
            )
        )

    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):

        return None


def _format_percent(
    value,
) -> str | None:

    number = _as_decimal(
        value
    )

    if number is None:
        return None

    raw = format(
        number,
        "f",
    )

    if "." in raw:

        whole, fraction = (
            raw.split(
                ".",
                1,
            )
        )

        fraction = (
            fraction
            .rstrip(
                "0"
            )
        )

        if len(
            fraction
        ) < 2:

            fraction = (
                fraction
                .ljust(
                    2,
                    "0",
                )
            )

        raw = (
            whole
            + ","
            + fraction
        )

    else:

        raw = (
            raw
            + ",00"
        )

    # BANSA finance rate semantigi yuzde puanidir.
    #
    # 0.5 -> %0,50
    #
    # 100 ile CARPILMAZ.
    return (
        "%"
        + raw
    )


def _format_money(
    value,
) -> str | None:

    number = _as_decimal(
        value
    )

    if number is None:
        return None

    if number == number.to_integral_value():

        value_text = (
            f"{int(number):,}"
            .replace(
                ",",
                ".",
            )
        )

    else:

        value_text = (
            f"{number:,.2f}"
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
        value_text
        + " TL"
    )


def _json_dict(
    raw,
) -> dict:

    if isinstance(
        raw,
        dict,
    ):
        return raw

    if not _present(
        raw
    ):
        return {}

    try:

        value = json.loads(
            str(
                raw
            )
        )

    except Exception:

        return {}

    if isinstance(
        value,
        dict,
    ):
        return value

    return {}


def _clean_note(
    value,
) -> str:

    text = str(
        value
        or ""
    ).strip()

    if not text:
        return ""

    return re.split(
        r"\bKaynak\s*:",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()


_BANK_STOPWORDS = {
    "bank",
    "bankasi",
    "katilim",
    "turk",
    "turkiye",
}


_PRODUCT_STOPWORDS = {
    "finansman",
    "finansmani",
    "bireysel",
    "ticari",
}


def _best_bank(
    frame,
    question_norm: str,
) -> str | None:

    banks = sorted(
        {
            str(value).strip()
            for value
            in frame[
                "bank_name"
            ].tolist()
            if _present(
                value
            )
        },
        key=len,
        reverse=True,
    )

    direct = [
        bank
        for bank in banks
        if (
            _normalize(
                bank
            )
            and _normalize(
                bank
            )
            in question_norm
        )
    ]

    if direct:

        direct.sort(
            key=lambda value: len(
                _normalize(
                    value
                )
            ),
            reverse=True,
        )

        return direct[0]

    question_tokens = set(
        question_norm.split()
    )

    scored = []

    for bank in banks:

        tokens = [
            token
            for token
            in _normalize(
                bank
            ).split()
            if token not in _BANK_STOPWORDS
        ]

        if not tokens:
            continue

        matched = sum(
            token
            in question_tokens
            for token in tokens
        )

        if matched <= 0:
            continue

        ratio = (
            matched
            / len(
                tokens
            )
        )

        scored.append(
            (
                ratio,
                matched,
                len(
                    " ".join(
                        tokens
                    )
                ),
                bank,
            )
        )

    if not scored:
        return None

    scored.sort(
        reverse=True
    )

    best = scored[0]

    if best[0] < 0.75:
        return None

    if (
        len(
            scored
        )
        > 1
        and scored[1][:2]
        == best[:2]
    ):
        return None

    return best[3]


def _product_candidates(
    frame,
    question_norm: str,
    bank_name: str | None,
):

    candidates = frame

    if bank_name:

        candidates = (
            candidates[
                candidates[
                    "bank_name"
                ].astype(
                    str
                )
                == bank_name
            ]
        )

    exact_rows = []

    for index, row in candidates.iterrows():

        product = str(
            row.get(
                "product_name"
            )
            or ""
        ).strip()

        normalized = _normalize(
            product
        )

        if (
            normalized
            and normalized
            in question_norm
        ):

            exact_rows.append(
                (
                    len(
                        normalized
                    ),
                    index,
                )
            )

    if exact_rows:

        best_length = max(
            value[0]
            for value
            in exact_rows
        )

        indexes = [
            index
            for length, index
            in exact_rows
            if length
            == best_length
        ]

        return candidates.loc[
            indexes
        ]

    question_tokens = set(
        question_norm.split()
    )

    scores = []

    for index, row in candidates.iterrows():

        product = str(
            row.get(
                "product_name"
            )
            or ""
        ).strip()

        tokens = [
            token
            for token
            in _normalize(
                product
            ).split()
            if token
            not in _PRODUCT_STOPWORDS
        ]

        if not tokens:
            continue

        matched = sum(
            token
            in question_tokens
            for token in tokens
        )

        if matched <= 0:
            continue

        ratio = (
            matched
            / len(
                tokens
            )
        )

        scores.append(
            (
                ratio,
                matched,
                len(
                    tokens
                ),
                index,
            )
        )

    if not scores:

        return candidates.iloc[
            0:0
        ]

    scores.sort(
        reverse=True
    )

    best = scores[0]

    if best[0] < 0.75:

        return candidates.iloc[
            0:0
        ]

    indexes = [
        item[3]
        for item in scores
        if item[:3]
        == best[:3]
    ]

    return candidates.loc[
        indexes
    ]


def _fee_type(
    row: dict,
) -> str:

    value = str(
        row.get(
            "fee_type"
        )
        or ""
    ).strip().casefold()

    if value:
        return value

    label = _normalize(
        row.get(
            "fee_label"
        )
        or row.get(
            "label"
        )
        or ""
    )

    if "tahsis" in label:
        return "allocation"

    if "ekspertiz" in label:
        return "appraisal"

    if (
        "ipotek" in label
        or "rehin" in label
    ):
        return "mortgage_establishment"

    return ""


def _fee_value(
    fee: dict,
) -> str | None:

    rate = _format_percent(
        fee.get(
            "rate"
        )
    )

    if rate:
        return rate

    amount = _format_money(
        fee.get(
            "amount"
        )
    )

    if amount:
        return amount

    if (
        fee.get(
            "waived"
        )
        is True
    ):
        return (
            "muaf"
        )

    note = _clean_note(
        fee.get(
            "note"
        )
    )

    if note:
        return note

    return None


def _fee_label(
    fee: dict,
) -> str:

    return str(
        fee.get(
            "fee_label"
        )
        or fee.get(
            "label"
        )
        or "\u00dccret"
    ).strip()


def _fee_answer(
    *,
    row,
    attribute: str,
    bank: str,
    product: str,
):

    rules = _json_dict(
        row.get(
            "finance_rules_json"
        )
    )

    fee_rules = rules.get(
        "fee_rules"
    )

    if not isinstance(
        fee_rules,
        list,
    ):
        fee_rules = []

    fee_rules = [
        item
        for item
        in fee_rules
        if isinstance(
            item,
            dict,
        )
    ]

    requested_types = {
        "allocation_fee": {
            "allocation",
        },
        "appraisal_fee": {
            "appraisal",
            "expertise",
        },
        "mortgage_fee": {
            "mortgage",
            "mortgage_establishment",
        },
    }

    if attribute == "fee_summary":

        lines = []

        seen = set()

        for fee in fee_rules:

            label = _fee_label(
                fee
            )

            value = _fee_value(
                fee
            )

            if not value:
                continue

            key = (
                _fee_type(
                    fee
                ),
                label,
                value,
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            lines.append(
                "- "
                + label
                + ": "
                + value
            )

        if not lines:

            return None

        return (
            bank
            + " "
            + product
            + " i\u00e7in yay\u0131mlanan masraf bilgileri:\n"
            + "\n".join(
                lines
            )
        )

    allowed = requested_types.get(
        attribute,
        set(),
    )

    matches = [
        fee
        for fee in fee_rules
        if _fee_type(
            fee
        )
        in allowed
    ]

    if not matches:
        return None

    fee = matches[0]

    label = _fee_label(
        fee
    )

    value = _fee_value(
        fee
    )

    if not value:
        return None

    if (
        _format_percent(
            fee.get(
                "rate"
            )
        )
        or _format_money(
            fee.get(
                "amount"
            )
        )
    ):

        return (
            bank
            + " "
            + product
            + " i\u00e7in "
            + label
            + " "
            + value
            + " olarak belirtiliyor."
        )

    return (
        bank
        + " "
        + product
        + " i\u00e7in "
        + label
        + ": "
        + value
    )


def _pricing_tier_text(
    row,
) -> str | None:

    rules = _json_dict(
        row.get(
            "finance_rules_json"
        )
    )

    tiers = rules.get(
        "pricing_tiers"
    )

    if not isinstance(
        tiers,
        list,
    ):
        return None

    parts = []

    seen = set()

    for tier in tiers:

        if not isinstance(
            tier,
            dict,
        ):
            continue

        rate = (
            tier.get(
                "profit_share_rate"
            )
        )

        if rate is None:
            rate = tier.get(
                "rate"
            )

        rate_text = _format_percent(
            rate
        )

        if not rate_text:
            continue

        maturity = tier.get(
            "maturity_months"
        )

        variant = str(
            tier.get(
                "pricing_variant"
            )
            or tier.get(
                "variant"
            )
            or ""
        ).strip()

        detail = []

        if _present(
            maturity
        ):
            detail.append(
                str(
                    maturity
                )
                + " ay"
            )

        if variant:
            detail.append(
                variant
            )

        prefix = (
            " / ".join(
                detail
            )
        )

        text = (
            (
                prefix
                + ": "
            )
            if prefix
            else ""
        ) + rate_text

        if text in seen:
            continue

        seen.add(
            text
        )

        parts.append(
            text
        )

        if len(
            parts
        ) >= 8:
            break

    if not parts:
        return None

    return "; ".join(
        parts
    )


def _build_answer(
    *,
    row,
    attribute: str,
    bank: str,
    product: str,
):

    if attribute in {
        "allocation_fee",
        "appraisal_fee",
        "mortgage_fee",
        "fee_summary",
    }:

        return _fee_answer(
            row=row,
            attribute=attribute,
            bank=bank,
            product=product,
        )

    if attribute == "maturity":

        value = row.get(
            "maximum_maturity_months"
        )

        if _present(
            value
        ):

            number = _as_decimal(
                value
            )

            if number is not None:

                text = (
                    bank
                    + " "
                    + product
                    + " i\u00e7in azami vade "
                    + str(
                        int(
                            number
                        )
                    )
                    + " ay olarak belirtiliyor."
                )

                rules_text = str(
                    row.get(
                        "maturity_rules_text"
                    )
                    or ""
                ).strip()

                if (
                    rules_text
                    and rules_text
                    not in text
                ):

                    text += (
                        " "
                        + rules_text
                    )

                return text

        return None

    if attribute == "profit_share_rate":

        rate = _format_percent(
            row.get(
                "profit_share_rate"
            )
        )

        if rate:

            return (
                bank
                + " "
                + product
                + " i\u00e7in yay\u0131mlanan k\u00e2r pay\u0131 oran\u0131 "
                + rate
                + "."
            )

        rate_text = str(
            row.get(
                "profit_share_rate_text"
            )
            or ""
        ).strip()

        if rate_text:

            return (
                bank
                + " "
                + product
                + " k\u00e2r pay\u0131 bilgisi: "
                + rate_text
            )

        tiers = _pricing_tier_text(
            row
        )

        if tiers:

            return (
                bank
                + " "
                + product
                + " i\u00e7in yay\u0131mlanan fiyatlama: "
                + tiers
            )

        return None

    if attribute == "financing_ratio":

        ratio = _format_percent(
            row.get(
                "maximum_financing_ratio"
            )
        )

        if ratio:

            return (
                bank
                + " "
                + product
                + " i\u00e7in azami finansman oran\u0131 "
                + ratio
                + " olarak belirtiliyor."
            )

        detail = str(
            row.get(
                "financing_ratio_rules_text"
            )
            or ""
        ).strip()

        if detail:

            return (
                bank
                + " "
                + product
                + " finansman oran\u0131 bilgisi: "
                + detail
            )

        return None

    if attribute == "maximum_amount":

        amount = _format_money(
            row.get(
                "maximum_financing_amount"
            )
        )

        if amount:

            return (
                bank
                + " "
                + product
                + " i\u00e7in yay\u0131mlanan azami finansman tutar\u0131 "
                + amount
                + "."
            )

        return None

    return None


def lookup_finance_fact(
    *,
    question: str,
    attribute: str | None,
) -> FinanceFactLookupResult:

    question = str(
        question
        or ""
    ).strip()

    if not attribute:

        return FinanceFactLookupResult(
            status="unsupported_attribute",
            attribute=None,
            bank_name=None,
            product_name=None,
            text=(
                "Sorulan finansman alan\u0131 "
                "yap\u0131sal veriyle e\u015fle\u015ftirilemedi."
            ),
        )

    try:

        frame = get_standard_products()

    except Exception as exc:

        return FinanceFactLookupResult(
            status="repository_error",
            attribute=attribute,
            bank_name=None,
            product_name=None,
            text=(
                "Do\u011frulanm\u0131\u015f finansman verisine "
                "\u015fu anda eri\u015filemiyor."
            ),
        )

    if frame.empty:

        return FinanceFactLookupResult(
            status="repository_empty",
            attribute=attribute,
            bank_name=None,
            product_name=None,
            text=(
                "Do\u011frulanm\u0131\u015f finansman verisi "
                "bulunamad\u0131."
            ),
        )

    question_norm = _normalize(
        question
    )

    bank = _best_bank(
        frame,
        question_norm,
    )

    products = _product_candidates(
        frame,
        question_norm,
        bank,
    )

    if products.empty:

        return FinanceFactLookupResult(
            status="product_not_found",
            attribute=attribute,
            bank_name=bank,
            product_name=None,
            text=(
                (
                    bank
                    + " i\u00e7in "
                )
                if bank
                else ""
            )
            + "Sorudaki finansman \u00fcr\u00fcn\u00fc "
              "do\u011frulanm\u0131\u015f kay\u0131tlarla "
              "net olarak e\u015fle\u015ftirilemedi.",
        )

    unique_banks = {
        str(value).strip()
        for value
        in products[
            "bank_name"
        ].tolist()
        if _present(
            value
        )
    }

    if (
        bank is None
        and len(
            unique_banks
        ) > 1
    ):

        return FinanceFactLookupResult(
            status="bank_required",
            attribute=attribute,
            bank_name=None,
            product_name=None,
            text=(
                "Bu finansman \u00fcr\u00fcn\u00fc birden fazla "
                "bankada bulundu\u011fu i\u00e7in banka ad\u0131n\u0131 "
                "belirtmeniz gerekiyor."
            ),
        )

    unique_products = {
        (
            str(
                row.get(
                    "bank_name"
                )
            ).strip(),
            str(
                row.get(
                    "product_name"
                )
            ).strip(),
        )
        for _, row
        in products.iterrows()
    }

    if len(
        unique_products
    ) > 1:

        return FinanceFactLookupResult(
            status="product_ambiguous",
            attribute=attribute,
            bank_name=bank,
            product_name=None,
            text=(
                "Sorunuz birden fazla finansman "
                "\u00fcr\u00fcn\u00fcyle e\u015fle\u015fiyor. "
                "\u00dcr\u00fcn ad\u0131n\u0131 biraz daha "
                "netle\u015ftirin."
            ),
        )

    row = products.iloc[
        0
    ]

    bank_name = str(
        row.get(
            "bank_name"
        )
        or ""
    ).strip()

    product_name = str(
        row.get(
            "product_name"
        )
        or ""
    ).strip()

    answer = _build_answer(
        row=row,
        attribute=attribute,
        bank=bank_name,
        product=product_name,
    )

    source_url = (
        str(
            row.get(
                "source_url"
            )
            or ""
        ).strip()
        or None
    )

    checked_at = (
        str(
            row.get(
                "last_checked_at"
            )
            or ""
        ).strip()
        or None
    )

    if not answer:

        return FinanceFactLookupResult(
            status="value_not_published",
            attribute=attribute,
            bank_name=bank_name,
            product_name=product_name,
            text=(
                bank_name
                + " "
                + product_name
                + " i\u00e7in bu bilgiye ili\u015fkin net bir de\u011fer belirtilmiyor."
            ),
            source_url=source_url,
            checked_at=checked_at,
        )

    return FinanceFactLookupResult(
        status="found",
        attribute=attribute,
        bank_name=bank_name,
        product_name=product_name,
        text=answer,
        source_url=source_url,
        checked_at=checked_at,
    )
