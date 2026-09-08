async def test_setup_status_and_setup_once(client):
    response = await client.get("/api/v1/auth/setup/status")
    assert response.status_code == 200
    assert response.json()["data"]["setup_completed"] is True

    response = await client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Second Admin",
            "email": "second@example.com",
            "password": "supersecret1",
            "confirm_password": "supersecret1",
            "telegram_chat_id": "111222333",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CONFLICT"


async def test_setup_validation_mismatch(client):
    response = await client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "X",
            "email": "x@example.com",
            "password": "supersecret1",
            "confirm_password": "different1",
        },
    )
    assert response.status_code == 422
