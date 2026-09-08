"""
app/config_ext.py — Additive settings for the v2 rebuild.

Kept separate from app/config.py (853 lines, already load-bearing for the
Streamlit app) so the new FastAPI + LangGraph + Groq + multi-user layer
never risks breaking the existing app on import. Import BOTH modules from
new code; app/config.py is still the source of truth for paths, chunking,
and DB settings.
"""

from __future__ import annotations

import os


def _env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ── Groq (the "brain") ───────────────────────────────────────────────────────
GROQ_API_KEY       = _env_str("GROQ_API_KEY")
# Cheap/fast model for query rewriting + relevance grading (high volume, low stakes)
GROQ_MODEL_FAST    = _env_str("GROQ_MODEL_FAST", "llama-3.1-8b-instant")
# Larger model for the actual answer generation
GROQ_MODEL_MAIN    = _env_str("GROQ_MODEL_MAIN", "llama-3.3-70b-versatile")
GROQ_TIMEOUT       = _env_int("GROQ_TIMEOUT", 60)
GROQ_MAX_TOKENS    = _env_int("GROQ_MAX_TOKENS", 1024)
# Max concurrent in-flight Groq calls across ALL users — the real ceiling for
# 10-15 simultaneous ICT-section staff hitting one shared API key.
GROQ_MAX_CONCURRENCY = _env_int("GROQ_MAX_CONCURRENCY", 4)

# ── Retrieval ─────────────────────────────────────────────────────────────
# Weight given to vector (semantic) search vs BM25 (keyword) search when the
# two rankings are fused. 0.5 = equal weight.
HYBRID_VECTOR_WEIGHT = _env_float("HYBRID_VECTOR_WEIGHT", 0.6)
RRF_K                = _env_int("RRF_K", 60)  # reciprocal rank fusion constant
RETRIEVAL_GRADE_ENABLED = _env_bool("RETRIEVAL_GRADE_ENABLED", True)
RETRIEVAL_MAX_RETRIES   = _env_int("RETRIEVAL_MAX_RETRIES", 1)

# ── Auth / multi-user (Firebase Authentication) ────────────────────────────
# Identity is Firebase's job (Google sign-in, email/password, password reset,
# email verification). FastAPI only verifies the ID token — see app/auth.py.
# One of these two must be set in any deployment that isn't running on GCP
# with Application Default Credentials available:
#   FIREBASE_SERVICE_ACCOUNT_JSON  — the service-account JSON, inline
#   FIREBASE_SERVICE_ACCOUNT_PATH  — path to the service-account JSON file
ADMIN_INVITE_CODE = _env_str("ADMIN_INVITE_CODE", "")  # required to self-promote to admin once

# ── API / CORS ─────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in _env_str(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000"
    ).split(",") if o.strip()
]

if GROQ_API_KEY == "" and _env_bool("GROQ_REQUIRED", True):
    # Not raised at import time to keep `alembic upgrade head` and other
    # tooling working without secrets present — checked at app startup instead.
    pass
