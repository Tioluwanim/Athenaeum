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
from app.db.repository import repository
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
    # NOT calling init_db() (Base.metadata.create_all) here anymore — it
    # was silently creating tables outside Alembic's migration tracking,
    # which then collided with `alembic upgrade head` in the Dockerfile's
    # startup command (DuplicateTable: relation "documents" already exists).
    # Alembic is now the single source of truth for schema — migrations
    # run once, before the app process starts (see Dockerfile CMD), never
    # from inside the app itself. init_db() still exists for tests, which
    # use a disposable SQLite DB with no migration history to protect.
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
    collection_id: Optional[int] = None
    collection_name: Optional[str] = None
    likely_scanned: bool = False


class CollectionOut(BaseModel):
    id: int
    name: str
    description: str = ""
    color: Optional[str] = None
    document_count: int = 0
    created_at: str
    updated_at: str


class CollectionCreate(BaseModel):
    name: str
    description: str = ""
    color: Optional[str] = None


class CollectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None


class AssignCollectionRequest(BaseModel):
    collection_id: Optional[int] = None  # null unassigns (back to "unfiled")


class UploadResult(BaseModel):
    doc_id: str
    filename: str
    status: str
    duplicate_of: Optional[str] = None


class ResearchRequest(BaseModel):
    query: str
    doc_id: Optional[str] = None
    session_id: Optional[int] = None  # continue an existing research session; omit to start a new one


class CitationOut(BaseModel):
    citation_id: str
    doc_id: str
    filename: str = ""
    page_number: int
    section_type: str
    snippet: str
    score: float


class ResearchResult(BaseModel):
    session_id: int
    answer: str
    citations: list[CitationOut]
    provider_used: str
    timings_ms: dict[str, int]


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    provider: Optional[str] = None
    citations: list[CitationOut] = []
    created_at: str


class ChatSessionOut(BaseModel):
    id: int
    name: Optional[str] = None
    document_id: Optional[int] = None
    created_at: str
    updated_at: str


class ChatSessionDetailOut(ChatSessionOut):
    messages: list[ChatMessageOut] = []


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


# ── Collections ──────────────────────────────────────────────────────────

@app.get("/api/collections", response_model=list[CollectionOut])
def list_collections(user: CurrentUser = Depends(get_current_user)):
    return [CollectionOut(**c) for c in repository.list_collections()]


@app.post("/api/collections", response_model=CollectionOut)
def create_collection(body: CollectionCreate, user: CurrentUser = Depends(require_admin)):
    c = repository.create_collection(
        name=body.name, description=body.description, color=body.color, created_by=user.id,
    )
    return CollectionOut(
        id=c.id, name=c.name, description=c.description, color=c.color,
        document_count=0, created_at=c.created_at.isoformat(), updated_at=c.updated_at.isoformat(),
    )


@app.patch("/api/collections/{collection_id}", response_model=CollectionOut)
def update_collection(collection_id: int, body: CollectionUpdate, user: CurrentUser = Depends(require_admin)):
    c = repository.update_collection(
        collection_id, name=body.name, description=body.description, color=body.color,
    )
    if not c:
        raise HTTPException(status_code=404, detail="Collection not found")
    counted = next((x for x in repository.list_collections() if x["id"] == collection_id), None)
    return CollectionOut(**counted) if counted else CollectionOut(
        id=c.id, name=c.name, description=c.description, color=c.color,
        document_count=0, created_at=c.created_at.isoformat(), updated_at=c.updated_at.isoformat(),
    )


@app.delete("/api/collections/{collection_id}")
def delete_collection(collection_id: int, user: CurrentUser = Depends(require_admin)):
    ok = repository.delete_collection(collection_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"status": "deleted"}


# ── Documents ────────────────────────────────────────────────────────────

@app.get("/api/documents", response_model=list[DocumentOut])
def list_documents(collection_id: Optional[int] = None, user: CurrentUser = Depends(get_current_user)):
    docs = analysis_service.list_documents(collection_id=collection_id)
    return [
        DocumentOut(
            doc_id=d["doc_id"], filename=d["filename"], title=d.get("title", ""),
            status=d.get("status", ""), page_count=d.get("pages", 0),
            chunk_count=d.get("chunks", 0), authors=d.get("authors") or [],
            year=d.get("year", ""), updated_at=str(d.get("updated_at", "")),
            last_error=d.get("last_error"),
            collection_id=d.get("collection_id"), collection_name=d.get("collection_name"),
            likely_scanned=d.get("likely_scanned", False),
        )
        for d in docs
    ]


@app.patch("/api/documents/{doc_id}/collection")
def assign_document_collection(
    doc_id: str, body: AssignCollectionRequest, user: CurrentUser = Depends(require_admin),
):
    ok = repository.set_document_collection(doc_id, body.collection_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "updated"}


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


@app.get("/api/documents/{doc_id}/sections")
def get_document_sections(doc_id: str, user: CurrentUser = Depends(get_current_user)):
    """Structural breakdown of a document — Abstract / Methods / Results /
    etc. as distinct blocks, the way the old Streamlit UI surfaced them.
    Pulled straight from document_sections; no re-processing involved."""
    processed = repository.load_processed_document(doc_id)
    if not processed:
        raise HTTPException(status_code=404, detail="Document not found")
    return [
        {
            "section_type": s.section_type.value,
            "title": s.title,
            "content": s.content,
            "page_start": s.page_start,
            "page_end": s.page_end,
            "word_count": s.word_count,
        }
        for s in processed.sections
    ]


# ── Export (Word / Excel) ─────────────────────────────────────────────────

class ExportRequest(BaseModel):
    doc_ids: list[str]
    template: str = "journal"  # "journal" | "thesis"


@app.post("/api/export/xlsx")
def export_xlsx(body: ExportRequest, user: CurrentUser = Depends(get_current_user)):
    from fastapi.responses import Response as _Response
    from app.services.export_service import export_service
    try:
        data, filename = export_service.export_xlsx(body.doc_ids, template=body.template)
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return _Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/export/docx")
def export_docx(body: ExportRequest, user: CurrentUser = Depends(get_current_user)):
    from fastapi.responses import Response as _Response
    from app.services.export_service import export_service
    try:
        data, filename = export_service.export_docx(body.doc_ids, template=body.template)
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return _Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, user: CurrentUser = Depends(require_admin)):
    ok = analysis_service.delete_document(doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted"}


def _process_document_background(doc_id: str, reprocess: bool = False) -> None:
    try:
        analysis_service.process_document(doc_id, reprocess=reprocess)
    except Exception as e:  # noqa: BLE001
        logger.error("Background processing failed for %s: %s", doc_id, e, exc_info=True)


@app.post("/api/documents/{doc_id}/reprocess")
def reprocess_document(
    doc_id: str,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(require_admin),
):
    """Re-runs extraction → chunking → embedding for a document that's
    stuck (e.g. the server restarted mid-processing, commonly from an OOM
    on a small hosting plan while loading the embedding model) or that
    failed. Safe to call on any document — process_document(reprocess=True)
    re-runs the full pipeline regardless of current status."""
    # get_document_info() returns {"error": ...} rather than None for a
    # missing doc (that's non-empty, so `if not info` never fires) — use
    # load_document() instead, the same check delete/file already use.
    doc = pdf_service.load_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    background_tasks.add_task(_process_document_background, doc_id, True)
    return {"status": "reprocessing"}


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

def _resolve_session(user: CurrentUser, body: ResearchRequest):
    """Continues an existing session (ownership-checked) or starts a new
    one, named from the first query so the history list is scannable
    rather than a wall of timestamps."""
    if body.session_id is not None:
        existing = repository.get_chat_session_with_messages(body.session_id, user.id)
        if not existing:
            raise HTTPException(status_code=404, detail="Research session not found")
        return existing

    document_row = repository.get_document_by_doc_id(body.doc_id) if body.doc_id else None
    name = body.query.strip()[:80]
    return repository.create_chat_session(
        user_id=user.id,
        document_id=document_row.id if document_row else None,
        name=name,
    )


def _persist_turn(session_id: int, query: str, state: dict) -> None:
    repository.add_chat_message(session_id, role="user", content=query)
    citations = state.get("citations", [])
    repository.add_chat_message(
        session_id,
        role="assistant",
        content=state.get("answer", ""),
        provider=state.get("provider_used", "none"),
        citations_json=json.dumps([c.model_dump() for c in citations]) if citations else None,
    )


@app.post("/api/research", response_model=ResearchResult)
async def research(body: ResearchRequest, user: CurrentUser = Depends(get_current_user)):
    session = _resolve_session(user, body)
    state = await run_research(query=body.query, doc_id=body.doc_id)
    _persist_turn(session.id, body.query, state)
    return ResearchResult(
        session_id=session.id,
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
    session = _resolve_session(user, body)

    async def event_stream():
        def emit(event: str, **data):
            return json.dumps({"event": event, **data}) + "\n"

        yield emit("stage", stage="searching", label="Searching the library…", session_id=session.id)
        state = await run_research(query=body.query, doc_id=body.doc_id)
        _persist_turn(session.id, body.query, state)
        yield emit("stage", stage="done", label="Answer ready", timings_ms=state.get("timings_ms", {}))

        citations = [c.model_dump() for c in state.get("citations", [])]
        yield emit("result", session_id=session.id, answer=state.get("answer", ""), citations=citations,
                    provider_used=state.get("provider_used", "none"))

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


# ── Research history ──────────────────────────────────────────────────────

@app.get("/api/chat/sessions", response_model=list[ChatSessionOut])
def list_chat_sessions(doc_id: Optional[str] = None, user: CurrentUser = Depends(get_current_user)):
    document_row = repository.get_document_by_doc_id(doc_id) if doc_id else None
    sessions = repository.list_chat_sessions(
        user_id=user.id,
        document_id=document_row.id if document_row else None,
    )
    return [
        ChatSessionOut(
            id=s.id, name=s.name, document_id=s.document_id,
            created_at=s.created_at.isoformat(), updated_at=s.updated_at.isoformat(),
        )
        for s in sessions
    ]


@app.get("/api/chat/sessions/{session_id}", response_model=ChatSessionDetailOut)
def get_chat_session(session_id: int, user: CurrentUser = Depends(get_current_user)):
    session = repository.get_chat_session_with_messages(session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found")
    messages = []
    for m in sorted(session.messages, key=lambda m: m.created_at):
        citations = json.loads(m.citations_json) if m.citations_json else []
        messages.append(ChatMessageOut(
            id=m.id, role=m.role, content=m.content, provider=m.provider,
            citations=[CitationOut(**c) for c in citations],
            created_at=m.created_at.isoformat(),
        ))
    return ChatSessionDetailOut(
        id=session.id, name=session.name, document_id=session.document_id,
        created_at=session.created_at.isoformat(), updated_at=session.updated_at.isoformat(),
        messages=messages,
    )


@app.delete("/api/chat/sessions/{session_id}")
def delete_chat_session(session_id: int, user: CurrentUser = Depends(get_current_user)):
    ok = repository.delete_chat_session(session_id, user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Research session not found")
    return {"status": "deleted"}


# ── Library stats ────────────────────────────────────────────────────────

@app.get("/api/library/stats")
def library_stats(user: CurrentUser = Depends(get_current_user)):
    return analysis_service.get_library_stats()
