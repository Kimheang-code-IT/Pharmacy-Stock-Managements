"""UOM module — CRUD, unique codes, safe delete, inactive filtering (spec 2.1.3)."""

import uuid

import pytest

from tests.utils import admin_headers, create_user_with_role, login

NO_PERM_EMAIL = "uom-denied@example.com"
NO_PERM_PASSWORD = "uomdenied1"


@pytest.fixture
async def no_perm_headers(client, db_session):
    await create_user_with_role(
        db_session,
        email=NO_PERM_EMAIL,
        password=NO_PERM_PASSWORD,
        role_name="UOM Denied",
        permissions=["pos.access"],
    )
    await db_session.commit()
    data = await login(client, NO_PERM_EMAIL, NO_PERM_PASSWORD)
    return {"Authorization": f"Bearer {data['access_token']}"}


async def _category(client, headers, tag: str) -> dict:
    response = await client.post(
        "/api/v1/categories", json={"code": f"UOMC-{tag}", "name": f"UOM Cat {tag}"}, headers=headers
    )
    return response.json()["data"]


@pytest.mark.asyncio
async def test_uom_seed_defaults_present(client):
    headers = await admin_headers(client)
    response = await client.get("/api/v1/uoms/options", headers=headers)
    assert response.status_code == 200, response.text
    codes = {row["code"] for row in response.json()["data"]}
    assert {"PCS", "BOX", "CAN", "BTL", "KG", "PACK"} <= codes


@pytest.mark.asyncio
async def test_uom_crud_and_unique_code(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]

    created = await client.post(
        "/api/v1/uoms",
        json={"code": f"U{tag}", "name": "Carton", "symbol": "ctn", "description": "Test UOM"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    uom = created.json()["data"]

    duplicate = await client.post(
        "/api/v1/uoms", json={"code": f"U{tag}", "name": "Dup", "symbol": "d"}, headers=headers
    )
    assert duplicate.status_code == 409

    patched = await client.patch(
        f"/api/v1/uoms/{uom['id']}", json={"symbol": "crtn", "description": "Updated"}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["symbol"] == "crtn"

    detail = await client.get(f"/api/v1/uoms/{uom['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["name"] == "Carton"

    deleted = await client.delete(f"/api/v1/uoms/{uom['id']}", headers=headers)
    assert deleted.status_code == 200
    missing = await client.get(f"/api/v1/uoms/{uom['id']}", headers=headers)
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_uom_safe_delete_prefer_disable_when_linked(client):
    """A UOM linked to products cannot be hard-deleted; disable instead (spec 2.1.3)."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]

    uom = (
        await client.post(
            "/api/v1/uoms", json={"code": f"L{tag}", "name": "Linked", "symbol": "lk"}, headers=headers
        )
    ).json()["data"]
    category = await _category(client, headers, tag)
    product = (
        await client.post(
            "/api/v1/products",
            json={
                "sku": f"UOMP-{tag}",
                "name": "Linked Product",
                "category_id": category["id"],
                "uom_id": uom["id"],
                "selling_price": "1.50",
            },
            headers=headers,
        )
    ).json()["data"]

    blocked = await client.delete(f"/api/v1/uoms/{uom['id']}", headers=headers)
    assert blocked.status_code == 409
    assert "disable" in blocked.json()["detail"]["message"].lower()

    disabled = await client.patch(
        f"/api/v1/uoms/{uom['id']}", json={"status": "INACTIVE"}, headers=headers
    )
    assert disabled.status_code == 200
    assert disabled.json()["data"]["status"] == "INACTIVE"

    # Cleanup: product first, then the UOM is deletable.
    await client.delete(f"/api/v1/products/{product['id']}", headers=headers)
    deleted = await client.delete(f"/api/v1/uoms/{uom['id']}", headers=headers)
    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_inactive_uom_hidden_from_options_and_rejected_on_products(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]

    uom = (
        await client.post(
            "/api/v1/uoms", json={"code": f"H{tag}", "name": "Hidden", "symbol": "hd"}, headers=headers
        )
    ).json()["data"]
    await client.patch(f"/api/v1/uoms/{uom['id']}", json={"status": "INACTIVE"}, headers=headers)

    options = await client.get("/api/v1/uoms/options", headers=headers)
    assert uom["id"] not in {row["id"] for row in options.json()["data"]}

    category = await _category(client, headers, tag)
    rejected = await client.post(
        "/api/v1/products",
        json={
            "sku": f"HIDP-{tag}",
            "name": "Hidden UOM Product",
            "category_id": category["id"],
            "uom_id": uom["id"],
            "selling_price": "2.00",
        },
        headers=headers,
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["detail"]["field_errors"]["uom_id"] == "UOM is inactive"

    # Switching a product to an inactive UOM is rejected as well.
    active_uom = (
        await client.get("/api/v1/uoms/options?q=PCS", headers=headers)
    ).json()["data"][0]
    active_category = await _category(client, headers, tag + "b")
    product = (
        await client.post(
            "/api/v1/products",
            json={
                "sku": f"HIDQ-{tag}",
                "name": "Active UOM Product",
                "category_id": active_category["id"],
                "uom_id": active_uom["id"],
                "selling_price": "2.00",
            },
            headers=headers,
        )
    ).json()["data"]
    patch_rejected = await client.patch(
        f"/api/v1/products/{product['id']}", json={"uom_id": uom["id"]}, headers=headers
    )
    assert patch_rejected.status_code == 422


@pytest.mark.asyncio
async def test_product_requires_uom(client):
    """Product create rejects a missing uom_id (spec section 2.1.5)."""
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    category = await _category(client, headers, tag)
    response = await client.post(
        "/api/v1/products",
        json={
            "sku": f"NOUOM-{tag}",
            "name": "No UOM Product",
            "category_id": category["id"],
            "selling_price": "2.00",
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_uom_permissions_enforced(client, no_perm_headers):
    denied_list = await client.get("/api/v1/uoms", headers=no_perm_headers)
    assert denied_list.status_code == 403
    denied_create = await client.post(
        "/api/v1/uoms", json={"code": "XX1", "name": "Nope", "symbol": "x"}, headers=no_perm_headers
    )
    assert denied_create.status_code == 403

    headers = await admin_headers(client)
    allowed = await client.get("/api/v1/uoms", headers=headers)
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_uom_unknown_reference_rejected(client):
    headers = await admin_headers(client)
    tag = uuid.uuid4().hex[:6]
    category = await _category(client, headers, tag)
    response = await client.post(
        "/api/v1/products",
        json={
            "sku": f"BADUOM-{tag}",
            "name": "Bad UOM Product",
            "category_id": category["id"],
            "uom_id": str(uuid.uuid4()),
            "selling_price": "2.00",
        },
        headers=headers,
    )
    assert response.status_code == 404
