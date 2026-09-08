from uuid import UUID

from fastapi import APIRouter, Depends, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ListParams, envelope, get_db_session, list_params, require_permission
from app.modules.auth.models import User
from app.modules.brands.schemas import BrandCreate, BrandOut, BrandUpdate
from app.modules.brands.service import BrandService

router = APIRouter(prefix="/brands", tags=["brands"])


@router.get("")
async def list_brands(
    params: ListParams = Depends(list_params),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("brand.view")),
) -> dict:
    service = BrandService(db)
    brands, total = await service.list(q=params.q, status=params.status, page=params.page, limit=params.limit)
    return envelope(
        [BrandOut.model_validate(b) for b in brands],
        {"page": params.page, "limit": params.limit, "total": total},
    )


@router.post("", status_code=http_status.HTTP_201_CREATED)
async def create_brand(
    payload: BrandCreate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("brand.create")),
) -> dict:
    service = BrandService(db)
    return envelope(BrandOut.model_validate(await service.create(payload)))


@router.get("/options")
async def brand_options(
    q: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission("brand.view")),
) -> dict:
    """Active-brand options for product form selectors (inactive brands hidden)."""
    service = BrandService(db)
    rows, _total = await service.list(q=q, status="ACTIVE", page=1, limit=limit)
    return envelope([
        {"id": str(b.id), "value": str(b.id), "label": b.name, "name": b.name}
        for b in rows
    ])


@router.get("/{brand_id}")
async def get_brand(
    brand_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("brand.view")),
) -> dict:
    service = BrandService(db)
    return envelope(BrandOut.model_validate(await service.get(brand_id)))


@router.patch("/{brand_id}")
async def update_brand(
    brand_id: UUID,
    payload: BrandUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("brand.update")),
) -> dict:
    service = BrandService(db)
    return envelope(BrandOut.model_validate(await service.update(brand_id, payload)))


@router.delete("/{brand_id}")
async def delete_brand(
    brand_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("brand.delete")),
) -> dict:
    service = BrandService(db)
    await service.delete(brand_id)
    return envelope({"message": "Brand deleted"})
