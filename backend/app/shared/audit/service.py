"""Audit writing.

`record_audit` appends to the caller's transaction (the owning service
commits). Request context (request id, IP, user agent) is propagated through a
ContextVar set by the HTTP middleware, so every mutation is attributed without
threading a `Request` object through the whole service layer.
"""

from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.audit.models import AuditLog, AuditLogArchive, SystemAuditEvent

_audit_context: ContextVar[dict[str, str | None]] = ContextVar("audit_context", default={})
_actor_context: ContextVar[dict[str, str | None]] = ContextVar("audit_actor", default={})

RESULT_SUCCESS = "success"
RESULT_FAILURE = "failure"
RESULT_DENIED = "denied"


def set_audit_context(
    *,
    request_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Set request context for the current task (called by the middleware)."""
    _audit_context.set(
        {"request_id": request_id, "ip_address": ip_address, "user_agent": user_agent}
    )


def audit_context() -> dict[str, str | None]:
    return dict(_audit_context.get())


def set_audit_actor(user_id=None, email: str | None = None, role: str | None = None) -> None:
    """Set the authenticated actor for the current task (called by deps)."""
    _actor_context.set(
        {
            "user_id": str(user_id) if user_id else None,
            "email": email,
            "role": role,
        }
    )


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    module: str,
    user_id=None,
    actor_email: str | None = None,
    entity_type: str | None = None,
    entity_id=None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    result: str = RESULT_SUCCESS,
) -> AuditLog:
    """Append an audit row to the caller's transaction.

    Explicit ip/user_agent/request_id win; otherwise the request context set by
    the middleware is used. The owning service commits.
    """
    context = _audit_context.get()
    actor = _actor_context.get()
    if user_id is None and actor.get("user_id"):
        from uuid import UUID as _UUID

        try:
            user_id = _UUID(actor["user_id"])
        except (ValueError, TypeError):
            user_id = None
    if actor_email is None:
        actor_email = actor.get("email")
    entry = AuditLog(
        user_id=user_id,
        actor_email=actor_email,
        action=action,
        module=module,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address or context.get("ip_address"),
        user_agent=user_agent or context.get("user_agent"),
        request_id=request_id or context.get("request_id"),
        result=result,
    )
    session.add(entry)
    await session.flush()
    return entry


async def record_system_event(
    session: AsyncSession,
    *,
    action: str,
    module: str,
    actor=None,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    result: str = RESULT_SUCCESS,
    note: str | None = None,
) -> SystemAuditEvent:
    """Write to the protected system audit store (no FKs, never reset-deleted).

    The caller commits. Used for destructive operations before AND after they
    run, so a full reset cannot erase who initiated it.
    """
    context = _audit_context.get()
    if actor is not None:
        actor_id = actor_id or getattr(actor, "id", None)
        actor_email = actor_email or getattr(actor, "email", None)
        role_ref = getattr(actor, "role_ref", None)
        actor_role = actor_role or (getattr(role_ref, "name", None) if role_ref else None)
    entry = SystemAuditEvent(
        action=action,
        module=module,
        actor_id=actor_id,
        actor_email=actor_email,
        actor_role=actor_role,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old_values,
        new_values=new_values,
        ip_address=context.get("ip_address"),
        user_agent=context.get("user_agent"),
        request_id=context.get("request_id"),
        result=result,
        note=note,
    )
    session.add(entry)
    await session.flush()
    return entry


async def archive_expired_audit_logs(session: AsyncSession, *, retention_days: int) -> int:
    """Move audit rows older than the retention window into the archive table.

    Returns the number of rows archived. The migrated schema's immutability
    trigger permits the DELETE only while `app.allow_audit_purge` is set for the
    transaction; archival is the one sanctioned deletion path.
    """
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    rows = (
        await session.execute(select(AuditLog).where(AuditLog.created_at < cutoff))
    ).scalars().all()
    if not rows:
        return 0
    await session.execute(
        insert(AuditLogArchive),
        [
            {
                "id": row.id,
                "user_id": row.user_id,
                "actor_email": row.actor_email,
                "action": row.action,
                "module": row.module,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "old_values": row.old_values,
                "new_values": row.new_values,
                "ip_address": row.ip_address,
                "user_agent": row.user_agent,
                "request_id": row.request_id,
                "result": row.result,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    )
    # Allow the trigger-guarded purge for this transaction only.
    try:
        from sqlalchemy import text

        await session.execute(text("SET LOCAL app.allow_audit_purge = 'on'"))
    except Exception:
        # Non-PostgreSQL / trigger absent: harmless.
        pass
    await session.execute(delete(AuditLog).where(AuditLog.id.in_([row.id for row in rows])))
    return len(rows)
