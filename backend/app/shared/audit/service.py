from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.audit.models import AuditLog


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    module: str,
    user_id=None,
    entity_type: str | None = None,
    entity_id=None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Append an audit row to the caller's transaction.

    The owning service commits; this function never commits itself.
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        module=module,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=old_values,
        new_values=new_values,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(entry)
    await session.flush()
    return entry
