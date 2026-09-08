from tests.utils import admin_headers


async def test_supplier_crud_with_auto_code(client):
    headers = await admin_headers(client)

    created = await client.post(
        "/api/v1/suppliers",
        json={"name": "Acme Trading", "company_name": "Acme Co Ltd", "phone": "012345678"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    supplier = created.json()["data"]
    assert supplier["code"].startswith("SUP-")

    patched = await client.patch(
        f"/api/v1/suppliers/{supplier['id']}", json={"contact_person": "Dara"}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["contact_person"] == "Dara"

    listing = await client.get("/api/v1/suppliers?q=acme", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["meta"]["total"] >= 1

    deleted = await client.delete(f"/api/v1/suppliers/{supplier['id']}", headers=headers)
    assert deleted.status_code == 200


async def test_supplier_requires_view_permission(client):
    anon = await client.get("/api/v1/suppliers")
    assert anon.status_code == 401
