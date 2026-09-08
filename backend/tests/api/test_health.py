async def test_health_endpoints(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"

    response = await client.get("/health/live")
    assert response.status_code == 200

    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["checks"]["postgres"] == "ok"
    assert data["checks"]["redis"] == "ok"


async def test_openapi_available(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/images/upload" in paths
    assert "/health" in paths
