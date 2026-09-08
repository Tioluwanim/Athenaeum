"""
app/services/model_router.py — Provider-agnostic ModelRouter.

Generalizes the retry/backoff/fallback pattern already proven in
ai_router.py (which stays in place, unmodified, powering the legacy
Streamlit UI) to an ordered chain of providers used by the v2 API:

    1. Groq         — primary. Fastest inference, used for every call in
                       the LangGraph research pipeline (rewrite, grade,
                       generate) unless it's down or rate-limited.
    2. OpenRouter    — fallback. Same free-router approach as ai_router.py.
    3. HuggingFace   — last resort.

All three providers expose OpenAI-compatible chat-completion APIs, so one
client shape covers all of them — the router differs only in which client
it tries first and how it logs/labels the attempt.

Concurrency: a single asyncio.Semaphore caps in-flight Groq calls across
ALL users (GROQ_MAX_CONCURRENCY, default 4) so 10-15 simultaneous chat
requests queue politely instead of all hitting Groq's rate limit at once
and cascading into the fallback chain unnecessarily.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

from app.config import (
    OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_TIMEOUT,
    HUGGINGFACE_API_KEY, HUGGINGFACE_MODEL, HUGGINGFACE_BASE_URL, HUGGINGFACE_TIMEOUT,
    MAX_TOKENS, TEMPERATURE, RETRY_MAX_ATTEMPTS,
)
from app.config_ext import (
    GROQ_API_KEY, GROQ_MODEL_FAST, GROQ_MODEL_MAIN, GROQ_TIMEOUT,
    GROQ_MAX_TOKENS, GROQ_MAX_CONCURRENCY,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

_OR_FREE_ROUTER = "openrouter/free"


@dataclass
class ModelResponse:
    text: str
    provider: str
    model: str
    latency_ms: int


class ProviderUnavailable(Exception):
    """Raised internally when a provider fails; caller falls through to the next."""


def _build_groq_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
        timeout=GROQ_TIMEOUT,
    )


def _build_openrouter_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        timeout=OPENROUTER_TIMEOUT,
        default_headers={
            "HTTP-Referer": "https://pdf-research-analyzer.local",
            "X-Title": "PDF Research Analyzer",
        },
    )


def _build_huggingface_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(
        api_key=HUGGINGFACE_API_KEY,
        base_url=HUGGINGFACE_BASE_URL,
        timeout=HUGGINGFACE_TIMEOUT,
    )


class ModelRouter:
    def __init__(self) -> None:
        self._groq = None
        self._or = None
        self._hf = None
        self._groq_sem = asyncio.Semaphore(GROQ_MAX_CONCURRENCY)
        logger.info(
            "ModelRouter ready — groq_configured=%s or_configured=%s hf_configured=%s "
            "groq_max_concurrency=%d",
            bool(GROQ_API_KEY), bool(OPENROUTER_API_KEY), bool(HUGGINGFACE_API_KEY),
            GROQ_MAX_CONCURRENCY,
        )

    @property
    def groq(self):
        if self._groq is None:
            self._groq = _build_groq_client()
        return self._groq

    @property
    def openrouter(self):
        if self._or is None:
            self._or = _build_openrouter_client()
        return self._or

    @property
    def huggingface(self):
        if self._hf is None:
            self._hf = _build_huggingface_client()
        return self._hf

    def status(self) -> dict:
        return {
            "groq":        {"configured": bool(GROQ_API_KEY), "model": GROQ_MODEL_MAIN},
            "openrouter":  {"configured": bool(OPENROUTER_API_KEY), "model": OPENROUTER_MODEL or _OR_FREE_ROUTER},
            "huggingface": {"configured": bool(HUGGINGFACE_API_KEY), "model": HUGGINGFACE_MODEL},
        }

    # ── Non-streaming completion, used by graph nodes (rewrite/grade/cite) ──

    async def complete(
        self,
        messages: list[dict],
        *,
        fast: bool = False,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> ModelResponse:
        """Try Groq, then OpenRouter, then HuggingFace. `fast=True` uses the
        cheaper Groq model for high-volume, low-stakes calls (query rewrite,
        relevance grading) — irrelevant to the fallback providers, which
        only have one configured model each."""
        errors: list[str] = []

        if GROQ_API_KEY:
            try:
                async with self._groq_sem:
                    return await self._complete_openai_compatible(
                        self.groq, "groq",
                        GROQ_MODEL_FAST if fast else GROQ_MODEL_MAIN,
                        messages, max_tokens or GROQ_MAX_TOKENS, temperature,
                    )
            except Exception as e:  # noqa: BLE001
                errors.append(f"groq: {e}")
                logger.warning("Groq completion failed, falling back: %s", e)

        if OPENROUTER_API_KEY:
            try:
                return await self._complete_openai_compatible(
                    self.openrouter, "openrouter", OPENROUTER_MODEL or _OR_FREE_ROUTER,
                    messages, max_tokens or MAX_TOKENS, temperature or TEMPERATURE,
                )
            except Exception as e:  # noqa: BLE001
                errors.append(f"openrouter: {e}")
                logger.warning("OpenRouter completion failed, falling back: %s", e)

        if HUGGINGFACE_API_KEY:
            try:
                return await self._complete_openai_compatible(
                    self.huggingface, "huggingface", HUGGINGFACE_MODEL,
                    messages, max_tokens or MAX_TOKENS, temperature or TEMPERATURE,
                )
            except Exception as e:  # noqa: BLE001
                errors.append(f"huggingface: {e}")
                logger.error("HuggingFace completion failed (last resort): %s", e)

        raise ProviderUnavailable(
            "All model providers failed or are unconfigured: " + "; ".join(errors)
        )

    async def _complete_openai_compatible(
        self, client, provider: str, model: str,
        messages: list[dict], max_tokens: int, temperature: Optional[float],
    ) -> ModelResponse:
        started = time.monotonic()
        last_exc: Optional[Exception] = None

        for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=max(float(temperature if temperature is not None else 0.2), 0.0),
                )
                text = resp.choices[0].message.content or ""
                latency_ms = int((time.monotonic() - started) * 1000)
                return ModelResponse(text=text, provider=provider, model=model, latency_ms=latency_ms)
            except Exception as e:  # noqa: BLE001
                last_exc = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status == 429 and attempt < RETRY_MAX_ATTEMPTS:
                    wait = 2 ** attempt
                    logger.warning("%s 429 — retrying in %ds (attempt %d/%d)",
                                    provider, wait, attempt, RETRY_MAX_ATTEMPTS)
                    await asyncio.sleep(wait)
                    continue
                if status and 400 <= status < 500:
                    raise
                if attempt < RETRY_MAX_ATTEMPTS:
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                raise
        raise last_exc or ProviderUnavailable(f"{provider} failed with no exception captured")

    # ── Streaming completion, used for the final answer sent to the client ──

    async def stream(
        self, messages: list[dict], *, fast: bool = False,
    ) -> AsyncGenerator[tuple[str, str], None]:
        """Yields (provider, token) pairs. Falls back to a full non-streaming
        `complete()` on the next provider if the current one fails mid-stream,
        so the caller doesn't need its own fallback logic."""
        chain = []
        if GROQ_API_KEY:
            chain.append(("groq", self.groq, GROQ_MODEL_FAST if fast else GROQ_MODEL_MAIN))
        if OPENROUTER_API_KEY:
            chain.append(("openrouter", self.openrouter, OPENROUTER_MODEL or _OR_FREE_ROUTER))
        if HUGGINGFACE_API_KEY:
            chain.append(("huggingface", self.huggingface, HUGGINGFACE_MODEL))

        for provider, client, model in chain:
            try:
                sem = self._groq_sem if provider == "groq" else _NULL_SEM
                async with sem:
                    stream = await client.chat.completions.create(
                        model=model, messages=messages,
                        max_tokens=GROQ_MAX_TOKENS if provider == "groq" else MAX_TOKENS,
                        temperature=0.2, stream=True,
                    )
                    got_any = False
                    async for chunk in stream:
                        delta = chunk.choices[0].delta if chunk.choices else None
                        if delta and delta.content:
                            got_any = True
                            yield provider, delta.content
                    if got_any:
                        return
            except Exception as e:  # noqa: BLE001
                logger.warning("%s streaming failed, trying next provider: %s", provider, e)
                continue

        yield "none", (
            "All model providers are currently unavailable. Please check API keys "
            "(GROQ_API_KEY, OPENROUTER_API_KEY, HUGGINGFACE_API_KEY) and try again."
        )


class _NullSemaphore:
    async def __aenter__(self): return None
    async def __aexit__(self, *a): return None


_NULL_SEM = _NullSemaphore()

model_router = ModelRouter()
