import uuid

from backend.config import settings

# In-memory for now; swap for SQLite/Redis later without touching main.py
_conversations: dict[str, list[dict]] = {}


def get_or_create(conversation_id: str | None) -> tuple[str, list[dict]]:
    if conversation_id not in _conversations:
        conversation_id = str(uuid.uuid4())
        _conversations[conversation_id] = []
    return conversation_id, _conversations[conversation_id]


def build_context(history: list[dict], user_message: str) -> list[dict]:
    # Trim old turns so long chats don't grow cost forever.
    # History is always even (user/assistant pairs), so the window starts with "user",
    # which Bedrock requires later.
    return history[-settings.max_history_messages:] + [{"role": "user", "content": user_message}]


def add_turn(history: list[dict], user_message: str, reply: str) -> None:
    # Only saved after a successful reply, so a failed call never leaves an orphan user message
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})