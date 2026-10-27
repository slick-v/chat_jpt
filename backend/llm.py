from collections.abc import Iterator


import groq
from groq import Groq


from backend.config import settings


_client = Groq(api_key=settings.groq_api_key, max_retries=2, timeout=60)


class LLMError(Exception):
    status_code = 502

class LLMRateLimited(LLMError):
    status_code = 429

class LLMUnavailable(LLMError):
    status_code = 503


def _wrap(e: groq.APIError) -> LLMError:

    # Turn provider errors into our own, so the rest of the app never imports groq

    if isinstance(e, groq.RateLimitError):
        return LLMRateLimited("Rate limited by the LLM provider, try again shortly")
    if isinstance(e, groq.APIConnectionError):
        return LLMUnavailable("Could not reach the LLM provider")
    return LLMError("LLM request failed")


def _to_provider_messages(messages: list[dict], system:str) -> list[dict]:
    # Neutral format -> Groq format (Groq takes the system prompt as the first message)

    return [{"role": "system", "content": system}, *messages]



def chat(messages: list[dict], system: str) -> tuple[str, dict]:

    try:
        response = _client.chat.completions.create(
            model=settings.model_name,
            messages=_to_provider_messages(messages,system),
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
        )
    except groq.APIError as e:
        raise _wrap(e) from e

    text = response.choices[0].message.content or ""
    usage = {
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,

    }
    return text, usage



def chat_stream(messages: list[dict], system: str, usage_out: dict) -> Iterator[str]:

    # Not a generator itself: the request is sent right here, so auth/rate-limit
    # errors raise before the HTTP response starts and the client gets a real status code


    try: 
        stream = _client.chat.completions.create(
            model=settings.model_name,
            messages=_to_provider_messages(messages, system),
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
            stream=True,
        )
    except groq.APIError as e:
        raise _wrap(e) from e

    def generate() -> Iterator[str]:
        try:
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                # Groq sends token usage on the last chunk
                x_groq = getattr(chunk, "x_groq", None)
                if x_groq and x_groq.usage:
                    usage_out["input_tokens"] = x_groq.usage.prompt_tokens
                    usage_out["output_tokens"] = x_groq.usage.completion_tokens
        except groq.APIError:
            yield "\n\n[stream interrupted]"

    return generate()



