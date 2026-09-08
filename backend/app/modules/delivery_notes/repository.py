from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer
from app.modules.delivery_notes.models import DeliveryNote, DeliveryNoteItem, DeliveryNoteSale
from app.modules.pos.models import Sale


class DeliveryNoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, delivery_note_id: uuid.UUID) -> DeliveryNote | None:
        return await self.session.get(DeliveryNote, delivery_note_id)

    async def get_by_no(self, delivery_no: str) -> DeliveryNote | None:
        result = await self.session.execute(
            select(DeliveryNote).where(DeliveryNote.delivery_no == delivery_no)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _sale_exists(sale_id: uuid.UUID) -> ColumnElement[bool]:
        return exists(
            select(DeliveryNoteSale.id).where(
                DeliveryNoteSale.delivery_note_id == DeliveryNote.id,
                DeliveryNoteSale.sale_id == sale_id,
            )
        )

    async def list(
        self,
        *,
        q: str | None,
        status: str | None,
        customer_id: uuid.UUID | None,
        sale_id: uuid.UUID | None,
        start,
        end,
        page: int,
        limit: int,
    ) -> tuple[list[DeliveryNote], int]:
        stmt = select(DeliveryNote)
        count_stmt = select(func.count()).select_from(DeliveryNote)
        conditions: list[ColumnElement[bool]] = []
        if q:
            pattern = f"%{q.strip()}%"
            # Delivery no / phone / location on the header; invoice no via the
            # linked sales; customer name via the customers table.
            conditions.append(
                DeliveryNote.delivery_no.ilike(pattern)
                | DeliveryNote.delivery_phone.ilike(pattern)
                | DeliveryNote.delivery_location.ilike(pattern)
                | DeliveryNote.id.in_(
                    select(DeliveryNoteSale.delivery_note_id).where(DeliveryNoteSale.invoice_no.ilike(pattern))
                )
                | DeliveryNote.customer_id.in_(
                    select(Customer.id).where(Customer.name.ilike(pattern) | Customer.phone.ilike(pattern))
                )
            )
        if status:
            conditions.append(DeliveryNote.status == status)
        if customer_id is not None:
            conditions.append(DeliveryNote.customer_id == customer_id)
        if sale_id is not None:
            conditions.append(self._sale_exists(sale_id))
        if start is not None:
            conditions.append(DeliveryNote.created_at >= start)
        if end is not None:
            conditions.append(DeliveryNote.created_at <= end)
        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one()
        rows = await self.session.execute(
            stmt.order_by(DeliveryNote.created_at.desc()).offset((page - 1) * limit).limit(limit)
        )
        return list(rows.scalars().all()), int(total)

    async def allocated_by_sale_item(
        self, sale_id: uuid.UUID, *, exclude_note_id: uuid.UUID | None = None
    ) -> dict[uuid.UUID, Decimal]:
        """qty_to_deliver totals per sale item across non-cancelled delivery notes.

        Cancelled notes release their reserved quantities back to the sale pool.
        ``exclude_note_id`` lets draft edits ignore the note's own lines.
        """
        conditions = [DeliveryNoteItem.sale_id == sale_id, DeliveryNote.status != DeliveryNote.STATUS_CANCELLED]
        if exclude_note_id is not None:
            conditions.append(DeliveryNote.id != exclude_note_id)
        stmt = (
            select(
                DeliveryNoteItem.sale_item_id,
                func.coalesce(func.sum(DeliveryNoteItem.qty_to_deliver), 0).label("allocated"),
            )
            .join(DeliveryNote, DeliveryNote.id == DeliveryNoteItem.delivery_note_id)
            .where(*conditions)
            .group_by(DeliveryNoteItem.sale_item_id)
        )
        rows = await self.session.execute(stmt)
        return {row[0]: Decimal(row[1]) for row in rows.all()}

    async def delivered_by_sale_item(self, sale_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
        """Delivered totals per sale item across non-cancelled delivery notes."""
        stmt = (
            select(
                DeliveryNoteItem.sale_item_id,
                func.coalesce(func.sum(DeliveryNoteItem.qty_delivered), 0).label("delivered"),
            )
            .join(DeliveryNote, DeliveryNote.id == DeliveryNoteItem.delivery_note_id)
            .where(DeliveryNoteItem.sale_id == sale_id, DeliveryNote.status != DeliveryNote.STATUS_CANCELLED)
            .group_by(DeliveryNoteItem.sale_item_id)
        )
        rows = await self.session.execute(stmt)
        return {row[0]: Decimal(row[1]) for row in rows.all()}

    async def remaining_qty_by_sale(
        self, sale_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Decimal]:
        """Total remaining-to-deliver qty per sale (non-cancelled notes)."""
        if not sale_ids:
            return {}
        allocated = (
            select(
                DeliveryNoteItem.sale_id.label("sid"),
                func.coalesce(func.sum(DeliveryNoteItem.qty_to_deliver), 0).label("allocated"),
            )
            .join(DeliveryNote, DeliveryNote.id == DeliveryNoteItem.delivery_note_id)
            .where(
                DeliveryNoteItem.sale_id.in_(sale_ids),
                DeliveryNote.status != DeliveryNote.STATUS_CANCELLED,
            )
            .group_by(DeliveryNoteItem.sale_id)
        )
        rows = (await self.session.execute(allocated)).all()
        return {row.sid: Decimal(row.allocated) for row in rows}

    def add(self, note: DeliveryNote) -> None:
        self.session.add(note)

    async def flush(self) -> None:
        await self.session.flush()
