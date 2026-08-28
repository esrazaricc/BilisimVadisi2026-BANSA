from dataclasses import dataclass
from decimal import Decimal

import pytest

from src.chatbot_rag_generator import (
    _attach_citations,
    _group_evidence_by_document,
    build_rag_generation_messages,
    sanitize_document_answer,
)


@dataclass(frozen=True)
class Evidence:

    evidence_id: str
    source_kind: str
    bank_name: str
    document_title: str
    section_type: str
    text: str
    source_url: str
    checked_at: str | None


@dataclass(frozen=True)
class Context:

    question: str
    route: str

    answer_mode: str = "rag"

    may_generate_answer: bool = True

    evidence: tuple = ()


def product_context():

    return Context(
        question=(
            "Egitim finansmaninin "
            "avantajlari nelerdir?"
        ),
        route="product_rag",
        evidence=(
            Evidence(
                evidence_id="E1",
                source_kind="standard_product",
                bank_name="Albaraka Turk",
                document_title="Egitim Finansmani",
                section_type="benefits",
                text=(
                    "Egitim giderleri icin "
                    "finansman sunulur. "
                    "Azami vade 24 aydir."
                ),
                source_url=(
                    "https://example.com/product"
                ),
                checked_at="2026-08-21",
            ),
            Evidence(
                evidence_id="E4",
                source_kind="standard_product",
                bank_name="Albaraka Turk",
                document_title="Egitim Finansmani",
                section_type="overview",
                text=(
                    "Basvuru bankanin "
                    "kanallarindan yapilabilir."
                ),
                source_url=(
                    "https://example.com/product"
                ),
                checked_at="2026-08-21",
            ),
        ),
    )


def test_model_prompt_contains_no_citation_requirement():

    ctx = product_context()

    messages = (
        build_rag_generation_messages(
            ctx
        )
    )

    system = (
        messages[0][
            "content"
        ]
    )

    assert (
        "citation etiketi yazma"
        in system
    )


def test_same_document_is_one_generation_group():

    ctx = product_context()

    groups = (
        _group_evidence_by_document(
            ctx
        )
    )

    assert len(
        groups
    ) == 1

    assert [
        item.evidence_id
        for item in groups[0]
    ] == [
        "E1",
        "E4",
    ]


def test_different_documents_are_separate_groups():

    ctx = product_context()

    other = Evidence(
        evidence_id="E7",
        source_kind="standard_product",
        bank_name="Albaraka Turk",
        document_title="Baska Urun",
        section_type="overview",
        text="Baska urun bilgisi.",
        source_url=(
            "https://example.com/other"
        ),
        checked_at="2026-08-21",
    )

    ctx = Context(
        question=ctx.question,
        route=ctx.route,
        evidence=(
            *ctx.evidence,
            other,
        ),
    )

    groups = (
        _group_evidence_by_document(
            ctx
        )
    )

    assert len(
        groups
    ) == 2


def test_finance_prompt_is_blocked():

    ctx = Context(
        question="hangi banka",
        route="finance_compare",
        evidence=(
            product_context()
            .evidence
        ),
    )

    with pytest.raises(
        ValueError
    ):

        build_rag_generation_messages(
            ctx
        )


def test_valid_uncited_model_line_is_accepted():

    ctx = product_context()

    (
        passed,
        sanitized,
        reasons,
        warnings,
    ) = sanitize_document_answer(
        (
            "- Egitim giderleri icin "
            "finansman sunulur."
        ),
        evidence_group=(
            ctx.evidence
        ),
    )

    assert passed is True

    assert (
        "finansman sunulur"
        in sanitized
    )

    assert reasons == ()


def test_system_attaches_real_evidence_ids():

    ctx = product_context()

    answer = (
        _attach_citations(
            "- Egitim finansmani sunulur.",
            evidence_group=(
                ctx.evidence
            ),
        )
    )

    assert (
        "[E1, E4]"
        in answer
    )


def test_unsupported_number_line_is_dropped():

    ctx = product_context()

    (
        passed,
        sanitized,
        reasons,
        warnings,
    ) = sanitize_document_answer(
        (
            "- Azami vade 36 aydir."
        ),
        evidence_group=(
            ctx.evidence
        ),
    )

    assert passed is False

    assert sanitized == ""

    assert (
        "no_safe_line"
        in reasons
    )

    assert any(
        value.startswith(
            "dropped_unsupported_numeric_line:"
        )
        for value in warnings
    )


def test_existing_number_is_allowed():

    ctx = product_context()

    (
        passed,
        sanitized,
        reasons,
        _,
    ) = sanitize_document_answer(
        (
            "- Azami vade 24 aydir."
        ),
        evidence_group=(
            ctx.evidence
        ),
    )

    assert passed is True

    assert (
        "24"
        in sanitized
    )

    assert reasons == ()


def test_model_url_is_dropped():

    ctx = product_context()

    (
        passed,
        sanitized,
        _,
        warnings,
    ) = sanitize_document_answer(
        (
            "- Egitim finansmani sunulur.\n"
            "- https://fake.example"
        ),
        evidence_group=(
            ctx.evidence
        ),
    )

    assert passed is True

    assert (
        "https://"
        not in sanitized
    )

    assert any(
        value.startswith(
            "dropped_url_line:"
        )
        for value in warnings
    )


def test_heading_is_dropped():

    ctx = product_context()

    (
        passed,
        sanitized,
        _,
        warnings,
    ) = sanitize_document_answer(
        (
            "**Cevap:**\n"
            "- Egitim finansmani sunulur."
        ),
        evidence_group=(
            ctx.evidence
        ),
    )

    assert passed is True

    assert (
        "Cevap"
        not in sanitized
    )

    assert any(
        value.startswith(
            "dropped_heading_line:"
        )
        for value in warnings
    )


def test_think_output_fails_closed():

    ctx = product_context()

    (
        passed,
        _,
        reasons,
        _,
    ) = sanitize_document_answer(
        (
            "<think>reason</think>\n"
            "- Egitim finansmani sunulur."
        ),
        evidence_group=(
            ctx.evidence
        ),
    )

    assert passed is False

    assert (
        "thinking_output_present"
        in reasons
    )


def test_advice_line_is_dropped():

    ctx = product_context()

    (
        passed,
        sanitized,
        _,
        warnings,
    ) = sanitize_document_answer(
        (
            "- Egitim finansmani sunulur.\n"
            "- Bu bankayi \u00f6neriyorum."
        ),
        evidence_group=(
            ctx.evidence
        ),
    )

    assert passed is True

    assert (
        "\u00f6neriyorum"
        not in sanitized
    )

    assert any(
        value.startswith(
            "dropped_advice_line:"
        )
        for value in warnings
    )



# RAG_GENERATOR_V1_3_QUALITY_TESTS


def test_prompt_echo_heading_is_removed():

    ctx = product_context()

    raw = (
        "**KESIN KURALLAR:**\n"
        "1. Yalnizca verilen kanitlari kullan.\n"
        "**Cevab:**\n"
        "- Egitim giderleri icin "
        "finansman sunulur."
    )

    (
        passed,
        sanitized,
        reasons,
        warnings,
    ) = sanitize_document_answer(
        raw,
        evidence_group=(
            ctx.evidence
        ),
    )

    assert passed is True

    assert (
        "KESIN KURALLAR"
        not in sanitized
    )

    assert (
        "Cevab"
        not in sanitized
    )

    assert (
        "Yalnizca verilen"
        not in sanitized
    )

    assert (
        "finansman sunulur"
        in sanitized
    )

    assert reasons == ()

    assert any(
        value.startswith(
            "dropped_heading_line:"
        )
        for value in warnings
    )


def test_kanit_heading_is_removed():

    ctx = product_context()

    (
        passed,
        sanitized,
        reasons,
        warnings,
    ) = sanitize_document_answer(
        (
            "**KANIT:**\n"
            "- Egitim giderleri icin "
            "finansman sunulur."
        ),
        evidence_group=(
            ctx.evidence
        ),
    )

    assert passed is True

    assert (
        "KANIT"
        not in sanitized
    )

    assert reasons == ()

    assert any(
        value.startswith(
            "dropped_metadata_line:"
        )
        for value in warnings
    )


def test_incomplete_tail_is_trimmed():

    ctx = product_context()

    (
        passed,
        sanitized,
        reasons,
        warnings,
    ) = sanitize_document_answer(
        (
            "- Azami vade 24 aydir. "
            "Sonraki cumle yar"
        ),
        evidence_group=(
            ctx.evidence
        ),
    )

    assert passed is True

    assert (
        sanitized
        == "- Azami vade 24 aydir."
    )

    assert reasons == ()

    assert any(
        value.startswith(
            "trimmed_incomplete_tail:"
        )
        for value in warnings
    )


def test_fully_incomplete_line_is_dropped():

    ctx = product_context()

    (
        passed,
        sanitized,
        reasons,
        warnings,
    ) = sanitize_document_answer(
        (
            "- Egitim finansmani hakkinda "
            "yarim kalan ifade"
        ),
        evidence_group=(
            ctx.evidence
        ),
    )

    assert passed is False

    assert sanitized == ""

    assert (
        "no_safe_line"
        in reasons
    )

    assert any(
        value.startswith(
            "dropped_incomplete_line:"
        )
        for value in warnings
    )


def test_placeholder_example_is_removed():

    ctx = product_context()

    (
        passed,
        sanitized,
        _,
        warnings,
    ) = sanitize_document_answer(
        (
            "- Dogrulanmis ilk bilgi.\n"
            "- Egitim giderleri icin "
            "finansman sunulur."
        ),
        evidence_group=(
            ctx.evidence
        ),
    )

    assert passed is True

    assert (
        "Dogrulanmis ilk bilgi"
        not in sanitized
    )

    assert any(
        value.startswith(
            "dropped_placeholder_line:"
        )
        for value in warnings
    )



# RAG_GENERATOR_V1_4_UI_CLEANUP_TESTS


def test_answer_prefix_is_stripped_but_content_survives():

    ctx = product_context()

    (
        passed,
        sanitized,
        reasons,
        warnings,
    ) = sanitize_document_answer(
        (
            "Cevabiniz: Egitim giderleri "
            "icin finansman sunulur."
        ),
        evidence_group=(
            ctx.evidence
        ),
        question=ctx.question,
    )

    assert passed is True

    assert (
        "Cevabiniz:"
        not in sanitized
    )

    assert (
        "Egitim giderleri"
        in sanitized
    )

    assert reasons == ()

    assert any(
        value.startswith(
            "stripped_answer_prefix:"
        )
        for value in warnings
    )


def test_question_echo_is_dropped():

    ctx = product_context()

    raw = (
        "Egitim finansmaninin "
        "avantajlari nelerdir?\n"
        "- Egitim giderleri icin "
        "finansman sunulur."
    )

    (
        passed,
        sanitized,
        reasons,
        warnings,
    ) = sanitize_document_answer(
        raw,
        evidence_group=(
            ctx.evidence
        ),
        question=ctx.question,
    )

    assert passed is True

    assert (
        "avantajlari nelerdir"
        not in sanitized
    )

    assert (
        "finansman sunulur"
        in sanitized
    )

    assert reasons == ()

    assert any(
        value.startswith(
            "dropped_question_echo_line:"
        )
        for value in warnings
    )


def test_document_metadata_is_dropped():

    ctx = product_context()

    raw = (
        "Banka: Albaraka Turk\n"
        "Belge: Egitim Finansmani\n"
        "Bolum: benefits\n"
        "- Egitim giderleri icin "
        "finansman sunulur."
    )

    (
        passed,
        sanitized,
        reasons,
        warnings,
    ) = sanitize_document_answer(
        raw,
        evidence_group=(
            ctx.evidence
        ),
        question=ctx.question,
    )

    assert passed is True

    assert (
        "Banka:"
        not in sanitized
    )

    assert (
        "Belge:"
        not in sanitized
    )

    assert (
        "Bolum:"
        not in sanitized
    )

    assert (
        "finansman sunulur"
        in sanitized
    )

    assert reasons == ()

    assert sum(
        value.startswith(
            "dropped_metadata_line:"
        )
        for value in warnings
    ) == 3


def test_kanit_metadata_line_is_dropped():

    ctx = product_context()

    raw = (
        "KANIT: resmi metin\n"
        "- Egitim giderleri icin "
        "finansman sunulur."
    )

    (
        passed,
        sanitized,
        _,
        warnings,
    ) = sanitize_document_answer(
        raw,
        evidence_group=(
            ctx.evidence
        ),
        question=ctx.question,
    )

    assert passed is True

    assert (
        "KANIT:"
        not in sanitized
    )

    assert any(
        value.startswith(
            "dropped_metadata_line:"
        )
        for value in warnings
    )

