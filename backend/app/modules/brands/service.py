from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.brands.models import Brand
from app.modules.brands.repository import BrandRepository
from app.shared.audit.service import record_audit
from app.shared.lifecycle import assert_inactive_for_delete


class BrandService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BrandRepository(session)

    async def list(self, *, q, status, page, limit) -> tuple[list[Brand], int]:
        return await self.repo.list(q=q, status=status, page=page, limit=limit)

    async def get(self, brand_id: uuid.UUID) -> Brand:
        brand = await self.repo.get(brand_id)
        if brand is None:
            raise NotFoundError("Brand not found")
        return brand

    async def create(self, payload) -> Brand:
        if await self.repo.get_by_code(payload.code.strip()):
            raise ConflictError("A brand with this code already exists")
        brand = Brand(
            code=payload.code.strip(),
            name=payload.name.strip(),
            description=payload.description,
            logo_object_key=payload.logo_object_key,
            status=payload.status,
        )
        self.repo.add(brand)
        await self.repo.flush()
        await record_audit(
            self.session,
            action="brand_created",
            module="brands",
            entity_type="brand",
            entity_id=brand.id,
            new_values={"code": brand.code, "name": brand.name, "status": brand.status},
        )
        await self.session.commit()
        return brand

    async def update(self, brand_id: uuid.UUID, payload) -> Brand:
        brand = await self.get(brand_id)
        old = {"code": brand.code, "name": brand.name, "status": brand.status}
        if payload.code is not None:
            code = payload.code.strip()
            if code and code != brand.code:
                if await self.repo.get_by_code(code):
                    raise ConflictError("A brand with this code already exists")
                brand.code = code
        if payload.name is not None:
            brand.name = payload.name.strip()
        if payload.description is not None:
            brand.description = payload.description
        if payload.logo_object_key is not None:
            brand.logo_object_key = payload.logo_object_key
        if payload.status is not None:
            brand.status = payload.status
        await self.repo.flush()
        await record_audit(
            self.session,
            action="brand_updated",
            module="brands",
            entity_type="brand",
            entity_id=brand.id,
            old_values=old,
            new_values={"code": brand.code, "name": brand.name, "status": brand.status},
        )
        await self.session.commit()
        return brand

    async def delete(self, brand_id: uuid.UUID) -> None:
        brand = await self.get(brand_id)
        assert_inactive_for_delete(brand.status, label="brand")
        if await self.repo.count_products(brand_id) > 0:
            raise ConflictError(
                "Cannot delete this brand because products reference it. "
                "Deactivate it instead."
            )
        snapshot = {"code": brand.code, "name": brand.name}
        await self.session.delete(brand)
        await record_audit(
            self.session,
            action="brand_deleted",
            module="brands",
            entity_type="brand",
            entity_id=brand.id,
            old_values=snapshot,
        )
        await self.session.commit()
