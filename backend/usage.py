import logging


logger = logging.getLogger("usage")

# USD per 1M tokens: (input, output). Check groq.com/pricing for current rates.


PRICES_PER_MILLION = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "llama-3.1-8b-instant": (0.05, 0.08),
}

_totals = {
    "requests": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cost_usd": 0.0
}



def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = PRICES_PER_MILLION.get(model, (0.0, 0.0))
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000




def record(model: str, input_tokens: int, output_tokens: int, latency_ms: int) -> dict:
    cost_usd = cost(model, input_tokens, output_tokens)

    _totals["requests"] += 1
    _totals["input_tokens"] += input_tokens
    _totals["output_tokens"] += output_tokens
    _totals["cost_usd"] += cost_usd

    logger.info(
        "model=%s in=%d out=%d latency=%dms cost=$%.6f",
        model, input_tokens, output_tokens, latency_ms, cost_usd,
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
    }


def totals() -> dict:
    return dict(_totals)