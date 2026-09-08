"""Canonical document number allocation. Row-locked, transaction-safe.

Callers allocate inside their own transaction; the owning service commits.
Never compute the next number from row counts.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.shared.documents.models import DocumentSequence

DEFAULT_SEQUENCES: dict[str, str] = {
    "INVOICE": "INV",
    "SALE_RETURN": "RET",
    "STOCK_IN": "STI",
    "STOCK_ADJUSTMENT": "STA",
    "STOCK_DAMAGE": "DMG",
    "STOCK_EXPIRE": "EXP",
    "DELIVERY_NOTE": "DN",
    "CUSTOMER": "CUS",
    "SUPPLIER": "SUP",
    "CUSTOMER_DEBT_PAYMENT": "CDP",
    "SUPPLIER_DEBT_PAYMENT": "SDP",
}


async def ensure_default_sequences(session: AsyncSession) -> None:
    """Create any missing default sequence rows (idempotent)."""
    result = await session.execute(select(DocumentSequence.document_type))
    existing = {row[0] for row in result.all()}
    for document_type, prefix in DEFAULT_SEQUENCES.items():
        if document_type in existing:
            continue
        session.add(
            DocumentSequence(
                document_type=document_type,
                prefix=prefix,
                next_number=1,
                number_length=6,
                status="ACTIVE",
            )
        )
    await session.flush()


async def allocate_document_number(session: AsyncSession, document_type: str) -> str:
    """Allocate the next document number, locking the sequence row."""
    result = await session.execute(
        select(DocumentSequence).where(DocumentSequence.document_type == document_type).with_for_update()
    )
    sequence = result.scalar_one_or_none()
    if sequence is None:
        raise NotFoundError(f"Document sequence '{document_type}' is not configured")
    if sequence.status != "ACTIVE":
        raise ConflictError(f"Document sequence '{document_type}' is inactive")

    number = f"{sequence.prefix}-{sequence.next_number:0{sequence.number_length}d}"
    sequence.next_number += 1
    await session.flush()
    return number
