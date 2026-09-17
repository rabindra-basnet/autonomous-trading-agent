"""Shared OpenAI-compatible chat client with token usage & cost accounting.

Creates a single ``AsyncOpenAI`` connection pool shared by every module that
talks to the configured LLM (researcher, multi-agent desk, ...) instead of each
module spinning up its own client and HTTP session. Every completion returns
token usage and an estimated USD cost, and a summary row is persisted to the
PostgreSQL ``llm_usage`` table without blocking the caller.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger("SharedLLMClient")

_client: AsyncOpenAI | None = None
_usage_store: Any = None


@dataclass(frozen=True)
class LLMUsage:
    """Token usage and estimated cost for a single completion."""

    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    input_price_per_1m: float = 0.0
    output_price_per_1m: float = 0.0
    cost_usd: float = 0.0


@dataclass(frozen=True)
class ChatResult:
    """Structured chat completion: message content plus usage/cost summary."""

    content: str
    usage: LLMUsage


def get_client() -> AsyncOpenAI:
    """Return the process-wide ``AsyncOpenAI`` client, building it on first use."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.llm_base_url.rstrip("/"),
            api_key=settings.llm_api_key,
            timeout=25.0,
            max_retries=2,
        )
    return _client


def _model_prices(model: str) -> tuple[float, float]:
    """Return (input, output) USD price per 1M tokens for a model.

    Per-model overrides from ``OPENAI_MODEL_PRICES`` win; otherwise the flat
    ``OPENAI_INPUT_PRICE_PER_1M`` / ``OPENAI_OUTPUT_PRICE_PER_1M`` apply.
    """
    override = settings.llm_model_prices.get(model) or {}
    input_price = float(override.get("input_per_1m", settings.llm_input_price_per_1m))
    output_price = float(override.get("output_per_1m", settings.llm_output_price_per_1m))
    return input_price, output_price


def _build_usage(model: str, prompt_tokens: int, completion_tokens: int) -> LLMUsage:
    input_price, output_price = _model_prices(model)
    cost = (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000.0
    return LLMUsage(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        input_price_per_1m=input_price,
        output_price_per_1m=output_price,
        cost_usd=round(cost, 8),
    )


async def _persist_usage(usage: LLMUsage) -> None:
    """Fire-and-forget persistence of a usage row to PostgreSQL (non-blocking)."""
    global _usage_store
    try:
        if _usage_store is None:
            from app.storage.postgres import PostgresStorage

            _usage_store = PostgresStorage()
        await _usage_store.save_llm_usage(
            id=f"usage_{datetime.now(UTC).timestamp() * 1000:.0f}_{uuid.uuid4().hex[:6]}",
            model=usage.model,
            provider=settings.llm_base_url,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            input_price_per_1m=usage.input_price_per_1m,
            output_price_per_1m=usage.output_price_per_1m,
            cost_usd=usage.cost_usd,
        )
    except Exception as e:
        logger.warning("Failed to persist LLM usage to DB: %s", e)


async def chat_completion(
    system: str,
    user: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    persist_usage: bool = True,
) -> ChatResult:
    """Send a chat completion on the shared client.

    Returns a ``ChatResult`` with the message content and an ``LLMUsage``
    summary (token counts + estimated USD cost). When ``persist_usage`` is set,
    the usage row is written to the database in the background.
    """
    resolved_model = model or settings.llm_model
    try:
        resp = await get_client().chat.completions.create(
            model=resolved_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        content = resp.choices[0].message.content or ""
        usage_obj = resp.usage
        usage = _build_usage(
            resolved_model,
            int(getattr(usage_obj, "prompt_tokens", 0) or 0),
            int(getattr(usage_obj, "completion_tokens", 0) or 0),
        )
    except Exception as e:
        logger.warning("LLM chat completion failed: %s", e)
        content = ""
        usage = _build_usage(resolved_model, 0, 0)

    if persist_usage:
        asyncio.create_task(_persist_usage(usage))
    return ChatResult(content=content, usage=usage)