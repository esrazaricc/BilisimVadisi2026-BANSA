# CHATBOT_ANSWER_EVIDENCE_SELECTOR_V2_2

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import unicodedata


SELECTION_SINGLE_DOCUMENT = (
    "single_document"
)

SELECTION_MULTI_DOCUMENT = (
    "multi_document"
)

SELECTION_EMPTY = (
    "empty"
)


_GENERIC_TOKENS = {
    "acikla",
    "aciklar",
    "avantaj",
    "avantajlari",
    "banka",
    "bankasi",
    "bilgi",
    "detay",
    "detaylari",
    "finans",
    "finansman",
    "finansmani",
    "finansmaninin",
    "firsat",
    "firsatlari",
    "hakkinda",
    "hangi",
    "kampanya",
    "kampanyasi",
    "kampanyasinin",
    "kampanyalari",
    "katilim",
    "nedir",
    "nelerdir",
    "neler",
    "ozellik",
    "ozellikleri",
    "sunuyor",
    "turk",
    "var",
    "ver",
}


# Canonical bank names are used only as strict
# entity locks when the user explicitly names a bank.
#
# The selector never guesses a bank from generic
# words such as "katilim" or "banka".

_BANK_ALIASES = (
    (
        "Albaraka Turk",
        (
            "albaraka turk",
            "albaraka",
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
        "Turkiye Finans",
        (
            "turkiye finans",
        ),
    ),
    (
        "Vakif Katilim",
        (
            "vakif katilim",
            "vakif",
        ),
    ),
    (
        "Ziraat Katilim",
        (
            "ziraat katilim",
            "ziraat",
        ),
    ),
    (
        "Turkiye Emlak Katilim",
        (
            "turkiye emlak katilim",
            "emlak katilim",
            "emlak",
        ),
    ),
    (
        "Dunya Katilim",
        (
            "dunya katilim",
            "dunya",
        ),
    ),
    (
        "Hayat Finans",
        (
            "hayat finans",
        ),
    ),
    (
        "TOM Katilim",
        (
            "tom katilim",
            "tom bank",
        ),
    ),
)


@dataclass(frozen=True)
class AnswerEvidenceSelection:

    mode: str

    items: tuple

    anchor_doc_id: str | None

    source_kind: str | None

    candidate_count: int

    selected_count: int

    dropped_count: int

    title_overlap: int

    reasons: tuple[str, ...]


def _normalize(
    value,
) -> str:

    text = str(
        value
        or ""
    )


    # Turkish dotless-i must be converted
    # before NFKD normalization.

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
        r"[^a-z0-9]+",
        " ",
        text,
    )


    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _normalize_bank_identity(
    value,
) -> str:
    """
    Normalize only bank identity comparisons.

    Dotted or spaced multi-letter initialisms
    are collapsed generically, while the
    ordinary query/RAG normalizer is unchanged.
    """

    raw = str(
        value
        or ""
    )

    raw = (
        raw
        .replace("\u0131", "i")
        .replace("\u0130", "I")
    )

    text = _normalize(
        raw
    )

    if not text:
        return ""

    parts = text.split()

    normalized_parts = []

    index = 0

    while index < len(parts):

        current = parts[
            index
        ]

        if (
            len(current) == 1
            and
            current.isalpha()
        ):

            letters = []
            cursor = index

            while (
                cursor < len(parts)
                and
                len(
                    parts[cursor]
                ) == 1
                and
                parts[cursor].isalpha()
            ):

                letters.append(
                    parts[cursor]
                )

                cursor += 1

            if len(letters) >= 2:

                normalized_parts.append(
                    "".join(
                        letters
                    )
                )

                index = cursor

                continue

        normalized_parts.append(
            current
        )

        index += 1

    return " ".join(
        normalized_parts
    )



def _tokens(
    value,
) -> set[str]:

    return {
        token
        for token in _normalize(
            value
        ).split()
        if (
            len(token) >= 3
            and token
            not in _GENERIC_TOKENS
        )
    }


def _metadata(
    item,
) -> dict:

    value = getattr(
        item,
        "metadata",
        None,
    )


    if isinstance(
        value,
        dict,
    ):

        return value


    return {}


def _item_family(
    item,
) -> str | None:

    value = (
        _metadata(
            item
        )
        .get(
            "product_family_key"
        )
    )


    if value is None:

        return None


    value = str(
        value
    ).strip()


    return (
        value
        if value
        else None
    )


def _detect_explicit_bank(
    question: str,
) -> str | None:

    normalized = _normalize(
        question
    )


    matches = []


    for canonical, aliases in (
        _BANK_ALIASES
    ):

        for alias in aliases:

            alias_normalized = (
                _normalize(
                    alias
                )
            )


            if (
                alias_normalized
                and
                re.search(
                    (
                        r"(?<![a-z0-9])"
                        + re.escape(
                            alias_normalized
                        )
                        + r"(?![a-z0-9])"
                    ),
                    normalized,
                )
            ):

                matches.append(
                    (
                        len(
                            alias_normalized
                        ),
                        canonical,
                    )
                )

                break


    if not matches:

        return None


    # Prefer the longest explicit alias.
    matches.sort(
        reverse=True
    )


    best_length = (
        matches[0][0]
    )


    best = {
        canonical
        for length, canonical
        in matches
        if length == best_length
    }


    if len(best) != 1:

        return None


    return next(
        iter(
            best
        )
    )


def _bank_matches(
    item,
    target_bank: str,
) -> bool:

    actual = _normalize_bank_identity(
        getattr(
            item,
            "bank_name",
            "",
        )
    )


    target = _normalize_bank_identity(
        target_bank
    )


    if actual == target:

        return True


    # Emlak may be represented as either
    # "Emlak Katilim" or
    # "Turkiye Emlak Katilim".

    if (
        target
        == "turkiye emlak katilim"
        and
        actual
        == "emlak katilim"
    ):

        return True


    if (
        actual
        == "turkiye emlak katilim"
        and
        target
        == "emlak katilim"
    ):

        return True


    return False


def _detect_attribute(
    question: str,
) -> str | None:

    text = _normalize(
        question
    )


    # Explicit broad-information intent must outrank
    # attribute words that can merely occur inside
    # a product or campaign title.
    #
    # Example:
    #
    # "... Vade Farksiz 3 taksit ... avantajlari nelerdir?"
    #
    # The user asks for benefits, not maturity.
    if any(
        term in text
        for term in (
            "avantajlari",
            "ozellikleri",
            "ne sunuyor",
            "neler sunuyor",
            "ne sunar",
            "neler sunar",
        )
    ):

        return "benefits"


    if any(
        term in text
        for term in (
            "kac ay",
            "kac taksit",
            "taksit sayisi",
            "vadesi ne",
            "vade nedir",
            "vade kac",
            "vade",
            "vadeli",
            "azami sure",
            "maksimum sure",
        )
    ):

        return "maturity"


    if any(
        term in text
        for term in (
            "kar payi",
            "kar orani",
            "oran nedir",
            "orani nedir",
        )
    ):

        return "rate"


    if any(
        term in text
        for term in (
            "tahsis ucreti",
            "ekspertiz ucreti",
            "ipotek ucreti",
            "masraf",
            "ucret",
        )
    ):

        return "fee"


    if any(
        term in text
        for term in (
            "kimler yararlanabilir",
            "kim yararlanabilir",
            "basvuru sarti",
            "basvuru sartlari",
            "kosullari neler",
            "sartlari neler",
            "uygun muyum",
        )
    ):

        return "eligibility"


    if any(
        term in text
        for term in (
            "nasil basvur",
            "nereden basvur",
            "basvuru nasil",
        )
    ):

        return "application"


    if any(
        term in text
        for term in (
            "limit",
            "en fazla ne kadar",
            "maksimum tutar",
            "azami tutar",
        )
    ):

        return "limit"


    if any(
        term in text
        for term in (
            "son tarih",
            "ne zamana kadar",
            "hangi tarihe kadar",
            "gecerlilik tarihi",
        )
    ):

        return "date"


    return None


def _structured_fields(
    item,
) -> dict:

    value = (
        _metadata(
            item
        )
        .get(
            "structured_fields"
        )
    )


    if isinstance(
        value,
        dict,
    ):

        return value


    return {}


def _nested_fee_rules(
    structured: dict,
) -> list[dict]:

    if not isinstance(
        structured,
        dict,
    ):
        return []

    direct = structured.get(
        "fee_rules"
    )

    if isinstance(
        direct,
        list,
    ):
        return [
            row
            for row in direct
            if isinstance(
                row,
                dict,
            )
        ]

    raw = structured.get(
        "finance_rules_json"
    )

    if raw in {
        None,
        "",
    }:
        return []

    if isinstance(
        raw,
        dict,
    ):

        rules = raw

    else:

        try:

            rules = json.loads(
                str(
                    raw
                )
            )

        except Exception:

            return []

    if not isinstance(
        rules,
        dict,
    ):
        return []

    fee_rules = rules.get(
        "fee_rules"
    )

    if not isinstance(
        fee_rules,
        list,
    ):
        return []

    return [
        row
        for row in fee_rules
        if isinstance(
            row,
            dict,
        )
    ]



def _attribute_strength(
    item,
    attribute: str,
) -> int:

    text = _normalize(
        getattr(
            item,
            "evidence_text",
            "",
        )
    )

    section = _normalize(
        getattr(
            item,
            "section_type",
            "",
        )
    )

    heading = _normalize(
        getattr(
            item,
            "section_heading",
            "",
        )
    )

    structured = (
        _structured_fields(
            item
        )
    )


    score = 0


    if attribute == "maturity":

        maximum = (
            structured.get(
                "maximum_maturity_months"
            )
        )


        if maximum not in {
            None,
            "",
        }:

            score += 100


        if re.search(
            r"\b\d{1,3}\s*ay[a-z]*\b",
            text,
        ):

            score += 70


        if any(
            term in text
            for term in (
                "aya kadar",
                "maksimum vade",
                "azami vade",
                "vade suresi",
                "vadeyle",
            )
        ):

            score += 30


        if section in {
            "features",
            "maturity",
            "terms",
        }:

            score += 10


    elif attribute == "rate":

        if (
            "kar payi"
            in text
            or "kar orani"
            in text
        ):

            score += 50


        if (
            "%"
            in str(
                getattr(
                    item,
                    "evidence_text",
                    "",
                )
            )
        ):

            score += 30


        if section in {
            "pricing",
            "rates",
        }:

            score += 20


    elif attribute == "fee":

        if any(
            term in text
            for term in (
                "tahsis ucreti",
                "ekspertiz ucreti",
                "ipotek",
                "komisyon",
                "masraf",
                "ucret",
            )
        ):

            score += 50


        fee_structured_keys = {
            str(
                key
            ).casefold()
            for key in structured
        }


        nested_fee_rules = (
            _nested_fee_rules(
                structured
            )
        )


        if nested_fee_rules:

            # Canonical structured fee data must outrank
            # generic product body text for hard fee queries.
            #
            # Example:
            # finance_rules_json
            #   -> fee_rules
            #       -> appraisal / allocation / mortgage
            score += 80


        # Structured fee metadata is valid grounding
        # even when the source sentence itself does not
        # contain a fee amount.
        #
        # Example:
        # allocation_fee_waived = False
        # commission_fee_waived = False
        # insurance_fee_waived = False

        if any(
            (
                "fee"
                in key
                or
                "commission"
                in key
                or
                "allocation"
                in key
                or
                "insurance"
                in key
                or
                "expert"
                in key
                or
                "mortgage"
                in key
            )
            for key
            in fee_structured_keys
        ):

            score += 40


    elif attribute == "eligibility":

        if any(
            term in text
            for term in (
                "kimler yararlanabilir",
                "yararlanabilir",
                "basvuru sartlari",
                "basvuru kosullari",
                "gelir belgesi",
                "18 yas",
            )
        ):

            score += 50


        if section in {
            "eligibility",
            "requirements",
        }:

            score += 30


    elif attribute == "application":

        if "basvur" in text:

            score += 50


        if section in {
            "application",
            "application_channels",
        }:

            score += 30


    elif attribute == "limit":

        if any(
            term in text
            for term in (
                "limit",
                "maksimum tutar",
                "azami tutar",
                "finansman tutari",
            )
        ):

            score += 50


        if any(
            key in structured
            for key in (
                "maximum_amount",
                "product_limit",
                "maximum_financing_ratio",
            )
        ):

            score += 30


    elif attribute == "date":

        if any(
            term in text
            for term in (
                "tarihleri arasinda",
                "tarihine kadar",
                "gecerlidir",
                "kampanya donemi",
            )
        ):

            score += 50


    elif attribute == "benefits":

        if any(
            term in text
            for term in (
                "avantaj",
                "fayda",
                "imkan",
                "firsat",
            )
        ):

            score += 40


        if section in {
            "benefits",
            "features",
        }:

            score += 40


    if heading:

        if (
            attribute
            == "maturity"
            and "vade" in heading
        ):

            score += 20


        if (
            attribute
            == "benefits"
            and (
                "avantaj"
                in heading
                or "ozellik"
                in heading
            )
        ):

            score += 20


    return score


def _is_safe_item(
    item,
    expected_source_kind,
) -> bool:

    if not str(
        getattr(
            item,
            "evidence_text",
            "",
        )
        or ""
    ).strip():

        return False


    if not str(
        getattr(
            item,
            "source_url",
            "",
        )
        or ""
    ).strip():

        return False


    policy = (
        str(
            getattr(
                item,
                "grounding_policy",
                "",
            )
            or ""
        )
        .strip()
        .casefold()
    )


    if policy not in {
        "",
        "allow",
        "structured_preferred",
    }:

        return False


    # "structured_preferred" is a valid
    # grounding policy for canonical BANSA
    # product evidence. It is accepted only
    # when the evidence really carries a
    # structured_fields payload.
    #
    # This prevents an arbitrary text chunk
    # from gaining trust merely by declaring
    # the structured_preferred policy.

    if (
        policy
        == "structured_preferred"
    ):

        metadata = _metadata(
            item
        )

        structured = metadata.get(
            "structured_fields"
        )

        if not (
            isinstance(
                structured,
                dict,
            )
            and structured
        ):

            return False


    if bool(
        getattr(
            item,
            "grounding_limited",
            False,
        )
    ):

        return False


    if expected_source_kind:

        actual = (
            str(
                getattr(
                    item,
                    "source_kind",
                    "",
                )
                or ""
            )
            .strip()
            .casefold()
        )


        expected = (
            str(
                expected_source_kind
            )
            .strip()
            .casefold()
        )


        if actual != expected:

            return False


    return True


def _empty_selection(
    *,
    raw_items,
    expected_source_kind,
    reasons,
) -> AnswerEvidenceSelection:

    return AnswerEvidenceSelection(
        mode=SELECTION_EMPTY,
        items=tuple(),
        anchor_doc_id=None,
        source_kind=(
            expected_source_kind
        ),
        candidate_count=len(
            raw_items
        ),
        selected_count=0,
        dropped_count=len(
            raw_items
        ),
        title_overlap=0,
        reasons=tuple(
            reasons
        ),
    )


def select_answer_evidence(
    pack,
    *,
    question: str,
    expected_source_kind: str | None = None,
    family: str | None = None,
) -> AnswerEvidenceSelection:

    """
    Strict answer-generation boundary.

    Order:

    1. Safe/source-kind filtering.
    2. Explicit bank lock.
    3. Product-family lock.
    4. Requested-attribute lock.
    5. Existing document-title targeting.

    If an explicitly named bank or product
    family has no matching evidence, the
    selector fails closed. It never substitutes
    another bank or another product.
    """


    raw_items = tuple(
        getattr(
            pack,
            "items",
            (),
        )
    )


    safe_items = tuple(
        item
        for item in raw_items
        if _is_safe_item(
            item,
            expected_source_kind,
        )
    )


    if not safe_items:

        return _empty_selection(
            raw_items=raw_items,
            expected_source_kind=(
                expected_source_kind
            ),
            reasons=(
                "no_safe_answer_evidence",
            ),
        )


    lock_reasons = []


    # ========================================================
    # STRICT BANK LOCK
    # ========================================================

    target_bank = (
        _detect_explicit_bank(
            question
        )
    )


    if target_bank is not None:

        bank_metadata_available = any(
            bool(
                _normalize(
                    getattr(
                        item,
                        "bank_name",
                        "",
                    )
                )
            )
            for item in safe_items
        )


        if bank_metadata_available:

            bank_items = tuple(
                item
                for item in safe_items
                if _bank_matches(
                    item,
                    target_bank,
                )
            )


            if not bank_items:

                return _empty_selection(
                    raw_items=raw_items,
                    expected_source_kind=(
                        expected_source_kind
                    ),
                    reasons=(
                        "explicit_bank_lock",
                        "explicit_bank_has_no_evidence",
                    ),
                )


            safe_items = (
                bank_items
            )


            lock_reasons.append(
                "explicit_bank_lock"
            )


        else:

            # Compatibility path for legacy or
            # synthetic evidence that does not
            # expose bank metadata.
            #
            # Real BANSA evidence contains
            # bank_name, so production evidence
            # still receives the HARD bank lock.

            lock_reasons.append(
                "bank_lock_skipped_no_bank_metadata"
            )


    # ========================================================
    # STRICT PRODUCT FAMILY LOCK
    # ========================================================

    expected_kind = (
        str(
            expected_source_kind
            or ""
        )
        .strip()
        .casefold()
    )


    if (
        family
        and
        expected_kind
        == "standard_product"
    ):

        family_items = tuple(
            item
            for item in safe_items
            if _item_family(
                item
            )
            == str(
                family
            )
        )


        if not family_items:

            return _empty_selection(
                raw_items=raw_items,
                expected_source_kind=(
                    expected_source_kind
                ),
                reasons=tuple(
                    lock_reasons
                    + [
                        "strict_product_family_lock",
                        "product_family_has_no_evidence",
                    ]
                ),
            )


        safe_items = (
            family_items
        )


        lock_reasons.append(
            "strict_product_family_lock"
        )


    # ========================================================
    # REQUESTED ATTRIBUTE LOCK
    # ========================================================

    attribute = (
        _detect_attribute(
            question
        )
    )


    # For an explicitly targeted bank, or when
    # only one bank remains after filtering,
    # choose only the strongest evidence for
    # the requested attribute.
    #
    # This avoids turning broad multi-bank
    # questions into a single-bank answer.

    remaining_banks = {
        _normalize(
            getattr(
                item,
                "bank_name",
                "",
            )
        )
        for item in safe_items
    }


    if (
        attribute is not None
        and (
            target_bank is not None
            or len(
                remaining_banks
            )
            <= 1
        )
    ):

        attribute_scores = {
            id(item):
                _attribute_strength(
                    item,
                    attribute,
                )
            for item in safe_items
        }


        best_attribute_score = max(
            attribute_scores.values(),
            default=0,
        )


        hard_attributes = {
            "maturity",
            "rate",
            "fee",
            "eligibility",
            "application",
            "limit",
            "date",
        }


        if best_attribute_score <= 0:

            if attribute in hard_attributes:

                return _empty_selection(
                    raw_items=raw_items,
                    expected_source_kind=(
                        expected_source_kind
                    ),
                    reasons=tuple(
                        lock_reasons
                        + [
                            (
                                "strict_attribute_lock:"
                                + attribute
                            ),
                            (
                                "requested_attribute_"
                                "has_no_evidence"
                            ),
                        ]
                    ),
                )


            lock_reasons.append(
                (
                    "soft_attribute_no_direct_match:"
                    + attribute
                )
            )


        else:

            safe_items = tuple(
                item
                for item in safe_items
                if attribute_scores[
                    id(
                        item
                    )
                ]
                == best_attribute_score
            )


            lock_reasons.append(
                (
                    (
                        "strict_attribute_lock:"
                        if attribute
                        in hard_attributes
                        else
                        "soft_attribute_preference:"
                    )
                    + attribute
                )
            )


    # ========================================================
    # DOCUMENT TARGETING
    # ========================================================

    query_tokens = _tokens(
        question
    )


    document_items = {}

    document_order = []


    for item in safe_items:

        doc_id = str(
            getattr(
                item,
                "doc_id",
                "",
            )
            or ""
        )


        # Fail-safe key when an evidence item
        # has no doc_id.

        if not doc_id:

            doc_id = (
                _normalize(
                    getattr(
                        item,
                        "bank_name",
                        "",
                    )
                )
                + "|"
                + _normalize(
                    getattr(
                        item,
                        "document_title",
                        "",
                    )
                )
                + "|"
                + _normalize(
                    getattr(
                        item,
                        "source_url",
                        "",
                    )
                )
            )


        if doc_id not in document_items:

            document_items[
                doc_id
            ] = []

            document_order.append(
                doc_id
            )


        document_items[
            doc_id
        ].append(
            item
        )


    scores = {}


    for doc_id in document_order:

        first = document_items[
            doc_id
        ][0]


        title_tokens = _tokens(
            getattr(
                first,
                "document_title",
                "",
            )
        )


        scores[
            doc_id
        ] = len(
            query_tokens
            & title_tokens
        )


    best_score = max(
        scores.values(),
        default=0,
    )


    best_docs = [
        doc_id
        for doc_id in document_order
        if scores[
            doc_id
        ]
        == best_score
    ]


    if (
        best_score > 0
        and
        len(
            best_docs
        )
        == 1
    ):

        anchor_doc_id = (
            best_docs[0]
        )


        selected = tuple(
            document_items[
                anchor_doc_id
            ]
        )


        return AnswerEvidenceSelection(
            mode=(
                SELECTION_SINGLE_DOCUMENT
            ),
            items=selected,
            anchor_doc_id=(
                anchor_doc_id
            ),
            source_kind=(
                expected_source_kind
            ),
            candidate_count=len(
                raw_items
            ),
            selected_count=len(
                selected
            ),
            dropped_count=(
                len(
                    raw_items
                )
                - len(
                    selected
                )
            ),
            title_overlap=(
                best_score
            ),
            reasons=tuple(
                lock_reasons
                + [
                    "unique_title_target",
                    "same_document_lock",
                ]
            ),
        )


    return AnswerEvidenceSelection(
        mode=(
            SELECTION_MULTI_DOCUMENT
        ),
        items=safe_items,
        anchor_doc_id=None,
        source_kind=(
            expected_source_kind
        ),
        candidate_count=len(
            raw_items
        ),
        selected_count=len(
            safe_items
        ),
        dropped_count=(
            len(
                raw_items
            )
            - len(
                safe_items
            )
        ),
        title_overlap=(
            best_score
        ),
        reasons=tuple(
            lock_reasons
            + [
                (
                    "no_unique_title_target"
                    if best_score > 0
                    else
                    "broad_or_generic_query"
                ),
            ]
        ),
    )
