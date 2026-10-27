import uuid

from backend import db
from backend.config import settings
import uuid

from backend import db
from backend.config import settings


def create_conversation(user_id: int, title: str) -> str:
    conversation_id = str(uuid.uuid4())
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, ?)",
            (conversation_id, user_id, title),
        )
    return conversation_id


def conversation_exists(user_id: int, conversation_id: str) -> bool:
    # Always filter by user_id too: otherwise anyone who has an id could read another user's chat
    with db.connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
    return row is not None


def list_conversations(user_id: int) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at FROM conversations WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_conversation(user_id: int, conversation_id: str) -> bool:
    # Messages are removed too, via ON DELETE CASCADE
    with db.connect() as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        return cur.rowcount > 0


def get_messages(conversation_id: str) -> list[dict]:
    # Full history, for showing a conversation in the UI
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_history(conversation_id: str) -> list[dict]:
    # Last N messages, oldest first, for sending to the LLM.
    # N is even and turns are saved in pairs, so the window always starts with "user",
    # which Bedrock requires later.
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM (
                SELECT id, role, content FROM messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) ORDER BY id
            """,
            (conversation_id, settings.max_history_messages),
        ).fetchall()
    return [dict(r) for r in rows]


def build_context(history: list[dict], user_message: str) -> list[dict]:
    return history + [{"role": "user", "content": user_message}]


def add_turn(conversation_id: str, user_message: str, reply: str) -> None:
    # Only saved after a successful reply, so a failed call never leaves an orphan user message
    with db.connect() as conn:
        conn.executemany(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
            [
                (conversation_id, "user", user_message),
                (conversation_id, "assistant", reply),
            ],
        )