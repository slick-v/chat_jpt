
import logging
import time
from pathlib import Path

from fastapi import FastAPI , Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend import llm, store, usage
from backend.config import settings
from backend.schemas import ChatRequest, ChatResponse


logging.basicConfig(level=logging.INFO)

app = FastAPI(title="chat_jpt")

@app.exception_handler(llm.LLMError)
def handle_llm_error(request: Request, exc:llm.LLMError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


@app.get("/")
def health():
    return {"status" : "ok!"}

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    conversation_id, history = store.get_or_create(req.conversation_id)
    messages = store.build_context(history, req.message)


    start = time.perf_counter()
    reply, tokens = llm.chat(messages, settings.system_prompt)
    latency_ms = int((time.perf_counter() - start) * 1000)

    store.add_turn(history, req.message, reply)
    stats = usage.record(settings.model_name, tokens["input_tokens"], tokens["output_tokens"], latency_ms)
    return ChatResponse(reply=reply, conversation_id=conversation_id, usage=stats)



@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    conversation_id, history = store.get_or_create(req.conversation_id)
    messages = store.build_context(history, req.message)

    tokens = {"input_tokens": 0, "output_tokens": 0}
    start = time.perf_counter()
    chunks = llm.chat_stream(messages, settings.system_prompt, tokens)  # raises here if the request fails

    def body():
        parts = []
        for piece in chunks:
            parts.append(piece)
            yield piece
        latency_ms = int((time.perf_counter() - start) * 1000)
        store.add_turn(history, req.message, "".join(parts))
        usage.record(settings.model_name, tokens["input_tokens"], tokens["output_tokens"], latency_ms)

    return StreamingResponse(
        body(),
        media_type="text/plain",
        headers={"X-Conversation-Id": conversation_id},
    )


@app.get("/usage")
def get_usage():
    return usage.totals()


# Serves frontend/index.html at http://127.0.0.1:8000/app/
app.mount(
    "/app",
    StaticFiles(directory=Path(__file__).parent.parent / "frontend", html=True),
    name="frontend",
)