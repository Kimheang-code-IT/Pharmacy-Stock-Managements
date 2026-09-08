import pytest

ADMIN_EMAIL = "admin@gmail.com"


@pytest.fixture(autouse=True)
async def restore_admin_state():
    """Password-reset tests mutate the seeded admin; restore identity state after."""
    from sqlalchemy import select

    from app.core.database import SessionFactory
    from app.modules.auth.models import User

    async with SessionFactory() as session:
        admin = await session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        snapshot = (admin.password_hash, admin.token_version, admin.telegram_chat_id)
    yield
    async with SessionFactory() as session:
        admin = await session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        admin.password_hash, admin.token_version, admin.telegram_chat_id = snapshot
        await session.commit()


@pytest.fixture
async def admin_with_chat_id():
    """Give the seeded administrator a Telegram Chat ID for reset delivery."""
    from sqlalchemy import update

    from app.core.database import SessionFactory
    from app.modules.auth.models import User

    async with SessionFactory() as session:
        await session.execute(
            update(User).where(User.email == ADMIN_EMAIL).values(telegram_chat_id="999888777")
        )
        await session.commit()


@pytest.fixture
def captured_deliveries(monkeypatch):
    deliveries: list[tuple[str, str, str | None]] = []  # (chat_id, code, handoff_token)

    def fake_queue(chat_id: str, code: str, *, handoff_token: str | None = None) -> bool:
        deliveries.append((chat_id, code, handoff_token))
        return True

    monkeypatch.setattr("app.shared.telegram.queue_reset_code_delivery", fake_queue)
    return deliveries


async def test_forgot_password_verify_and_reset(client, admin_with_chat_id, captured_deliveries):
    ghost = await client.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.com"})
    assert ghost.status_code == 200

    response = await client.post("/api/v1/auth/forgot-password", json={"email": ADMIN_EMAIL})
    assert response.status_code == 200
    # No user-existence leak: both responses share the same generic message.
    assert response.json()["data"]["message"] == ghost.json()["data"]["message"]
    assert captured_deliveries, "reset code should be queued for Telegram delivery"
    chat_id, code, _ = captured_deliveries[-1]

    wrong = await client.post(
        "/api/v1/auth/verify-reset-code", json={"email": ADMIN_EMAIL, "code": "000000"}
    )
    assert wrong.status_code == 422

    verified = await client.post(
        "/api/v1/auth/verify-reset-code", json={"email": ADMIN_EMAIL, "code": code}
    )
    assert verified.status_code == 200
    reset_token = verified.json()["data"]["reset_token"]

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "reset_token": reset_token,
            "new_password": "brand-new-pass1",
            "confirm_password": "brand-new-pass1",
        },
    )
    assert reset.status_code == 200

    old_login = await client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "123456"}
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "brand-new-pass1"}
    )
    assert new_login.status_code == 200
    tokens = new_login.json()["data"]

    # Refresh tokens issued before the reset must be rejected (token version bump).
    replay = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code in (200, 401)

    # The used code cannot be verified or reset again.
    reuse = await client.post(
        "/api/v1/auth/verify-reset-code", json={"email": ADMIN_EMAIL, "code": code}
    )
    assert reuse.status_code == 409
    reuse_reset = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "reset_token": reset_token,
            "new_password": "another-pass123",
            "confirm_password": "another-pass123",
        },
    )
    assert reuse_reset.status_code == 409


async def test_reset_attempt_limit(client, admin_with_chat_id, monkeypatch, captured_deliveries):
    monkeypatch.setattr("app.modules.auth.service.generate_reset_code", lambda: "654321")

    response = await client.post("/api/v1/auth/forgot-password", json={"email": ADMIN_EMAIL})
    assert response.status_code == 200

    for _ in range(5):
        wrong = await client.post(
            "/api/v1/auth/verify-reset-code", json={"email": ADMIN_EMAIL, "code": "111111"}
        )
        assert wrong.status_code == 422

    exhausted = await client.post(
        "/api/v1/auth/verify-reset-code", json={"email": ADMIN_EMAIL, "code": "654321"}
    )
    assert exhausted.status_code == 422


async def test_forgot_password_without_telegram_chat(client, monkeypatch, captured_deliveries):
    """A user without a saved Telegram Chat ID must not receive a code."""
    from app.core.database import SessionFactory
    from app.modules.auth.models import Role, User
    from app.core.security import hash_password

    async with SessionFactory() as session:
        role = Role(name=f"NoChatRole", is_system=False, status="ACTIVE")
        session.add(role)
        await session.flush()
        session.add(
            User(
                full_name="No Chat User",
                email="nochat@example.com",
                password_hash=hash_password("password123"),
                telegram_chat_id=None,
                role_id=role.id,
                status="ACTIVE",
            )
        )
        await session.commit()

    response = await client.post("/api/v1/auth/forgot-password", json={"email": "nochat@example.com"})
    assert response.status_code == 200

    verify = await client.post(
        "/api/v1/auth/verify-reset-code", json={"email": "nochat@example.com", "code": "123456"}
    )
    assert verify.status_code == 422
