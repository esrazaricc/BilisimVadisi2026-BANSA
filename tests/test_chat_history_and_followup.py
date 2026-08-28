from pathlib import Path

from src.chat_followup_context import (
    resolve_followup_question,
)

from src.chat_history import (
    add_message,
    create_conversation,
    get_messages,
    list_conversations,
)


def test_chat_history_roundtrip(
    tmp_path: Path,
):

    db = (
        tmp_path
        / "history.sqlite"
    )

    conversation_id = (
        create_conversation(
            db_path=db
        )
    )

    add_message(
        conversation_id=(
            conversation_id
        ),
        role="user",
        content=(
            "Albaraka T\u00fcrk konut finansman\u0131 ka\u00e7 ay?"
        ),
        resolved_question=(
            "Albaraka T\u00fcrk konut finansman\u0131 ka\u00e7 ay?"
        ),
        db_path=db,
    )

    add_message(
        conversation_id=(
            conversation_id
        ),
        role="assistant",
        content=(
            "Azami vade 120 aya kadard\u0131r."
        ),
        route="product_rag",
        backend="grounded_natural_rag",
        qwen_used=True,
        db_path=db,
    )

    messages = (
        get_messages(
            conversation_id,
            db_path=db,
        )
    )

    assert len(
        messages
    ) == 2

    assert (
        messages[0][
            "role"
        ]
        == "user"
    )

    assert (
        messages[1][
            "backend"
        ]
        == "grounded_natural_rag"
    )

    conversations = (
        list_conversations(
            db_path=db
        )
    )

    assert len(
        conversations
    ) == 1

    assert (
        "Albaraka"
        in conversations[0][
            "title"
        ]
    )


def test_implicit_followup_inherits_bank_and_product():

    result = (
        resolve_followup_question(
            "Peki bunun masraf\u0131 ne?",
            [
                (
                    "Albaraka T\u00fcrk konut "
                    "finansman\u0131 ka\u00e7 ay?"
                )
            ],
        )
    )

    assert result.used_context

    assert (
        result.inherited_bank
        == "Albaraka T\u00fcrk"
    )

    assert (
        result.inherited_product
        == "konut finansman\u0131"
    )

    assert (
        "Albaraka T\u00fcrk"
        in result.resolved_question
    )

    assert (
        "konut finansman\u0131"
        in result.resolved_question
    )


def test_new_product_inherits_only_bank():

    result = (
        resolve_followup_question(
            (
                "Peki e\u011fitim finansman\u0131n\u0131n "
                "avantajlar\u0131?"
            ),
            [
                (
                    "Albaraka T\u00fcrk konut "
                    "finansman\u0131 ka\u00e7 ay?"
                )
            ],
        )
    )

    assert result.used_context

    assert (
        result.inherited_bank
        == "Albaraka T\u00fcrk"
    )

    assert (
        result.inherited_product
        is None
    )

    assert (
        "konut finansman\u0131"
        not in result.resolved_question
    )


def test_explicit_new_bank_and_product_do_not_inherit():

    question = (
        "Vak\u0131f Kat\u0131l\u0131m ihtiya\u00e7 "
        "finansman\u0131 vadesi nedir?"
    )

    result = (
        resolve_followup_question(
            question,
            [
                (
                    "Albaraka T\u00fcrk konut "
                    "finansman\u0131 ka\u00e7 ay?"
                )
            ],
        )
    )

    assert not result.used_context

    assert (
        result.resolved_question
        == question
    )
