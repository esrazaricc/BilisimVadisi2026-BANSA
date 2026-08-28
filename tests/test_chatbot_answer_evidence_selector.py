from dataclasses import dataclass

from src.chatbot_answer_evidence_selector import (
    SELECTION_MULTI_DOCUMENT,
    SELECTION_SINGLE_DOCUMENT,
    select_answer_evidence,
)


@dataclass
class Item:

    evidence_id: str

    doc_id: str

    source_kind: str

    document_title: str

    evidence_text: str = "official text"

    source_url: str = (
        "https://example.com"
    )

    grounding_policy: str = (
        "allow"
    )

    grounding_limited: bool = False


@dataclass
class Pack:

    items: tuple


def test_targeted_product_locks_same_document():

    pack = Pack(
        items=(
            Item(
                "E1",
                "education",
                "standard_product",
                "Egitim Finansmani",
            ),
            Item(
                "E2",
                "dealer",
                "standard_product",
                "Bayide Finansman",
            ),
            Item(
                "E3",
                "education",
                "standard_product",
                "Egitim Finansmani",
            ),
        )
    )

    result = select_answer_evidence(
        pack,
        question=(
            "Albaraka Turk egitim "
            "finansmaninin avantajlari nelerdir?"
        ),
        expected_source_kind=(
            "standard_product"
        ),
    )

    assert (
        result.mode
        == SELECTION_SINGLE_DOCUMENT
    )

    assert (
        result.anchor_doc_id
        == "education"
    )

    assert [
        item.evidence_id
        for item in result.items
    ] == [
        "E1",
        "E3",
    ]


def test_targeted_campaign_locks_same_document():

    pack = Pack(
        items=(
            Item(
                "E1",
                "flight",
                "campaign",
                (
                    "Ucak Bileti "
                    "Harcamalariniza "
                    "2000 TL ParafPara"
                ),
            ),
            Item(
                "E2",
                "flight",
                "campaign",
                (
                    "Ucak Bileti "
                    "Harcamalariniza "
                    "2000 TL ParafPara"
                ),
            ),
            Item(
                "E3",
                "damat",
                "campaign",
                (
                    "Paraf ile DS Damat "
                    "1000 TL ParafPara"
                ),
            ),
        )
    )

    result = select_answer_evidence(
        pack,
        question=(
            "Ucak bileti ParafPara "
            "kampanyasi var mi?"
        ),
        expected_source_kind="campaign",
    )

    assert (
        result.mode
        == SELECTION_SINGLE_DOCUMENT
    )

    assert [
        item.evidence_id
        for item in result.items
    ] == [
        "E1",
        "E2",
    ]


def test_broad_campaign_question_keeps_multiple_documents():

    pack = Pack(
        items=(
            Item(
                "E1",
                "flight",
                "campaign",
                "Ucak Bileti ParafPara",
            ),
            Item(
                "E2",
                "education",
                "campaign",
                "Egitim Harcamalari",
            ),
        )
    )

    result = select_answer_evidence(
        pack,
        question=(
            "Albaraka Turk hangi "
            "kampanyalari sunuyor?"
        ),
        expected_source_kind="campaign",
    )

    assert (
        result.mode
        == SELECTION_MULTI_DOCUMENT
    )

    assert len(
        result.items
    ) == 2


def test_wrong_source_kind_is_removed():

    pack = Pack(
        items=(
            Item(
                "E1",
                "education",
                "standard_product",
                "Egitim Finansmani",
            ),
            Item(
                "E2",
                "campaign",
                "campaign",
                "Egitim Kampanyasi",
            ),
        )
    )

    result = select_answer_evidence(
        pack,
        question=(
            "Egitim finansmani nedir?"
        ),
        expected_source_kind=(
            "standard_product"
        ),
    )

    assert len(
        result.items
    ) == 1

    assert (
        result.items[0].source_kind
        == "standard_product"
    )


def test_grounding_limited_is_removed():

    unsafe = Item(
        "E2",
        "unsafe",
        "standard_product",
        "Egitim Finansmani",
        grounding_limited=True,
    )

    pack = Pack(
        items=(
            Item(
                "E1",
                "education",
                "standard_product",
                "Egitim Finansmani",
            ),
            unsafe,
        )
    )

    result = select_answer_evidence(
        pack,
        question=(
            "Egitim finansmani nedir?"
        ),
        expected_source_kind=(
            "standard_product"
        ),
    )

    assert [
        item.evidence_id
        for item in result.items
    ] == [
        "E1",
    ]
