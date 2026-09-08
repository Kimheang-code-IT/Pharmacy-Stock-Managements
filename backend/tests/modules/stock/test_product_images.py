"""Product image contract: local-disk object keys, API-mediated URLs (spec 2.1.5)."""

import uuid

import pytest

from tests.utils import DEFAULT_UOM_ID, admin_headers


@pytest.mark.asyncio
async def test_product_stores_object_key_and_resolves_image_url(client, db_session):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]

    from sqlalchemy import text as sql_text

    category = (
        await client.post(
            "/api/v1/categories", json={"code": f"IMG-{tag}", "name": f"Img Cat {tag}"}, headers=headers
        )
    ).json()["data"]
    created = await client.post(
        "/api/v1/products",
        json={
            "sku": f"IMG-{tag}",
            "name": f"Image Widget {tag}",
            "category_id": category["id"],
            "uom_id": str(DEFAULT_UOM_ID),
            "selling_price": "3.00",
            "image_object_key": "images/products/2026/09/widget.webp",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    product = created.json()["data"]
    assert product["image_object_key"] == "images/products/2026/09/widget.webp"
    assert product["image_url"] == "/api/v1/images/images/products/2026/09/widget.webp"

    # The products table must not have any binary image column (local files only).
    columns = await db_session.execute(
        sql_text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'products'"
        )
    )
    rows = {row[0]: row[1] for row in columns.all()}
    blob_columns = [name for name, dtype in rows.items() if "BYTEA" in dtype.upper() or "BLOB" in dtype.upper()]
    assert blob_columns == [], f"products must not store image blobs: {blob_columns}"
    assert rows["image_object_key"] == "character varying"

    # Clearing the key clears the URL.
    patched = await client.patch(
        f"/api/v1/products/{product['id']}", json={"image_object_key": None}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["image_url"] is None

    await client.delete(f"/api/v1/products/{product['id']}", headers=headers)
    await client.delete(f"/api/v1/categories/{category['id']}", headers=headers)
