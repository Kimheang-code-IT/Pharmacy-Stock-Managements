"""Canonical document number allocation. Row-locked, transaction-safe.

Callers allocate inside their own transaction; the owning service commits.
Never compute the next number from row counts.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as sqlalchemy_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.shared.documents.models import DocumentSequence

DEFAULT_SEQUENCES: dict[str, str] = {
    "INVOICE": "INV",
    "SALE_RETURN": "SRT",
    "PURCHASE_RETURN": "PRT",
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


async def _get_sequence_for_update(session: AsyncSession, document_type: str) -> DocumentSequence | None:
    result = await session.execute(
        select(DocumentSequence).where(DocumentSequence.document_type == document_type).with_for_update()
    )
    return result.scalar_one_or_none()


async def allocate_document_number(session: AsyncSession, document_type: str) -> str:
    """Allocate the next document number, locking the sequence row.

    Sequences added by later migrations (e.g. PURCHASE_RETURN) self-heal on
    first use for databases seeded before they existed; the insert is
    conflict-safe so concurrent first allocations stay collision-free."""
    sequence = await _get_sequence_for_update(session, document_type)
    if sequence is None:
        prefix = DEFAULT_SEQUENCES.get(document_type)
        if prefix is not None:
            await session.execute(
                sqlalchemy_insert(DocumentSequence.__table__)
                .values(
                    document_type=document_type,
                    prefix=prefix,
                    next_number=1,
                    number_length=6,
                    status="ACTIVE",
                )
                .on_conflict_do_nothing(index_elements=[DocumentSequence.__table__.c.document_type])
            )
            await session.flush()
            sequence = await _get_sequence_for_update(session, document_type)
    if sequence is None:
        raise NotFoundError(f"Document sequence '{document_type}' is not configured")
    if sequence is None:
        raise NotFoundError(f"Document sequence '{document_type}' is not configured")
    if sequence.status != "ACTIVE":
        raise ConflictError(f"Document sequence '{document_type}' is inactive")

    number = f"{sequence.prefix}-{sequence.next_number:0{sequence.number_length}d}"
    sequence.next_number += 1
    await session.flush()
    return number
