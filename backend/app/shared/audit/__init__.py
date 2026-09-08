"""Shared audit logging. Append-only audit trail entries."""

from app.shared.audit.models import AuditLog
from app.shared.audit.service import record_audit

__all__ = ["AuditLog", "record_audit"]
