"""
embedding_service.py - Hosted embeddings via the HuggingFace Inference API.

v3 rewrite — was previously loading `sentence-transformers` + `torch`
in-process. That's what was crashing document processing on Render: the
combined weight of PyTorch + the model easily exceeds a small instance's
RAM on first load, silently killing the whole server process mid-request
(hence documents stuck on "Queued" forever — the background task never
got to write a status past "uploaded").

This version calls HuggingFace's hosted feature-extraction endpoint
instead — no model ever loads into this process's memory. The trade-off
is a network round-trip per embedding call instead of an in-process one;
mitigated with batching, retries, and a query-embedding cache, same as
before.

Public interface is unchanged (embed_chunks, embed_query, embed_texts,
dimension, model_name, is_loaded, cosine_similarity) — nothing else in
the codebase (rag_service.py, hybrid_retrieval.py, etc.) needs to change.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from functools import lru_cache
from typing import Optional

import numpy as np
import requests

# Silence HF noise before any optional import happens (harmless to keep
# even though nothing local loads anymore — cheap insurance).
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)

from app.config import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    HUGGINGFACE_API_KEY,
    HUGGINGFACE_TIMEOUT,
    RETRY_MAX_ATTEMPTS,
)
from app.models.schemas import TextChunk
from app.utils.logger import ServiceLogger, get_logger

logger = get_logger(__name__)

# HF's current, verified endpoint shape (their old api-inference.huggingface.co
# host was retired — router.huggingface.co is the replacement).
_HF_FEATURE_EXTRACTION_URL = "https://router.huggingface.co/hf-inference/models/{model}/pipeline/feature-extraction"

# HF batches reasonably well but very large single requests risk timing out
# on their side before returning — keep individual API calls to a sane size
# and let embed_chunks() loop over batches.
_API_BATCH_SIZE = 32


class _FallbackEmbeddingModel:
    """
    Deterministic local fallback for when the HF API is unreachable or
    unconfigured (no API key, network blocked, HF outage, etc.). Produces
    normalized hashing-based vectors so the app keeps working — degraded
    retrieval quality rather than a hard failure. Pure numpy, no ML
    dependency, negligible memory.
    """

    def __init__(self, dimension: int) -> None:
        self.dimension = int(dimension)

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors: list[np.ndarray] = []
        for text in texts:
            vec = np.zeros(self.dimension, dtype=np.float32)
            cleaned = (text or "").strip()
            if cleaned:
                tokens = re.findall(r"[A-Za-z0-9_']+", cleaned.lower()) or [cleaned.lower()]
                for token in tokens:
                    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
                    idx = int.from_bytes(digest[:4], "little") % self.dimension
                    sign = 1.0 if (digest[4] % 2 == 0) else -1.0
                    weight = 1.0 + (digest[5] / 255.0)
                    vec[idx] += sign * weight
            norm = float(np.linalg.norm(vec))
            if norm > 0:
                vec /= norm
            vectors.append(vec)
        return np.vstack(vectors) if vectors else np.empty((0, self.dimension), dtype=np.float32)


_fallback_model: Optional[_FallbackEmbeddingModel] = None


def _get_fallback(dimension: int) -> _FallbackEmbeddingModel:
    global _fallback_model
    if _fallback_model is None:
        _fallback_model = _FallbackEmbeddingModel(dimension)
    return _fallback_model


def _call_hf_feature_extraction(texts: list[str], model_name: str) -> list[list[float]]:
    """One HTTP call to HF's hosted feature-extraction endpoint. Retries on
    429/5xx with backoff (HF's serverless models cold-start and occasionally
    return 503 while loading — worth retrying rather than falling back
    immediately). Raises on final failure; caller decides whether to fall
    back to the local hashing encoder."""
    if not HUGGINGFACE_API_KEY:
        raise RuntimeError("HUGGINGFACE_API_KEY is not configured")

    url = _HF_FEATURE_EXTRACTION_URL.format(model=model_name)
    headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}

    last_exc: Optional[Exception] = None
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(
                url, headers=headers, json={"inputs": texts}, timeout=HUGGINGFACE_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                if not isinstance(data, list) or not data:
                    raise ValueError(f"Unexpected HF response shape: {type(data)}")
                return data
            if resp.status_code in (429, 503) and attempt < RETRY_MAX_ATTEMPTS:
                wait = 2 ** attempt
                logger.warning(
                    "HF embeddings API %d (attempt %d/%d) — retrying in %ds",
                    resp.status_code, attempt, RETRY_MAX_ATTEMPTS, wait,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
        except requests.RequestException as e:
            last_exc = e
            if attempt < RETRY_MAX_ATTEMPTS:
                time.sleep(2 ** (attempt - 1))
                continue
            raise
    raise last_exc or RuntimeError("HF embeddings API failed with no exception captured")


def _auto_batch_size(n_texts: int) -> int:
    """Client-side batch size for looping over the HF API — independent of
    any local model, this just balances request count vs. payload size."""
    if n_texts < 50:
        return _API_BATCH_SIZE
    if n_texts < 500:
        return 48
    return 64


class EmbeddingService:
    """
    Calls HuggingFace's hosted feature-extraction API for encoding chunks
    and queries. No model is ever loaded into this process — the entire
    RAM cost of the old local approach is gone.
    """

    def __init__(self) -> None:
        self._model_name = EMBEDDING_MODEL
        self._dimension = EMBEDDING_DIMENSION
        self._api_available = bool(HUGGINGFACE_API_KEY)
        logger.info(
            "EmbeddingService ready — provider=%s model=%s dimension=%d",
            "huggingface-api" if self._api_available else "local-fallback",
            self._model_name, self._dimension,
        )

    def _encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self._dimension), dtype=np.float32)

        if self._api_available:
            try:
                batch_size = _auto_batch_size(len(texts))
                all_vecs: list[list[float]] = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    all_vecs.extend(_call_hf_feature_extraction(batch, self._model_name))
                arr = np.asarray(all_vecs, dtype=np.float32)
                if arr.ndim == 1:
                    arr = arr.reshape(1, -1)
                # Normalize — HF's raw feature-extraction output for
                # sentence-transformers models is already mean-pooled but
                # not guaranteed unit-normalized; normalize defensively so
                # cosine similarity behaves the same as the old local path.
                norms = np.linalg.norm(arr, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                return arr / norms
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "HF embeddings API failed, falling back to local hashing encoder "
                    "(retrieval quality will be degraded until this is resolved): %s",
                    exc,
                )

        return _get_fallback(self._dimension).encode(texts)

    # ── Public API (unchanged signatures) ────────────────────────────────

    def embed_chunks(
        self,
        chunks: list[TextChunk],
        doc_id: str = "",
        batch_size: int = 0,  # kept for signature compatibility; batching is internal now
        show_progress: bool = False,
    ) -> np.ndarray:
        slog = ServiceLogger("embedding_service", doc_id=doc_id)
        if not chunks:
            slog.warning("embed_chunks called with empty list")
            return np.empty((0, self._dimension), dtype=np.float32)

        slog.info("Embedding %d chunks via HF API …", len(chunks))
        vecs = self._encode([c.content for c in chunks])
        slog.info("Embeddings done ✓  shape=%s", str(vecs.shape))
        return vecs

    def embed_query(self, query: str) -> np.ndarray:
        if not query or not query.strip():
            raise ValueError("Query must not be empty.")
        cached = self._embed_query_cached(query.strip())
        return cached.copy()  # caller may mutate; never hand out the cached array

    @lru_cache(maxsize=256)
    def _embed_query_cached(self, query: str) -> np.ndarray:
        vec = self._encode([query])
        vec.setflags(write=False)
        return vec

    def embed_texts(self, texts: list[str], batch_size: int = 0) -> np.ndarray:
        return self._encode(texts)

    # ── Utilities ─────────────────────────────────────────────────────────

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def is_loaded(self) -> bool:
        """Kept for backward compatibility with callers that checked this
        before triggering a load — there's no load step anymore, so this
        just reflects whether the API path is configured."""
        return self._api_available

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        a, b = a.flatten(), b.flatten()
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))


# ── Singleton ─────────────────────────────────────────────────────────────
embedding_service = EmbeddingService()
