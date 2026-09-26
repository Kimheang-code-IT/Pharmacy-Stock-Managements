"""Destructive-operation protection + audit hardening (spec: Phase 3).

A reset/clear requires the dedicated permission, the exact confirmation phrase,
and a verified pre-deletion backup. Denied attempts are audited, the audit trail
has no update/delete route, and the protected system-event store survives a reset.
"""

import uuid

import pytest
from sqlalchemy import select

from app.shared.audit.models import AuditLog, SystemAuditEvent
from tests.modules.pos.helpers import make_stocked_product
from tests.utils import admin_headers, create_user_with_role, login


def _confirmation(action: str) -> dict:
    phrases = {
        "RESET_ALL_DATA": "RESET ALL DATA",
        "CLEAR_TRANSACTIONS": "CLEAR TRANSACTIONS",
    }
    return {"confirmation_phrase": phrases[action]}


@pytest.mark.asyncio
async def test_reset_requires_system_permission(client, db_session):
    """settings.update alone can never run a destructive reset."""
    email = f"settings-only-{uuid.uuid4().hex[:8]}@example.com"
    await create_user_with_role(
        db_session,
        email=email,
        password="SettingsOnly1",
        role_name=f"Settings Only {uuid.uuid4().hex[:6]}",
        permissions=["settings.update"],
    )
    await db_session.commit()
    data = await login(client, email, "SettingsOnly1")
    headers = {"Authorization": f"Bearer {data['access_token']}"}

    denied = await client.post("/api/v1/settings/reset-data", json={}, headers=headers)
    assert denied.status_code == 403, denied.text
    denied_with_phrase = await client.post(
        "/api/v1/settings/reset-data",
        json=_confirmation("RESET_ALL_DATA"),
        headers=headers,
    )
    assert denied_with_phrase.status_code == 403, denied_with_phrase.text


@pytest.mark.asyncio
async def test_reset_requires_exact_phrase(client):
    admin = await admin_headers(client)
    product = await make_stocked_product(client, admin, sku="MAINT-1", name="Maint Widget")

    # No phrase at all.
    assert (await client.post("/api/v1/settings/reset-data", json={}, headers=admin)).status_code == 422
    # Wrong phrase.
    body = _confirmation("RESET_ALL_DATA")
    body["confirmation_phrase"] = "please reset"
    wrong = await client.post("/api/v1/settings/reset-data", json=body, headers=admin)
    assert wrong.status_code == 422, wrong.text
    # Nothing was deleted.
    assert (await client.get(f"/api/v1/products/{product['id']}", headers=admin)).status_code == 200


@pytest.mark.asyncio
async def test_reset_fails_when_backup_fails(client, monkeypatch):
    """No backup -> no deletion (abort before the wipe)."""
    admin = await admin_headers(client)
    product = await make_stocked_product(client, admin, sku="MAINT-2", name="Maint Widget 2")
    body = _confirmation("RESET_ALL_DATA")

    import app.modules.administration.maintenance as maintenance_module
    from app.core.exceptions import MaintenanceError

    async def _boom(self, *, action, models, actor):
        raise MaintenanceError("simulated backup failure")

    monkeypatch.setattr(maintenance_module.MaintenanceService, "create_backup", _boom)

    failed = await client.post("/api/v1/settings/reset-data", json=body, headers=admin)
    assert failed.status_code == 500, failed.text
    # The product still exists: the destructive action never ran.
    assert (await client.get(f"/api/v1/products/{product['id']}", headers=admin)).status_code == 200


@pytest.mark.asyncio
async def test_reset_preserves_protected_audit_evidence(client, db_session):
    admin = await admin_headers(client)
    await make_stocked_product(client, admin, sku="MAINT-3", name="Maint Widget 3")
    body = _confirmation("RESET_ALL_DATA")

    response = await client.post("/api/v1/settings/reset-data", json=body, headers=admin)
    assert response.status_code == 200, response.text

    # The protected store keeps the before/after evidence of who reset.
    events = (
        await db_session.execute(
            select(SystemAuditEvent).where(SystemAuditEvent.action == "all_data_reset")
        )
    ).scalars().all()
    phases = {event.new_values.get("phase") for event in events}
    assert {"before", "after"}.issubset(phases)
    assert all(event.actor_email for event in events)

    # The shared test DB relies on the seeded UOM catalogue; restore it so the
    # rest of the suite still runs (the reset intentionally leaves it empty).
    from tests.utils import DEFAULT_UOM_ID
    from app.modules.uoms.models import UOM
    from app.modules.uoms.service import ensure_default_uoms

    await ensure_default_uoms(db_session)
    db_session.add(UOM(id=DEFAULT_UOM_ID, code="EA", name="Each", symbol="ea", status="ACTIVE"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_permission_denied_is_audited(client, db_session):
    email = f"denied-{uuid.uuid4().hex[:8]}@example.com"
    await create_user_with_role(
        db_session,
        email=email,
        password="DeniedUser1",
        role_name=f"Denied {uuid.uuid4().hex[:6]}",
        permissions=["pos.access"],
    )
    await db_session.commit()
    data = await login(client, email, "DeniedUser1")
    headers = {"Authorization": f"Bearer {data['access_token']}", "X-Request-ID": "req-deny-1"}

    denied = await client.get("/api/v1/admin/users", headers=headers)
    assert denied.status_code == 403, denied.text

    entry = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == "permission_denied", AuditLog.result == "denied")
            .order_by(AuditLog.created_at.desc())
        )
    ).scalars().first()
    assert entry is not None
    assert entry.request_id == "req-deny-1"
    assert entry.new_values.get("path") == "/api/v1/admin/users"


@pytest.mark.asyncio
async def test_audit_logs_have_no_update_or_delete_route(client):
    admin = await admin_headers(client)
    # The API exposes read-only audit access: no update/delete route exists.
    assert (await client.delete("/api/v1/admin/audit-logs", headers=admin)).status_code in (404, 405)
    assert (
        await client.patch("/api/v1/admin/audit-logs", json={}, headers=admin)
    ).status_code in (404, 405)


@pytest.mark.asyncio
async def test_mutation_audit_captures_request_id_and_result(client, db_session):
    admin = await admin_headers(client)
    request_id = f"req-{uuid.uuid4().hex[:10]}"
    created = await client.post(
        "/api/v1/categories",
        json={"code": f"AR-{uuid.uuid4().hex[:6]}", "name": "Audit Result Cat"},
        headers={**admin, "X-Request-ID": request_id},
    )
    assert created.status_code == 201, created.text

    entry = (
        await db_session.execute(
            select(AuditLog)
            .where(AuditLog.action == "category_created")
            .order_by(AuditLog.created_at.desc())
        )
    ).scalars().first()
    assert entry is not None
    assert entry.result == "success"
    assert entry.request_id == request_id
    assert entry.actor_email == "admin@gmail.com"


def test_backup_serializer_handles_date_and_time_values():
    """Regression: a Date/Time column must not break the pre-reset backup.

    `datetime` is a subclass of `date`, so the old serializer left plain
    `date`/`time` values untouched and `json.dumps` raised
    "Object of type date is not JSON serializable" (HTTP 500)."""
    from datetime import date, datetime, time

    from app.modules.administration.maintenance import MaintenanceService

    serialize = MaintenanceService._serialize
    assert serialize(date(2026, 9, 26)) == "2026-09-26"
    assert serialize(datetime(2026, 9, 26, 13, 30, 5)) == "2026-09-26T13:30:05"
    assert serialize(time(13, 30, 5)) == "13:30:05"
