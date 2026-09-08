"""
app/services/storage_service.py — StorageService abstraction.

Replaces the implicit "just write to UPLOAD_DIR" behaviour scattered in
pdf_service.py with a single provider-agnostic interface:

    storage_service.put(doc_id, filename, file_bytes) -> StoredObject
    storage_service.get(key) -> bytes
    storage_service.url(key) -> str | None   # signed URL, if remote
    storage_service.delete(key) -> bool
    storage_service.exists_by_checksum(sha256) -> StoredObject | None

Two backends, chosen by STORAGE_BACKEND env var ("local" | "r2"):
  - LocalStorageBackend: writes under DATA_DIR/uploads, used for dev and
    for the OAU ICT-section LAN deployment where there's no reason to pay
    for object storage.
  - R2StorageBackend: Cloudflare R2 via the S3-compatible API (boto3),
    used in production/cloud deployment. R2 has zero egress fees, which
    matters for a library serving many read-heavy PDF downloads.

Add a third backend later (e.g. S3, GCS) by implementing StorageBackend
and registering it in `_build_backend()` — nothing else in the codebase
should need to change.
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import DATA_DIR
from app.utils.logger import get_logger

logger = get_logger(__name__)

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").strip().lower()
R2_BUCKET       = os.getenv("R2_BUCKET", "").strip()
R2_ACCOUNT_ID   = os.getenv("R2_ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID     = os.getenv("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
R2_PUBLIC_BASE_URL   = os.getenv("R2_PUBLIC_BASE_URL", "").strip()  # optional custom domain
R2_SIGNED_URL_TTL    = int(os.getenv("R2_SIGNED_URL_TTL", "3600"))

LOCAL_STORAGE_DIR = DATA_DIR / "uploads"


@dataclass
class StoredObject:
    key: str                 # backend-relative key, e.g. "documents/<doc_id>/<filename>"
    size_bytes: int
    checksum_sha256: str
    content_type: str
    backend: str              # "local" | "r2"


class StorageBackend(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> bool: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def url(self, key: str, ttl_seconds: int = 3600) -> Optional[str]: ...


class LocalStorageBackend(StorageBackend):
    """Filesystem-backed storage under DATA_DIR/uploads. Good for dev and
    for a LAN-only library deployment with no internet dependency."""

    def __init__(self, root: Path = LOCAL_STORAGE_DIR) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Guard against path traversal via a crafted key.
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError(f"Invalid storage key: {key!r}")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def url(self, key: str, ttl_seconds: int = 3600) -> Optional[str]:
        # No HTTP server fronts local storage by default; the FastAPI layer
        # serves these via its own /files/{key} route instead of a signed URL.
        return None


class R2StorageBackend(StorageBackend):
    """Cloudflare R2 via the S3-compatible API. Zero egress fees matter here
    since PDFs get downloaded/viewed repeatedly by many students."""

    def __init__(self) -> None:
        import boto3  # local import: keeps boto3 optional for local-only deployments
        from botocore.config import Config as BotoConfig

        if not (R2_BUCKET and R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY):
            raise RuntimeError(
                "STORAGE_BACKEND=r2 requires R2_BUCKET, R2_ACCOUNT_ID, "
                "R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY to be set."
            )
        self.bucket = R2_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=BotoConfig(signature_version="s3v4"),
            region_name="auto",
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
        )

    def get(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    def delete(self, key: str) -> bool:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("R2 delete failed for %s: %s", key, exc)
            return False

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def url(self, key: str, ttl_seconds: int = 3600) -> Optional[str]:
        if R2_PUBLIC_BASE_URL:
            return f"{R2_PUBLIC_BASE_URL.rstrip('/')}/{key}"
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=ttl_seconds or R2_SIGNED_URL_TTL,
        )


def _build_backend() -> StorageBackend:
    if STORAGE_BACKEND == "r2":
        logger.info("StorageService using Cloudflare R2 backend (bucket=%s)", R2_BUCKET)
        return R2StorageBackend()
    logger.info("StorageService using local disk backend at %s", LOCAL_STORAGE_DIR)
    return LocalStorageBackend()


class StorageService:
    def __init__(self) -> None:
        self.backend_name = "r2" if STORAGE_BACKEND == "r2" else "local"
        self._backend = _build_backend()
        # In-memory checksum index for local dev; production dedup is done
        # against the `documents.checksum` DB column (see repository.py),
        # this is just a fast pre-DB-hit short circuit for repeat uploads
        # within the same process lifetime.
        self._checksum_cache: dict[str, str] = {}

    @staticmethod
    def compute_checksum(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def build_key(doc_id: str, filename: str) -> str:
        safe_name = Path(filename).name  # strip any path components
        return f"documents/{doc_id}/{safe_name}"

    def put_document(self, filename: str, data: bytes, doc_id: Optional[str] = None) -> StoredObject:
        doc_id = doc_id or str(uuid.uuid4())
        checksum = self.compute_checksum(data)
        content_type = mimetypes.guess_type(filename)[0] or "application/pdf"
        key = self.build_key(doc_id, filename)

        self._backend.put(key, data, content_type)
        self._checksum_cache[checksum] = key

        return StoredObject(
            key=key,
            size_bytes=len(data),
            checksum_sha256=checksum,
            content_type=content_type,
            backend=self.backend_name,
        )

    def get_document(self, key: str) -> bytes:
        return self._backend.get(key)

    def delete_document(self, key: str) -> bool:
        return self._backend.delete(key)

    def document_url(self, key: str, ttl_seconds: int = 3600) -> Optional[str]:
        return self._backend.url(key, ttl_seconds=ttl_seconds)

    def exists(self, key: str) -> bool:
        return self._backend.exists(key)


storage_service = StorageService()
