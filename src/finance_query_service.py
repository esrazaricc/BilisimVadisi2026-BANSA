"""
BANSA finance catalog query service.

BANSA_FINANCE_QUERY_SERVICE_V1

Purpose
-------
Expose the validated finance catalog used by BANSA to
application layers such as the chatbot without forcing every
finance comparison through a live calculator.

Primary repository:
    local PostgreSQL used by the Finance Comparison dashboard.

Fallback:
    validated portable finance runtime snapshot.

Important:
    This service compares published product terms.
    It does NOT invent monthly installment or total repayment.

Exact repayment calculations remain the responsibility of the
verified finance calculation resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import unicodedata

import pandas as pd

from src.finance_comparison_purpose import (
    resolve_comparison_purpose,
)


@dataclass(frozen=True)
class FinanceCatalogQueryResult:

    status: str

    text: str

    rows: tuple[
        dict,
        ...,
    ]

    repository_source: str

    family: str

    scope: str

    amount: float | None = None

    maturity: int | None = None

    purpose: str | None = None


def _normalize(
    value,
):

    text = str(
        value
        or ""
    ).strip()

    text = (
        text
        .replace("\u0131", "i")
        .replace("\u0130", "I")
    )

    text = (
        unicodedata
        .normalize(
            "NFKD",
            text,
        )
        .encode(
            "ascii",
            "ignore",
        )
        .decode(
            "ascii",
        )
        .casefold()
    )

    return "_".join(
        text
        .replace("-", " ")
        .split()
    )


def _present(
    value,
):

    if value is None:
        return False

    try:

        if pd.isna(
            value
        ):
            return False

    except Exception:

        pass

    return bool(
        str(
            value
        ).strip()
    )


def _number(
    value,
):

    if not _present(
        value
    ):
        return None

    try:

        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):

        return None


def _integer(
    value,
):

    number = _number(
        value
    )

    if number is None:
        return None

    return int(
        number
    )


def _scope_key(
    value,
):

    key = _normalize(
        value
    )

    aliases = {
        "individual":
            "bireysel",

        "bireysel":
            "bireysel",

        "business":
            "ticari",

        "commercial":
            "ticari",

        "ticari":
            "ticari",
    }

    return aliases.get(
        key,
        key,
    )


# ============================================================
# FINANCE_QUERY_FAMILY_ALIAS_V1
#
# User/planner vocabulary and canonical BANSA catalog keys
# are not always identical.
#
# Example:
#   tasit_finansmani -> arac_finansmani
#
# Keep this translation at the query-service boundary instead
# of changing the validated product taxonomy.
# ============================================================

def _family_key(
    value,
):

    key = _normalize(
        value
    )

    aliases = {
        "arac":
            "arac_finansmani",

        "arac_finansmani":
            "arac_finansmani",

        "tasit":
            "arac_finansmani",

        "tasit_finansmani":
            "arac_finansmani",

        "vehicle":
            "arac_finansmani",

        "vehicle_financing":
            "arac_finansmani",
    }

    return aliases.get(
        key,
        key,
    )


def _load_products():

    # --------------------------------------------------------
    # Primary:
    # same local PostgreSQL product repository used by
    # Finance Comparison dashboard.
    # --------------------------------------------------------

    try:

        from src.postgres_repository import (
            get_standard_products,
        )

        frame = (
            get_standard_products()
        )

        if (
            isinstance(
                frame,
                pd.DataFrame,
            )
            and
            not frame.empty
        ):

            return (
                frame.copy(
                    deep=True
                ),
                "postgres_dashboard",
            )

    except Exception:

        pass


    # --------------------------------------------------------
    # Offline / demo-safe fallback:
    # validated portable finance snapshot.
    # --------------------------------------------------------

    from src.finance_runtime_repository import (
        get_standard_products,
    )

    frame = (
        get_standard_products()
    )

    if not isinstance(
        frame,
        pd.DataFrame,
    ):

        raise TypeError(
            "Finance product repository "
            "did not return DataFrame."
        )

    return (
        frame.copy(
            deep=True
        ),
        "portable_runtime_snapshot",
    )


def _amount_eligible(
    row,
    amount,
):

    if amount is None:
        return True


    minimum = _number(
        row.get(
            "minimum_financing_amount"
        )
    )

    maximum = _number(
        row.get(
            "maximum_financing_amount"
        )
    )


    if (
        minimum is not None
        and
        float(
            amount
        )
        <
        minimum
    ):
        return False


    if (
        maximum is not None
        and
        float(
            amount
        )
        >
        maximum
    ):
        return False


    return True


def _maturity_eligible(
    row,
    maturity,
):

    if maturity is None:
        return True


    minimum = _integer(
        row.get(
            "minimum_maturity_months"
        )
    )

    maximum = _integer(
        row.get(
            "maximum_maturity_months"
        )
    )


    if (
        minimum is not None
        and
        int(
            maturity
        )
        <
        minimum
    ):
        return False


    if (
        maximum is not None
        and
        int(
            maturity
        )
        >
        maximum
    ):
        return False


    return True


def _money(
    value,
):

    number = _number(
        value
    )

    if number is None:
        return None


    if float(
        number
    ).is_integer():

        raw = f"{int(number):,}"

    else:

        raw = f"{number:,.2f}"


    return (
        raw
        .replace(",", "\u0000")
        .replace(".", ",")
        .replace("\u0000", ".")
        + " TL"
    )


def _rate(
    row,
):

    numeric = _number(
        row.get(
            "profit_share_rate"
        )
    )

    if numeric is not None:

        value = (
            f"{numeric:.2f}"
            .replace(".", ",")
        )

        return (
            "%"
            + value
        )


    text = str(
        row.get(
            "profit_share_rate_text"
        )
        or ""
    ).strip()

    if text:

        return text


    return (
        "Kaynakta say\u0131sal oran "
        "yay\u0131mlanmam\u0131\u015f"
    )


def _amount_range(
    row,
):

    low = _money(
        row.get(
            "minimum_financing_amount"
        )
    )

    high = _money(
        row.get(
            "maximum_financing_amount"
        )
    )


    if (
        low
        and
        high
    ):

        return (
            low
            + " - "
            + high
        )


    if high:

        return (
            "En fazla "
            + high
        )


    if low:

        return (
            "En az "
            + low
        )


    return (
        "Kaynakta say\u0131sal limit "
        "yay\u0131mlanmam\u0131\u015f"
    )


def _maturity_text(
    row,
):

    low = _integer(
        row.get(
            "minimum_maturity_months"
        )
    )

    high = _integer(
        row.get(
            "maximum_maturity_months"
        )
    )


    if (
        low is not None
        and
        high is not None
    ):

        if low == high:

            return (
                str(
                    high
                )
                + " ay"
            )

        return (
            str(
                low
            )
            + "-"
            + str(
                high
            )
            + " ay"
        )


    if high is not None:

        return (
            "Azami "
            + str(
                high
            )
            + " ay"
        )


    if low is not None:

        return (
            "En az "
            + str(
                low
            )
            + " ay"
        )


    return (
        "Kaynakta say\u0131sal vade "
        "yay\u0131mlanmam\u0131\u015f"
    )


def query_finance_catalog(
    *,
    family: str,
    bank_names: Iterable[str] | None = None,
    amount: float | None = None,
    maturity: int | None = None,
    purpose: str | None = None,
    scope: str = "bireysel",
    limit: int = 50,
) -> FinanceCatalogQueryResult:
    """
    Query published/normalized finance product terms.

    This is a catalog comparison, not an exact repayment
    calculator.
    """

    frame, repository_source = (
        _load_products()
    )


    if frame.empty:

        return FinanceCatalogQueryResult(
            status="empty",
            text=(
                "Do\u011frulanm\u0131\u015f finansman "
                "katalo\u011fu bo\u015f."
            ),
            rows=tuple(),
            repository_source=(
                repository_source
            ),
            family=str(
                family
            ),
            scope=str(
                scope
            ),
            amount=amount,
            maturity=maturity,
            purpose=purpose,
        )


    family_key = _family_key(
        family
    )

    scope_key = _scope_key(
        scope
    )


    working = frame[
        frame[
            "product_family_key"
        ]
        .fillna("")
        .astype(str)
        .apply(
            _normalize
        )
        .eq(
            family_key
        )
    ].copy()


    if (
        "scope"
        in working.columns
    ):

        working = working[
            working[
                "scope"
            ]
            .fillna("")
            .astype(str)
            .apply(
                _scope_key
            )
            .eq(
                scope_key
            )
        ].copy()


    if purpose:

        normalized_purpose = (
            _normalize(
                purpose
            )
        )

        working[
            "_bansa_query_purpose"
        ] = working.apply(
            resolve_comparison_purpose,
            axis=1,
        )

        working = working[
            working[
                "_bansa_query_purpose"
            ]
            .fillna("")
            .astype(str)
            .apply(
                _normalize
            )
            .eq(
                normalized_purpose
            )
        ].copy()


    if bank_names is not None:

        allowed = {
            _normalize(
                value
            )
            for value in bank_names
            if str(
                value
                or ""
            ).strip()
        }


        if allowed:

            working = working[
                working[
                    "bank_name"
                ]
                .fillna("")
                .astype(str)
                .apply(
                    _normalize
                )
                .isin(
                    allowed
                )
            ].copy()


    if amount is not None:

        working = working[
            working.apply(
                lambda row:
                    _amount_eligible(
                        row,
                        amount,
                    ),
                axis=1,
            )
        ].copy()


    if maturity is not None:

        working = working[
            working.apply(
                lambda row:
                    _maturity_eligible(
                        row,
                        maturity,
                    ),
                axis=1,
            )
        ].copy()


    if working.empty:

        return FinanceCatalogQueryResult(
            status="not_found",
            text=(
                "Belirtilen ko\u015fullarla e\u015fle\u015fen "
                "do\u011frulanm\u0131\u015f finansman "
                "\u00fcr\u00fcn\u00fc bulunamad\u0131."
            ),
            rows=tuple(),
            repository_source=(
                repository_source
            ),
            family=str(
                family
            ),
            scope=str(
                scope
            ),
            amount=amount,
            maturity=maturity,
            purpose=purpose,
        )


    rows = []


    for _, row in working.iterrows():

        rate_numeric = _number(
            row.get(
                "profit_share_rate"
            )
        )


        item = {
            "product_id":
                int(
                    row.get(
                        "id"
                    )
                ),

            "bank_name":
                str(
                    row.get(
                        "bank_name"
                    )
                    or ""
                ).strip(),

            "product_name":
                str(
                    row.get(
                        "product_name"
                    )
                    or ""
                ).strip(),

            "profit_share_rate":
                rate_numeric,

            "profit_share_rate_text":
                _rate(
                    row
                ),

            "amount_range":
                _amount_range(
                    row
                ),

            "maturity":
                _maturity_text(
                    row
                ),

            "source_url":
                (
                    str(
                        row.get(
                            "source_url"
                        )
                        or ""
                    ).strip()
                    or None
                ),

            "checked_at":
                (
                    str(
                        row.get(
                            "last_checked_at"
                        )
                        or ""
                    ).strip()
                    or None
                ),
        }


        rows.append(
            item
        )


    rows.sort(
        key=lambda item: (
            (
                1
                if item[
                    "profit_share_rate"
                ]
                is None
                else 0
            ),

            (
                item[
                    "profit_share_rate"
                ]
                if item[
                    "profit_share_rate"
                ]
                is not None
                else float(
                    "inf"
                )
            ),

            _normalize(
                item[
                    "bank_name"
                ]
            ),

            _normalize(
                item[
                    "product_name"
                ]
            ),
        )
    )


    max_rows = max(
        1,
        int(
            limit
        ),
    )

    visible = rows[
        :max_rows
    ]


    lines = [
        (
            "Do\u011frulanm\u0131\u015f BANSA finansman "
            "katalo\u011funda e\u015fle\u015fen "
            + str(
                len(
                    rows
                )
            )
            + " \u00fcr\u00fcn bulundu."
        ),
        "",
    ]


    for item in visible:

        line = (
            "- **"
            + item[
                "bank_name"
            ]
            + " - "
            + item[
                "product_name"
            ]
            + "**"
            + " | K\u00e2r pay\u0131: "
            + item[
                "profit_share_rate_text"
            ]
            + " | Vade: "
            + item[
                "maturity"
            ]
            + " | Finansman tutar\u0131: "
            + item[
                "amount_range"
            ]
        )


        if item[
            "source_url"
        ]:

            line += (
                " | [Resm\u00ee kaynak]("
                + item[
                    "source_url"
                ]
                + ")"
            )


        lines.append(
            line
        )


    if (
        len(
            rows
        )
        >
        len(
            visible
        )
    ):

        lines.extend(
            (
                "",
                (
                    "Not: "
                    + str(
                        len(
                            rows
                        )
                        -
                        len(
                            visible
                        )
                    )
                    + " ek \u00fcr\u00fcn daha var."
                ),
            )
        )


    lines.extend(
        (
            "",
            (
                "Bu liste BANSA'n\u0131n do\u011frulanm\u0131\u015f "
                "\u00fcr\u00fcn/kural verisini kar\u015f\u0131la\u015ft\u0131r\u0131r. "
                "Ayl\u0131k taksit veya toplam geri \u00f6deme "
                "istenirse ayr\u0131 do\u011frulanm\u0131\u015f hesaplama "
                "motoru kullan\u0131l\u0131r."
            ),
        )
    )


    return FinanceCatalogQueryResult(
        status="found",
        text="\n".join(
            lines
        ),
        rows=tuple(
            rows
        ),
        repository_source=(
            repository_source
        ),
        family=str(
            family
        ),
        scope=str(
            scope
        ),
        amount=amount,
        maturity=maturity,
        purpose=purpose,
    )
