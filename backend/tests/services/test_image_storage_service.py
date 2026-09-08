from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.modules.image.service import ImageStorageService, image_object_name


@pytest.mark.asyncio
async def test_image_upload_writes_local_file(tmp_path: Path):
    service = ImageStorageService(root=tmp_path)

    stored = await service.upload_image(
        folder="products",
        filename="widget.png",
        content=b"png-bytes",
        content_type="image/png",
        at=datetime(2026, 3, 15, tzinfo=UTC),
    )

    assert stored.object_name == "images/products/2026/03/widget.png"
    assert stored.size == 9
    assert stored.bucket == "local"
    path = tmp_path / "images" / "products" / "2026" / "03" / "widget.png"
    assert path.read_bytes() == b"png-bytes"
    assert await service.object_exists(stored.object_name) is True


def test_image_object_name_sanitizes_segments():
    name = image_object_name("shop logo!", "Brand Logo (1).jpg", at=datetime(2026, 1, 2, tzinfo=UTC))
    assert name == "images/shop-logo/2026/01/Brand-Logo-1-.jpg"


@pytest.mark.asyncio
async def test_rejects_path_traversal(tmp_path: Path):
    service = ImageStorageService(root=tmp_path)
    from app.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        service.resolved_path("../secret.png")
