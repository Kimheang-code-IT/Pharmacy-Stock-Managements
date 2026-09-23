"""UOM service — spec section 2.1.3.

Inactive UOMs are hidden from product/POS selectors; a UOM linked to products
must not be hard-deleted (prefer disable).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.uoms.models import DEFAULT_UOMS, UOM
from app.modules.uoms.repository import UOMRepository
from app.shared.audit.service import record_audit
from app.shared.lifecycle import assert_inactive_for_delete


async def ensure_default_uoms(session: AsyncSession) -> None:
    """Idempotently insert the default UOM seed rows."""
    repo = UOMRepository(session)
    for code, name, symbol in DEFAULT_UOMS:
        if await repo.get_by_code(code) is None:
            repo.add(UOM(code=code, name=name, symbol=symbol, status="ACTIVE"))
    await session.flush()


class UOMService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UOMRepository(session)

    async def list(self, *, q, status, page, limit) -> tuple[list[UOM], int]:
        return await self.repo.list(q=q, status=status, page=page, limit=limit)

    async def get(self, uom_id: uuid.UUID) -> UOM:
        uom = await self.repo.get(uom_id)
        if uom is None:
            raise NotFoundError("UOM not found")
        return uom

    async def create(self, payload) -> UOM:
        if await self.repo.get_by_code(payload.code.strip()):
            raise ConflictError("A UOM with this code already exists")
        uom = UOM(
            code=payload.code.strip(),
            name=payload.name.strip(),
            symbol=payload.symbol.strip(),
            description=payload.description,
            status=payload.status,
        )
        self.repo.add(uom)
        await self.repo.flush()
        await record_audit(
            self.session,
            action="uom_created",
            module="uoms",
            entity_type="uom",
            entity_id=uom.id,
            new_values={"code": uom.code, "name": uom.name, "status": uom.status},
        )
        await self.session.commit()
        await self.session.refresh(uom)
        return uom

    async def update(self, uom_id: uuid.UUID, payload) -> UOM:
        uom = await self.get(uom_id)
        old = {"code": uom.code, "name": uom.name, "status": uom.status}
        if payload.code is not None:
            code = payload.code.strip()
            if code and code != uom.code:
                if await self.repo.get_by_code(code):
                    raise ConflictError("A UOM with this code already exists")
                uom.code = code
        if payload.name is not None:
            uom.name = payload.name.strip()
        if payload.symbol is not None:
            uom.symbol = payload.symbol.strip()
        if payload.description is not None:
            uom.description = payload.description
        if payload.status is not None:
            uom.status = payload.status
        await self.repo.flush()
        await record_audit(
            self.session,
            action="uom_updated",
            module="uoms",
            entity_type="uom",
            entity_id=uom.id,
            old_values=old,
            new_values={"code": uom.code, "name": uom.name, "status": uom.status},
        )
        await self.session.commit()
        await self.session.refresh(uom)
        return uom

    async def delete(self, uom_id: uuid.UUID) -> None:
        uom = await self.get(uom_id)
        assert_inactive_for_delete(uom.status, label="unit of measure")
        if await self.repo.count_products(uom_id) > 0 or await self.repo.count_sale_price_uoms(uom_id) > 0:
            raise ConflictError(
                "Cannot delete this unit of measure because products or pricing history "
                "reference it. Deactivate it instead."
            )
        snapshot = {"code": uom.code, "name": uom.name}
        await self.session.delete(uom)
        await record_audit(
            self.session,
            action="uom_deleted",
            module="uoms",
            entity_type="uom",
            entity_id=uom.id,
            old_values=snapshot,
        )
        await self.session.commit()
