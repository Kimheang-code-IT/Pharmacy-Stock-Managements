from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import envelope, get_current_user
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.auth.models import User
from app.modules.image.service import ImageStorageService

router = APIRouter(prefix="/images", tags=["images"])

_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)

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
) -> dict:
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise ValidationError("Unsupported image type. Allowed: jpeg, png, webp, gif")

    content = await file.read()
    if not content:
        raise ValidationError("Empty file")

    stored = await ImageStorageService.from_settings().upload_image(
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
    actor: User = Depends(get_current_user),
):
    key = _safe_object_key(object_key)
    service = ImageStorageService.from_settings()
    path = service.resolved_path(key)
    if not await service.object_exists(key):
        raise NotFoundError("Object not found")

    suffix = key.rsplit(".", 1)
    content_type = _CONTENT_TYPE_BY_SUFFIX.get(
        f".{suffix[-1].lower()}" if len(suffix) > 1 else "",
        "application/octet-stream",
    )
    filename = key.rsplit("/", 1)[-1]
    return FileResponse(
        path,
        media_type=content_type,
        filename=filename,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}"},
    )
