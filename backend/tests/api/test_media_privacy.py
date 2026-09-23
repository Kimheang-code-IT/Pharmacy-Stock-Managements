"""The public media route must never expose non-image / private files, and
maintenance backups must live outside the public media root (security fix)."""

from pathlib import Path

import pytest

from app.core.config import settings
from app.modules.administration.maintenance import MaintenanceService
from app.modules.categories.models import Category
from tests.utils import admin_headers


@pytest.mark.asyncio
async def test_non_image_keys_are_not_downloadable(client):
    media_root = Path(settings.local_storage_dir)
    # A private file accidentally placed under the media root.
    (media_root / "secret.json").write_text('{"password": "hunter2"}', encoding="utf-8")
    nested = media_root / "images" / "general" / "2026" / "01"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "data.json").write_text("{}", encoding="utf-8")

    assert (await client.get("/api/v1/images/secret.json")).status_code == 404
    assert (
        await client.get("/api/v1/images/images/general/2026/01/data.json")
    ).status_code == 404
    # Traversal is rejected too.
    assert (await client.get("/api/v1/images/../secret.json")).status_code in (404, 422)


@pytest.mark.asyncio
async def test_real_images_are_still_served(client):
    headers = await admin_headers(client)
    # Minimal valid PNG (1x1).
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6360000002000154a24f5e0000000049454e44ae42"
        "6082"
    )
    upload = await client.post(
        "/api/v1/images/upload",
        files={"file": ("dot.png", png, "image/png")},
        data={"folder": "general"},
        headers=headers,
    )
    assert upload.status_code == 200, upload.text
    object_name = upload.json()["data"]["objectName"]
    served = await client.get(f"/api/v1/images/{object_name}")
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/png")


@pytest.mark.asyncio
async def test_maintenance_backup_is_outside_public_media_root(db_session):
    service = MaintenanceService(db_session)
    result = await service.create_backup(action="TEST_BACKUP", models=(Category,), actor=None)

    backup_path = Path(result["path"]).resolve()
    media_root = Path(settings.local_storage_dir).resolve()
    assert backup_path.is_file()
    # The snapshot is NOT under the publicly-served media root.
    assert media_root not in backup_path.parents
