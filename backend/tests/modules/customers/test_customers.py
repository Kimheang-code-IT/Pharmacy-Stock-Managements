from tests.utils import admin_headers


async def test_customer_crud_auto_code_and_walkin_protection(client):
    headers = await admin_headers(client)

    listing = await client.get("/api/v1/customers?q=walk-in", headers=headers)
    assert listing.status_code == 200
    walk_in = next(
        (c for c in listing.json()["data"] if c["is_walk_in"]), None
    ) or (await client.get("/api/v1/customers?q=Walk", headers=headers)).json()["data"][0]
    assert walk_in["is_walk_in"] is True

    patch_walk_in = await client.patch(
        f"/api/v1/customers/{walk_in['id']}", json={"name": "Renamed"}, headers=headers
    )
    assert patch_walk_in.status_code == 409

    delete_walk_in = await client.delete(f"/api/v1/customers/{walk_in['id']}", headers=headers)
    assert delete_walk_in.status_code == 409

    created = await client.post(
        "/api/v1/customers",
        json={"name": "Sok Dara", "phone": "098765432", "location": "Phnom Penh, Toul Kork"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    customer = created.json()["data"]
    assert customer["code"].startswith("CUS-")
    assert customer["is_walk_in"] is False
    assert customer["location"] == "Phnom Penh, Toul Kork"

    patched = await client.patch(f"/api/v1/customers/{customer['id']}", json={"note": "VIP"}, headers=headers)
    assert patched.status_code == 200

    deleted = await client.delete(f"/api/v1/customers/{customer['id']}", headers=headers)
    assert deleted.status_code == 200
