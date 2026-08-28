from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4
from datetime import datetime, timezone


DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "runtime"
    / "chat_history.sqlite"
)


def _utc_now() -> str:

    return datetime.now(
        timezone.utc
    ).isoformat()


def _connect(
    db_path: Path | str | None = None,
) -> sqlite3.Connection:

    path = Path(
        db_path
        or DEFAULT_DB_PATH
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        path,
        timeout=20,
    )

    connection.row_factory = (
        sqlite3.Row
    )

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    connection.execute(
        "PRAGMA journal_mode = WAL"
    )

    return connection


def init_chat_history(
    db_path: Path | str | None = None,
) -> None:

    with _connect(
        db_path
    ) as connection:

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                resolved_question TEXT,
                route TEXT,
                backend TEXT,
                qwen_used INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (
                    conversation_id
                )
                REFERENCES conversations(id)
                ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS
            idx_messages_conversation_id
            ON messages(
                conversation_id,
                id
            );

            CREATE INDEX IF NOT EXISTS
            idx_conversations_updated_at
            ON conversations(
                updated_at DESC
            );
            """
        )


def _title_from_text(
    text: str,
    max_length: int = 52,
) -> str:

    value = " ".join(
        str(
            text
            or ""
        ).split()
    ).strip()

    if not value:

        return "Yeni Sohbet"

    if len(
        value
    ) <= max_length:

        return value

    return (
        value[
            : max_length - 1
        ].rstrip()
        + "\u2026"
    )


def create_conversation(
    title: str = "Yeni Sohbet",
    db_path: Path | str | None = None,
) -> str:

    init_chat_history(
        db_path
    )

    conversation_id = str(
        uuid4()
    )

    now = _utc_now()

    with _connect(
        db_path
    ) as connection:

        connection.execute(
            """
            INSERT INTO conversations (
                id,
                title,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                conversation_id,
                str(
                    title
                    or "Yeni Sohbet"
                ),
                now,
                now,
            ),
        )

    return conversation_id


def conversation_exists(
    conversation_id: str,
    db_path: Path | str | None = None,
) -> bool:

    if not conversation_id:

        return False

    init_chat_history(
        db_path
    )

    with _connect(
        db_path
    ) as connection:

        row = connection.execute(
            """
            SELECT 1
            FROM conversations
            WHERE id = ?
            LIMIT 1
            """,
            (
                conversation_id,
            ),
        ).fetchone()

    return row is not None


def add_message(
    *,
    conversation_id: str,
    role: str,
    content: str,
    resolved_question: str | None = None,
    route: str | None = None,
    backend: str | None = None,
    qwen_used: bool | None = None,
    db_path: Path | str | None = None,
) -> int:

    init_chat_history(
        db_path
    )

    if role not in {
        "user",
        "assistant",
    }:

        raise ValueError(
            "role must be user or assistant"
        )

    now = _utc_now()

    with _connect(
        db_path
    ) as connection:

        cursor = connection.execute(
            """
            INSERT INTO messages (
                conversation_id,
                role,
                content,
                resolved_question,
                route,
                backend,
                qwen_used,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                role,
                str(
                    content
                    or ""
                ),
                resolved_question,
                route,
                backend,
                (
                    None
                    if qwen_used is None
                    else int(
                        bool(
                            qwen_used
                        )
                    )
                ),
                now,
            ),
        )

        connection.execute(
            """
            UPDATE conversations
            SET updated_at = ?
            WHERE id = ?
            """,
            (
                now,
                conversation_id,
            ),
        )

        if role == "user":

            user_count = (
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM messages
                    WHERE conversation_id = ?
                      AND role = 'user'
                    """,
                    (
                        conversation_id,
                    ),
                ).fetchone()[0]
            )

            if user_count == 1:

                connection.execute(
                    """
                    UPDATE conversations
                    SET title = ?
                    WHERE id = ?
                    """,
                    (
                        _title_from_text(
                            content
                        ),
                        conversation_id,
                    ),
                )

        return int(
            cursor.lastrowid
        )


def get_messages(
    conversation_id: str,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:

    if not conversation_id:

        return []

    init_chat_history(
        db_path
    )

    with _connect(
        db_path
    ) as connection:

        rows = connection.execute(
            """
            SELECT
                id,
                conversation_id,
                role,
                content,
                resolved_question,
                route,
                backend,
                qwen_used,
                created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (
                conversation_id,
            ),
        ).fetchall()

    return [
        dict(
            row
        )
        for row in rows
    ]


def list_conversations(
    *,
    limit: int = 40,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:

    init_chat_history(
        db_path
    )

    with _connect(
        db_path
    ) as connection:

        rows = connection.execute(
            """
            SELECT
                c.id,
                c.title,
                c.created_at,
                c.updated_at,
                (
                    SELECT COUNT(*)
                    FROM messages AS m
                    WHERE m.conversation_id = c.id
                ) AS message_count
            FROM conversations AS c
            ORDER BY c.updated_at DESC
            LIMIT ?
            """,
            (
                int(
                    limit
                ),
            ),
        ).fetchall()

    return [
        dict(
            row
        )
        for row in rows
    ]


def delete_conversation(
    conversation_id: str,
    db_path: Path | str | None = None,
) -> None:

    if not conversation_id:

        return

    init_chat_history(
        db_path
    )

    with _connect(
        db_path
    ) as connection:

        connection.execute(
            """
            DELETE FROM conversations
            WHERE id = ?
            """,
            (
                conversation_id,
            ),
        )
