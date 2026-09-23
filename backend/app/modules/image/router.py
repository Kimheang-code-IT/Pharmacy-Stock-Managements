from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import envelope, get_current_user, get_db_session
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.administration import get_setting_value
from app.modules.auth.models import User
from app.modules.image.service import ImageStorageService

router = APIRouter(prefix="/images", tags=["images"])

_EXTENSION_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}

_ALLOWED_CONTENT_TYPES = frozenset(_EXTENSION_CONTENT_TYPES.values())

_CONTENT_TYPE_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _safe_object_key(object_key: str) -> str:
    key = (object_key or "").replace("\\", "/").strip("/")
    if not key or ".." in key.split("/"):
        raise ValidationError("Invalid object key")
    return key


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    folder: str = Form(default="general"),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    # Allowed extensions are a persisted Security setting (falling back to the
    # raster defaults); unknown extensions are ignored.
    configured = await get_setting_value(db, "security", "allowed_upload_extensions", None)
    allowed_types = {
        _EXTENSION_CONTENT_TYPES[str(ext).strip().lstrip(".").lower()]
        for ext in (configured or [])
        if str(ext).strip().lstrip(".").lower() in _EXTENSION_CONTENT_TYPES
    } or set(_ALLOWED_CONTENT_TYPES)
    content_type = (file.content_type or "").lower()
    if content_type not in allowed_types:
        raise ValidationError("Unsupported image type. Allowed: " + ", ".join(sorted(allowed_types)))

    service = ImageStorageService.from_settings()
    max_bytes = service.max_bytes
    if file.size is not None and file.size > max_bytes:
        raise ValidationError("File is too large")
    # Read at most one byte past the cap so an oversized upload can never be
    # buffered into memory before the size check.
    content = await file.read(max_bytes + 1)
    if not content:
        raise ValidationError("Empty file")
    if len(content) > max_bytes:
        raise ValidationError("File is too large")

    stored = await service.upload_image(
        folder=folder,
        filename=file.filename or "upload.bin",
        content=content,
        content_type=content_type,
    )
    return envelope(
        {
            "bucket": stored.bucket,
            "objectName": stored.object_name,
            "etag": stored.etag,
            "size": stored.size,
            "contentType": content_type,
        }
    )


@router.get("/{object_key:path}")
async def download_object(
    object_key: str,
):
    """Public static media: the SPA renders product images with plain <img>,
    which cannot attach a bearer token (see docs/API.md §12).

    Only real images are served: the key must live under the `images/` prefix
    and have an allowed image extension. Everything else (including any private
    operational file that might end up under the media root) returns 404, so a
    non-image file can never be downloaded from this public route."""
    key = _safe_object_key(object_key)
    if not key.startswith("images/"):
        raise NotFoundError("Object not found")

    suffix = key.rsplit(".", 1)
    extension = f".{suffix[-1].lower()}" if len(suffix) > 1 else ""
    content_type = _CONTENT_TYPE_BY_SUFFIX.get(extension)
    if content_type is None:
        raise NotFoundError("Object not found")

    service = ImageStorageService.from_settings()
    if not await service.object_exists(key):
        raise NotFoundError("Object not found")
    path = service.resolved_path(key)

    filename = key.rsplit("/", 1)[-1]
    return FileResponse(
        path,
        media_type=content_type,
        filename=filename,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "public, max-age=86400",
        },
    )
