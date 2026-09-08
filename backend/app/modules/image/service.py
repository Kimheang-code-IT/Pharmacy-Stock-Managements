"""Local-disk image storage. PostgreSQL stores object keys only — never image blobs.

Files live under `settings.local_storage_dir` (Docker volume or `backend/var/media`).
Clients never read the disk path; they use `GET /api/v1/images/{object_key}`.
Do not store invoice PDFs here.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from app.core.config import settings
from app.core.exceptions import ValidationError

MAX_IMAGE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class StoredObject:
    bucket: str
    object_name: str
    etag: str
    size: int


class ImageStorageService:
    """Write and read product/shop/brand images on the local filesystem."""

    def __init__(self, *, root: Path | None = None, max_bytes: int = MAX_IMAGE_BYTES) -> None:
        self.root = (root or Path(settings.local_storage_dir)).expanduser().resolve()
        self.max_bytes = max_bytes
        self.bucket = "local"

    @classmethod
    def from_settings(cls) -> ImageStorageService:
        return cls(root=Path(settings.local_storage_dir), max_bytes=settings.max_upload_bytes)

    def resolved_path(self, object_name: str) -> Path:
        key = (object_name or "").replace("\\", "/").strip("/")
        if not key or ".." in key.split("/"):
            raise ValidationError("Invalid object key")
        path = (self.root / key).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValidationError("Invalid object key") from exc
        return path

    async def put_bytes(self, object_name: str, content: bytes, content_type: str) -> StoredObject:
        if len(content) > self.max_bytes:
            raise ValidationError("File is too large")
        path = self.resolved_path(object_name)

        def _write() -> str:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            return hashlib.sha256(content).hexdigest()[:16]

        etag = await asyncio.to_thread(_write)
        return StoredObject(
            bucket=self.bucket,
            object_name=object_name.replace("\\", "/").strip("/"),
            etag=etag,
            size=len(content),
        )

    async def upload_image(
        self,
        *,
        folder: str,
        filename: str,
        content: bytes,
        content_type: str,
        at: datetime | None = None,
    ) -> StoredObject:
        object_name = image_object_name(folder, filename, at=at)
        return await self.put_bytes(object_name, content, content_type)

    async def object_exists(self, object_name: str) -> bool:
        try:
            path = self.resolved_path(object_name)
        except ValidationError:
            return False
        return await asyncio.to_thread(path.is_file)


def image_object_name(folder: str, filename: str, *, at: datetime | None = None) -> str:
    timestamp = at or datetime.now(timezone.utc)
    safe_folder = _safe_segment(folder)
    safe_filename = _safe_segment(filename)
    return f"images/{safe_folder}/{timestamp:%Y/%m}/{safe_filename}"


def resolve_media_url(object_key: str | None) -> str | None:
    """Resolve a local object key to the API-mediated download URL."""
    if not object_key:
        return None
    return "/api/v1/images/" + quote(object_key.replace("\\", "/").strip("/"))


def _safe_segment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-.")
    return cleaned or "unknown"
