import uuid

import pytest

from tests.utils import DEFAULT_UOM_ID, admin_headers, create_user_with_role, login

VIEWER_EMAIL = "brand-viewer@example.com"
VIEWER_PASSWORD = "viewerpass1"
VIEWER_ROLE = "Brand Viewer"


@pytest.fixture
async def viewer_headers(client, db_session):
    await create_user_with_role(
        db_session, email=VIEWER_EMAIL, password=VIEWER_PASSWORD, role_name=VIEWER_ROLE, permissions=["brand.view"]
    )
    await db_session.commit()
    data = await login(client, VIEWER_EMAIL, VIEWER_PASSWORD)
    return {"Authorization": f"Bearer {data['access_token']}"}


async def _create_brand(client, headers, code=None, name="Beverage Brand"):
    code = code or f"BEV-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/v1/brands",
        json={"code": code, "name": name, "description": "Drinks"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_brand_crud_flow(client):
    headers = await admin_headers(client)
    brand = await _create_brand(client, headers)

    dup = await client.post(
        "/api/v1/brands", json={"code": brand["code"], "name": "Dup"}, headers=headers
    )
    assert dup.status_code == 409

    patched = await client.patch(
        f"/api/v1/brands/{brand['id']}", json={"name": "Soft Drinks Brand", "status": "ACTIVE"}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["name"] == "Soft Drinks Brand"

    listing = await client.get("/api/v1/brands?q=soft", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["meta"]["total"] >= 1

    deleted = await client.delete(f"/api/v1/brands/{brand['id']}", headers=headers)
    assert deleted.status_code == 200

    missing = await client.get(f"/api/v1/brands/{brand['id']}", headers=headers)
    assert missing.status_code == 404


async def test_brand_options_lists_active_only(client):
    headers = await admin_headers(client)
    active = await _create_brand(client, headers, name="Active Option Brand")
    await _create_brand(client, headers, name="Inactive Option Brand")

    listing = await client.get("/api/v1/brands", headers=headers)
    inactive_id = next(
        row["id"] for row in listing.json()["data"] if row["name"] == "Inactive Option Brand"
    )
    await client.patch(f"/api/v1/brands/{inactive_id}", json={"status": "INACTIVE"}, headers=headers)

    options = await client.get("/api/v1/brands/options", headers=headers)
    assert options.status_code == 200
    values = [row["value"] for row in options.json()["data"]]
    assert active["id"] in values
    assert inactive_id not in values

    labeled = next(row for row in options.json()["data"] if row["value"] == active["id"])
    assert labeled["label"] == "Active Option Brand"


async def test_brand_view_only_cannot_create(client, viewer_headers):
    response = await client.post(
        "/api/v1/brands", json={"code": "NOPE", "name": "Nope"}, headers=viewer_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ACCESS_DENIED"


async def test_brand_delete_blocked_when_products_exist(client):
    headers = await admin_headers(client)
    brand = await _create_brand(client, headers, code="SNK", name="Snack Brand")

    product = await client.post(
        "/api/v1/products",
        json={
            "sku": "SNK-001",
            "name": "Chips",
            "category_id": await _category_id(client, headers),
            "uom_id": str(DEFAULT_UOM_ID),
            "brand_id": brand["id"],
            "selling_price": "2.50",
        },
        headers=headers,
    )
    assert product.status_code == 201, product.text
    assert product.json()["data"]["brand_id"] == brand["id"]
    assert product.json()["data"]["brand_name"] == "Snack Brand"

    blocked = await client.delete(f"/api/v1/brands/{brand['id']}", headers=headers)
    assert blocked.status_code == 409

    await client.delete(f"/api/v1/products/{product.json()['data']['id']}", headers=headers)
    unblocked = await client.delete(f"/api/v1/brands/{brand['id']}", headers=headers)
    assert unblocked.status_code == 200


async def test_product_accepts_unknown_brand_error(client):
    headers = await admin_headers(client)
    response = await client.post(
        "/api/v1/products",
        json={
            "sku": "SNK-002",
            "name": "Chips No Brand",
            "category_id": await _category_id(client, headers),
            "uom_id": str(DEFAULT_UOM_ID),
            "brand_id": "00000000-0000-0000-0000-000000000000",
            "selling_price": "2.50",
        },
        headers=headers,
    )
    assert response.status_code == 404


async def _category_id(client, headers) -> str:
    suffix = uuid.uuid4().hex[:8]
    created = await client.post(
        "/api/v1/categories",
        json={"code": f"SNKC-{suffix}", "name": f"Snacks Cat {suffix}"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]["id"]
