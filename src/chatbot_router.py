# CHATBOT_ROUTER_V1

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
import unicodedata


ROUTE_CAMPAIGN_RAG = "campaign_rag"
ROUTE_PRODUCT_RAG = "product_rag"
ROUTE_FINANCE_COMPARE = "finance_compare"
ROUTE_FINANCE_FACT = "finance_fact"
ROUTE_HYBRID = "hybrid"
ROUTE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ChatbotRouteDecision:
    route: str
    normalized_question: str
    family: str | None = None
    purpose: str | None = None
    amount: Decimal | None = None
    maturity: int | None = None
    finance_attribute: str | None = None
    missing_fields: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    bank_names: tuple[str, ...] = ()

    @property
    def ready_for_finance_compare(self) -> bool:
        return (
            self.route in {
                ROUTE_FINANCE_COMPARE,
                ROUTE_HYBRID,
            }
            and not self.missing_fields
            and self.family is not None
            and self.amount is not None
            and self.maturity is not None
        )


def _normalize(value: str) -> str:
    text = str(value or "").strip().casefold()

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
        if not unicodedata.combining(ch)
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


_RUNTIME_BANK_ALIAS_CACHE = None


def _runtime_bank_alias_catalog():
    """
    Return:
        (
            (
                canonical_runtime_bank,
                (normalized_alias, ...),
            ),
            ...
        )

    Canonical bank names come from the validated
    finance runtime snapshot.

    Existing follow-up aliases are used only as
    additional spelling/name variants.
    """

    global _RUNTIME_BANK_ALIAS_CACHE

    if (
        _RUNTIME_BANK_ALIAS_CACHE
        is not None
    ):

        return (
            _RUNTIME_BANK_ALIAS_CACHE
        )


    from src.finance_runtime_repository import (
        get_standard_products,
    )

    from src.chat_followup_context import (
        _BANKS as followup_banks,
        _normalize_bank_identity,
    )


    products = (
        get_standard_products()
    )


    runtime_names = []


    if (
        products is not None
        and
        not products.empty
        and
        "bank_name"
        in products.columns
    ):

        for value in products[
            "bank_name"
        ].tolist():

            name = str(
                value
                or ""
            ).strip()

            if (
                name
                and
                name not in runtime_names
            ):

                runtime_names.append(
                    name
                )


    catalog = []


    for runtime_name in runtime_names:

        runtime_key = (
            _normalize_bank_identity(
                runtime_name
            )
        )

        aliases = {
            runtime_key,
        }


        for (
            canonical,
            defined_aliases,
        ) in followup_banks:

            definition_keys = {
                _normalize_bank_identity(
                    canonical
                ),
            }

            definition_keys.update(
                _normalize_bank_identity(
                    alias
                )
                for alias
                in defined_aliases
            )


            if (
                runtime_key
                in definition_keys
            ):

                aliases.update(
                    definition_keys
                )


        aliases.discard(
            ""
        )


        catalog.append(
            (
                runtime_name,
                tuple(
                    sorted(
                        aliases,
                        key=len,
                        reverse=True,
                    )
                ),
            )
        )


    _RUNTIME_BANK_ALIAS_CACHE = (
        tuple(
            catalog
        )
    )


    return (
        _RUNTIME_BANK_ALIAS_CACHE
    )


def _extract_bank_names(
    question: str,
) -> tuple[str, ...]:
    """
    Detect explicitly named banks.

    Empty tuple means:
        no explicit bank restriction
        -> compare all eligible banks.

    One/multiple names means:
        restrict finance comparison to
        exactly those banks.
    """

    from src.chat_followup_context import (
        _normalize_bank_identity,
    )


    normalized = (
        _normalize_bank_identity(
            question
        )
    )


    if not normalized:

        return tuple()


    matches = []


    for (
        canonical,
        aliases,
    ) in _runtime_bank_alias_catalog():

        first_position = None


        for alias in aliases:

            if not alias:

                continue


            match = re.search(
                (
                    r"(?<![a-z0-9])"
                    + re.escape(
                        alias
                    )
                    + r"(?![a-z0-9])"
                ),
                normalized,
            )


            if match is None:

                continue


            if (
                first_position is None
                or
                match.start()
                < first_position
            ):

                first_position = (
                    match.start()
                )


        if first_position is not None:

            matches.append(
                (
                    first_position,
                    canonical,
                )
            )


    matches.sort(
        key=lambda item:
        item[0]
    )


    return tuple(
        canonical
        for _position, canonical
        in matches
    )



def _extract_amount(
    question: str,
) -> Decimal | None:

    text = _normalize(question)

    patterns = [
        r"\b(\d+(?:[.,]\d+)?)\s*(bin|k)\s*(?:tl|try)?\b",
        r"\b(\d{1,3}(?:[.\s]\d{3})+|\d+)\s*(?:tl|try)\b",
    ]

    for index, pattern in enumerate(patterns):

        match = re.search(
            pattern,
            text,
            flags=re.I,
        )

        if not match:
            continue

        raw = match.group(1)

        if index == 0:
            raw = raw.replace(",", ".")
            return (
                Decimal(raw)
                * Decimal("1000")
            )

        normalized = (
            raw
            .replace(".", "")
            .replace(" ", "")
        )

        return Decimal(normalized)

    return None


def _extract_maturity(
    question: str,
) -> int | None:

    text = _normalize(question)

    match = re.search(
        r"\b(\d{1,3})\s*ay\b",
        text,
    )

    if not match:
        return None

    value = int(match.group(1))

    if value <= 0:
        return None

    return value


def _detect_family(
    question: str,
) -> str | None:

    text = _normalize(question)

    mappings = [
        (
            (
                "ihtiyac finansmani",
                "ihtiyac finansman",
                "ihtiyac kredisi",
            ),
            "ihtiyac_finansmani",
        ),
        (
            (
                "konut finansmani",
                "ev finansmani",
                "konut kredisi",
            ),
            "konut_finansmani",
        ),
        (
            (
                "tasit finansmani",
                "arac finansmani",
                "otomobil finansmani",
                "tasit kredisi",
            ),
            "arac_finansmani",
        ),
    ]

    for terms, family in mappings:
        if any(
            term in text
            for term in terms
        ):
            return family

    return None


def _detect_purpose(
    question: str,
    family: str | None,
) -> str | None:

    if family != "ihtiyac_finansmani":
        return None

    text = _normalize(question)

    if any(
        term in text
        for term in (
            "motosiklet",
            "motor finansmani",
            "motor al",
        )
    ):
        return "motosiklet"

    if any(
        term in text
        for term in (
            "ev ofis",
            "ev/ofis",
            "ofis gerecleri",
            "ev gerecleri",
            "mobilya",
        )
    ):
        return "ev_ofis_gerecleri"

    if any(
        term in text
        for term in (
            "genel ihtiyac",
            "nakit ihtiyac",
            "bireysel ihtiyac",
        )
    ):
        return "genel_ihtiyac"

    return None



def _detect_finance_fact_attribute(
    question: str,
) -> str | None:

    text = _normalize(
        question
    )

    if any(
        term in text
        for term in (
            "tahsis ucreti",
            "tahsis masrafi",
        )
    ):
        return "allocation_fee"

    if any(
        term in text
        for term in (
            "ekspertiz ucreti",
            "ekspertiz masrafi",
            "ekspertiz",
        )
    ):
        return "appraisal_fee"

    if any(
        term in text
        for term in (
            "ipotek ucreti",
            "ipotek masrafi",
            "tasinmaz rehin",
            "rehin ucreti",
        )
    ):
        return "mortgage_fee"

    if any(
        term in text
        for term in (
            "hangi masraflar",
            "masraflar neler",
            "masraflari neler",
            "ucretler neler",
            "ucretleri neler",
        )
    ):
        return "fee_summary"

    if any(
        term in text
        for term in (
            "kar payi",
            "kar orani",
        )
    ):
        return "profit_share_rate"

    if any(
        term in text
        for term in (
            "finansman orani",
            "kredi deger orani",
        )
    ):
        return "financing_ratio"

    if any(
        term in text
        for term in (
            "kac aya kadar",
            "azami vade",
            "maksimum vade",
            "vade suresi",
            "vadesi nedir",
        )
    ):
        return "maturity"

    if any(
        term in text
        for term in (
            "maksimum tutar",
            "azami tutar",
            "en fazla ne kadar",
            "finansman limiti",
            "limit ne kadar",
        )
    ):
        return "maximum_amount"

    return None


def _route_question_before_inflection_v2(
    question: str,
) -> ChatbotRouteDecision:

    normalized = _normalize(question)

    if not normalized:
        return ChatbotRouteDecision(
            route=ROUTE_UNKNOWN,
            normalized_question=normalized,
            reasons=("empty_question",),
        )

    bank_names = (
        _extract_bank_names(
            question
        )
    )

    amount = _extract_amount(question)
    maturity = _extract_maturity(question)
    family = _detect_family(question)
    purpose = _detect_purpose(
        question,
        family,
    )

    finance_attribute = (
        _detect_finance_fact_attribute(
            question
        )
    )

    has_campaign_signal = any(
        term in normalized
        for term in (
            "kampanya",
            "kampanyasi",
            "kampanyalari",
            "indirim",
            "puan",
            "nakit iade",
            "odul",
            "firsat",
            "harcama",
        )
    )

    has_finance_product_signal = any(
        term in normalized
        for term in (
            "finansmani",
            "finansman",
            "vade",
            "kar payi",
            "oran",
            "tahsis ucreti",
            "ekspertiz ucreti",
            "ipotek ucreti",
            "masraf",
            "ucret",
            "limit",
            "finansman orani",
        )
    )

    has_product_info_signal = any(
        term in normalized
        for term in (
            "avantaj",
            "ozellik",
            "neler sun",
            "neler sagla",
        )
    )

    has_product_signal = (
        has_finance_product_signal
        or has_product_info_signal
    )

    has_compare_signal = (
        any(
            term in normalized
            for term in (
                "hangi banka",
                "hangisi",
                "karsilastir",
                "karsilastirma",
                "daha uygun",
                "en uygun",
                "en dusuk",
                "en avantajli",
                "sirala",
            )
        )
        or (
            len(bank_names) >= 2
            and any(
                term in normalized
                for term in (
                    "daha avantajli",
                    "daha iyi",
                    "daha mantikli",
                )
            )
        )
    )

    has_finance_context = (
        has_finance_product_signal
        or family is not None
        or has_compare_signal
    )

    wants_numeric_finance = (
        (
            (
                amount is not None
                or maturity is not None
            )
            and has_finance_context
        )
        or (
            has_finance_product_signal
            and has_compare_signal
        )
    )

    # CAMPAIGN_DETAIL_LOCK_V1
    #
    # A number, maturity term or profit-share phrase may belong
    # to the campaign itself. Examples:
    #
    #   "... kampanyasinda kar payi nedir?"
    #   "... kampanyasinin vadesi kac ay?"
    #   "... kampanyada destek tutari nedir?"
    #
    # These must stay inside campaign RAG instead of opening a
    # finance calculation merely because the campaign title/body
    # contains an amount, "vade" or "kar payi".
    #
    # Explicit comparisons remain outside this lock so genuine
    # campaign + finance hybrid requests keep working.
    campaign_detail_lock = (
        has_campaign_signal
        and not has_compare_signal
        and any(
            marker in normalized
            for marker in (
                "kampanyasi",
                "kampanyanin",
                "kampanyada",
            )
        )
    )

    reasons: list[str] = []

    if has_campaign_signal:
        reasons.append(
            "campaign_signal"
        )

    if campaign_detail_lock:
        reasons.append(
            "campaign_detail_lock"
        )

    if has_product_signal:
        reasons.append(
            "product_signal"
        )

    if finance_attribute is not None:
        reasons.append(
            "finance_fact_attribute:"
            + finance_attribute
        )

    if has_compare_signal:
        reasons.append(
            "comparison_signal"
        )

    if amount is not None:
        reasons.append(
            "amount_detected"
        )

    if maturity is not None:
        reasons.append(
            "maturity_detected"
        )

    if family is not None:
        reasons.append(
            "finance_family_detected"
        )

    if campaign_detail_lock:
        route = ROUTE_CAMPAIGN_RAG

    elif (
        has_campaign_signal
        and wants_numeric_finance
    ):
        route = ROUTE_HYBRID

    elif (
        finance_attribute is not None
        and not has_campaign_signal
        and not has_compare_signal
    ):
        route = ROUTE_FINANCE_FACT

    elif wants_numeric_finance:
        route = ROUTE_FINANCE_COMPARE

    elif has_campaign_signal:
        route = ROUTE_CAMPAIGN_RAG

    elif has_product_signal:
        route = ROUTE_PRODUCT_RAG

    else:
        route = ROUTE_UNKNOWN

    missing: list[str] = []

    if route in {
        ROUTE_FINANCE_COMPARE,
        ROUTE_HYBRID,
    }:

        if family is None:
            missing.append(
                "family"
            )

        if amount is None:
            missing.append(
                "amount"
            )

        if maturity is None:
            missing.append(
                "maturity"
            )

        if (
            family
            == "ihtiyac_finansmani"
            and purpose is None
        ):
            missing.append(
                "purpose"
            )

    return ChatbotRouteDecision(
        route=route,
        normalized_question=normalized,
        family=family,
        purpose=purpose,
        amount=amount,
        maturity=maturity,
        bank_names=tuple(
            bank_names
        ),
        finance_attribute=(
            finance_attribute
        ),
        missing_fields=tuple(
            missing
        ),
        reasons=tuple(
            reasons
        ),
    )


# ============================================================
# ROUTER_FINANCE_FAMILY_INFLECTION_REPAIR_V2
# ============================================================

def _detect_inflected_finance_family_v2(
    question: str,
) -> str | None:
    """
    Narrow Turkish morphology fallback.

    It is consulted only when the existing router has already
    selected finance_compare but family is unresolved.

    Therefore this helper cannot convert product_rag,
    campaign_rag, finance_fact or other routes into a finance
    comparison.
    """

    text = _normalize(
        question
    )


    patterns = (
        (
            (
                "konut finansmanlar",
            ),
            "konut_finansmani",
        ),

        (
            (
                "arac finansmanlar",
                "tasit finansmanlar",
            ),
            "arac_finansmani",
        ),

        (
            (
                "arsa finansmanlar",
            ),
            "arsa_finansmani",
        ),

        (
            (
                "is yeri finansmanlar",
                "isyeri finansmanlar",
            ),
            "isyeri_finansmani",
        ),

        (
            (
                "ihtiyac finansmanlar",
            ),
            "ihtiyac_finansmani",
        ),

        (
            (
                "alisveris finansmanlar",
            ),
            "alisveris_finansmani",
        ),
    )


    matches = []


    for terms, family in patterns:

        if any(
            term in text
            for term in terms
        ):

            matches.append(
                family
            )


    matches = tuple(
        dict.fromkeys(
            matches
        )
    )


    # Multiple family signals -> fail closed.
    if len(
        matches
    ) != 1:

        return None


    return matches[
        0
    ]


def route_question(
    question: str,
):
    """
    Preserve all existing routing decisions.

    Repair family only when:
      route == finance_compare
      family is missing
      exactly one plural/inflected family stem is present
    """

    from dataclasses import (
        fields as _dataclass_fields,
        is_dataclass as _is_dataclass,
        replace as _dataclass_replace,
    )


    decision = (
        _route_question_before_inflection_v2(
            question
        )
    )


    # Never touch other routes.
    if (
        str(
            getattr(
                decision,
                "route",
                "",
            )
        )
        != "finance_compare"
    ):

        return decision


    # Existing resolved family always wins.
    if getattr(
        decision,
        "family",
        None,
    ):

        return decision


    family = (
        _detect_inflected_finance_family_v2(
            question
        )
    )


    if family is None:

        return decision


    if not _is_dataclass(
        decision
    ):

        return decision


    field_names = {
        field.name
        for field
        in _dataclass_fields(
            decision
        )
    }


    updates = {
        "family":
            family,
    }


    if (
        "missing_fields"
        in field_names
    ):

        current_missing = tuple(
            getattr(
                decision,
                "missing_fields",
                (),
            )
            or ()
        )


        updates[
            "missing_fields"
        ] = tuple(
            value
            for value
            in current_missing
            if str(
                value
            )
            .strip()
            .casefold()
            not in {
                "family",
                "finance_family",
                "finansman_turu",
            }
        )


    return _dataclass_replace(
        decision,
        **updates,
    )

# ============================================================
# CAMPAIGN_COMPARE_ROUTER_V1_3
# ============================================================

from dataclasses import replace as _campaign_compare_replace_v1_3


ROUTE_CAMPAIGN_COMPARE = "campaign_compare"


_route_question_before_campaign_compare_v1_3 = (
    route_question
)


def _campaign_compare_intent_v1_3(
    question: str,
) -> bool:

    text = _normalize(
        question
    )

    has_compare_intent = (
        "karsilastir" in text
        or
        "en avantajli" in text
        or
        "en uygun" in text
        or
        "en iyi" in text
        or (
            "hangi banka" in text
            and any(
                value in text
                for value in (
                    "avantajli",
                    "uygun",
                    "iyi",
                )
            )
        )
        or (
            "hangisi" in text
            and any(
                value in text
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

    campaign_topic_signals = (
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
        "amazon",
        "hepsiburada",
        "trendyol",
        "idefix",

        "yeni musteri",
        "musteri ol",
        "davet et",
    )

    return any(
        signal in text
        for signal
        in campaign_topic_signals
    )


def _explicit_finance_context_v1_3(
    question: str,
) -> bool:

    text = _normalize(
        question
    )

    return any(
        signal in text
        for signal in (
            "finansman",
            "kar payi",
            "aylik taksit",
            "toplam geri odeme",
            "geri odeme",
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
    )


def route_question(
    question: str,
):

    decision = (
        _route_question_before_campaign_compare_v1_3(
            question
        )
    )

    if not _campaign_compare_intent_v1_3(
        question
    ):

        return decision

    current_route = str(
        getattr(
            decision,
            "route",
            "",
        )
    )

    # Finance always keeps priority.
    if current_route in {
        "finance_compare",
        "finance_fact",
    }:

        return decision

    if _explicit_finance_context_v1_3(
        question
    ):

        return decision

    # product_rag is intentionally allowed here.
    #
    # Some natural campaign questions such as:
    #
    # "Market alisverisinde hangi banka
    # daha avantajli?"
    #
    # are classified by the historical router as
    # product_rag because they do not explicitly contain
    # the word "kampanya".
    #
    # Conversion still requires BOTH:
    #   1. explicit comparison intent
    #   2. a campaign-domain topic signal
    #
    # Therefore ordinary product questions remain untouched.
    if current_route not in {
        "campaign_rag",
        "product_rag",
        "unknown",
        "hybrid",
    }:

        return decision

    old_reasons = tuple(
        getattr(
            decision,
            "reasons",
            (),
        )
    )

    return _campaign_compare_replace_v1_3(
        decision,
        route=ROUTE_CAMPAIGN_COMPARE,
        missing_fields=tuple(),
        reasons=(
            old_reasons
            + (
                "campaign_compare_signal",
                "campaign_compare_product_rag_bridge",
            )
        ),
    )
