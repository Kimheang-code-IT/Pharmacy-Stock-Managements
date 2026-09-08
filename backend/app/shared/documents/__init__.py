"""Shared document sequence service (canonical number allocation)."""

from app.shared.documents.models import DocumentSequence
from app.shared.documents.service import (
    DEFAULT_SEQUENCES,
    allocate_document_number,
    ensure_default_sequences,
)

__all__ = ["DEFAULT_SEQUENCES", "DocumentSequence", "allocate_document_number", "ensure_default_sequences"]
