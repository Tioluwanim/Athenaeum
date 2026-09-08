"""
api_main.py — FastAPI application for the v2 multi-user rebuild.

Run with:  uvicorn api_main:app --host 0.0.0.0 --port 8000

This sits ALONGSIDE the existing Streamlit app (streamlit_app.py / run.py),
which keeps working unchanged for anyone still using it. This is the new
surface the Next.js frontend talks to.
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth import CurrentUser, get_current_user, require_admin
from app.config_ext import ADMIN_INVITE_CODE, CORS_ALLOWED_ORIGINS
from app.db.repository import init_db, repository
from app.services.analysis_service import analysis_service
from app.services.hybrid_retrieval import hybrid_search
from app.services.model_router import model_router
from app.services.pdf_service import pdf_service
from app.services.rag_graph import run_research
from app.services.storage_service import storage_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

@asynccontextmanager
async def _lifespan(app: FastAPI):
    init_db()
    logger.info("API startup complete — model providers: %s", model_router.status())
    yield


app = FastAPI(title="PDF Research Analyzer API", version="2.0.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request logging / monitoring middleware ─────────────────────────────

@app.middleware("http")
async def _request_logging(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    started = time.monotonic()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        status_code = response.status_code if response else 500
        logger.info(
            "[%s] %s %s -> %d (%dms)",
            request_id, request.method, request.url.path, status_code, elapsed_ms,
        )
        if response is not None:
            response.headers["X-Request-ID"] = request_id


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": "Something went wrong. Please try again."},
    )


# ── Schemas ──────────────────────────────────────────────────────────────

class DocumentOut(BaseModel):
    doc_id: str
    filename: str
    title: str = ""
    status: str
    page_count: int = 0
    chunk_count: int = 0
    authors: list[str] = []
    year: str = ""
    updated_at: str = ""
    last_error: Optional[str] = None


class UploadResult(BaseModel):
    doc_id: str
    filename: str
    status: str
    duplicate_of: Optional[str] = None


class ResearchRequest(BaseModel):
    query: str
    doc_id: Optional[str] = None


class CitationOut(BaseModel):
    citation_id: str
    doc_id: str
    filename: str = ""
    page_number: int
    section_type: str
    snippet: str
    score: float


class ResearchResult(BaseModel):
    answer: str
    citations: list[CitationOut]
    provider_used: str
    timings_ms: dict[str, int]


# ── Health / monitoring ──────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "providers": model_router.status(),
        "storage_backend": storage_service.backend_name,
    }


# ── Auth ─────────────────────────────────────────────────────────────────

@app.get("/api/auth/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return user


class PromoteRequest(BaseModel):
    invite_code: str


@app.post("/api/auth/promote-to-admin")
def promote_to_admin(body: PromoteRequest, user: CurrentUser = Depends(get_current_user)):
    """One-time bootstrap: the first admin(s) promote themselves with a
    server-side invite code (set via ADMIN_INVITE_CODE) since there's no
    existing admin yet to grant the role. After that, admins should manage
    roles directly rather than sharing the code further."""
    if not ADMIN_INVITE_CODE:
        raise HTTPException(status_code=403, detail="Admin self-promotion is disabled")
    if body.invite_code != ADMIN_INVITE_CODE:
        raise HTTPException(status_code=403, detail="Invalid invite code")

    from app.db.models import User
    from app.db.session import get_session
    with get_session() as session:
        row = session.get(User, user.id)
        row.role = "admin"
        session.commit()
    return {"status": "promoted"}


# ── Documents ────────────────────────────────────────────────────────────

@app.get("/api/documents", response_model=list[DocumentOut])
def list_documents(user: CurrentUser = Depends(get_current_user)):
    docs = analysis_service.list_documents()
    return [
        DocumentOut(
            doc_id=d["doc_id"], filename=d["filename"], title=d.get("title", ""),
            status=d.get("status", ""), page_count=d.get("pages", 0),
            chunk_count=d.get("chunks", 0), authors=d.get("authors") or [],
            year=d.get("year", ""), updated_at=str(d.get("updated_at", "")),
            last_error=d.get("last_error"),
        )
        for d in docs
    ]


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str, user: CurrentUser = Depends(get_current_user)):
    info = analysis_service.get_document_info(doc_id)
    if not info:
        raise HTTPException(status_code=404, detail="Document not found")
    return info


@app.get("/api/documents/{doc_id}/file")
def get_document_file(doc_id: str, user: CurrentUser = Depends(get_current_user)):
    """Streams the original PDF bytes for the viewer. Requires a valid
    Firebase session like every other endpoint — the frontend fetches this
    with an Authorization header and turns the response into a blob URL
    rather than linking to it directly, since <iframe>/<embed> can't attach
    custom headers."""
    from fastapi.responses import Response
    doc = pdf_service.load_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        data = open(doc.file_path, "rb").read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Source file is missing on disk")
    return Response(content=data, media_type="application/pdf")


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, user: CurrentUser = Depends(require_admin)):
    ok = analysis_service.delete_document(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted"}


def _process_document_background(doc_id: str) -> None:
    try:
        analysis_service.process_document(doc_id)
    except Exception as e:  # noqa: BLE001
        logger.error("Background processing failed for %s: %s", doc_id, e, exc_info=True)


@app.post("/api/documents/upload", response_model=list[UploadResult])
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    user: CurrentUser = Depends(require_admin),  # only admins add to the shared library
):
    """Multi-file upload with checksum-based duplicate detection. Each
    accepted file is queued for background processing (extraction →
    chunking → embedding → indexing) so the request returns immediately —
    important with 10-15 staff possibly uploading batches at once."""
    results: list[UploadResult] = []

    for upload in files:
        file_bytes = await upload.read()
        checksum = storage_service.compute_checksum(file_bytes)

        existing = repository.get_document_by_checksum(checksum)
        if existing is not None:
            results.append(UploadResult(
                doc_id=existing.doc_id, filename=upload.filename, status="duplicate",
                duplicate_of=existing.doc_id,
            ))
            continue

        doc, error = pdf_service.save_upload(file_bytes, upload.filename)
        if error is not None:
            results.append(UploadResult(doc_id="", filename=upload.filename, status=f"error: {error.detail}"))
            continue

        repository.set_document_checksum(doc.doc_id, checksum)

        if storage_service.backend_name == "r2":
            try:
                storage_service.put_document(doc.filename, file_bytes, doc_id=doc.doc_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("R2 mirror upload failed for %s (local copy still ingests fine): %s", doc.doc_id, e)

        background_tasks.add_task(_process_document_background, doc.doc_id)
        results.append(UploadResult(doc_id=doc.doc_id, filename=doc.filename, status="processing"))

    return results


# ── Search ───────────────────────────────────────────────────────────────

@app.get("/api/search")
def search(q: str, doc_id: Optional[str] = None, top_k: int = 8, user: CurrentUser = Depends(get_current_user)):
    results = hybrid_search(query=q, doc_id=doc_id, top_k=top_k)
    return [
        {
            "chunk_id": r.chunk.chunk_id, "doc_id": r.chunk.doc_id,
            "page_number": r.chunk.page_number, "section_type": str(r.chunk.section_type),
            "content": r.chunk.content, "score": r.score,
        }
        for r in results
    ]


# ── Research (the core "ask a question, get a cited answer" flow) ───────

@app.post("/api/research", response_model=ResearchResult)
async def research(body: ResearchRequest, user: CurrentUser = Depends(get_current_user)):
    state = await run_research(query=body.query, doc_id=body.doc_id)
    return ResearchResult(
        answer=state.get("answer", ""),
        citations=[CitationOut(**c.model_dump()) for c in state.get("citations", [])],
        provider_used=state.get("provider_used", "none"),
        timings_ms=state.get("timings_ms", {}),
    )


@app.post("/api/research/stream")
async def research_stream(body: ResearchRequest, user: CurrentUser = Depends(get_current_user)):
    """Streams research progress as newline-delimited JSON events, then the
    final answer — powers the frontend's 'Research Progress' UI (rewrite →
    retrieve → grade → generate stages) instead of a single opaque wait."""

    async def event_stream():
        def emit(event: str, **data):
            return json.dumps({"event": event, **data}) + "\n"

        yield emit("stage", stage="searching", label="Searching the library…")
        state = await run_research(query=body.query, doc_id=body.doc_id)
        yield emit("stage", stage="done", label="Answer ready", timings_ms=state.get("timings_ms", {}))

        citations = [c.model_dump() for c in state.get("citations", [])]
        yield emit("result", answer=state.get("answer", ""), citations=citations,
                    provider_used=state.get("provider_used", "none"))

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


# ── Library stats ────────────────────────────────────────────────────────

@app.get("/api/library/stats")
def library_stats(user: CurrentUser = Depends(get_current_user)):
    return analysis_service.get_library_stats()
