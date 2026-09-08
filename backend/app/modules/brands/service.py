from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.modules.brands.models import Brand
from app.modules.brands.repository import BrandRepository


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
        await self.session.commit()
        return brand

    async def update(self, brand_id: uuid.UUID, payload) -> Brand:
        brand = await self.get(brand_id)
        if payload.code is not None and payload.code.strip() != brand.code:
            if await self.repo.get_by_code(payload.code.strip()):
                raise ConflictError("A brand with this code already exists")
            brand.code = payload.code.strip()
        if payload.name is not None:
            brand.name = payload.name.strip()
        if payload.description is not None:
            brand.description = payload.description
        if payload.logo_object_key is not None:
            brand.logo_object_key = payload.logo_object_key
        if payload.status is not None:
            brand.status = payload.status
        await self.repo.flush()
        await self.session.commit()
        return brand

    async def delete(self, brand_id: uuid.UUID) -> None:
        brand = await self.get(brand_id)
        if await self.repo.count_products(brand_id) > 0:
            raise ConflictError("Cannot delete a brand that still has products; disable it instead")
        await self.session.delete(brand)
        await self.session.commit()
