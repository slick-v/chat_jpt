from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


class Usage(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    usage: Usage


    