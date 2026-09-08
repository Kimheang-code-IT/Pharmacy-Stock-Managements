"""Expiry alert state persistence and lot discovery.

Lots are derived from immutable stock movements: any (product, batch_no,
expiry_date) group on an expiry-tracked product with a positive remaining
quantity. Only movements that carry a batch/expiry participate in lot groups;
non-batched sale outflows cannot be attributed to a specific lot and are
excluded from lot math (documented limitation — alerts are informational).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.stock.models import Product, StockMovement
from app.modules.telegram.models import TelegramExpiryAlertState


class ExpiryAlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def expiring_lots(self) -> list[dict]:
        """All expiry-tracked lots with remaining qty > 0 (any expiry date)."""
        stmt = (
            select(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.sku.label("sku"),
                Product.barcode.label("barcode"),
                StockMovement.batch_no.label("batch_no"),
                StockMovement.expiry_date.label("expiry_date"),
                func.sum(StockMovement.quantity_delta).label("remaining_qty"),
            )
            .join(Product, Product.id == StockMovement.product_id)
            .where(
                Product.expiry_tracking.is_(True),
                Product.status == "ACTIVE",
                StockMovement.expiry_date.is_not(None),
            )
            .group_by(
                Product.id,
                Product.name,
                Product.sku,
                Product.barcode,
                StockMovement.batch_no,
                StockMovement.expiry_date,
            )
            .having(func.sum(StockMovement.quantity_delta) > 0)
        )
        rows = await self.session.execute(stmt)
        return [
            {
                "product_id": row.product_id,
                "product_name": row.product_name,
                "sku": row.sku,
                "barcode": row.barcode,
                "batch_no": row.batch_no,
                "expiry_date": row.expiry_date,
                "remaining_qty": Decimal(row.remaining_qty),
            }
            for row in rows.all()
        ]

    async def sent_levels(self) -> set[tuple[uuid.UUID, str, date, int]]:
        """All (product_id, batch, expiry_date, alert_level) already alerted.

        Batch is normalized with COALESCE(batch_no, '') so unbatched lots
        dedupe exactly like the functional unique index does.
        """
        stmt = select(
            TelegramExpiryAlertState.product_id,
            func.coalesce(TelegramExpiryAlertState.batch_no, ""),
            TelegramExpiryAlertState.expiry_date,
            TelegramExpiryAlertState.alert_level,
        )
        rows = await self.session.execute(stmt)
        return {(row[0], row[1], row[2], row[3]) for row in rows.all()}

    def record_state(
        self, *, product_id: uuid.UUID, batch_no: str | None, expiry_date: date, alert_level: int
    ) -> TelegramExpiryAlertState:
        state = TelegramExpiryAlertState(
            product_id=product_id,
            batch_no=batch_no,
            expiry_date=expiry_date,
            alert_level=alert_level,
        )
        self.session.add(state)
        return state
