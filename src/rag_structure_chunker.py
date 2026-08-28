# RAG_STRUCTURE_CHUNKER_V1

from __future__ import annotations

from dataclasses import dataclass
import re

from src.rag_document_model import (
    GROUNDING_ALLOW,
    GROUNDING_LIVE_ONLY,
    GROUNDING_STRUCTURED_PREFERRED,
    RagChunkCandidate,
    RagDocument,
    stable_rag_id,
)


# ------------------------------------------------------------
# ASCII shadow
#
# The shadow keeps one character per source character.
# Therefore section offsets stay aligned with retrieval text.
# ------------------------------------------------------------

_TRANSLATE = str.maketrans(
    {
        "\u00c7": "c",
        "\u00e7": "c",
        "\u011e": "g",
        "\u011f": "g",
        "\u0130": "i",
        "I": "i",
        "\u0131": "i",
        "\u00d6": "o",
        "\u00f6": "o",
        "\u015e": "s",
        "\u015f": "s",
        "\u00dc": "u",
        "\u00fc": "u",
    }
)


def ascii_shadow(
    text: str,
) -> str:

    return (
        str(text or "")
        .translate(_TRANSLATE)
        .lower()
    )


# ------------------------------------------------------------
# Retrieval-only noise cleanup.
#
# Raw source text remains untouched inside RagDocument.
# ------------------------------------------------------------

_NOISE_SUFFIX_MARKERS = (
    "tum site ziyaretcilerimizi daha iyi tanimak",
    "cerez ayarlari cerez politikasi",
)


_INLINE_NOISE = (
    "your browser does not support the audio element.",
)


@dataclass(frozen=True)
class PreparedRetrievalText:

    text: str
    removed_noise: tuple[str, ...]


def prepare_retrieval_text(
    text: str,
) -> PreparedRetrievalText:

    value = str(
        text or ""
    )

    removed: list[str] = []

    for noise in _INLINE_NOISE:

        shadow = ascii_shadow(
            value
        )

        marker = ascii_shadow(
            noise
        )

        if marker in shadow:

            start = shadow.find(
                marker
            )

            end = start + len(
                marker
            )

            value = (
                value[:start]
                + " "
                + value[end:]
            )

            removed.append(
                noise
            )

    shadow = ascii_shadow(
        value
    )

    cut_positions = []

    for marker in _NOISE_SUFFIX_MARKERS:

        pos = shadow.find(
            marker
        )

        # Cookie banner markers are explicit web-site
        # boilerplate signals. Their position is irrelevant:
        # once detected, the suffix must not enter the RAG
        # retrieval corpus.
        if pos >= 0:
            cut_positions.append(
                (
                    pos,
                    marker,
                )
            )

    if cut_positions:

        pos, marker = min(
            cut_positions,
            key=lambda item: item[0],
        )

        value = value[:pos]

        removed.append(
            marker
        )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return PreparedRetrievalText(
        text=value,
        removed_noise=tuple(
            removed
        ),
    )


# ------------------------------------------------------------
# Domain section markers.
#
# These are structural boundaries, not final semantic chunks.
# Long sections are flagged for the later embedding-based
# semantic splitter.
# ------------------------------------------------------------

_SECTION_PATTERNS = (

    # Campaign
    (
        "campaign_period",
        r"\bkampanya tarihleri\b",
    ),
    (
        "campaign_participation",
        r"\bkampanyaya nasil katilirim\??",
    ),
    (
        "campaign_terms",
        r"\bkampanya kosullari\b",
    ),
    (
        "campaign_details",
        r"\bkampanya detaylari\b",
    ),
    (
        "eligibility",
        r"\bkimler faydalanabilir\??",
    ),

    # Product/application
    (
        "required_documents",
        (
            r"\bbasvuru icin gerekli "
            r"belgeler nelerdir\??"
        ),
    ),
    (
        "required_documents",
        r"\bgerekli belgeler nelerdir\??",
    ),
    (
        "application",
        r"\bnasil basvurulur\??",
    ),
    (
        "benefits",
        r"\bavantajlari nelerdir\??",
    ),
    (
        "features",
        r"\bozellikleri\b",
    ),

    # Finance / calculation
    (
        "financing_ratio",
        (
            r"\bekspertiz degerine gore "
            r"finansman oranlari\b"
        ),
    ),
    (
        "financing_ratio",
        r"\bfinansman oranlari\b",
    ),
    (
        "calculation_explanation",
        r"\bnasil hesaplanir\??",
    ),

    # Dynamic calculator widget.
    #
    # Numbers from this block must NOT become normal RAG
    # numeric evidence. Live adapters / structured finance
    # engine own that responsibility.
    (
        "dynamic_calculator",
        r"\bfinansal hesaplama\b",
    ),
    (
        "dynamic_calculator",
        r"\bhesaplama araci\b",
    ),

    # Generic definition marker is deliberately last.
    (
        "definition",
        r"\bnedir\??",
    ),
)


_POLICY_BY_SECTION = {

    "dynamic_calculator":
        GROUNDING_LIVE_ONLY,

    "financing_ratio":
        GROUNDING_STRUCTURED_PREFERRED,

    "calculation_explanation":
        GROUNDING_STRUCTURED_PREFERRED,

    "features":
        GROUNDING_STRUCTURED_PREFERRED,

    "campaign_period":
        GROUNDING_STRUCTURED_PREFERRED,

    "campaign_terms":
        GROUNDING_ALLOW,

    "campaign_participation":
        GROUNDING_ALLOW,

    "campaign_details":
        GROUNDING_ALLOW,

    "eligibility":
        GROUNDING_ALLOW,

    "required_documents":
        GROUNDING_ALLOW,

    "application":
        GROUNDING_ALLOW,

    "benefits":
        GROUNDING_ALLOW,

    "definition":
        GROUNDING_ALLOW,

    "overview":
        GROUNDING_ALLOW,

    "body":
        GROUNDING_ALLOW,
}


@dataclass(frozen=True)
class _SectionMatch:

    start: int
    end: int
    section_type: str
    heading: str


def _find_section_matches(
    text: str,
) -> list[_SectionMatch]:

    shadow = ascii_shadow(
        text
    )

    found: list[_SectionMatch] = []

    for (
        section_type,
        pattern,
    ) in _SECTION_PATTERNS:

        for match in re.finditer(
            pattern,
            shadow,
            flags=re.I,
        ):

            found.append(
                _SectionMatch(
                    start=match.start(),
                    end=match.end(),
                    section_type=section_type,
                    heading=text[
                        match.start():
                        match.end()
                    ].strip(),
                )
            )

    found.sort(
        key=lambda item: (
            item.start,
            item.end,
        )
    )

    # Same heading may match two rules or appear twice in a
    # tiny widget label. Deduplicate near-identical boundaries.
    result: list[_SectionMatch] = []

    for item in found:

        if result:

            previous = result[-1]

            if (
                item.start
                == previous.start
            ):
                continue

            if (
                item.section_type
                == previous.section_type
                and item.start
                - previous.start
                < 45
            ):
                continue

        result.append(
            item
        )

    return result


def sectionize_document(
    document: RagDocument,
    *,
    semantic_split_threshold: int = 1800,
) -> list[RagChunkCandidate]:

    prepared = prepare_retrieval_text(
        document.text
    )

    text = prepared.text

    if not text:
        return []

    matches = _find_section_matches(
        text
    )

    boundaries = []

    if not matches:

        boundaries.append(
            (
                0,
                len(text),
                "body",
                "",
            )
        )

    else:

        first = matches[0]

        if first.start > 0:

            boundaries.append(
                (
                    0,
                    first.start,
                    "overview",
                    "",
                )
            )

        for index, item in enumerate(
            matches
        ):

            end = (
                matches[index + 1].start
                if index + 1
                < len(matches)
                else len(text)
            )

            boundaries.append(
                (
                    item.start,
                    end,
                    item.section_type,
                    item.heading,
                )
            )

    chunks: list[
        RagChunkCandidate
    ] = []

    ordinal = 0

    for (
        start,
        end,
        section_type,
        heading,
    ) in boundaries:

        raw_section = text[
            start:end
        ]

        left_trim = (
            len(raw_section)
            - len(raw_section.lstrip())
        )

        right_trimmed = (
            raw_section.rstrip()
        )

        section_start = (
            start
            + left_trim
        )

        section_end = (
            start
            + len(right_trimmed)
        )

        section_text = (
            raw_section.strip()
        )

        if not section_text:
            continue

        # Skip tiny structural fragments.
        if (
            len(section_text) < 20
            and chunks
        ):
            continue

        policy = _POLICY_BY_SECTION.get(
            section_type,
            GROUNDING_ALLOW,
        )

        requires_semantic_split = (
            len(section_text)
            > int(
                semantic_split_threshold
            )
        )

        chunk_id = stable_rag_id(
            document.doc_id,
            ordinal,
            section_type,
            section_text,
        )

        chunks.append(
            RagChunkCandidate(
                chunk_id=chunk_id,
                doc_id=document.doc_id,
                ordinal=ordinal,
                section_type=section_type,
                section_heading=heading,
                text=section_text,
                retrieval_start=section_start,
                retrieval_end=section_end,
                grounding_policy=policy,
                requires_semantic_split=(
                    requires_semantic_split
                ),
                source_kind=(
                    document.source_kind
                ),
                bank_name=(
                    document.bank_name
                ),
                document_title=(
                    document.title
                ),
                source_url=(
                    document.source_url
                ),
                checked_at=(
                    document.checked_at
                ),
                metadata={
                    **document.metadata,
                    "source_id":
                        document.source_id,
                    "source_hash":
                        document.source_hash,
                    "removed_noise":
                        prepared.removed_noise,
                },
            )
        )

        ordinal += 1

    return chunks
