import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles

from backend import auth, db, llm, store, usage
from backend.auth import CurrentUser
from backend.config import settings
from backend.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationSummary,
    MessageOut,
    RegisterRequest,
    Token,
    UserOut,
)

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()  # creates the tables on startup if they don't exist yet
    yield


app = FastAPI(title="chat_jpt", lifespan=lifespan)


@app.exception_handler(llm.LLMError)
def handle_llm_error(request: Request, exc: llm.LLMError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.get("/")
def health():
    return {"status": "ok!"}


# ---------- auth ----------

@app.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest):
    user = auth.create_user(req.username, req.password)
    if user is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    return user


@app.post("/auth/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    # Takes form fields (not JSON) so the "Authorize" button in /docs works
    user = auth.authenticate(form.username, form.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=auth.create_access_token(user["id"]))


@app.get("/auth/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


# ---------- chat ----------

def _resolve_conversation(user_id: int, req: ChatRequest) -> str:
    if req.conversation_id is None:
        return store.create_conversation(user_id, title=req.message[:60])
    # 404 (not 403) for someone else's conversation, so we don't reveal that it exists
    if not store.conversation_exists(user_id, req.conversation_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return req.conversation_id


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, user: CurrentUser):
    conversation_id = _resolve_conversation(user["id"], req)
    messages = store.build_context(store.get_history(conversation_id), req.message)

    start = time.perf_counter()
    reply, tokens = llm.chat(messages, settings.system_prompt)
    latency_ms = int((time.perf_counter() - start) * 1000)

    store.add_turn(conversation_id, req.message, reply)
    stats = usage.record(user["id"], settings.model_name, tokens["input_tokens"], tokens["output_tokens"], latency_ms)
    return ChatResponse(reply=reply, conversation_id=conversation_id, usage=stats)


@app.post("/chat/stream")
def chat_stream(req: ChatRequest, user: CurrentUser):
    conversation_id = _resolve_conversation(user["id"], req)
    messages = store.build_context(store.get_history(conversation_id), req.message)

    tokens = {"input_tokens": 0, "output_tokens": 0}
    start = time.perf_counter()
    chunks = llm.chat_stream(messages, settings.system_prompt, tokens)  # raises here if the request fails

    def body():
        parts = []
        for piece in chunks:
            parts.append(piece)
            yield piece
        latency_ms = int((time.perf_counter() - start) * 1000)
        store.add_turn(conversation_id, req.message, "".join(parts))
        usage.record(user["id"], settings.model_name, tokens["input_tokens"], tokens["output_tokens"], latency_ms)

    return StreamingResponse(
        body(),
        media_type="text/plain",
        headers={"X-Conversation-Id": conversation_id},
    )


# ---------- conversations ----------

@app.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(user: CurrentUser):
    return store.list_conversations(user["id"])


@app.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def get_conversation_messages(conversation_id: str, user: CurrentUser):
    if not store.conversation_exists(user["id"], conversation_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return store.get_messages(conversation_id)


@app.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, user: CurrentUser):
    if not store.delete_conversation(user["id"], conversation_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")


@app.get("/usage")
def get_usage(user: CurrentUser):
    return usage.totals(user["id"])


# Serves frontend/index.html at http://127.0.0.1:8000/app/
app.mount(
    "/app",
    StaticFiles(directory=Path(__file__).parent.parent / "frontend", html=True),
    name="frontend",
)