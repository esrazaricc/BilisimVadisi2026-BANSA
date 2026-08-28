# FINANCE_COMPARISON_PURPOSE_V2
# ASCII-SAFE SOURCE: Turkish literals use Unicode escapes.

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping


PURPOSE_GENERAL_NEEDS = "genel_ihtiyac"
PURPOSE_MOTORCYCLE = "motosiklet"
PURPOSE_HOME_OFFICE_GOODS = "ev_ofis_gerecleri"


@dataclass(frozen=True)
class PurposeRule:
    product_id: int
    bank_name: str
    product_name: str
    family_key: str
    purpose_key: str


#
# FAIL-CLOSED explicit semantic comparison map.
#
# family_key alone is NOT sufficient for comparability.
#
# Only explicitly verified products are mapped.
# Unknown or identity-drifted products return None.
#
_RULES = {

    4: PurposeRule(
        product_id=4,
        bank_name="D\u00fcnya Kat\u0131l\u0131m",
        product_name="\u0130htiya\u00e7 Finansman\u0131",
        family_key="ihtiyac_finansmani",
        purpose_key=PURPOSE_GENERAL_NEEDS,
    ),

    70: PurposeRule(
        product_id=70,
        bank_name="T\u00fcrkiye Finans",
        product_name=(
            "Dijital \u0130htiya\u00e7 Finansman\u0131 "
            "(Dijital \u0130htiya\u00e7 Kredisi)*"
        ),
        family_key="ihtiyac_finansmani",
        purpose_key=PURPOSE_GENERAL_NEEDS,
    ),

    72: PurposeRule(
        product_id=72,
        bank_name="T\u00fcrkiye Finans",
        product_name=(
            "\u0130htiya\u00e7 Finansman\u0131 "
            "(\u0130htiya\u00e7 Kredisi)*"
        ),
        family_key="ihtiyac_finansmani",
        purpose_key=PURPOSE_GENERAL_NEEDS,
    ),

    118: PurposeRule(
        product_id=118,
        bank_name="Albaraka T\u00fcrk",
        product_name=(
            "Motosiklet, ATV , Bisiklet"
        ),
        family_key="ihtiyac_finansmani",
        purpose_key=PURPOSE_MOTORCYCLE,
    ),

    121: PurposeRule(
        product_id=121,
        bank_name="Albaraka T\u00fcrk",
        product_name="\u0130htiya\u00e7 Finansman\u0131",
        family_key="ihtiyac_finansmani",
        purpose_key=PURPOSE_GENERAL_NEEDS,
    ),

    273: PurposeRule(
        product_id=273,
        bank_name=(
            "T\u00fcrkiye Emlak Kat\u0131l\u0131m"
        ),
        product_name=(
            "Ev/Ofis Gere\u00e7leri "
            "T\u00fcketici Finansman\u0131"
        ),
        family_key="ihtiyac_finansmani",
        purpose_key=PURPOSE_HOME_OFFICE_GOODS,
    ),

    318: PurposeRule(
        product_id=318,
        bank_name=(
            "Vak\u0131f Kat\u0131l\u0131m"
        ),
        product_name=(
            "\u0130htiya\u00e7 Finansman\u0131"
        ),
        family_key="ihtiyac_finansmani",
        purpose_key=PURPOSE_GENERAL_NEEDS,
    ),
}


def _normalized(value: Any) -> str:
    """
    Turkish-safe comparison normalization.

    ASCII-safe source literals are deliberately used
    because this project is frequently patched through
    Windows PowerShell.
    """

    text = str(
        value
        or ""
    )

    # Turkish dotless/dotted I normalization.
    text = (
        text
        .replace(
            "\u0131",
            "i",
        )
        .replace(
            "\u0130",
            "I",
        )
    )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(
            character
        )
    )

    text = (
        " ".join(
            text
            .casefold()
            .split()
        )
    )

    return text


def _value(
    product: Mapping[str, Any] | Any,
    key: str,
):
    """
    Supports dictionaries and pandas Series without
    relying on pandas-specific imports.
    """

    if isinstance(
        product,
        Mapping,
    ):
        return product.get(
            key
        )

    try:
        return product[
            key
        ]

    except Exception:
        return getattr(
            product,
            key,
            None,
        )


def resolve_comparison_purpose(
    product: Mapping[str, Any] | Any,
) -> str | None:
    """
    Resolve an explicitly verified semantic comparison key.

    FAIL CLOSED:
    - Unknown product -> None
    - Bank identity mismatch -> None
    - Product identity mismatch -> None
    - Family mismatch -> None

    Broad family equality alone NEVER establishes
    apples-to-apples comparability.
    """

    try:

        product_id = int(
            _value(
                product,
                "id",
            )
        )

    except Exception:

        return None


    rule = _RULES.get(
        product_id
    )


    if rule is None:

        return None


    actual_bank = _normalized(
        _value(
            product,
            "bank_name",
        )
    )

    expected_bank = _normalized(
        rule.bank_name
    )


    if actual_bank != expected_bank:

        return None


    actual_product = _normalized(
        _value(
            product,
            "product_name",
        )
    )

    expected_product = _normalized(
        rule.product_name
    )


    if actual_product != expected_product:

        return None


    actual_family = _normalized(
        _value(
            product,
            "product_family_key",
        )
    )

    expected_family = _normalized(
        rule.family_key
    )


    if actual_family != expected_family:

        return None


    return rule.purpose_key


def are_products_comparable(
    product_a,
    product_b,
) -> bool:
    """
    Two products are semantically comparable only when:

    1. both have an explicitly verified purpose;
    2. both purpose keys are identical.
    """

    purpose_a = (
        resolve_comparison_purpose(
            product_a
        )
    )

    purpose_b = (
        resolve_comparison_purpose(
            product_b
        )
    )


    return (
        purpose_a is not None
        and
        purpose_b is not None
        and
        purpose_a
        ==
        purpose_b
    )


def get_verified_purpose_rules():
    """
    Read-only diagnostic copy.
    """

    return dict(
        _RULES
    )


# ============================================================
# STRICT_SEMANTIC_COMPARISON_UNIVERSE_V1
# ============================================================

_DEFAULT_COMPARISON_UNIVERSES = {
    "konut_finansmani": {
        "key":
            "standart_konut",

        "product_names": {
            _normalized(
                "Konut Finansman\u0131"
            ),

            _normalized(
                "Konut Finansman\u0131 "
                "(Konut Kredisi)*"
            ),
        },
    },

    "arac_finansmani": {
        "key":
            "standart_arac",

        "product_names": {
            _normalized(
                "Ara\u00e7 Finansman\u0131"
            ),

            _normalized(
                "Ta\u015f\u0131t Finansman\u0131"
            ),

            _normalized(
                "Ta\u015f\u0131t Finansman\u0131 "
                "(Ta\u015f\u0131t Kredisi)*"
            ),
        },
    },

    "arsa_finansmani": {
        "key":
            "standart_arsa",

        "product_names": {
            _normalized(
                "Arsa Finansman\u0131"
            ),

            _normalized(
                "Arsa Finansman\u0131 "
                "(Arsa Kredisi)*"
            ),

            _normalized(
                "Bireysel Arsa Finansman\u0131"
            ),
        },
    },

    "isyeri_finansmani": {
        "key":
            "standart_isyeri",

        "product_names": {
            _normalized(
                "\u0130\u015f Yeri Finansman\u0131"
            ),

            _normalized(
                "\u0130\u015f yeri Finansman\u0131 "
                "(\u0130\u015f yeri Kredisi)*"
            ),

            _normalized(
                "Bireysel \u0130\u015f Yeri Finansman\u0131"
            ),
        },
    },
}


def default_comparison_universe_key(
    family_key,
):
    """
    Generic finance comparison universe.

    None means that the family has no automatic
    semantic universe and existing behavior must remain.
    """

    family = _normalized(
        family_key
    )


    rule = (
        _DEFAULT_COMPARISON_UNIVERSES
        .get(
            family
        )
    )


    if rule is None:

        return None


    return str(
        rule[
            "key"
        ]
    )


def resolve_default_comparison_universe(
    product,
):
    """
    Fail-closed semantic classification.

    A product belongs to the generic comparison universe only
    when both its canonical family and exact normalized product
    identity match the approved generic product-name set.

    Special products are intentionally excluded.
    """

    family = _normalized(
        _value(
            product,
            "product_family_key",
        )
    )


    rule = (
        _DEFAULT_COMPARISON_UNIVERSES
        .get(
            family
        )
    )


    if rule is None:

        return None


    product_name = _normalized(
        _value(
            product,
            "product_name",
        )
    )


    if (
        product_name
        not in rule[
            "product_names"
        ]
    ):

        return None


    return str(
        rule[
            "key"
        ]
    )


def get_default_comparison_universes():
    """
    Diagnostic copy.
    """

    return {
        family: {
            "key":
                rule[
                    "key"
                ],

            "product_names":
                tuple(
                    sorted(
                        rule[
                            "product_names"
                        ]
                    )
                ),
        }

        for family, rule
        in _DEFAULT_COMPARISON_UNIVERSES.items()
    }

