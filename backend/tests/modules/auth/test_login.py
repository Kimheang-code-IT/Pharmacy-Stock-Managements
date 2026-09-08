ADMIN_EMAIL = "admin@gmail.com"
ADMIN_PASSWORD = "123456"


async def _login(client, email=ADMIN_EMAIL, password=ADMIN_PASSWORD):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def test_login_success_and_me(client):
    response = await _login(client)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["user"]["email"] == ADMIN_EMAIL
    assert data["user"]["role"] == "Administrator"
    assert "ALL_PAGES" in data["user"]["permissions"]

    headers = {"Authorization": f"Bearer {data['access_token']}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["data"]["email"] == ADMIN_EMAIL


async def test_login_failure_and_logout_revocation(client):
    response = await _login(client, password="wrong-password")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_REQUIRED"

    response = await _login(client)
    data = response.json()["data"]
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    logout = await client.post("/api/v1/auth/logout", json={"refresh_token": data["refresh_token"]}, headers=headers)
    assert logout.status_code == 200

    refresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert refresh.status_code == 401


async def test_refresh_rotation(client):
    response = await _login(client)
    data = response.json()["data"]

    refresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert refresh.status_code == 200
    rotated = refresh.json()["data"]
    assert rotated["refresh_token"] != data["refresh_token"]

    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert replay.status_code == 401


async def test_me_requires_auth(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401

    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401
