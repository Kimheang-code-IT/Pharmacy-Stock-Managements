import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import SessionFactory
from app.shared.documents import allocate_document_number, ensure_default_sequences


async def test_allocate_format_and_increment(db_session):
    from sqlalchemy import select

    from app.shared.documents.models import DocumentSequence

    await ensure_default_sequences(db_session)
    row = await db_session.scalar(select(DocumentSequence).where(DocumentSequence.document_type == "INVOICE"))
    start, prefix, length = row.next_number, row.prefix, row.number_length

    first = await allocate_document_number(db_session, "INVOICE")
    second = await allocate_document_number(db_session, "INVOICE")
    assert first == f"{prefix}-{start:0{length}d}"
    assert second == f"{prefix}-{start + 1:0{length}d}"
    await db_session.rollback()


async def test_all_default_sequences_seeded(db_session):
    from sqlalchemy import select

    from app.shared.documents.models import DocumentSequence

    await ensure_default_sequences(db_session)
    for document_type, prefix in {
        "INVOICE": "INV",
        "STOCK_IN": "STI",
        "STOCK_ADJUSTMENT": "STA",
        "STOCK_DAMAGE": "DMG",
        "STOCK_EXPIRE": "EXP",
        "CUSTOMER": "CUS",
        "SUPPLIER": "SUP",
        "CUSTOMER_DEBT_PAYMENT": "CDP",
        "SUPPLIER_DEBT_PAYMENT": "SDP",
    }.items():
        row = await db_session.scalar(
            select(DocumentSequence).where(DocumentSequence.document_type == document_type)
        )
        number = await allocate_document_number(db_session, document_type)
        assert number.startswith(f"{row.prefix or prefix}-")
    await db_session.rollback()


async def test_concurrent_allocation_never_duplicates():
    """Two concurrent transactions must receive distinct, gap-free numbers."""
    # Seed once with its own session.
    async with SessionFactory() as session:
        await ensure_default_sequences(session)
        await session.commit()

    results: list[str] = []

    async def allocate() -> None:
        async with SessionFactory() as session:
            number = await allocate_document_number(session, "STOCK_IN")
            await session.commit()
            results.append(number)

    await asyncio.gather(allocate(), allocate())

    assert len(results) == 2
    assert len(set(results)) == 2, f"duplicate document numbers allocated: {results}"
