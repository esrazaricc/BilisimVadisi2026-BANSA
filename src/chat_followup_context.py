from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class FollowupResolution:

    original_question: str

    resolved_question: str

    used_context: bool

    inherited_bank: str | None = None

    inherited_product: str | None = None


_BANKS = (
    (
        "T\u00fcrkiye Emlak Kat\u0131l\u0131m",
        (
            "turkiye emlak katilim",
            "emlak katilim",
        ),
    ),
    (
        "Albaraka T\u00fcrk",
        (
            "albaraka turk",
            "albaraka",
        ),
    ),
    (
        "Kuveyt T\u00fcrk",
        (
            "kuveyt turk",
        ),
    ),
    (
        "T\u00fcrkiye Finans",
        (
            "turkiye finans",
        ),
    ),
    (
        "Vak\u0131f Kat\u0131l\u0131m",
        (
            "vakif katilim",
        ),
    ),
    (
        "Ziraat Kat\u0131l\u0131m",
        (
            "ziraat katilim",
        ),
    ),
    (
        "D\u00fcnya Kat\u0131l\u0131m",
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
        "TOM Bank",
        (
            "tom bank",
            "tom katilim",
        ),
    ),
)


_PRODUCTS = (
    (
        "konut finansman\u0131",
        (
            "konut finansmani",
            "konut",
            "ev finansmani",
        ),
    ),
    (
        "e\u011fitim finansman\u0131",
        (
            "egitim finansmani",
            "egitim",
        ),
    ),
    (
        "ihtiya\u00e7 finansman\u0131",
        (
            "ihtiyac finansmani",
            "ihtiyac",
        ),
    ),
    (
        "ta\u015f\u0131t finansman\u0131",
        (
            "tasit finansmani",
            "arac finansmani",
            "tasit",
            "arac",
        ),
    ),
    (
        "i\u015f yeri finansman\u0131",
        (
            "is yeri finansmani",
            "isyeri finansmani",
            "is yeri",
        ),
    ),
    (
        "motosiklet finansman\u0131",
        (
            "motosiklet finansmani",
            "motosiklet",
        ),
    ),
    (
        "arsa finansman\u0131",
        (
            "arsa finansmani",
            "arsa",
        ),
    ),
    (
        "hac ve umre finansman\u0131",
        (
            "hac ve umre finansmani",
            "umre finansmani",
            "hac finansmani",
            "umre",
        ),
    ),
)


_FOLLOWUP_HINTS = (
    'peki',
    'bunun',
    'bunda',
    'buna',
    'onun',
    'onda',
    'o zaman',
    'ya bunun',
    'ya peki',
    'vadesi',
    'orani',
    'masrafi',
    'ucreti',
    'avantaji',
    'avantajlari',
    'limiti',
    'ne kadar',
    'kac aya kadar',
    'kac ay',
    'kac ay vade',
    'vade',
    'azami vade',
    'maksimum vade',
    'tahsis ucreti',
    'tahsis',
    'ekspertiz ucreti',
    'ekspertiz',
    'masraf',
    'ucret',
    'oran kac',
    'ipotek ucreti',
    'rehin ucreti',
    'hangi masraflar',
    'masraflar neler',
    'ucretleri neler',
    'kar payi',
    'kar payi orani',
    'finansman orani',
    'limit ne kadar',
    'finansman limiti',
    'en fazla ne kadar',
)


def _normalize(
    value: str,
) -> str:

    text = str(
        value
        or ""
    )

    text = text.translate(
        str.maketrans(
            {
                "\u0131": "i",
                "\u0130": "I",
                "\u015f": "s",
                "\u015e": "S",
                "\u011f": "g",
                "\u011e": "G",
                "\u00fc": "u",
                "\u00dc": "U",
                "\u00f6": "o",
                "\u00d6": "O",
                "\u00e7": "c",
                "\u00c7": "C",
            }
        )
    )

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        char
        for char in text
        if not unicodedata.combining(
            char
        )
    )

    text = text.casefold()

    text = re.sub(
        r"[^a-z0-9%.,:+-]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _normalize_bank_identity(
    value: str,
) -> str:
    """
    Bank-only canonical identity normalization.

    Preserves the ordinary entity/product
    normalization contract while generically
    collapsing dotted or spaced initialisms.
    """

    text = _normalize(
        value
    )

    if not text:
        return ""

    tokens = text.split()

    normalized_tokens = []

    index = 0

    while index < len(tokens):

        token = tokens[
            index
        ]

        # Same-token dotted initialism:
        # t.o.m. -> tom
        if "." in token:

            pieces = [
                part
                for part
                in token.split(".")
                if part
            ]

            if (
                len(pieces) >= 2
                and
                all(
                    len(part) == 1
                    and
                    part.isalpha()
                    for part in pieces
                )
            ):

                normalized_tokens.append(
                    "".join(
                        pieces
                    )
                )

                index += 1
                continue

        # Space-separated initialism:
        # t. o. m. -> tom
        cleaned = (
            token[:-1]
            if token.endswith(".")
            else token
        )

        if (
            len(cleaned) == 1
            and
            cleaned.isalpha()
        ):

            letters = []
            cursor = index

            while cursor < len(tokens):

                candidate = tokens[
                    cursor
                ]

                candidate_clean = (
                    candidate[:-1]
                    if candidate.endswith(".")
                    else candidate
                )

                if not (
                    len(candidate_clean) == 1
                    and
                    candidate_clean.isalpha()
                ):
                    break

                letters.append(
                    candidate_clean
                )

                cursor += 1

            if len(letters) >= 2:

                normalized_tokens.append(
                    "".join(
                        letters
                    )
                )

                index = cursor
                continue

        normalized_tokens.append(
            token
        )

        index += 1

    return " ".join(
        normalized_tokens
    )



def _find_entity(
    question: str,
    definitions,
) -> str | None:

    normalized = _normalize(
        question
    )

    for canonical, aliases in definitions:

        for alias in aliases:

            alias_norm = _normalize(
                alias
            )

            if re.search(
                (
                    r"(?<![a-z0-9])"
                    + re.escape(
                        alias_norm
                    )
                    + r"(?![a-z0-9])"
                ),
                normalized,
            ):

                return canonical

    return None


def _find_bank(
    question: str,
) -> str | None:

    normalized = (
        _normalize_bank_identity(
            question
        )
    )

    for canonical, aliases in _BANKS:

        for alias in aliases:

            alias_norm = (
                _normalize_bank_identity(
                    alias
                )
            )

            if re.search(
                (
                    r"(?<![a-z0-9])"
                    + re.escape(
                        alias_norm
                    )
                    + r"(?![a-z0-9])"
                ),
                normalized,
            ):

                return canonical

    return None


def _find_product(
    question: str,
) -> str | None:

    return _find_entity(
        question,
        _PRODUCTS,
    )


def _looks_like_followup(
    question: str,
) -> bool:

    normalized = _normalize(
        question
    )

    if not normalized:

        return False

    if len(
        normalized
    ) > 140:

        return False

    return any(
        hint in normalized
        for hint in _FOLLOWUP_HINTS
    )




def _starts_with_context_continuation(
    question: str,
) -> bool:

    normalized = _normalize(
        question
    )

    if not normalized:
        return False

    prefixes = (
        "peki",
        "ya peki",
        "ya bunun",
        "bunun",
        "bunda",
        "buna",
        "onun",
        "onda",
        "o zaman",
    )

    return any(
        (
            normalized
            == prefix
            or
            normalized.startswith(
                prefix + " "
            )
        )
        for prefix in prefixes
    )


def _is_explicit_new_topic_boundary(
    question: str,
    *,
    current_bank: str | None,
    current_product: str | None,
) -> bool:
    """
    An independently specified bank + broad
    product/campaign-information request starts
    a new context boundary.

    Genuine continuations such as "Peki ..."
    remain eligible for context inheritance.
    """

    if not current_bank:
        return False

    if current_product:
        return False

    if _starts_with_context_continuation(
        question
    ):
        return False

    normalized = _normalize(
        question
    )

    topic_signals = (
        "avantajlari",
        "ozellikleri",
        "ne sunuyor",
        "neler sunuyor",
        "ne sunar",
        "neler sunar",
        "kampanya",
        "kampanyasi",
        "firsat",
        "firsati",
    )

    return any(
        signal in normalized
        for signal in topic_signals
    )




def _has_finance_amount_signal(
    question: str,
) -> bool:

    normalized = _normalize(
        question
    )

    if not normalized:
        return False

    return bool(
        re.search(
            (
                r"(?<![a-z0-9])"
                r"\d[\d.,]*"
                r"\s*"
                r"(?:tl|try)"
                r"(?![a-z0-9])"
            ),
            normalized,
        )
        or
        re.search(
            (
                r"(?<![a-z0-9])"
                r"\d+(?:[.,]\d+)?"
                r"\s*"
                r"(?:bin|milyon)"
                r"(?:\s*tl)?"
                r"(?![a-z0-9])"
            ),
            normalized,
        )
    )


def _has_finance_maturity_signal(
    question: str,
) -> bool:

    normalized = _normalize(
        question
    )

    if not normalized:
        return False

    return bool(
        re.search(
            (
                r"(?<![a-z0-9])"
                r"\d{1,3}"
                r"\s*"
                r"(?:ay|aylik)"
                r"(?![a-z0-9])"
            ),
            normalized,
        )
    )


def _looks_like_finance_compare_request(
    question: str,
) -> bool:

    normalized = _normalize(
        question
    )

    if not normalized:
        return False

    compare_signals = (
        "karsilastir",
        "karsilastirma",
        "hangisi daha avantajli",
        "hangi banka daha avantajli",
        "hangi banka daha uygun",
        "hangisi daha uygun",
        "en avantajli",
        "en uygun",
        "daha mantikli",
    )

    if not any(
        signal in normalized
        for signal in compare_signals
    ):
        return False

    # A finance comparison must still carry a
    # recognisable finance product/family signal.
    return (
        _find_product(
            question
        )
        is not None
    )


def _looks_like_numeric_compare_completion(
    question: str,
) -> bool:
    """
    True only for a short follow-up that mainly
    supplies missing finance amount/maturity.
    """

    if _find_bank(
        question
    ):
        return False

    if _find_product(
        question
    ):
        return False

    normalized = _normalize(
        question
    )

    if not normalized:
        return False

    if len(normalized) > 90:
        return False

    has_amount = (
        _has_finance_amount_signal(
            question
        )
    )

    has_maturity = (
        _has_finance_maturity_signal(
            question
        )
    )

    if not (
        has_amount
        or
        has_maturity
    ):
        return False

    # Avoid treating a new broad question as
    # merely numeric completion.
    blockers = (
        "avantajlari",
        "ozellikleri",
        "kampanya",
        "hangi banka",
        "hangisi",
        "karsilastir",
    )

    return not any(
        blocker in normalized
        for blocker in blockers
    )


def _find_pending_finance_compare(
    question: str,
    previous_user_messages: list[str],
) -> str | None:
    """
    Find the latest comparison request whose
    missing numeric field(s) are supplied by
    the current short message.

    Existing numeric values are never silently
    overwritten.
    """

    if not _looks_like_numeric_compare_completion(
        question
    ):
        return None

    current_has_amount = (
        _has_finance_amount_signal(
            question
        )
    )

    current_has_maturity = (
        _has_finance_maturity_signal(
            question
        )
    )


    for previous in reversed(
        previous_user_messages
    ):

        if not _looks_like_finance_compare_request(
            previous
        ):
            continue

        previous_has_amount = (
            _has_finance_amount_signal(
                previous
            )
        )

        previous_has_maturity = (
            _has_finance_maturity_signal(
                previous
            )
        )


        supplies_missing_amount = (
            current_has_amount
            and
            not previous_has_amount
        )

        supplies_missing_maturity = (
            current_has_maturity
            and
            not previous_has_maturity
        )


        # Do not append a second competing amount
        # or maturity to the previous request.
        conflicts = (
            (
                current_has_amount
                and
                previous_has_amount
            )
            or
            (
                current_has_maturity
                and
                previous_has_maturity
            )
        )


        if conflicts:
            continue


        if (
            supplies_missing_amount
            or
            supplies_missing_maturity
        ):

            return str(
                previous
                or ""
            ).strip()


    return None

def resolve_followup_question(
    question: str,
    previous_user_messages: list[str],
) -> FollowupResolution:

    original = str(
        question
        or ""
    ).strip()

    if not original:

        return FollowupResolution(
            original_question=original,
            resolved_question=original,
            used_context=False,
        )

    current_bank = _find_bank(
        original
    )

    current_product = _find_product(
        original
    )


    # Explicitly named bank + independent
    # campaign/broad-info request starts a
    # new topic and must not inherit the
    # previous finance product.
    if _is_explicit_new_topic_boundary(
        original,
        current_bank=current_bank,
        current_product=current_product,
    ):

        return FollowupResolution(
            original_question=original,
            resolved_question=original,
            used_context=False,
        )

    # A fully explicit question never inherits
    # context from an earlier turn.

    if (
        current_bank
        and
        current_product
    ):

        return FollowupResolution(
            original_question=original,
            resolved_question=original,
            used_context=False,
        )

    pending_compare = (
        _find_pending_finance_compare(
            original,
            previous_user_messages,
        )
    )

    if pending_compare:

        resolved = (
            pending_compare
            + " - "
            + original
        )

        return FollowupResolution(
            original_question=original,
            resolved_question=resolved,
            used_context=True,
        )

    if not _looks_like_followup(
        original
    ):

        return FollowupResolution(
            original_question=original,
            resolved_question=original,
            used_context=False,
        )

    previous_bank = None
    previous_product = None

    for previous in reversed(
        previous_user_messages
    ):

        if previous_bank is None:

            previous_bank = _find_bank(
                previous
            )

        if previous_product is None:

            previous_product = _find_product(
                previous
            )

        if (
            previous_bank
            and
            previous_product
        ):
            break

    inherited_bank = None
    inherited_product = None

    prefixes = []

    # Current question names a new product:
    # inherit only the bank.

    if (
        current_product
        and
        not current_bank
        and
        previous_bank
    ):

        prefixes.append(
            previous_bank
        )

        inherited_bank = (
            previous_bank
        )

    # Current question names a new bank:
    # inherit only the product.

    elif (
        current_bank
        and
        not current_product
        and
        previous_product
    ):

        prefixes.append(
            previous_product
        )

        inherited_product = (
            previous_product
        )

    # Fully implicit follow-up:
    # inherit both only when both are known.

    elif (
        not current_bank
        and
        not current_product
        and
        previous_bank
        and
        previous_product
    ):

        prefixes.extend(
            (
                previous_bank,
                previous_product,
            )
        )

        inherited_bank = (
            previous_bank
        )

        inherited_product = (
            previous_product
        )

    if not prefixes:

        return FollowupResolution(
            original_question=original,
            resolved_question=original,
            used_context=False,
        )

    resolved = (
        " ".join(
            prefixes
        )
        + " - "
        + original
    )

    return FollowupResolution(
        original_question=original,
        resolved_question=resolved,
        used_context=True,
        inherited_bank=(
            inherited_bank
        ),
        inherited_product=(
            inherited_product
        ),
    )

# ============================================================
# CAMPAIGN_COMPARE_FOLLOWUP_CONTEXT_V1
# ============================================================

_resolve_followup_question_before_campaign_context_v1 = (
    resolve_followup_question
)


_CAMPAIGN_COMPARE_CONTEXT_TOPICS_V1 = (
    "kampanya",
    "market",
    "supermarket",
    "alisveris",
    "indirim",
    "nakit iade",
    "iade",
    "puan",
    "odul",
    "cashback",
    "parafpara",
    "worldpuan",

    "egitim",
    "okul",
    "kirtasiye",
    "universite",
    "kolej",
    "kurs",
    "taksit",
    "vade farksiz",

    "akaryakit",
    "benzin",
    "motorin",

    "seyahat",
    "tatil",
    "otel",

    "restoran",
    "restaurant",
    "yemek",

    "e ticaret",
    "eticaret",

    "yeni musteri",
    "musteri ol",
)


_CAMPAIGN_EXPLICIT_TOPIC_CHANGE_V1 = (
    "market",
    "supermarket",

    "egitim",
    "okul",
    "kirtasiye",
    "universite",
    "kolej",
    "kurs",

    "akaryakit",
    "benzin",
    "motorin",

    "seyahat",
    "tatil",
    "otel",

    "restoran",
    "restaurant",
    "yemek",

    "e ticaret",
    "eticaret",

    "yeni musteri",
)


_FINANCE_TOPIC_SIGNALS_V1 = (
    "finansman",
    "kar payi",
    "aylik taksit",
    "geri odeme",
    "toplam geri",
    "tahsis",
    "ekspertiz",
    "ipotek",

    "konut finans",
    "arac finans",
    "tasit finans",
    "arsa finans",
    "is yeri finans",
    "isyeri finans",
    "ihtiyac finans",
)


def _looks_like_campaign_compare_context_v1(
    question: str,
) -> bool:

    normalized = _normalize(
        question
    )

    if not normalized:

        return False

    has_compare_intent = (
        "karsilastir" in normalized

        or
        "en avantajli" in normalized

        or (
            "hangi banka" in normalized
            and any(
                value in normalized
                for value in (
                    "avantajli",
                    "uygun",
                    "iyi",
                )
            )
        )

        or (
            "hangisi" in normalized
            and any(
                value in normalized
                for value in (
                    "avantajli",
                    "uygun",
                    "iyi",
                )
            )
        )
    )

    if not has_compare_intent:

        return False

    return any(
        signal in normalized
        for signal
        in _CAMPAIGN_COMPARE_CONTEXT_TOPICS_V1
    )


def _find_previous_campaign_compare_context_v1(
    previous_user_messages: list[str],
) -> str | None:

    for previous in reversed(
        previous_user_messages
    ):

        previous = str(
            previous
            or ""
        ).strip()

        if (
            previous
            and
            _looks_like_campaign_compare_context_v1(
                previous
            )
        ):

            return previous

    return None


def _campaign_followup_can_inherit_v1(
    question: str,
) -> bool:

    normalized = _normalize(
        question
    )

    if not normalized:

        return False

    if not _looks_like_followup(
        question
    ):

        return False

    # A finance question is a genuine topic switch.
    if any(
        signal in normalized
        for signal
        in _FINANCE_TOPIC_SIGNALS_V1
    ):

        return False

    # A follow-up that explicitly introduces another
    # campaign topic must stand on its own.
    #
    # Scope modifiers such as "ticari", "bireysel",
    # bank-only narrowing and "sadece" do not appear
    # in this list and therefore inherit the campaign
    # comparison context.
    if any(
        signal in normalized
        for signal
        in _CAMPAIGN_EXPLICIT_TOPIC_CHANGE_V1
    ):

        return False

    return True


def _resolve_campaign_compare_followup_v1(
    original: str,
    previous_user_messages: list[str],
) -> FollowupResolution | None:

    if not _campaign_followup_can_inherit_v1(
        original
    ):

        return None

    previous_campaign = (
        _find_previous_campaign_compare_context_v1(
            previous_user_messages
        )
    )

    if previous_campaign is None:

        return None

    resolved = (
        previous_campaign
        + " - "
        + original
    )

    return FollowupResolution(
        original_question=original,
        resolved_question=resolved,
        used_context=True,
        inherited_bank=None,
        inherited_product=None,
    )


def resolve_followup_question(
    question: str,
    previous_user_messages: list[str],
) -> FollowupResolution:

    original = str(
        question
        or ""
    ).strip()

    if original:

        campaign_resolution = (
            _resolve_campaign_compare_followup_v1(
                original,
                previous_user_messages,
            )
        )

        if campaign_resolution is not None:

            return campaign_resolution

    # Every existing finance/product/new-topic rule
    # remains under the historical resolver.
    return (
        _resolve_followup_question_before_campaign_context_v1(
            question,
            previous_user_messages,
        )
    )


# ============================================================
# BANSA_CONTEXT_ISOLATION_FINANCE_FOLLOWUP_V5_1
#
# Narrow pre/post resolver guard:
#
# 1. Explicit bank/entity in a new question prevents stale
#    bank/product inheritance.
#
# 2. Housing variant questions may inherit only amount and
#    maturity from the latest successful finance comparison.
#
# 3. Numeric followups such as:
#       "Peki 200.000 TL, 36 ay olursa?"
#    reuse the latest finance comparison, not campaign context.
#
# 4. Existing resolver remains the default for every other
#    question.
#
# No finance values are calculated here.
# ============================================================

from dataclasses import (
    replace as _v51_replace,
)

import re as _v51_re
import unicodedata as _v51_unicodedata


_resolve_followup_question_before_v51 = (
    resolve_followup_question
)


_V51_BANKS = (
    "Adil Kat\u0131l\u0131m",
    "Albaraka T\u00fcrk",
    "D\u00fcnya Kat\u0131l\u0131m",
    "Hayat Finans",
    "Kuveyt T\u00fcrk",
    "T.O.M. Kat\u0131l\u0131m",
    "T\u00fcrkiye Emlak Kat\u0131l\u0131m",
    "T\u00fcrkiye Finans",
    "Vak\u0131f Kat\u0131l\u0131m",
    "Ziraat Kat\u0131l\u0131m",
)


def _v51_norm(
    value,
):

    text = str(
        value
        or ""
    ).casefold()

    text = (
        text
        .replace("\u0131", "i")
        .replace("\u015f", "s")
        .replace("\u011f", "g")
        .replace("\u00e7", "c")
        .replace("\u00f6", "o")
        .replace("\u00fc", "u")
    )

    text = (
        _v51_unicodedata
        .normalize(
            "NFKD",
            text,
        )
    )

    text = "".join(
        char
        for char in text
        if not (
            _v51_unicodedata
            .combining(
                char
            )
        )
    )

    return " ".join(
        text.split()
    )


_V51_BANK_NORMS = {
    _v51_norm(bank):
        bank

    for bank in _V51_BANKS
}


# V52_SHORT_BANK_ALIAS
_V51_BANK_NORMS["albaraka"] = "Albaraka T\u00fcrk"


def _v51_detect_banks(
    text,
):

    normalized = (
        _v51_norm(
            text
        )
    )

    found = []

    for key, canonical in (
        _V51_BANK_NORMS.items()
    ):

        if key in normalized:

            if canonical not in found:
                found.append(
                    canonical
                )

    return tuple(
        found
    )

def _v51_history_strings(
    history,
):

    output = []


    def visit(
        value,
    ):

        if value is None:
            return

        if isinstance(
            value,
            str,
        ):

            if value.strip():

                output.append(
                    value.strip()
                )

            return


        if isinstance(
            value,
            dict,
        ):

            preferred = (
                "question",
                "content",
                "text",
                "user",
            )

            used = False

            for key in preferred:

                if key in value:

                    visit(
                        value[
                            key
                        ]
                    )

                    used = True


            if not used:

                for item in (
                    value.values()
                ):

                    visit(
                        item
                    )

            return


        if isinstance(
            value,
            (
                list,
                tuple,
            ),
        ):

            for item in value:

                visit(
                    item
                )

            return


    visit(
        history
    )

    return tuple(
        output
    )


def _v51_parse_number(
    raw,
):

    text = str(
        raw
        or ""
    ).strip()

    if not text:
        return None


    text = (
        text
        .replace(" ", "")
    )


    # Turkish thousands + decimal convention.
    if (
        "."
        in text
        and
        ","
        in text
    ):

        text = (
            text
            .replace(".", "")
            .replace(",", ".")
        )

    elif "." in text:

        pieces = (
            text.split(".")
        )

        if (
            len(
                pieces[-1]
            )
            ==
            3
        ):

            text = "".join(
                pieces
            )

    elif "," in text:

        text = (
            text.replace(
                ",",
                ".",
            )
        )


    try:

        return float(
            text
        )

    except Exception:

        return None


def _v51_extract_amount(
    text,
):

    normalized = (
        _v51_norm(
            text
        )
    )

    scaled_match = (
        _v51_re.search(
            (
                r"(?<!\d)"
                r"(\d+(?:[.,]\d+)?)"
                r"\s*(bin|k|milyon)"
                r"\s*(?:tl|try|lira)?\b"
            ),
            normalized,
            flags=(
                _v51_re.IGNORECASE
            ),
        )
    )

    if scaled_match:

        number = (
            _v51_parse_number(
                scaled_match.group(
                    1
                )
            )
        )

        scale = (
            scaled_match.group(
                2
            ).casefold()
        )

        multiplier = (
            1_000_000
            if scale == "milyon"
            else 1_000
        )

        return float(
            number * multiplier
        )


    pattern = (
        r"(?<!\d)"
        r"(\d{1,3}(?:\.\d{3})+"
        r"|\d{1,3}(?:,\d{3})+"
        r"|\d+(?:[.,]\d+)?)"
        r"\s*(?:tl|try|lira)\b"
    )

    match = (
        _v51_re.search(
            pattern,
            normalized,
            flags=(
                _v51_re.IGNORECASE
            ),
        )
    )

    if not match:

        return None


    return (
        _v51_parse_number(
            match.group(
                1
            )
        )
    )


def _v51_extract_maturity(
    text,
):

    normalized = (
        _v51_norm(
            text
        )
    )

    match = (
        _v51_re.search(
            r"(?<!\d)(\d{1,3})\s*ay\b",
            normalized,
            flags=(
                _v51_re.IGNORECASE
            ),
        )
    )

    if not match:
        return None


    try:

        return int(
            match.group(
                1
            )
        )

    except Exception:

        return None


def _v51_product_family(
    text,
):

    normalized = (
        _v51_norm(
            text
        )
    )


    if "konut" in normalized:
        return "konut"


    if (
        "motosiklet"
        in normalized
    ):
        return "motosiklet"


    if (
        "tasit"
        in normalized
        or
        "arac"
        in normalized
    ):
        return "arac"


    if (
        "ihtiyac"
        in normalized
    ):
        return "ihtiyac"


    if (
        "ticari"
        in normalized
    ):
        return "ticari"


    if (
        "arsa"
        in normalized
    ):
        return "arsa"


    if (
        "is yeri"
        in normalized
        or
        "isyeri"
        in normalized
    ):
        return "is_yeri"


    return None


def _v51_is_campaign_text(
    text,
):

    normalized = (
        _v51_norm(
            text
        )
    )

    return any(
        token in normalized

        for token in (
            "kampanya",
            "market",
            "gida",
            "indirim",
            "cashback",
            "nakit iade",
            "mil",
        )
    )


def _v51_is_finance_compare_text(
    text,
):

    normalized = (
        _v51_norm(
            text
        )
    )

    family = (
        _v51_product_family(
            normalized
        )
    )

    banks = (
        _v51_detect_banks(
            normalized
        )
    )

    explicit_compare_signal = (
        "karsilastir"
        in normalized
        or
        "karsilastirma"
        in normalized
    )

    natural_compare_signal = (
        len(banks) >= 2
        and any(
            term in normalized
            for term in (
                "daha avantajli",
                "daha uygun",
                "daha iyi",
                "daha mantikli",
            )
        )
    )

    compare_signal = (
        explicit_compare_signal
        or
        natural_compare_signal
    )


    if not family:
        return False


    if (
        _v51_is_campaign_text(
            normalized
        )
    ):
        return False


    return bool(
        compare_signal
    )


def _v51_find_latest_finance_context(
    history,
):

    texts = (
        _v51_history_strings(
            history
        )
    )


    for text in reversed(
        texts
    ):

        if not (
            _v51_is_finance_compare_text(
                text
            )
        ):
            continue


        family = (
            _v51_product_family(
                text
            )
        )

        banks = (
            _v51_detect_banks(
                text
            )
        )

        amount = (
            _v51_extract_amount(
                text
            )
        )

        maturity = (
            _v51_extract_maturity(
                text
            )
        )


        return {
            "text":
                text,

            "family":
                family,

            "banks":
                banks,

            "amount":
                amount,

            "maturity":
                maturity,
        }


    return None


def _v51_family_phrase(
    family,
):

    mapping = {
        "konut":
            "konut finansman\u0131",

        "motosiklet":
            "motosiklet finansman\u0131",

        "arac":
            "ara\u00e7 finansman\u0131",

        "ihtiyac":
            "ihtiya\u00e7 finansman\u0131",

        "ticari":
            "ticari finansman",

        "arsa":
            "arsa finansman\u0131",

        "is_yeri":
            "i\u015f yeri finansman\u0131",
    }

    return mapping.get(
        family,
        "finansman",
    )


def _v51_amount_text(
    value,
):

    if value is None:
        return None


    if float(
        value
    ).is_integer():

        number = str(
            int(
                value
            )
        )

    else:

        number = (
            f"{float(value):.2f}"
        )


    return (
        number
        + " TL"
    )


def _v51_bank_phrase(
    banks,
):

    values = tuple(
        banks
        or ()
    )


    if not values:
        return ""


    if len(
        values
    ) == 1:

        return values[0]


    if len(
        values
    ) == 2:

        return (
            values[0]
            + " ile "
            + values[1]
        )


    return (
        ", ".join(
            values[:-1]
        )
        + " ve "
        + values[-1]
    )


def _v51_variant_question(
    question,
):

    normalized = (
        _v51_norm(
            question
        )
    )


    has_new = (
        "yeni konut"
        in normalized
        or
        "sifir konut"
        in normalized
    )


    has_second = (
        "ikinci el"
        in normalized
        or
        "2 el"
        in normalized
        or
        "2. el"
        in normalized
    )


    comparison = any(
        token in normalized

        for token in (
            "fark",
            "karsilastir",
            "ayni mi",
            "degisiyor mu",
        )
    )


    return bool(
        has_new
        and
        has_second
        and
        comparison
    )


def _v51_numeric_followup(
    question,
):

    normalized = (
        _v51_norm(
            question
        )
    )


    if (
        _v51_is_campaign_text(
            normalized
        )
    ):

        return False


    amount = (
        _v51_extract_amount(
            question
        )
    )

    maturity = (
        _v51_extract_maturity(
            question
        )
    )


    if (
        amount is None
        and
        maturity is None
    ):

        return False


    follow_signal = any(
        token in normalized

        for token in (
            "peki",
            "olursa",
            "olsun",
            "bu kez",
            "bunu",
            "ya ",
        )
    )


    # A short parameter-only turn is also accepted.
    short_parameter_turn = (
        len(
            normalized.split()
        )
        <=
        8
    )


    return bool(
        follow_signal
        or
        short_parameter_turn
    )


def _v51_explicit_bank_like(
    question,
):

    normalized = (
        _v51_norm(
            question
        )
    )

    detected = (
        _v51_detect_banks(
            question
        )
    )


    if detected:
        return True


    # Unknown bank-like names must also block stale
    # inheritance rather than reusing the previous bank.
    if (
        "katilim"
        in normalized
        and
        any(
            token in normalized

            for token in (
                "finansman",
                "kar payi",
                "vade",
                "oran",
                "kredi",
            )
        )
    ):

        return True


    return False


def resolve_followup_question(
    question,
    history,
):

    original = str(
        question
        or ""
    )


    # ========================================================
    # CAMPAIGN_COMPARE_SLOT_FOLLOWUP_V1
    #
    # Preserve only the previous campaign-comparison banks.
    # The current message owns the new topic.
    #
    # Example:
    # previous -> Kuveyt + Turkiye Finans campaigns
    # current  -> housing campaigns compare
    # resolved -> Kuveyt + Turkiye Finans housing campaigns
    #
    # Old campaign topic is intentionally NOT copied.
    # ========================================================

    normalized_original = _normalize(
        original
    )

    current_campaign_banks = (
        _v51_detect_banks(
            original
        )
    )

    has_campaign_reference = (
        "kampanya"
        in normalized_original
    )

    has_campaign_compare_intent = (
        "karsilastir"
        in normalized_original
        or
        "hangisi"
        in normalized_original
        or
        "daha avantajli"
        in normalized_original
        or
        "daha uygun"
        in normalized_original
        or
        "daha iyi"
        in normalized_original
    )

    has_campaign_followup_discourse = (
        normalized_original.startswith(
            (
                "peki",
                "ya ",
                "sadece ",
                "yalniz ",
                "yalnizca ",
            )
        )
    )

    if (
        has_campaign_reference
        and
        not current_campaign_banks
        and (
            has_campaign_compare_intent
            or
            has_campaign_followup_discourse
        )
    ):

        # Search backward for the latest campaign-comparison
        # turn that actually contains bank slots.
        #
        # Topic-only followups such as:
        #   "market kampanyalarini karsilastir"
        # must not shadow the earlier bank context.
        previous_campaign = None
        previous_banks = ()

        for previous in reversed(
            history
        ):

            previous_text = str(
                previous
                or ""
            ).strip()

            if not previous_text:
                continue

            if not _looks_like_campaign_compare_context_v1(
                previous_text
            ):
                continue

            candidate_banks = (
                _v51_detect_banks(
                    previous_text
                )
            )

            if not candidate_banks:
                continue

            previous_campaign = (
                previous_text
            )

            previous_banks = (
                candidate_banks
            )

            break

        if previous_banks:

                bank_phrase = (
                    _v51_bank_phrase(
                        previous_banks
                    )
                )

                if bank_phrase:

                    resolved = (
                        bank_phrase
                        + " "
                        + original.strip()
                    )

                    if not has_campaign_compare_intent:

                        resolved = (
                            resolved.rstrip(
                                " ?.!"
                            )
                            + " karsilastir."
                        )

                    base = (
                        _resolve_followup_question_before_v51(
                            original,
                            history,
                        )
                    )

                    return _v51_replace(
                        base,

                        resolved_question=(
                            resolved
                        ),

                        used_context=True,

                        inherited_bank=(
                            bank_phrase
                        ),

                        inherited_product=None,
                    )


    # --------------------------------------------------------
    # 1. Housing new/second-hand followup.
    #
    # Explicit current bank wins.
    # Only amount/maturity are inherited from finance history.
    # --------------------------------------------------------

    if (
        _v51_variant_question(
            original
        )
    ):

        finance_context = (
            _v51_find_latest_finance_context(
                history
            )
        )


        if (
            finance_context
            and
            finance_context.get(
                "family"
            )
            ==
            "konut"
        ):

            current_banks = (
                _v51_detect_banks(
                    original
                )
            )

            banks = (
                current_banks
                or
                finance_context.get(
                    "banks"
                )
                or
                ()
            )


            # Variant question with an explicit bank must not
            # inherit another bank from the old comparison.
            if current_banks:
                banks = current_banks


            amount = (
                _v51_extract_amount(
                    original
                )
            )

            if amount is None:

                amount = (
                    finance_context.get(
                        "amount"
                    )
                )


            maturity = (
                _v51_extract_maturity(
                    original
                )
            )

            if maturity is None:

                maturity = (
                    finance_context.get(
                        "maturity"
                    )
                )


            parts = []


            bank_phrase = (
                _v51_bank_phrase(
                    banks
                )
            )


            if bank_phrase:

                parts.append(
                    bank_phrase
                )


            parts.append(
                (
                    "konut finansman\u0131nda "
                    "yeni / s\u0131f\u0131r konut ile "
                    "ikinci el konut ko\u015fullar\u0131n\u0131 "
                    "kar\u015f\u0131la\u015ft\u0131r."
                )
            )


            if amount is not None:

                parts.append(
                    _v51_amount_text(
                        amount
                    )
                    + "."
                )


            if maturity is not None:

                parts.append(
                    str(
                        maturity
                    )
                    + " ay."
                )


            resolved = " ".join(
                parts
            )


            base = (
                _resolve_followup_question_before_v51(
                    original,
                    history,
                )
            )


            return _v51_replace(
                base,

                resolved_question=(
                    resolved
                ),

                used_context=True,

                inherited_bank=(
                    _v51_bank_phrase(
                        banks
                    )
                    or None
                ),

                inherited_product=(
                    "konut finansman\u0131"
                ),
            )


    # --------------------------------------------------------
    # 2. Numeric finance followup.
    #
    # Search backward for the latest FINANCE comparison;
    # campaign turns are intentionally ignored.
    # --------------------------------------------------------

    if (
        _v51_numeric_followup(
            original
        )
    ):

        finance_context = (
            _v51_find_latest_finance_context(
                history
            )
        )


        if finance_context:

            family = (
                finance_context.get(
                    "family"
                )
            )

            banks = (
                finance_context.get(
                    "banks"
                )
                or ()
            )


            amount = (
                _v51_extract_amount(
                    original
                )
            )

            if amount is None:

                amount = (
                    finance_context.get(
                        "amount"
                    )
                )


            maturity = (
                _v51_extract_maturity(
                    original
                )
            )

            if maturity is None:

                maturity = (
                    finance_context.get(
                        "maturity"
                    )
                )


            bank_phrase = (
                _v51_bank_phrase(
                    banks
                )
            )


            family_phrase = (
                _v51_family_phrase(
                    family
                )
            )


            parts = []


            if bank_phrase:

                parts.append(
                    bank_phrase
                )


            parts.append(
                family_phrase
                + " kar\u015f\u0131la\u015ft\u0131r."
            )


            if amount is not None:

                parts.append(
                    _v51_amount_text(
                        amount
                    )
                    + "."
                )


            if maturity is not None:

                parts.append(
                    str(
                        maturity
                    )
                    + " ay."
                )


            resolved = " ".join(
                parts
            )


            base = (
                _resolve_followup_question_before_v51(
                    original,
                    history,
                )
            )


            return _v51_replace(
                base,

                resolved_question=(
                    resolved
                ),

                used_context=True,

                inherited_bank=(
                    bank_phrase
                    or None
                ),

                inherited_product=(
                    family_phrase
                ),
            )


    # --------------------------------------------------------
    # 3. Existing resolver handles everything else.
    # --------------------------------------------------------

    result = (
        _resolve_followup_question_before_v51(
            original,
            history,
        )
    )


    # --------------------------------------------------------
    # 4. Explicit current bank / bank-like entity boundary.
    #
    # If the old resolver tried to prepend an older bank or
    # product, discard that inheritance completely.
    # --------------------------------------------------------

    if (
        _v51_explicit_bank_like(
            original
        )
        and
        bool(
            getattr(
                result,
                "used_context",
                False,
            )
        )
    ):

        current_banks = (
            _v51_detect_banks(
                original
            )
        )

        inherited = str(
            getattr(
                result,
                "inherited_bank",
                "",
            )
            or ""
        )


        inherited_norm = (
            _v51_norm(
                inherited
            )
        )


        current_norms = {
            _v51_norm(
                bank
            )

            for bank in current_banks
        }


        stale_inheritance = (
            not current_banks
            or
            (
                inherited_norm
                and
                inherited_norm
                not in current_norms
            )
        )


        if stale_inheritance:

            return _v51_replace(
                result,

                resolved_question=(
                    original
                ),

                used_context=False,

                inherited_bank=None,

                inherited_product=None,
            )


    return result



# ============================================================
# BANSA_IMMEDIATE_FINANCE_FOLLOWUP_V6
#
# Numeric short turns inherit the latest explicit bank+product
# finance topic, not an older comparison hidden further back.
# This fixes:
#   "Vakıf Katılım motosiklet finansmanı hakkında bilgi ver."
#   "Peki 600 bin TL için?"
# without changing campaign context rules.
# ============================================================

_resolve_followup_question_before_v6 = resolve_followup_question


def _v6_latest_explicit_finance_topic(history):
    texts = _v51_history_strings(history)
    checked = 0
    for text in reversed(texts):
        if not str(text or "").strip():
            continue
        checked += 1
        if checked > 4:
            break
        if _v51_is_campaign_text(text):
            # Do not inherit finance context across a newer campaign turn.
            break
        family = _v51_product_family(text)
        banks = _v51_detect_banks(text)
        if family and banks:
            return {
                "text": text,
                "family": family,
                "banks": banks,
                "amount": _v51_extract_amount(text),
                "maturity": _v51_extract_maturity(text),
            }
    return None


def resolve_followup_question(question, history):
    original = str(question or "").strip()

    if original and _v51_numeric_followup(original):
        # Explicit current bank/product always owns the turn.
        current_banks = _v51_detect_banks(original)
        current_family = _v51_product_family(original)
        if not current_banks and not current_family:
            context = _v6_latest_explicit_finance_topic(history)
            if context:
                bank_phrase = _v51_bank_phrase(context.get("banks") or ())
                family_phrase = _v51_family_phrase(context.get("family"))
                parts = [x for x in (bank_phrase, family_phrase, original) if x]
                resolved = " ".join(parts)
                base = _resolve_followup_question_before_v6(original, history)
                return _v51_replace(
                    base,
                    resolved_question=resolved,
                    used_context=True,
                    inherited_bank=bank_phrase or None,
                    inherited_product=family_phrase or None,
                )

    return _resolve_followup_question_before_v6(original, history)

# ============================================================
# COMPETITION CONTEXT ISOLATION V7
# ------------------------------------------------------------
# A fully explicit current finance question must always own the
# turn.  Older context may only fill genuinely missing slots.
# The robust competition detector also understands typo forms
# such as "vakf katlm motosklet".
# ============================================================

_resolve_followup_question_before_v7 = resolve_followup_question


def resolve_followup_question(question, history):
    original = str(question or "").strip()

    if original:
        try:
            from src.competition_fast_router import detect_banks, detect_family

            explicit_banks = detect_banks(original)
            explicit_family = detect_family(original)

            # Bank + product family is a self-contained finance request. Never
            # prepend an older bank/product, even when this turn also contains
            # numbers that resemble a follow-up.
            if explicit_banks and explicit_family:
                return FollowupResolution(
                    original_question=original,
                    resolved_question=original,
                    used_context=False,
                    inherited_bank=None,
                    inherited_product=None,
                )
        except Exception:
            pass

    return _resolve_followup_question_before_v7(original, history)

# ============================================================
# COMPETITION NUMERIC CONTEXT CARRY V8
# ------------------------------------------------------------
# Carry the other numeric slot across short follow-ups when the
# bank+family context is the same. Example:
#   Vakıf motosiklet -> Peki 600 bin? -> 24 ay olur mu?
# The third turn keeps the 600k context instead of forgetting it.
# ============================================================

_resolve_followup_question_before_v8 = resolve_followup_question


def resolve_followup_question(question, history):
    original = str(question or "").strip()
    base = _resolve_followup_question_before_v8(original, history)

    try:
        from src.competition_fast_router import (
            detect_banks,
            detect_family,
            parse_amount_and_maturity,
        )

        current_amount, current_maturity = parse_amount_and_maturity(original)

        # Only augment genuine partial numeric turns. Full questions and turns
        # without numbers stay under the established resolver behavior.
        if (current_amount is None) == (current_maturity is None):
            return base

        resolved_banks = tuple(detect_banks(base.resolved_question))
        resolved_family = detect_family(base.resolved_question)
        if not resolved_banks or not resolved_family:
            return base

        inherited_amount = None
        inherited_maturity = None

        for previous in reversed(list(history or [])[-8:]):
            previous = str(previous or "").strip()
            if not previous:
                continue
            previous_banks = tuple(detect_banks(previous))
            previous_family = detect_family(previous)
            if set(previous_banks) != set(resolved_banks) or previous_family != resolved_family:
                continue
            pa, pm = parse_amount_and_maturity(previous)
            if inherited_amount is None and pa is not None:
                inherited_amount = pa
            if inherited_maturity is None and pm is not None:
                inherited_maturity = pm
            if inherited_amount is not None and inherited_maturity is not None:
                break

        resolved = str(base.resolved_question or original).strip()

        if current_amount is None and inherited_amount is not None:
            amount_text = (
                f"{int(inherited_amount)} TL"
                if float(inherited_amount).is_integer()
                else f"{inherited_amount} TL"
            )
            if amount_text not in resolved:
                resolved = f"{resolved} {amount_text}".strip()

        if current_maturity is None and inherited_maturity is not None:
            maturity_text = f"{int(inherited_maturity)} ay"
            if maturity_text not in resolved:
                resolved = f"{resolved} {maturity_text}".strip()

        if resolved != base.resolved_question:
            return FollowupResolution(
                original_question=base.original_question,
                resolved_question=resolved,
                used_context=True,
                inherited_bank=base.inherited_bank,
                inherited_product=base.inherited_product,
            )

    except Exception:
        pass

    return base

# ============================================================
# COMPETITION CONTEXT OWNERSHIP V9
# ------------------------------------------------------------
# Refines V7 so a *self-contained* explicit bank+family query
# overrides history, while variant-only questions such as
# "Dünya Katılım'da yeni/ikinci el farkı?" may still inherit
# the amount/maturity from the immediately relevant scenario.
# ============================================================

_resolve_followup_question_before_v9 = resolve_followup_question


def resolve_followup_question(question, history):
    original = str(question or "").strip()

    try:
        from src.competition_fast_router import (
            detect_attribute,
            detect_banks,
            detect_family,
            normalize as _competition_normalize,
            parse_amount_and_maturity,
        )

        banks = tuple(detect_banks(original))
        family = detect_family(original)
        amount, maturity = parse_amount_and_maturity(original)
        attribute = detect_attribute(original)
        qn = _competition_normalize(original)

        explicit_self_contained = bool(
            banks
            and family
            and (
                len(banks) >= 2
                or amount is not None
                or maturity is not None
                or attribute is not None
                or any(
                    phrase in qn
                    for phrase in (
                        "hakkinda bilgi",
                        "bilgi ver",
                        "nedir",
                        "ne sunuyor",
                        "ne sunuluyor",
                        "kullanabilir miyim",
                    )
                )
            )
        )

        if explicit_self_contained:
            base = FollowupResolution(
                original_question=original,
                resolved_question=original,
                used_context=False,
                inherited_bank=None,
                inherited_product=None,
            )
        elif banks and family:
            # Variant/sub-condition question: use the pre-V7 resolver so only
            # missing numeric context can be inherited from the prior scenario.
            base = _resolve_followup_question_before_v7(original, history)
        else:
            base = _resolve_followup_question_before_v9(original, history)

        # Preserve the historical normalized-number contract for numeric
        # follow-ups (e.g. 200.000 TL -> 200000 TL) because several downstream
        # tests and deterministic parsers rely on that canonical form.
        if base.used_context and amount is not None:
            resolved = str(base.resolved_question or original)
            canonical = f"{int(amount)} TL" if float(amount).is_integer() else f"{amount} TL"
            if canonical not in resolved:
                resolved = re.sub(
                    r"(?<!\d)\d[\d.]*?(?:,\d+)?\s*(?:TL|₺)",
                    canonical,
                    resolved,
                    count=1,
                    flags=re.I,
                )
                if canonical not in resolved:
                    resolved = f"{resolved} {canonical}".strip()
            if resolved != base.resolved_question:
                base = FollowupResolution(
                    original_question=base.original_question,
                    resolved_question=resolved,
                    used_context=base.used_context,
                    inherited_bank=base.inherited_bank,
                    inherited_product=base.inherited_product,
                )

        return base

    except Exception:
        return _resolve_followup_question_before_v9(original, history)


# ============================================================
# COMPETITION GLOBAL QUERY OWNERSHIP V10
# ------------------------------------------------------------
# Explicit family-wide comparison / superlative questions are new global
# questions, not follow-ups to the last named bank.  This prevents history
# such as "Albaraka ..." from contaminating:
#   "100 bin TL 36 ay konut finansmanlarını kıyasla"
#   "en uzun vadeli motosiklet finansmanı hangi bankada?"
# ============================================================

_resolve_followup_question_before_v10 = resolve_followup_question


def resolve_followup_question(question, history):
    original = str(question or "").strip()
    try:
        from src.competition_fast_router import (
            detect_banks,
            detect_family,
            normalize as _competition_normalize,
        )

        banks = tuple(detect_banks(original))
        family = detect_family(original)
        qn = _competition_normalize(original)

        global_query = bool(
            family
            and not banks
            and (
                any(token in qn for token in (
                    "karsilastir", "kiyasla", "hangisi", "hangi banka",
                    "en uzun", "en kisa", "en dusuk", "en yuksek",
                    "en avantajli", "en ucuz", "tum bank", "finansmanlarini",
                ))
                or ("secenekler" in qn and "hangi" in qn)
            )
        )

        if global_query:
            return FollowupResolution(
                original_question=original,
                resolved_question=original,
                used_context=False,
                inherited_bank=None,
                inherited_product=None,
            )
    except Exception:
        pass

    return _resolve_followup_question_before_v10(original, history)


# ============================================================
# COMPETITION MULTI-BANK NUMERIC FOLLOWUP V11
# ------------------------------------------------------------
# A pure numeric follow-up after a comparison must retain *all* compared
# banks (or the global all-bank scope), not just whichever bank happened to
# be selected by an older resolver layer.
# ============================================================

_resolve_followup_question_before_v11 = resolve_followup_question


def resolve_followup_question(question, history):
    original = str(question or "").strip()
    try:
        from src.competition_fast_router import (
            detect_banks,
            detect_family,
            is_compare_query,
            parse_amount_and_maturity,
        )

        current_banks = tuple(detect_banks(original))
        current_family = detect_family(original)
        amount, maturity = parse_amount_and_maturity(original)

        numeric_only = bool((amount is not None or maturity is not None) and not current_banks and not current_family)
        if numeric_only:
            # Only the *latest relevant finance topic* may own this follow-up.
            # If the user discussed a two-bank comparison, then asked about a
            # single motorcycle product, "Peki 600 bin?" belongs to the newer
            # motorcycle turn, not the older comparison.
            for previous in reversed(list(history or [])[-6:]):
                prev = str(previous or "").strip()
                if not prev:
                    continue
                prev_family = detect_family(prev)
                if not prev_family:
                    continue
                if not is_compare_query(prev):
                    break

                prev_banks = tuple(detect_banks(prev))
                family_phrase = {
                    "konut_finansmani": "konut finansmanı",
                    "ihtiyac_finansmani": "ihtiyaç finansmanı",
                    "arac_finansmani": "taşıt finansmanı",
                    "alisveris_finansmani": "alışveriş finansmanı",
                    "arsa_finansmani": "arsa finansmanı",
                    "isyeri_finansmani": "iş yeri finansmanı",
                    "ticari_finansman": "ticari finansman",
                }.get(prev_family, "finansman")
                bank_phrase = " ve ".join(prev_banks)
                numeric_parts = []
                if amount is not None:
                    numeric_parts.append(f"{int(amount)} TL" if float(amount).is_integer() else f"{amount} TL")
                if maturity is not None:
                    numeric_parts.append(f"{int(maturity)} ay")
                numeric_text = " ".join(numeric_parts) or original
                resolved = " ".join(x for x in (bank_phrase, family_phrase, numeric_text, "karşılaştır") if x).strip()
                return FollowupResolution(
                    original_question=original,
                    resolved_question=resolved,
                    used_context=True,
                    inherited_bank=bank_phrase or None,
                    inherited_product=family_phrase,
                )
    except Exception:
        pass

    return _resolve_followup_question_before_v11(original, history)


# ============================================================
# COMPETITION EXPLICIT FAMILY OVERRIDE V12
# ------------------------------------------------------------
# If the current user explicitly names a product family and it differs from
# the latest finance topic, the current family owns the turn.  Do not inherit
# an old bank/category from e.g. a housing comparison into a new vehicle query.
# ============================================================

_resolve_followup_question_before_v12 = resolve_followup_question


def resolve_followup_question(question, history):
    original = str(question or "").strip()
    if original:
        try:
            from src.competition_fast_router import detect_banks, detect_family

            current_family = detect_family(original)
            current_banks = tuple(detect_banks(original))
            if current_family:
                # Find the newest explicit finance family in recent history.
                previous_family = None
                for previous in reversed(list(history or [])[-6:]):
                    previous = str(previous or "").strip()
                    if not previous:
                        continue
                    pf = detect_family(previous)
                    if pf:
                        previous_family = pf
                        break

                if previous_family and previous_family != current_family:
                    return FollowupResolution(
                        original_question=original,
                        resolved_question=original,
                        used_context=False,
                        inherited_bank=None,
                        inherited_product=None,
                    )
        except Exception:
            pass

    return _resolve_followup_question_before_v12(original, history)

# ============================================================
# COMPETITION SEMANTIC NUMERIC FOLLOWUP V13
# ------------------------------------------------------------
# Numeric-only follow-ups inherit the *whole semantic finance turn*, not just
# bank/family.  This preserves qualifiers and intent such as:
#   TF sigortalı taşıt kâr payı -> "36 ay"
#   Vakıf motosiklet -> "600 bin" -> "24 ay olur mu?"
# while explicit current bank/family continues to override history via V12.
# ============================================================

_resolve_followup_question_before_v13 = resolve_followup_question


def _v13_strip_numeric_slot(text: str, *, amount: bool = False, maturity: bool = False) -> str:
    value = str(text or "")
    if amount:
        value = re.sub(
            r"(?<!\d)\d+(?:[.,]\d+)?\s*(?:bin|milyon)\s*(?:TL|₺)?\b",
            " ", value, flags=re.I,
        )
        value = re.sub(
            r"(?<!\d)\d[\d.]*?(?:,\d+)?\s*(?:TL|₺)\b",
            " ", value, flags=re.I,
        )
    if maturity:
        value = re.sub(r"(?<!\d)\d{1,3}\s*(?:ay|aylık|aylik)\b", " ", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip(" ?.,;:-")


def _v13_latest_semantic_finance_turn(history):
    try:
        from src.competition_fast_router import (
            detect_banks,
            detect_family,
            is_campaign_query,
            is_finance_query,
        )

        for previous in reversed(list(history or [])[-8:]):
            previous = str(previous or "").strip()
            if not previous:
                continue

            # A newer campaign owns the topic boundary.  Do not resurrect an
            # older finance turn across it.
            banks = tuple(detect_banks(previous))
            if is_campaign_query(previous) and not is_finance_query(previous):
                break

            if is_finance_query(previous) and (banks or detect_family(previous)):
                return previous
    except Exception:
        return None
    return None


def resolve_followup_question(question, history):
    original = str(question or "").strip()

    try:
        from src.competition_fast_router import (
            detect_banks,
            detect_family,
            parse_amount_and_maturity,
        )

        current_banks = tuple(detect_banks(original))
        current_family = detect_family(original)
        amount, maturity = parse_amount_and_maturity(original)

        numeric_only = bool(
            (amount is not None or maturity is not None)
            and not current_banks
            and not current_family
        )

        if numeric_only:
            previous = _v13_latest_semantic_finance_turn(history)
            if previous:
                # Multi-bank comparisons already had a canonical builder in
                # V11 ("Bank A ve Bank B konut finansmanı ... karşılaştır").
                # Keep using it so the semantic V13 wrapper does not preserve
                # conversational suffixes such as "finansmanında" and break
                # deterministic comparison routing.
                try:
                    from src.competition_fast_router import is_compare_query
                    if is_compare_query(previous):
                        return _resolve_followup_question_before_v13(original, history)
                except Exception:
                    pass

                # Replace only the slot explicitly changed by the user.  The
                # other numeric slot and all semantic qualifiers remain.
                stem = _v13_strip_numeric_slot(
                    previous,
                    amount=amount is not None,
                    maturity=maturity is not None,
                )

                parts = [stem]
                if amount is not None:
                    parts.append(
                        f"{int(amount)} TL" if float(amount).is_integer() else f"{amount} TL"
                    )
                if maturity is not None:
                    parts.append(f"{int(maturity)} ay")

                resolved = " ".join(x for x in parts if x).strip()
                return FollowupResolution(
                    original_question=original,
                    resolved_question=resolved,
                    used_context=True,
                    inherited_bank=(" ve ".join(detect_banks(previous)) or None),
                    inherited_product=detect_family(previous),
                )
    except Exception:
        pass

    return _resolve_followup_question_before_v13(original, history)

# ============================================================
# BANSA CONVERSATIONAL STATE COMPOSER V14
# ------------------------------------------------------------
# Fixes remaining jury-facing continuation failures observed in
# end-to-end chat tests:
#   * semantic numeric follow-up keeps the NEW intent
#       rate -> "100 bin için aylık taksit?"
#   * same-bank family turns keep bank context
#       Dünya araç -> "600 bin araç için?"
#   * explicit product switch keeps only the still-valid bank
#       Vakıf konut -> "Peki motosiklet ...?"
#   * explicit bank switch keeps product specificity, not rules
#       Vakıf motosiklet -> "Peki Ziraat'ta?"
#   * single campaign detail follow-ups keep campaign identity
#       Teknosa -> "Ne zamana kadar?" -> "şartı ne?"
#   * comparison summary follow-ups keep scenario/family
#       100k/36 compare -> "En düşük geri ödeme hangisinde?"
#
# This layer composes only semantic slots.  It does not calculate
# any financial value.
# ============================================================

_resolve_followup_question_before_v14 = resolve_followup_question


def _v14_family_phrase(family: str | None, hint: str | None = None) -> str:
    if hint == "motosiklet":
        return "motosiklet finansmanı"
    if hint == "bisiklet":
        return "bisiklet finansmanı"
    return {
        "konut_finansmani": "konut finansmanı",
        "ihtiyac_finansmani": "ihtiyaç finansmanı",
        "arac_finansmani": "taşıt finansmanı",
        "alisveris_finansmani": "alışveriş finansmanı",
        "arsa_finansmani": "arsa finansmanı",
        "isyeri_finansmani": "iş yeri finansmanı",
        "ticari_finansman": "ticari finansman",
    }.get(family, "finansman")


def _v14_variant_phrase(text: str) -> str:
    q = _normalize(text)
    # Negative form must be tested first because "sigortasiz" contains the
    # beginning of "sigortali" only in fuzzy logic, not exact text.
    if "sigortasiz" in q:
        return "sigortasız"
    if "sigortali" in q:
        return "sigortalı"
    if any(x in q for x in ("ikinci el", "2 el", "2.el")):
        return "ikinci el"
    if any(x in q for x in ("0 km", "sifir km", "sifir arac")):
        return "0 km"
    return ""


def _v14_starts_continuation(text: str) -> bool:
    q = _normalize(text)
    return any(
        q == prefix or q.startswith(prefix + " ")
        for prefix in (
            "peki", "bunun", "bunda", "buna", "onda", "onun", "o zaman",
            "ya peki", "ya bunun",
        )
    )


def _v14_calc_intent(text: str) -> bool:
    q = _normalize(text)
    return any(
        marker in q
        for marker in (
            "aylik taksit", "taksit ne", "taksiti", "taksit hesapla",
            "hesapla", "toplam geri odeme", "geri odeme ne kadar",
            "ne kadar oder", "ayda ne kadar",
        )
    )


def _v14_repayment_winner_intent(text: str) -> bool:
    q = _normalize(text)
    return (
        "geri odeme" in q
        and any(x in q for x in ("en dusuk", "hangisi", "hangi banka"))
    )


def _v14_campaign_followup_intent(text: str) -> bool:
    q = _normalize(text)
    if not q:
        return False
    return any(
        marker in q
        for marker in (
            "ne zamana kadar", "zamana kadar", "gecerli", "son tarih",
            "bitis tarihi", "ne zaman bitiyor", "ne zaman sona eriyor",
            "sarti", "sartlari", "kosulu", "kosullari", "nasil yararlan",
            "kimler yararlan", "ne yapmam gerek", "ne gerekiyor",
            "kac taksit", "taksit var mi",
        )
    )


def _v14_explicit_family_surface(text: str) -> bool:
    """Detect visibly named finance families even when Turkish suffixes
    prevent the strict family detector from matching the exact token boundary.
    Example: ``Ticari Finansmanın`` contains ``ticari finansman`` but ends with
    the possessive suffix ``-ın``.
    """
    q = _normalize(text)
    return any(
        marker in q
        for marker in (
            "konut finansman", "ev finansman", "tasit finansman", "arac finansman",
            "motosiklet finansman", "ihtiyac finansman", "alisveris finansman",
            "arsa finansman", "is yeri finansman", "isyeri finansman",
            "ticari finansman", "isletme finansman",
        )
    )


def _v14_previous_finance_state(text: str):
    try:
        from src.competition_fast_router import (
            detect_attribute,
            detect_banks,
            detect_family,
            detect_product_hint,
            is_compare_query,
            is_finance_query,
            parse_amount_and_maturity,
        )
    except Exception:
        return None

    value = str(text or "").strip()
    if not value or not is_finance_query(value):
        return None
    family = detect_family(value)
    banks = tuple(detect_banks(value))
    if not family and not banks:
        return None
    amount, maturity = parse_amount_and_maturity(value)
    return {
        "text": value,
        "family": family,
        "banks": banks,
        "hint": detect_product_hint(value),
        "variant": _v14_variant_phrase(value),
        "attribute": detect_attribute(value),
        "amount": amount,
        "maturity": maturity,
        "compare": bool(is_compare_query(value)),
        "asset_value": (
            (lambda: (
                __import__("src.finance_amount_semantics", fromlist=["resolve_amount_semantics", "AmountKind"])
                .resolve_amount_semantics(
                    value, family=family, amount_present=(amount is not None), compare=bool(is_compare_query(value))
                ).kind
                == __import__("src.finance_amount_semantics", fromlist=["AmountKind"]).AmountKind.ASSET_VALUE
            ))()
            if family == "arac_finansmani" and amount is not None
            else False
        ),
    }


def _v14_latest_finance_state(history):
    try:
        from src.competition_fast_router import is_campaign_query, is_finance_query
    except Exception:
        is_campaign_query = lambda _x: False
        is_finance_query = lambda _x: True

    checked = 0
    for previous in reversed(list(history or [])):
        previous = str(previous or "").strip()
        if not previous:
            continue
        checked += 1
        if checked > 10:
            break
        # A newer campaign detail/list is a hard boundary for finance context.
        try:
            if is_campaign_query(previous) and not is_finance_query(previous):
                break
        except Exception:
            pass
        state = _v14_previous_finance_state(previous)
        if state:
            return state
    return None


def _v14_latest_campaign_context(history):
    try:
        from src.competition_fast_router import detect_banks, is_campaign_query, is_finance_query
    except Exception:
        return None

    checked = 0
    for previous in reversed(list(history or [])):
        previous = str(previous or "").strip()
        if not previous:
            continue
        checked += 1
        if checked > 8:
            break
        # A newer explicit finance turn prevents resurrecting an older campaign.
        if is_finance_query(previous) and not is_campaign_query(previous):
            break
        if is_campaign_query(previous) and detect_banks(previous):
            return previous
    return None


def _v14_intent_tail(original: str, previous_state) -> tuple[str, str | None]:
    """Return (canonical intent phrase, attribute override)."""
    try:
        from src.competition_fast_router import detect_attribute, parse_amount_and_maturity
    except Exception:
        return "", None

    q = _normalize(original)
    current_attribute = detect_attribute(original)
    _amount, current_maturity = parse_amount_and_maturity(original)

    if _v14_calc_intent(original):
        return "aylık taksiti ve toplam geri ödemeyi hesapla", "scenario_calc"

    if current_attribute == "profit_share_rate":
        return "kar payı oranı nedir?", current_attribute
    if current_attribute == "allocation_fee":
        return "tahsis ücreti nedir?", current_attribute
    if current_attribute == "appraisal_fee":
        return "ekspertiz ücreti nedir?", current_attribute
    if current_attribute == "mortgage_fee":
        return "ipotek/rehin ücreti nedir?", current_attribute
    if current_attribute == "insurance_fee":
        return "sigorta ücreti nedir?", current_attribute
    if current_attribute == "fees":
        return "masrafları nelerdir?", current_attribute
    if current_attribute == "maximum_maturity":
        return "azami vade nedir?", current_attribute
    if current_attribute == "maximum_amount":
        return "azami finansman tutarı nedir?", current_attribute

    if current_maturity is not None and any(x in q for x in ("olur mu", "uygun mu", "mumkun mu")):
        return "bu vade uygun mu?", "maturity_fit"

    # A bare numeric turn such as "36 ay" keeps the immediately previous fact
    # intent.  This is what makes TF sigortalı -> 36 ay remain a rate question.
    if previous_state:
        previous_attr = previous_state.get("attribute")
        if previous_attr == "profit_share_rate":
            return "kar payı oranı nedir?", previous_attr
        if previous_attr == "allocation_fee":
            return "tahsis ücreti nedir?", previous_attr
        if previous_attr == "appraisal_fee":
            return "ekspertiz ücreti nedir?", previous_attr
        if previous_attr == "mortgage_fee":
            return "ipotek/rehin ücreti nedir?", previous_attr
        if previous_attr == "maximum_maturity":
            return "azami vade nedir?", previous_attr

    return "", None


def _v14_compose_finance_continuation(original: str, state, *, current_banks, current_family, current_hint):
    try:
        from src.competition_fast_router import parse_amount_and_maturity
    except Exception:
        return None

    amount, maturity = parse_amount_and_maturity(original)
    banks = tuple(current_banks or state.get("banks") or ())
    family = current_family or state.get("family")
    hint = current_hint or state.get("hint")

    # An explicit generic vehicle family ("araç/taşıt") intentionally drops a
    # previous specialty hint unless the current turn itself says motorcycle.
    if current_family == "arac_finansmani" and current_hint is None:
        qn = _normalize(original)
        if any(x in qn for x in ("arac", "tasit")):
            hint = None

    if not banks or not family:
        return None

    variant = _v14_variant_phrase(original) or state.get("variant") or ""
    intent_tail, intent_kind = _v14_intent_tail(original, state)

    # Carry the other numeric slot only inside the same conversational
    # scenario.  A new explicit amount/maturity replaces the corresponding
    # prior slot, never duplicates it.
    final_amount = amount if amount is not None else state.get("amount")
    final_maturity = maturity if maturity is not None else state.get("maturity")

    # Vehicle value and requested financing amount are distinct semantics.
    # V17 no longer turns a bare numeric follow-up ("600 bin için?") into a
    # vehicle value merely because the previous product was motorcycle.
    qn = _normalize(original)
    asks_financing_amount = any(x in qn for x in (
        "finansman tutari", "kredi tutari", "kullanmak istedigim",
        "finansman kullan", "kredi kullan",
    ))
    value_mode = False
    if family == "arac_finansmani" and intent_kind != "scenario_calc" and not asks_financing_amount:
        try:
            from src.finance_amount_semantics import AmountKind, resolve_amount_semantics
            semantics = resolve_amount_semantics(
                original, family=family, amount_present=(amount is not None), compare=False
            )
            if semantics.kind == AmountKind.ASSET_VALUE:
                value_mode = True
        except Exception:
            pass
        # Preserve an already explicit asset-value context for a pure maturity
        # follow-up such as "24 ay olur mu?". Do not create that context from a
        # bare amount turn.
        if amount is None and state.get("asset_value"):
            value_mode = True

    parts = []
    parts.append(" ve ".join(banks))
    if variant:
        parts.append(variant)
    parts.append(_v14_family_phrase(family, hint))

    if final_amount is not None:
        amount_text = f"{int(final_amount)} TL" if float(final_amount).is_integer() else f"{final_amount} TL"
        if value_mode:
            asset_label = "motosiklet" if hint == "motosiklet" else "araç"
            parts.append(amount_text + f" {asset_label} değeri")
        else:
            parts.append(amount_text)

    if final_maturity is not None:
        parts.append(f"{int(final_maturity)} ay")

    if intent_tail:
        parts.append(intent_tail)

    return " ".join(x for x in parts if x).strip()


def resolve_followup_question(question, history):
    original = str(question or "").strip()
    if not original:
        return _resolve_followup_question_before_v14(original, history)

    try:
        from src.competition_fast_router import (
            detect_banks,
            detect_family,
            detect_product_hint,
            is_compare_query,
            is_finance_query,
            parse_amount_and_maturity,
        )

        current_banks = tuple(detect_banks(original))
        current_family = detect_family(original)
        current_hint = detect_product_hint(original)
        amount, maturity = parse_amount_and_maturity(original)
        qn = _normalize(original)

        # V15: an explicit campaign surface is an absolute topic boundary.
        # Do NOT delegate this to the legacy resolver because the legacy path
        # may resurrect an older finance/motorcycle product before campaign
        # routing sees the turn.
        if any(token in qn for token in ("kampanya", "kampanyasi", "kampanyasinda", "kampanyalari")):
            return FollowupResolution(
                original_question=original,
                resolved_question=original,
                used_context=False,
                inherited_bank=None,
                inherited_product=None,
            )
        try:
            from src.competition_fast_router import is_campaign_query
            if is_campaign_query(original) and not is_finance_query(original):
                return FollowupResolution(
                    original_question=original, resolved_question=original,
                    used_context=False, inherited_bank=None, inherited_product=None,
                )
        except Exception:
            pass

        # Explicit bank + visibly named finance family is self-contained even
        # if the strict family detector misses a Turkish suffix.
        if current_banks and current_family is None and _v14_explicit_family_surface(original):
            return FollowupResolution(
                original_question=original,
                resolved_question=original,
                used_context=False,
                inherited_bank=None,
                inherited_product=None,
            )

        # A visibly new, non-family product such as "eğitim finansmanının"
        # may be recognized by the legacy product lexicon even when the fast
        # family detector returns None because of Turkish possessive suffixes.
        # In that case inherit only the latest bank; never resurrect the old
        # product/family.  Vehicle specialties are handled by the richer V14
        # family composer below.
        legacy_current_product = _find_product(original)
        if (
            legacy_current_product
            and current_family is None
            and not current_banks
            and _v14_starts_continuation(original)
        ):
            state_for_product_switch = _v14_latest_finance_state(history)
            if (
                state_for_product_switch
                and len(state_for_product_switch.get("banks") or ()) == 1
                and legacy_current_product not in {"motosiklet finansmanı", "taşıt finansmanı"}
            ):
                bank = (state_for_product_switch.get("banks") or (None,))[0]
                return FollowupResolution(
                    original_question=original,
                    resolved_question=f"{bank} - {original}",
                    used_context=True,
                    inherited_bank=bank,
                    inherited_product=None,
                )

        # ----------------------------------------------------
        # 1. Single campaign detail continuation.
        # ----------------------------------------------------
        if (
            not current_banks
            and current_family is None
            and _v14_campaign_followup_intent(original)
            and not is_finance_query(original)
        ):
            previous_campaign = _v14_latest_campaign_context(history)
            if previous_campaign:
                return FollowupResolution(
                    original_question=original,
                    resolved_question=previous_campaign + " - " + original,
                    used_context=True,
                    inherited_bank=None,
                    inherited_product=None,
                )

        state = _v14_latest_finance_state(history)

        # ----------------------------------------------------
        # 2. Winner/summary follow-up after a concrete compare.
        # ----------------------------------------------------
        comparison_followup = bool(
            _v14_repayment_winner_intent(original)
            or any(marker in qn for marker in (
                "ikinci en dusuk", "ikinci en iyi", "en dusuk aylik",
                "aylik taksit hang", "ilk uc", "ilk 3", "sirala",
                "aradaki fark", "fark ne kadar", "farki ne kadar",
                "hangisinin toplam", "toplam geri odemede",
            ))
        )
        if state and state.get("compare") and comparison_followup:
            # Always attach a comparison follow-up to the original comparison
            # scenario, not to a previous compounded follow-up.  Otherwise a
            # chain such as "ikinci en düşük" -> "ilk üçü sırala" keeps the
            # old intent token in the resolved query and the renderer remains
            # locked on the second-place branch.
            base_compare_text = str(state.get("text") or "").split(" - ", 1)[0].strip()
            return FollowupResolution(
                original_question=original,
                resolved_question=base_compare_text + " - " + original,
                used_context=True,
                inherited_bank=(" ve ".join(state.get("banks") or ()) or None),
                inherited_product=_v14_family_phrase(state.get("family"), state.get("hint")),
            )

        # No finance context to compose: preserve all established behavior.
        if not state:
            return _resolve_followup_question_before_v14(original, history)

        # ----------------------------------------------------
        # 3. Explicit global comparison/superlative owns turn.
        # ----------------------------------------------------
        global_family_query = bool(
            current_family
            and not current_banks
            and (
                is_compare_query(original)
                or any(x in qn for x in ("hangi banka", "tum bank", "finansmanlarini"))
            )
        )
        if global_family_query:
            return _resolve_followup_question_before_v14(original, history)

        # ----------------------------------------------------
        # 4. Fully explicit bank + family owns turn unchanged.
        # ----------------------------------------------------
        if current_banks and current_family:
            return _resolve_followup_question_before_v14(original, history)

        # ----------------------------------------------------
        # 5. Bank switch: inherit product semantics only.
        #    Numeric scenario may carry, bank-specific rules never do.
        # ----------------------------------------------------
        if current_banks and not current_family:
            if _v14_starts_continuation(original) or len(qn.split()) <= 8:
                composed = _v14_compose_finance_continuation(
                    original,
                    state,
                    current_banks=current_banks,
                    current_family=None,
                    current_hint=None,
                )
                if composed:
                    return FollowupResolution(
                        original_question=original,
                        resolved_question=composed,
                        used_context=True,
                        inherited_bank=None,
                        inherited_product=_v14_family_phrase(state.get("family"), state.get("hint")),
                    )

        # ----------------------------------------------------
        # 6. Product/family switch or same-family short turn:
        #    retain the latest single bank, unless query is global.
        # ----------------------------------------------------
        if current_family and not current_banks and len(state.get("banks") or ()) == 1:
            short_scenario = bool(
                _v14_starts_continuation(original)
                or amount is not None
                or maturity is not None
                or len(qn.split()) <= 10
            )
            if short_scenario:
                composed = _v14_compose_finance_continuation(
                    original,
                    state,
                    current_banks=state.get("banks"),
                    current_family=current_family,
                    current_hint=current_hint,
                )
                if composed:
                    return FollowupResolution(
                        original_question=original,
                        resolved_question=composed,
                        used_context=True,
                        inherited_bank=(state.get("banks") or (None,))[0],
                        inherited_product=None,
                    )

        # ----------------------------------------------------
        # 7. Fully implicit finance continuation.
        #    Preserve latest bank/product/variant/other numeric slot while
        #    letting CURRENT intent replace the old intent.
        # ----------------------------------------------------
        implicit_finance = bool(
            not current_banks
            and current_family is None
            and (
                amount is not None
                or maturity is not None
                or _v14_starts_continuation(original)
                or _v14_calc_intent(original)
                or any(
                    token in qn
                    for token in (
                        "kar payi", "tahsis", "ekspertiz", "ipotek", "rehin",
                        "masraf", "ucret", "azami vade", "maksimum vade",
                        "azami finansman", "maksimum finansman", "en fazla ne kadar finansman",
                        "kac ay", "olur mu", "uygun mu",
                    )
                )
            )
        )
        if implicit_finance and not state.get("compare"):
            composed = _v14_compose_finance_continuation(
                original,
                state,
                current_banks=state.get("banks"),
                current_family=state.get("family"),
                current_hint=state.get("hint"),
            )
            if composed:
                return FollowupResolution(
                    original_question=original,
                    resolved_question=composed,
                    used_context=True,
                    inherited_bank=(" ve ".join(state.get("banks") or ()) or None),
                    inherited_product=_v14_family_phrase(state.get("family"), state.get("hint")),
                )

    except Exception:
        pass

    return _resolve_followup_question_before_v14(original, history)

# ============================================================
# BANSA CENTRAL EXPLICIT-OVERRIDE GUARD V16.4
# ------------------------------------------------------------
# Final high-priority wrapper around the accumulated resolver.
# Contract:
#   explicit topic/product in CURRENT turn > historical state
#   explicit bank + product is self-contained
#   explicit product without bank may inherit ONE recent bank only
#   inherited amount/maturity/comparison state is cleared on product switch
#   true slot-only turns still delegate to the proven V14/V16 resolver
# ============================================================

_resolve_followup_question_before_v164 = resolve_followup_question


def _v164_explicit_product(question: str) -> str | None:
    """Return a visibly named product surface from the CURRENT turn.

    Uses both the strict fast family taxonomy and the older product lexicon so
    Turkish possessive forms such as ``eğitim finansmanının`` are not missed.
    """
    text = str(question or "").strip()
    qn = _normalize(text)
    if not qn:
        return None

    # Specific products first.  These must beat generic family inheritance.
    surfaces = (
        # Branded/special financing programs are explicit topic boundaries.
        # They must clear stale vehicle/housing amount state from a previous turn.
        ("Enerya finansmanı", ("enerya", "karz-i hasen", "karzi hasen", "karz hasen")),
        ("eğitim finansmanı", ("egitim finansman",)),
        ("motosiklet finansmanı", ("motosiklet finansman", "motosiklet")),
        ("konut finansmanı", ("konut finansman", "ev finansman")),
        ("taşıt finansmanı", ("tasit finansman", "arac finansman")),
        ("ihtiyaç finansmanı", ("ihtiyac finansman",)),
        ("arsa finansmanı", ("arsa finansman",)),
        ("iş yeri finansmanı", ("is yeri finansman", "isyeri finansman")),
        ("ticari finansman", ("ticari finansman", "isletme finansman")),
        ("hac ve umre finansmanı", ("hac finansman", "umre finansman", "hac ve umre finansman")),
    )
    for canonical, markers in surfaces:
        if any(marker in qn for marker in markers):
            return canonical

    try:
        legacy = _find_product(text)
        if legacy:
            # Legacy product matching is fuzzy.  Do not let the generic word
            # "finansman" turn a request such as "600 bin finansman kullanmak
            # istiyorum" into an unrelated named product (e.g. SÖİK).  Accept
            # the legacy hit only when at least one distinctive product token is
            # visibly present in the CURRENT user turn.
            legacy_n = _normalize(str(legacy))
            generic_tokens = {
                "finansman", "finansmani", "destegi", "destek", "kredisi",
                "kredi", "urun", "urunu", "bireysel", "ticari",
            }
            distinctive = [
                t for t in legacy_n.split()
                if len(t) >= 3 and t not in generic_tokens
            ]
            if distinctive and any(t in qn for t in distinctive):
                return str(legacy)
    except Exception:
        pass
    return None


def _v164_latest_single_bank(history) -> str | None:
    """Find one unambiguous recent finance bank without crossing campaign boundaries."""
    try:
        from src.competition_fast_router import detect_banks, is_campaign_query, is_finance_query
    except Exception:
        return None

    checked = 0
    for item in reversed(list(history or [])):
        value = str(item or "").strip()
        if not value:
            continue
        checked += 1
        if checked > 10:
            break
        try:
            if is_campaign_query(value) and not is_finance_query(value):
                break
        except Exception:
            pass
        banks = tuple(detect_banks(value))
        if len(banks) == 1:
            return banks[0]
        if len(banks) > 1:
            # A recent comparison is an ambiguity boundary. Do not jump past it
            # and resurrect an older single-bank context.
            break
    return None



def _v18_latest_product_context(history, required_bank: str | None = None):
    """Recover the most recent explicit finance product from RAW user turns.

    Streamlit stores raw user messages, not resolved canonical questions.  A
    clarification sequence such as ``Vakıf motosiklet -> 600 bin için? ->
    motosikletin değeri`` therefore needs to look past the bare numeric turn.
    """
    try:
        from src.competition_fast_router import (
            detect_banks, detect_family, detect_product_hint,
            is_campaign_query, is_finance_query,
        )
    except Exception:
        return None

    required_n = _normalize(required_bank or "")
    checked = 0
    for item in reversed(list(history or [])):
        value = str(item or "").strip()
        if not value:
            continue
        checked += 1
        if checked > 12:
            break
        try:
            if is_campaign_query(value) and not is_finance_query(value):
                break
        except Exception:
            pass
        banks = tuple(detect_banks(value))
        if required_n and banks:
            bank_norms = {_normalize(b) for b in banks}
            if required_n not in bank_norms:
                # A newer explicit different bank is a context boundary.
                break
        family = detect_family(value)
        hint = detect_product_hint(value)
        explicit = _v164_explicit_product(value)
        if family is None and hint == "motosiklet":
            family = "arac_finansmani"
        if family is None and explicit:
            exp_n = _normalize(explicit)
            if "motosiklet" in exp_n or "tasit" in exp_n or "arac" in exp_n:
                family = "arac_finansmani"
            elif "konut" in exp_n:
                family = "konut_finansmani"
            elif "ihtiyac" in exp_n or "egitim" in exp_n:
                family = "ihtiyac_finansmani"
        if family or hint or explicit:
            return {"family": family, "hint": hint, "explicit": explicit}
    return None


def _v18_latest_amount(history):
    try:
        from src.competition_fast_router import parse_amount_and_maturity
    except Exception:
        return None
    for item in reversed(list(history or [])):
        value = str(item or "").strip()
        if not value:
            continue
        amount, _maturity = parse_amount_and_maturity(value)
        if amount is not None:
            return amount
    return None

def resolve_followup_question(question, history):
    original = str(question or "").strip()
    if not original:
        return _resolve_followup_question_before_v164(original, history)

    try:
        from src.competition_fast_router import detect_banks, parse_amount_and_maturity

        current_banks = tuple(detect_banks(original))
        explicit_product = _v164_explicit_product(original)
        qn = _normalize(original)

        # V17 clarification reply: when BANSA has just asked whether a bare
        # amount means the asset value or the requested financing amount, a
        # short answer such as "motosikletin değeri" must bind that semantic
        # label to the PREVIOUS amount.  It must not lose 600.000 TL merely
        # because the confirmation turn itself contains no number.
        asset_reply = any(marker in qn for marker in (
            "aracin degeri", "tasitin degeri", "motosikletin degeri",
            "motorun degeri", "fatura degeri", "kasko degeri",
            "urun degeri", "degeri kastediyorum", "degerini kastediyorum",
        ))
        financing_reply = any(marker in qn for marker in (
            "finansman tutari", "finansman tutarini", "kullanmak istedigim finansman",
            "istedigim finansman", "finansmani kastediyorum", "kredi tutari",
        ))
        if (asset_reply or financing_reply) and not current_banks:
            current_amount, current_maturity = parse_amount_and_maturity(original)
            state = _v14_latest_finance_state(history)
            bank = None
            family = None
            hint = None
            inherited_maturity = None
            if state and len(state.get("banks") or ()) == 1:
                bank = (state.get("banks") or (None,))[0]
                family = state.get("family")
                hint = state.get("hint")
                inherited_maturity = state.get("maturity")
            if not bank:
                bank = _v164_latest_single_bank(history)
            if not family and bank:
                product_ctx = _v18_latest_product_context(history, required_bank=bank)
                if product_ctx:
                    family = product_ctx.get("family")
                    hint = product_ctx.get("hint")
            amount = current_amount if current_amount is not None else (state.get("amount") if state else None)
            if amount is None:
                amount = _v18_latest_amount(history)
            if bank and family and amount is not None:
                amount_text = f"{int(float(amount))} TL" if float(amount).is_integer() else f"{amount} TL"
                product_phrase = _v14_family_phrase(family, hint)
                if asset_reply:
                    asset_label = "motosiklet" if hint == "motosiklet" else ("araç" if family == "arac_finansmani" else "ürün")
                    resolved = f"{bank} {product_phrase} {amount_text} {asset_label} değeri"
                else:
                    resolved = f"{bank} {product_phrase} {amount_text} finansman tutarı"
                final_maturity = current_maturity if current_maturity is not None else inherited_maturity
                if final_maturity is not None:
                    resolved += f" {int(final_maturity)} ay"
                return FollowupResolution(
                    original_question=original,
                    resolved_question=resolved.strip(),
                    used_context=True,
                    inherited_bank=bank,
                    inherited_product=product_phrase,
                )

        # Explicit merchant/campaign switch in a conversational continuation:
        # preserve only the most recent unambiguous campaign bank, never an old
        # finance product or numeric scenario.
        if (
            not current_banks
            and _v14_starts_continuation(original)
            and any(token in qn for token in ("kampanya", "kampanyasi", "kampanyasinda", "kampanyalari"))
        ):
            previous_campaign = _v14_latest_campaign_context(history)
            if previous_campaign:
                prev_banks = tuple(detect_banks(previous_campaign))
                if len(prev_banks) == 1:
                    bank = prev_banks[0]
                    return FollowupResolution(
                        original_question=original,
                        resolved_question=f"{bank} - {original}",
                        used_context=True,
                        inherited_bank=bank,
                        inherited_product=None,
                    )

        # V18: an explicit SAME bank with a generic financing-amount follow-up
        # may inherit the immediately recent product, but never old numeric
        # slots. This prevents a query such as "Vakıf Katılım'da 600 bin TL
        # finansman kullanmak istiyorum" from falling onto an unrelated catalog
        # row (e.g. SÖİK) after a motorcycle conversation.
        if current_banks and len(current_banks) == 1 and not explicit_product:
            qn_current = _normalize(original)
            financing_amount_surface = any(marker in qn_current for marker in (
                "finansman kullan", "finansman tutari", "finansman ihtiyaci",
                "kredi kullan", "kredi tutari", "kullanmak istiyorum",
            ))
            if financing_amount_surface:
                bank = current_banks[0]
                product_ctx = _v18_latest_product_context(history, required_bank=bank)
                if product_ctx and product_ctx.get("family"):
                    amount_now, maturity_now = parse_amount_and_maturity(original)
                    product_phrase = _v14_family_phrase(product_ctx.get("family"), product_ctx.get("hint"))
                    parts = [bank, product_phrase]
                    if amount_now is not None:
                        amount_text = f"{int(float(amount_now))} TL" if float(amount_now).is_integer() else f"{amount_now} TL"
                        parts.append(amount_text + " finansman tutarı")
                    if maturity_now is not None:
                        parts.append(f"{int(maturity_now)} ay")
                    if any(x in qn_current for x in ("olur mu", "uygun mu", "mumkun mu")):
                        parts.append("uygun mu?")
                    resolved = " ".join(parts).strip()
                    return FollowupResolution(
                        original_question=original,
                        resolved_question=resolved,
                        used_context=True,
                        inherited_bank=bank,
                        inherited_product=product_phrase,
                    )

        # Current turn explicitly names BOTH bank and product: it owns the turn.
        # This is the critical guard for:
        #   housing comparison -> "Albaraka Türk eğitim finansmanının ..."
        # No old product, amount, maturity or compare token may be resurrected.
        if current_banks and explicit_product:
            return FollowupResolution(
                original_question=original,
                resolved_question=original,
                used_context=False,
                inherited_bank=None,
                inherited_product=None,
            )

        # Current turn explicitly names a NEW product but omits a bank.  Preserve
        # at most one unambiguous recent bank and intentionally clear every other
        # historical slot by composing BANK + ORIGINAL only.
        if explicit_product and not current_banks:
            # Enerya is a branded Dünya Katılım finance surface.  It must not
            # inherit an unrelated bank from the preceding turn.
            if explicit_product == "Enerya finansmanı":
                return FollowupResolution(
                    original_question=original,
                    resolved_question=f"Dünya Katılım - {original}",
                    used_context=True,
                    inherited_bank="Dünya Katılım",
                    inherited_product=explicit_product,
                )

            # Global comparisons/superlatives explicitly ask across banks, so a
            # previous single-bank context must not narrow the new turn.
            try:
                from src.competition_fast_router import is_compare_query
                qn = _normalize(original)
                if is_compare_query(original) or any(x in qn for x in (
                    "hangi banka", "tum bank", "finansmanlarini", "karsilastir", "kiyasla",
                )):
                    return _resolve_followup_question_before_v164(original, history)
            except Exception:
                pass

            bank = _v164_latest_single_bank(history)
            if bank:
                return FollowupResolution(
                    original_question=original,
                    resolved_question=f"{bank} - {original}",
                    used_context=True,
                    inherited_bank=bank,
                    inherited_product=None,
                )

    except Exception:
        # The established resolver remains the safe fallback.
        pass

    return _resolve_followup_question_before_v164(original, history)

# ============================================================
# BANSA V22 MULTI-TURN COMPARISON SLOT COLLECTOR
# ------------------------------------------------------------
# Natural demo flow:
#   "Albaraka ile Türkiye Finans konutu karşılaştır"
#   -> asks amount + maturity
#   "500 bin TL"
#   -> asks only maturity
#   "36 ay"
#   -> restores BOTH 500k and 36m, rather than losing the amount because the
#      UI intentionally stores raw user turns.
# ============================================================

_resolve_followup_question_before_v22 = resolve_followup_question


def _v22_family_phrase(family: str | None) -> str:
    return {
        "konut_finansmani": "konut finansmanı",
        "ihtiyac_finansmani": "ihtiyaç finansmanı",
        "arac_finansmani": "taşıt finansmanı",
        "alisveris_finansmani": "alışveriş finansmanı",
        "arsa_finansmani": "arsa finansmanı",
        "isyeri_finansmani": "iş yeri finansmanı",
        "ticari_finansman": "ticari finansman",
        "gayri_nakdi_finansman": "gayri nakdi finansman",
        "tarim_finansmani": "tarım finansmanı",
        "leasing": "leasing",
    }.get(family, "finansman")


def resolve_followup_question(question, history):
    original = str(question or "").strip()
    try:
        from src.competition_fast_router import (
            detect_banks,
            detect_family,
            is_campaign_query,
            is_compare_query,
            parse_amount_and_maturity,
        )

        current_banks = tuple(detect_banks(original))
        current_family = detect_family(original)
        current_amount, current_maturity = parse_amount_and_maturity(original)
        numeric_followup = bool(
            (current_amount is not None or current_maturity is not None)
            and not current_banks
            and not current_family
        )
        if numeric_followup:
            recent = [str(x or "").strip() for x in list(history or [])[-10:]]
            anchor_index = None
            anchor_banks: tuple[str, ...] = ()
            anchor_family = None
            for idx in range(len(recent) - 1, -1, -1):
                turn = recent[idx]
                if not turn:
                    continue
                banks = tuple(detect_banks(turn))
                fam = detect_family(turn)
                if is_compare_query(turn) and fam and len(banks) >= 2:
                    anchor_index = idx
                    anchor_banks = banks
                    anchor_family = fam
                    break
            if anchor_index is not None:
                amount = None
                maturity = None
                safe_chain = True
                for turn in recent[anchor_index + 1:]:
                    if not turn:
                        continue
                    # A later explicit topic starts a new conversation branch.
                    later_banks = tuple(detect_banks(turn))
                    later_family = detect_family(turn)
                    if is_campaign_query(turn) and not later_family:
                        safe_chain = False
                        break
                    if later_family and later_family != anchor_family:
                        safe_chain = False
                        break
                    if later_banks and set(later_banks) != set(anchor_banks):
                        safe_chain = False
                        break
                    a, m = parse_amount_and_maturity(turn)
                    if a is not None:
                        amount = a
                    if m is not None:
                        maturity = m
                if safe_chain:
                    if current_amount is not None:
                        amount = current_amount
                    if current_maturity is not None:
                        maturity = current_maturity
                    pieces = [" ve ".join(anchor_banks), _v22_family_phrase(anchor_family)]
                    if amount is not None:
                        pieces.append(f"{int(amount)} TL" if float(amount).is_integer() else f"{amount} TL")
                    if maturity is not None:
                        pieces.append(f"{int(maturity)} ay")
                    pieces.append("karşılaştır")
                    return FollowupResolution(
                        original_question=original,
                        resolved_question=" ".join(x for x in pieces if x).strip(),
                        used_context=True,
                        inherited_bank=" ve ".join(anchor_banks),
                        inherited_product=_v22_family_phrase(anchor_family),
                    )
    except Exception:
        pass

    return _resolve_followup_question_before_v22(original, history)

# V22.1 - explicit housing variant follow-up after a priced comparison.
# Keep only amount/maturity from the previous comparison; never inherit the
# other bank when the current turn explicitly names a bank.
_resolve_followup_question_before_v22_variant = resolve_followup_question


def resolve_followup_question(question, history):
    original = str(question or "").strip()
    try:
        from src.competition_fast_router import (
            detect_banks,
            detect_family,
            is_compare_query,
            normalize,
            parse_amount_and_maturity,
        )
        qn = normalize(original)
        current_banks = tuple(detect_banks(original))
        is_housing_variant = (
            current_banks
            and ("ikinci el konut" in qn)
            and ("yeni konut" in qn or "sifir konut" in qn)
        )
        if is_housing_variant:
            for previous in reversed(list(history or [])[-10:]):
                previous = str(previous or "").strip()
                if not previous:
                    continue
                if detect_family(previous) != "konut_finansmani" or not is_compare_query(previous):
                    continue
                amount, maturity = parse_amount_and_maturity(previous)
                if amount is None and maturity is None:
                    continue
                parts = [
                    " ve ".join(current_banks),
                    "konut finansmanında yeni / sıfır konut ile ikinci el konut koşullarını karşılaştır.",
                ]
                if amount is not None:
                    parts.append(f"{int(amount)} TL." if float(amount).is_integer() else f"{amount} TL.")
                if maturity is not None:
                    parts.append(f"{int(maturity)} ay.")
                return FollowupResolution(
                    original_question=original,
                    resolved_question=" ".join(parts),
                    used_context=True,
                    inherited_bank=" ve ".join(current_banks),
                    inherited_product="konut finansmanı",
                )
    except Exception:
        pass
    return _resolve_followup_question_before_v22_variant(original, history)

# ============================================================
# V25.1 accuracy patch - branded finance-campaign follow-up memory
# "Dünya Katılım Enerya Karz-ı Hasen ..." -> "Peki minimum vadesi ne?"
# must inherit the immediately preceding Enerya subject, not an older unrelated
# comparison branch.
# ============================================================
_resolve_followup_question_before_v251_accuracy = resolve_followup_question


def resolve_followup_question(question, history):
    original = str(question or "").strip()
    try:
        from src.competition_fast_router import normalize
        qn = normalize(original)
        generic_term_followup = any(x in qn for x in (
            "minimum vade", "minimum vadesi", "min vade", "asgari vade", "en az kac ay",
            "maksimum vade", "maksimum vadesi", "azami vade", "en fazla kac ay",
        ))
        if generic_term_followup:
            for previous in reversed(list(history or [])[-6:]):
                prev = str(previous or "").strip()
                pn = normalize(prev)
                if "enerya" in pn and any(x in pn for x in ("karz", "hasen", "vade farksiz")):
                    return FollowupResolution(
                        original_question=original,
                        resolved_question=f"Dünya Katılım Enerya Karz-ı Hasen {original}",
                        used_context=True,
                        inherited_bank="Dünya Katılım",
                        inherited_product="Enerya Karz-ı Hasen",
                    )
                # A later explicit finance/campaign subject is a hard boundary;
                # do not jump over it to an older comparison.
                if any(token in pn for token in ("finansman", "kampanya")) and len(pn.split()) >= 3:
                    break
    except Exception:
        pass
    return _resolve_followup_question_before_v251_accuracy(original, history)

# ============================================================
# V25.4 context-isolation guard: an explicit unknown "X Katılım" name is a
# new bank-like subject, not a follow-up to the previous known bank. Generic
# phrases such as "bütün katılım bankaları" are excluded from this guard.
# ============================================================
_resolve_followup_question_before_v254_unknown_bank = resolve_followup_question


def resolve_followup_question(question, history):
    original = str(question or "").strip()
    try:
        from src.competition_fast_router import detect_banks, normalize
        qn = normalize(original)
        known = detect_banks(original)
        if not known:
            m = re.search(r"\b([a-z0-9]+)\s+katilim\b", qn)
            if m:
                lead = m.group(1)
                generic = {"tum", "butun", "tüm", "bütün", "katilim", "bankalari", "bankalar", "hangi"}
                if lead not in generic:
                    return FollowupResolution(
                        original_question=original,
                        resolved_question=original,
                        used_context=False,
                    )
    except Exception:
        pass
    return _resolve_followup_question_before_v254_unknown_bank(original, history)

# ============================================================
# V25.5 self-contained broad-scope / purpose-query isolation
# ============================================================
# Explicit requests that introduce a complete new scope ("bütün katılım
# bankaları", "hangi katılım bankaları", laptop/bilgisayar purchase, etc.)
# must never inherit bank/product state from the previous comparison.  This is
# especially important after a Hayat Finans vs T.O.M. comparison: a new
# "50.000 TL laptop ... hangi finansman seçeneklerim var?" turn is a fresh
# multi-bank discovery request, not a numeric follow-up to those two banks.
_resolve_followup_question_before_v255_self_contained = resolve_followup_question


def resolve_followup_question(question, history):
    original = str(question or "").strip()
    try:
        from src.competition_fast_router import normalize
        qn = normalize(original)
        broad_scope = any(x in qn for x in (
            "hangi katilim bankalari",
            "hangi katilim bankalar",
            "butun katilim bankalari",
            "tum katilim bankalari",
            "butun katilim bankalar",
            "tum katilim bankalar",
            "katilim bankalarinda hangi",
            "katilim bankalarinda ne",
            "tum bankalari ve urunlerini",
            "butun bankalari ve urunlerini",
        ))
        explicit_new_purchase_topic = (
            any(x in qn for x in ("laptop", "bilgisayar", "beyaz esya", "telefon", "tablet", "mobilya"))
            and any(x in qn for x in ("almak istiyorum", "finansman secenek", "hangi finansman", "katilim bankalar"))
        )
        if broad_scope or explicit_new_purchase_topic:
            return FollowupResolution(
                original_question=original,
                resolved_question=original,
                used_context=False,
            )
    except Exception:
        pass
    return _resolve_followup_question_before_v255_self_contained(original, history)

# ============================================================
# V40 guard - campaign context must beat finance family aliases.
# Example: previous "Eğitim kampanyalarını karşılaştır" + current
# "Peki sadece Albaraka ile Kuveyt Türk?" must remain a campaign comparison,
# not become "eğitim finansmanı".
# ============================================================
_resolve_followup_question_before_v40_campaign_guard = resolve_followup_question


def resolve_followup_question(question, history):
    original = str(question or "").strip()
    try:
        from src.competition_fast_router import detect_banks, normalize
        qn = normalize(original)
        banks = tuple(detect_banks(original))
        is_bank_narrowing = bool(banks) and any(x in qn for x in ("peki", "sadece", "yalniz", "yalnız"))
        if is_bank_narrowing:
            for previous in reversed(list(history or [])[-6:]):
                prev = str(previous or "").strip()
                pn = normalize(prev)
                if any(token in pn for token in ("kampanya", "kampanyasi", "kampanyalarini", "kampanyaları")):
                    bank_text = " ile ".join(banks)
                    return FollowupResolution(
                        original_question=original,
                        resolved_question=f"{prev} sadece {bank_text}",
                        used_context=True,
                        inherited_bank=bank_text,
                        inherited_product=None,
                    )
                if any(token in pn for token in ("finansman", "kredi")) and len(pn.split()) >= 3:
                    break
    except Exception:
        pass
    return _resolve_followup_question_before_v40_campaign_guard(original, history)
