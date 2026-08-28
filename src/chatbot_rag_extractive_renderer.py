# CHATBOT_RAG_EXTRACTIVE_RENDERER_V1_2

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


_ALLOWED_ROUTES = {
    "campaign_rag",
    "product_rag",
    "hybrid",
}


_STOPWORDS = {
    "acaba",
    "avantaj",
    "avantajlari",
    "bana",
    "banka",
    "bankasi",
    "bilgi",
    "bir",
    "bu",
    "da",
    "de",
    "icin",
    "ile",
    "finansman",
    "finansmani",
    "hangi",
    "hakkinda",
    "kampanya",
    "kampanyasi",
    "kampanyalari",
    "katilim",
    "mi",
    "midir",
    "nedir",
    "nelerdir",
    "olan",
    "olarak",
    "sunuyor",
    "turk",
    "var",
    "ve",
}


@dataclass(frozen=True)
class ExtractiveSentence:

    evidence_id: str

    bank_name: str

    document_title: str

    source_kind: str

    section_type: str

    sentence: str

    score: int

    source_url: str

    checked_at: str | None


@dataclass(frozen=True)
class ExtractiveRagAnswer:

    text: str

    evidence_ids: tuple[str, ...]

    document_count: int

    sentence_count: int

    source_kind: str | None

    reasons: tuple[str, ...]


def _normalize(
    value,
) -> str:

    text = str(
        value
        or ""
    )


    # Turkish dotless-i does not decompose
    # into ASCII with NFKD. Convert Turkish
    # letters explicitly before normalization.
    #
    # Example:
    #   "?al??anlar?na"
    #       -> "Calisanlarina"
    #
    # Without this mapping:
    #   "?al??anlar?na"
    #       -> "cal sanlar na"
    #
    # which breaks target-audience matching.

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
            not in _STOPWORDS
        )
    }


def _split_sentences(
    value,
) -> tuple[str, ...]:

    text = re.sub(
        r"\s+",
        " ",
        str(
            value
            or ""
        ),
    ).strip()


    if not text:

        return tuple()


    parts = re.split(
        (
            r"(?<=[!?])\s+"
            r"|"
            r"(?<=\.)\s+(?=[A-Z\u00c7\u011e\u0130\u00d6\u015e\u00dc])"
        ),
        text,
    )


    result = []


    for part in parts:

        sentence = (
            part.strip()
        )


        if not sentence:
            continue


        if len(sentence) < 15:
            continue


        result.append(
            sentence
        )


    return tuple(
        result
    )


def _section_priority(
    section_type: str,
    question: str,
) -> int:

    section = _normalize(
        section_type
    )

    question_normalized = _normalize(
        question
    )


    if (
        "avantaj"
        in question_normalized
        or "ozellik"
        in question_normalized
    ):

        if section == "benefits":
            return 10

        if section == "overview":
            return 6


    if "kampanya" in question_normalized:

        if section in {
            "campaign_terms",
            "campaign_details",
        }:

            return 10

        if section == "overview":
            return 5


    if section == "definition":
        return 6

    if section == "overview":
        return 5

    if section == "benefits":
        return 5

    if section == "body":
        return 2


    return 1


def _clean_sentence(
    value,
) -> str:

    text = str(
        value
        or ""
    )

    text = (
        text
        .replace(
            "\u00d7",
            " ",
        )
        .replace(
            "\u00a0",
            " ",
        )
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def _is_heading_noise(
    sentence: str,
) -> bool:

    text = _normalize(
        sentence
    )


    if not text:

        return True


    raw = str(
        sentence
        or ""
    ).strip()


    word_count = len(
        text.split()
    )


    # Scrapers sometimes leave fragments such as:
    #
    #   "Egitim Finansmanina"
    #   "Egitim Finansmani"
    #
    # They are neither complete sentences nor useful
    # factual claims. Do not remove legitimate short
    # statements that end with punctuation, e.g.
    # "Kefil sarti yok!"

    if (
        word_count <= 3
        and raw
        and raw[-1]
        not in ".!?"
    ):

        return True


    # Scraped section headings such as
    # "Avantajlari Nelerdir?"
    if (
        str(
            sentence
        ).strip().endswith("?")
        and len(
            text.split()
        ) <= 6
    ):

        return True


    heading_phrases = {
        "avantajlari nelerdir",
        "kampanya kosullari",
        "kampanya detaylari",
        "basvuru kosullari",
        "urun ozellikleri",
        "detayli bilgi",
    }


    if (
        text.rstrip("?")
        in heading_phrases
    ):

        return True


    return False


def _is_navigation_noise(
    sentence: str,
) -> bool:

    text = _normalize(
        sentence
    )


    navigation_terms = (
        "anasayfa",
        "bireysel finansmanlar",
        "mobil bankacilik ac",
        "musteri ol musteri ol",
        "basvuru merkezi hesaplama araclari",
        "en yakin sube",
        "sube ve atm listesi",
        "tiklayin",
    )


    if any(
        term in text
        for term in navigation_terms
    ):

        return True


    # Menu/breadcrumb dumps generally repeat
    # "finansman" many times in one sentence.
    if (
        text.count(
            "finansman"
        ) >= 5
    ):

        return True


    return False



def _is_broad_list_question(
    question: str,
) -> bool:

    text = _normalize(
        question
    )

    broad_terms = (
        "avantaj",
        "ozellik",
        "fayda",
        "kosul",
        "sart",
        "neler sun",
        "neler sagla",
    )

    return any(
        term in text
        for term in broad_terms
    )


def _broad_marker_terms(
    question: str,
) -> tuple[str, ...]:

    text = _normalize(
        question
    )

    if "avantaj" in text:

        return (
            "avantaj",
            "fayda",
        )

    if "fayda" in text:

        return (
            "fayda",
            "avantaj",
        )

    if "ozellik" in text:

        return (
            "ozellik",
        )

    if "kosul" in text:

        return (
            "kosul",
            "sart",
        )

    if "sart" in text:

        return (
            "sart",
            "kosul",
        )

    return tuple()


def _looks_like_labeled_fact(
    sentence: str,
) -> bool:

    raw = str(
        sentence
        or ""
    ).strip()

    if ":" not in raw:

        return False

    label, value = raw.split(
        ":",
        1,
    )

    label_words = (
        _normalize(
            label
        ).split()
    )

    value_words = (
        _normalize(
            value
        ).split()
    )

    return (
        2
        <= len(label_words)
        <= 14
        and
        len(value_words)
        >= 3
    )


def _broad_structure_bonus(
    *,
    question: str,
    sentence: str,
    sentence_order: int,
    sentences,
) -> int:

    if not _is_broad_list_question(
        question
    ):

        return 0

    if not _looks_like_labeled_fact(
        sentence
    ):

        return 0

    # Structurally formatted
    # "Heading: explanation" item.
    bonus = 10

    markers = (
        _broad_marker_terms(
            question
        )
    )

    if not markers:

        return bonus

    marker_order = None

    for index, candidate in enumerate(
        sentences,
        start=1,
    ):

        normalized = _normalize(
            candidate
        )

        if any(
            marker in normalized
            for marker in markers
        ):

            marker_order = index
            break

    # A labeled fact at/after the relevant
    # list heading is very likely one of
    # the requested list items.
    if (
        marker_order is not None
        and
        sentence_order >= marker_order
    ):

        bonus += 30

    sentence_normalized = (
        _normalize(
            sentence
        )
    )

    if any(
        marker in sentence_normalized
        for marker in markers
    ):

        bonus += 10

    return bonus


def _is_broad_list_noise(
    sentence: str,
) -> bool:

    text = _normalize(
        sentence
    )

    # These are useful when the user asks
    # specifically about application/contact,
    # but they are noise for benefits/features/
    # conditions style list questions.
    noise_terms = (
        "hemen basvur",
        "hangi kanallari kullanabilirsiniz",
        "detayli bilgi ve diger bankacilik",
        "numarali alo",
        "arayabilirsiniz",
        "subelerimiz",
        "internet subesi",
    )

    return any(
        term in text
        for term in noise_terms
    )


def _broad_candidate_priority(
    item,
    question: str,
) -> int:

    if not _is_broad_list_question(
        question
    ):

        return 0

    priority = 0

    if _looks_like_labeled_fact(
        item.sentence
    ):

        priority += 20

    question_text = _normalize(
        question
    )

    sentence_text = _normalize(
        item.sentence
    )

    if (
        "avantaj" in question_text
        and
        "avantaj" in sentence_text
    ):

        priority += 10

    if (
        "ozellik" in question_text
        and
        "ozellik" in sentence_text
    ):

        priority += 10

    if (
        (
            "kosul" in question_text
            or "sart" in question_text
        )
        and
        (
            "kosul" in sentence_text
            or "sart" in sentence_text
        )
    ):

        priority += 10

    return priority


def _display_sentence(
    sentence: str,
    *,
    question: str,
) -> str:

    text = str(
        sentence
        or ""
    ).strip()

    if not _is_broad_list_question(
        question
    ):

        return text

    # Scraped pages may concatenate the
    # container heading and first list item:
    #
    # "... Finansmaninin Avantajlari
    #  Avantajli Kar Payi Oranlari: ..."
    #
    # Remove only the container heading.
    patterns = (
        (
            r"^.*?\bAvantajlar[\u0131i]\b"
            r"\s+(?=[A-Z\u00c7\u011e\u0130"
            r"\u00d6\u015e\u00dc])"
        ),
        (
            r"^.*?\b(?:\u00d6zellikler|Ozellikler)"
            r"[\u0131i]\b"
            r"\s+(?=[A-Z\u00c7\u011e\u0130"
            r"\u00d6\u015e\u00dc])"
        ),
        (
            r"^.*?\b(?:Ko\u015fullar|Kosullar)"
            r"[\u0131i]\b"
            r"\s+(?=[A-Z\u00c7\u011e\u0130"
            r"\u00d6\u015e\u00dc])"
        ),
        (
            r"^.*?\b(?:\u015eartlar|Sartlar)"
            r"[\u0131i]\b"
            r"\s+(?=[A-Z\u00c7\u011e\u0130"
            r"\u00d6\u015e\u00dc])"
        ),
    )

    if ":" in text:

        for pattern in patterns:

            cleaned = re.sub(
                pattern,
                "",
                text,
                count=1,
            ).strip()

            if (
                cleaned
                and
                cleaned != text
                and
                ":" in cleaned
            ):

                text = cleaned
                break

    return text

def _segment_restriction(
    title: str,
    sentence: str,
) -> str | None:

    text = _normalize(
        str(
            title
            or ""
        )
        + " "
        + str(
            sentence
            or ""
        )
    )


    mappings = (
        (
            "banka_calisani",
            (
                "banka calisanlarina ozel",
                "banka calisani",
            ),
        ),
        (
            "kamu_calisani",
            (
                "kamu calisanlarina ozel",
                "kamu calisani",
            ),
        ),
        (
            "emekli",
            (
                "emeklilere ozel",
                "emekli muster",
            ),
        ),
        (
            "ogrenci",
            (
                "ogrencilere ozel",
            ),
        ),
    )


    for segment, terms in mappings:

        if any(
            term in text
            for term in terms
        ):

            return segment


    return None


def _question_segments(
    question: str,
) -> set[str]:

    text = _normalize(
        question
    )

    result = set()


    mappings = (
        (
            "banka_calisani",
            (
                "banka calisani",
                "bankada calisiyorum",
            ),
        ),
        (
            "kamu_calisani",
            (
                "kamu calisani",
                "memurum",
                "devlet memuru",
            ),
        ),
        (
            "emekli",
            (
                "emekliyim",
                "emekli",
            ),
        ),
        (
            "ogrenci",
            (
                "ogrenciyim",
                "ogrenci",
            ),
        ),
    )


    for segment, terms in mappings:

        if any(
            term in text
            for term in terms
        ):

            result.add(
                segment
            )


    return result


def _segment_allowed(
    *,
    question: str,
    title: str,
    sentence: str,
) -> bool:

    restriction = (
        _segment_restriction(
            title,
            sentence,
        )
    )


    if restriction is None:

        return True


    return (
        restriction
        in _question_segments(
            question
        )
    )


def _document_key(
    item,
):

    return (
        str(
            item.bank_name
        ),
        str(
            item.document_title
        ),
        str(
            item.source_url
        ),
    )


def _build_candidates(
    context,
    *,
    question: str,
) -> tuple[ExtractiveSentence, ...]:

    question_tokens = _tokens(
        question
    )


    candidates = []


    for evidence_order, item in enumerate(
        context.evidence,
        start=1,
    ):

        title_tokens = _tokens(
            item.document_title
        )

        title_overlap = len(
            question_tokens
            & title_tokens
        )


        sentences = _split_sentences(
            item.text
        )


        for sentence_order, sentence in enumerate(
            sentences,
            start=1,
        ):

            sentence = (
                _clean_sentence(
                    sentence
                )
            )


            if _is_heading_noise(
                sentence
            ):

                continue


            if _is_navigation_noise(
                sentence
            ):

                continue


            if not _segment_allowed(
                question=question,
                title=item.document_title,
                sentence=sentence,
            ):

                continue


            sentence_tokens = _tokens(
                sentence
            )

            sentence_overlap = len(
                question_tokens
                & sentence_tokens
            )


            campaign_fact_bonus = 0

            normalized_sentence = (
                _normalize(
                    sentence
                )
            )


            if (
                "kampanya"
                in _normalize(
                    question
                )
            ):

                if any(
                    token in normalized_sentence
                    for token in (
                        "gecerlidir",
                        "harcamaya",
                        "parafpara",
                        "indirim",
                        "odul",
                        "taksit",
                        "katilim",
                    )
                ):

                    campaign_fact_bonus += 8


                if any(
                    token in normalized_sentence
                    for token in (
                        "diledigi zaman",
                        "degistirme hakki",
                        "durdurma hakki",
                    )
                ):

                    campaign_fact_bonus -= 12


            score = (
                title_overlap * 8
                + sentence_overlap * 5
                + _section_priority(
                    item.section_type,
                    question,
                )
                + campaign_fact_bonus
                + _broad_structure_bonus(
                    question=question,
                    sentence=sentence,
                    sentence_order=sentence_order,
                    sentences=sentences,
                )
                + max(
                    0,
                    5 - evidence_order,
                )
                + max(
                    0,
                    3 - sentence_order,
                )
            )


            candidates.append(
                ExtractiveSentence(
                    evidence_id=str(
                        item.evidence_id
                    ),
                    bank_name=str(
                        item.bank_name
                    ),
                    document_title=str(
                        item.document_title
                    ),
                    source_kind=str(
                        item.source_kind
                    ),
                    section_type=str(
                        item.section_type
                    ),
                    sentence=sentence,
                    score=score,
                    source_url=str(
                        item.source_url
                    ),
                    checked_at=(
                        None
                        if item.checked_at is None
                        else str(
                            item.checked_at
                        )
                    ),
                )
            )


    return tuple(
        candidates
    )


def _group_candidates(
    candidates,
):

    groups = {}

    order = []


    for item in candidates:

        key = (
            item.bank_name,
            item.document_title,
            item.source_url,
        )


        if key not in groups:

            groups[key] = []

            order.append(
                key
            )


        groups[key].append(
            item
        )


    return (
        groups,
        order,
    )


def _dedupe_sentences(
    candidates,
):

    result = []

    seen = set()


    for item in candidates:

        normalized = _normalize(
            item.sentence
        )


        if normalized in seen:
            continue


        seen.add(
            normalized
        )

        result.append(
            item
        )


    return tuple(
        result
    )


def _source_footer(
    selected,
) -> str:

    groups = {}


    for item in selected:

        key = (
            item.bank_name,
            item.document_title,
            item.source_url,
            item.checked_at,
        )


        groups.setdefault(
            key,
            [],
        )


        if (
            item.evidence_id
            not in groups[key]
        ):

            groups[key].append(
                item.evidence_id
            )


    rows = []


    for (
        bank,
        title,
        url,
        checked_at,
    ), evidence_ids in groups.items():

        row = (
            "- ["
            + ", ".join(
                evidence_ids
            )
            + "] "
            + bank
            + " - "
            + title
            + "\n  "
            + url
        )


        if checked_at:

            row += (
                "\n  Kontrol: "
                + checked_at
            )


        rows.append(
            row
        )


    if not rows:

        return ""


    return (
        "\n\nKaynaklar:\n"
        + "\n".join(
            rows
        )
    )


def render_extractive_rag_answer(
    context,
    *,
    question: str | None = None,
    max_sentences: int = 3,
) -> ExtractiveRagAnswer:

    route = str(
        context.route
    )


    if route not in _ALLOWED_ROUTES:

        raise ValueError(
            "Extractive RAG renderer "
            "received unsupported route."
        )


    if not context.evidence:

        raise ValueError(
            "Extractive RAG renderer "
            "received no evidence."
        )


    question = str(
        question
        if question is not None
        else context.question
    )


    broad_list_question = (
        _is_broad_list_question(
            question
        )
    )

    effective_max_sentences = (
        max(
            max_sentences,
            5,
        )
        if broad_list_question
        else max_sentences
    )

    candidates = (
        _build_candidates(
            context,
            question=question,
        )
    )


    candidates = (
        _dedupe_sentences(
            candidates
        )
    )


    if not candidates:

        return ExtractiveRagAnswer(
            text=(
                "Bu soru için kullanıcıya "
                "uygunluğu doğrulanmış "
                "bir kampanya veya ürün bilgisi "
                "bulunamadı."
            ),
            evidence_ids=tuple(),
            document_count=0,
            sentence_count=0,
            source_kind=None,
            reasons=(
                "no_eligible_extractive_evidence",
                "fail_closed",
            ),
        )


    groups, group_order = (
        _group_candidates(
            candidates
        )
    )


    ranked_groups = sorted(
        group_order,
        key=lambda key: (
            max(
                item.score
                for item in groups[key]
            )
        ),
        reverse=True,
    )


    selected = []


    # --------------------------------------------------------
    # One target document:
    # select the best factual sentences.
    # --------------------------------------------------------

    if len(ranked_groups) == 1:

        key = ranked_groups[0]


        ranked_sentences = sorted(
            groups[key],
            key=lambda item: (
                (
                    _broad_candidate_priority(
                        item,
                        question,
                    )
                    if broad_list_question
                    else 0
                ),
                item.score,
            ),
            reverse=True,
        )


        if broad_list_question:

            ranked_sentences = [
                item
                for item in ranked_sentences
                if not _is_broad_list_noise(
                    item.sentence
                )
            ]


        selected.extend(
            ranked_sentences[
                :effective_max_sentences
            ]
        )


    # --------------------------------------------------------
    # Multi-document:
    # one strongest sentence per document first.
    # This is safer for broad campaign questions.
    # --------------------------------------------------------

    else:

        for key in ranked_groups:

            ranked_sentences = sorted(
                groups[key],
                key=lambda item: (
                    (
                        _broad_candidate_priority(
                            item,
                            question,
                        )
                        if broad_list_question
                        else 0
                    ),
                    item.score,
                ),
                reverse=True,
            )


            if broad_list_question:

                ranked_sentences = [
                    item
                    for item in ranked_sentences
                    if not _is_broad_list_noise(
                        item.sentence
                    )
                ]


            if ranked_sentences:

                selected.append(
                    ranked_sentences[0]
                )


            if len(selected) >= (
                effective_max_sentences
            ):

                break


    if not selected:

        raise ValueError(
            "Extractive selection is empty."
        )


    source_kinds = {
        item.source_kind
        for item in selected
    }


    selected_document_keys = {
        (
            item.bank_name,
            item.document_title,
            item.source_url,
        )
        for item in selected
    }


    # --------------------------------------------------------
    # Deterministic user-facing body
    # --------------------------------------------------------

    body = []


    if len(
        selected_document_keys
    ) == 1:

        first = selected[0]


        if first.source_kind == "campaign":

            body.append(
                (
                    "Do\u011frulanm\u0131\u015f kampanya: "
                    "\""
                    + first.document_title
                    + "\". "
                    + "["
                    + first.evidence_id
                    + "]"
                )
            )


        elif first.source_kind == (
            "standard_product"
        ):

            body.append(
                (
                    "Do\u011frulanm\u0131\u015f \u00fcr\u00fcn: "
                    "\""
                    + first.document_title
                    + "\". "
                    + "["
                    + first.evidence_id
                    + "]"
                )
            )


    for item in selected:

        sentence = (
            _display_sentence(
                item.sentence,
                question=question,
            )
        )


        body.append(
            "- "
            + sentence
            + " ["
            + item.evidence_id
            + "]"
        )


    cited_ids = []


    for item in selected:

        if (
            item.evidence_id
            not in cited_ids
        ):

            cited_ids.append(
                item.evidence_id
            )


    text = (
        "\n".join(
            body
        )
        + _source_footer(
            selected
        )
    )


    return ExtractiveRagAnswer(
        text=text,
        evidence_ids=tuple(
            cited_ids
        ),
        document_count=len(
            selected_document_keys
        ),
        sentence_count=len(
            selected
        ),
        source_kind=(
            next(
                iter(
                    source_kinds
                )
            )
            if len(
                source_kinds
            ) == 1
            else None
        ),
        reasons=(
            "official_evidence_only",
            "extractive_no_paraphrase",
            "deterministic_citations",
        ),
    )
