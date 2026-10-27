import logging

from backend import db

logger = logging.getLogger("usage")

# USD per 1M tokens: (input, output). Check groq.com/pricing for current rates.
PRICES_PER_MILLION = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "llama-3.1-8b-instant": (0.05, 0.08),
}


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = PRICES_PER_MILLION.get(model, (0.0, 0.0))
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def record(user_id: int, model: str, input_tokens: int, output_tokens: int, latency_ms: int) -> dict:
    cost_usd = cost(model, input_tokens, output_tokens)

    with db.connect() as conn:
        conn.execute(
            """
            INSERT INTO usage_log (user_id, model, input_tokens, output_tokens, cost_usd, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, model, input_tokens, output_tokens, cost_usd, latency_ms),
        )

    logger.info(
        "user=%d model=%s in=%d out=%d latency=%dms cost=$%.6f",
        user_id, model, input_tokens, output_tokens, latency_ms, cost_usd,
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
    }


def totals(user_id: int) -> dict:
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)                        AS requests,
                   COALESCE(SUM(input_tokens), 0)  AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(cost_usd), 0.0)    AS cost_usd
            FROM usage_log
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    return dict(row)