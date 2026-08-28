from dataclasses import dataclass

from src.chatbot_answer_evidence_selector import (
    SELECTION_EMPTY,
    select_answer_evidence,
)


@dataclass(frozen=True)
class Evidence:

    evidence_id: str

    doc_id: str

    source_kind: str

    bank_name: str

    document_title: str

    section_type: str

    evidence_text: str

    source_url: str

    metadata: dict

    section_heading: str = ""

    grounding_policy: str = "allow"

    grounding_limited: bool = False

    checked_at: str | None = None


@dataclass(frozen=True)
class Pack:

    items: tuple


def item(
    evidence_id,
    *,
    bank,
    title,
    family,
    text,
    section="features",
    maximum_maturity_months=None,
):

    structured = {}


    if (
        maximum_maturity_months
        is not None
    ):

        structured[
            "maximum_maturity_months"
        ] = maximum_maturity_months


    return Evidence(
        evidence_id=evidence_id,
        doc_id=(
            bank
            + "|"
            + title
        ),
        source_kind=(
            "standard_product"
        ),
        bank_name=bank,
        document_title=title,
        section_type=section,
        evidence_text=text,
        source_url=(
            "https://example.com/"
            + evidence_id
        ),
        metadata={
            "product_family_key":
                family,
            "structured_fields":
                structured,
        },
    )


def test_explicit_bank_lock_rejects_other_bank():

    pack = Pack(
        items=(
            item(
                "E1",
                bank="Albaraka Turk",
                title="Konut Finansmani",
                family="konut_finansmani",
                text=(
                    "Dilediginiz evi "
                    "120 aya kadar "
                    "taksitlendirebilirsiniz."
                ),
                maximum_maturity_months=120,
            ),
            item(
                "E2",
                bank="Turkiye Finans",
                title="Konut Finansmani",
                family="konut_finansmani",
                text=(
                    "Maksimum vade "
                    "120 aydir."
                ),
                maximum_maturity_months=120,
            ),
        ),
    )


    result = select_answer_evidence(
        pack,
        question=(
            "Albaraka Turk'te konut "
            "finansmani kac ay vade?"
        ),
        expected_source_kind=(
            "standard_product"
        ),
        family="konut_finansmani",
    )


    assert result.items

    assert {
        value.bank_name
        for value in result.items
    } == {
        "Albaraka Turk"
    }


def test_product_family_lock_rejects_wrong_product():

    pack = Pack(
        items=(
            item(
                "E1",
                bank="Albaraka Turk",
                title="Konut Finansmani",
                family="konut_finansmani",
                text=(
                    "120 aya kadar."
                ),
                maximum_maturity_months=120,
            ),
            item(
                "E2",
                bank="Albaraka Turk",
                title="Is Yeri Finansmani",
                family="isyeri_finansmani",
                text=(
                    "60 aya kadar."
                ),
                maximum_maturity_months=60,
            ),
        ),
    )


    result = select_answer_evidence(
        pack,
        question=(
            "Albaraka'da ev finansmani "
            "kac ay?"
        ),
        expected_source_kind=(
            "standard_product"
        ),
        family="konut_finansmani",
    )


    assert {
        value.document_title
        for value in result.items
    } == {
        "Konut Finansmani"
    }


def test_maturity_lock_prefers_numeric_maturity_fact():

    pack = Pack(
        items=(
            item(
                "E1",
                bank="Albaraka Turk",
                title="Konut Finansmani",
                family="konut_finansmani",
                text=(
                    "Dilediginiz evi "
                    "120 aya kadar "
                    "taksitlendirebilirsiniz."
                ),
                section="features",
                maximum_maturity_months=120,
            ),
            item(
                "E2",
                bank="Albaraka Turk",
                title="Konut Finansmani",
                family="konut_finansmani",
                text=(
                    "Vade ve musteri profiline "
                    "gore degisen oranlar sunulur."
                ),
                section="overview",
            ),
        ),
    )


    result = select_answer_evidence(
        pack,
        question=(
            "Albaraka Turk konut "
            "finansmaninin vadesi nedir?"
        ),
        expected_source_kind=(
            "standard_product"
        ),
        family="konut_finansmani",
    )


    assert tuple(
        value.evidence_id
        for value in result.items
    ) == (
        "E1",
    )


def test_named_bank_without_evidence_fails_closed():

    pack = Pack(
        items=(
            item(
                "E1",
                bank="Turkiye Finans",
                title="Konut Finansmani",
                family="konut_finansmani",
                text=(
                    "120 aya kadar."
                ),
                maximum_maturity_months=120,
            ),
        ),
    )


    result = select_answer_evidence(
        pack,
        question=(
            "Albaraka Turk'te konut "
            "finansmani kac ay?"
        ),
        expected_source_kind=(
            "standard_product"
        ),
        family="konut_finansmani",
    )


    assert (
        result.mode
        == SELECTION_EMPTY
    )

    assert (
        result.items
        == tuple()
    )

    assert (
        "explicit_bank_has_no_evidence"
        in result.reasons
    )


def test_generic_question_does_not_force_bank():

    campaign_a = Evidence(
        evidence_id="E1",
        doc_id="A",
        source_kind="campaign",
        bank_name="Albaraka Turk",
        document_title="Kampanya A",
        section_type="campaign_terms",
        evidence_text=(
            "Kampanya A bilgisi."
        ),
        source_url=(
            "https://example.com/a"
        ),
        metadata={},
    )


    campaign_b = Evidence(
        evidence_id="E2",
        doc_id="B",
        source_kind="campaign",
        bank_name="Vakif Katilim",
        document_title="Kampanya B",
        section_type="campaign_terms",
        evidence_text=(
            "Kampanya B bilgisi."
        ),
        source_url=(
            "https://example.com/b"
        ),
        metadata={},
    )


    result = select_answer_evidence(
        Pack(
            items=(
                campaign_a,
                campaign_b,
            )
        ),
        question=(
            "Hangi kampanyalar var?"
        ),
        expected_source_kind="campaign",
    )


    assert len(
        result.items
    ) == 2



def test_structured_preferred_with_structured_fields_is_safe():

    evidence = Evidence(
        evidence_id="E-SP",
        doc_id="albaraka-konut",
        source_kind="standard_product",
        bank_name="Albaraka Turk",
        document_title="Konut Finansmani",
        section_type="features",
        evidence_text=(
            "Dilediginiz evi 120 aya kadar "
            "taksitlendirebilirsiniz."
        ),
        source_url=(
            "https://example.com/albaraka-konut"
        ),
        metadata={
            "product_family_key":
                "konut_finansmani",
            "structured_fields": {
                "maximum_maturity_months":
                    120.0,
            },
        },
        grounding_policy=(
            "structured_preferred"
        ),
    )


    result = select_answer_evidence(
        Pack(
            items=(
                evidence,
            )
        ),
        question=(
            "Albaraka Turk'te konut "
            "finansmani kac ay vade?"
        ),
        expected_source_kind=(
            "standard_product"
        ),
        family="konut_finansmani",
    )


    assert result.items

    assert (
        result.items[0].evidence_id
        == "E-SP"
    )


def test_structured_preferred_without_structured_fields_is_blocked():

    evidence = Evidence(
        evidence_id="E-UNSAFE",
        doc_id="unsafe",
        source_kind="standard_product",
        bank_name="Albaraka Turk",
        document_title="Konut Finansmani",
        section_type="features",
        evidence_text=(
            "120 aya kadar."
        ),
        source_url=(
            "https://example.com/unsafe"
        ),
        metadata={
            "product_family_key":
                "konut_finansmani",
            "structured_fields": {},
        },
        grounding_policy=(
            "structured_preferred"
        ),
    )


    result = select_answer_evidence(
        Pack(
            items=(
                evidence,
            )
        ),
        question=(
            "Albaraka Turk'te konut "
            "finansmani kac ay vade?"
        ),
        expected_source_kind=(
            "standard_product"
        ),
        family="konut_finansmani",
    )


    assert result.items == tuple()
