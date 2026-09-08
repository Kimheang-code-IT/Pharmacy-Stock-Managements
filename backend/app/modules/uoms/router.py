from uuid import UUID

from fastapi import APIRouter, Depends, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ListParams, envelope, get_db_session, list_params, require_permission
from app.modules.auth.models import User
from app.modules.uoms.schemas import UOMCreate, UOMOut, UOMUpdate
from app.modules.uoms.service import UOMService

router = APIRouter(prefix="/uoms", tags=["uoms"])


@router.get("")
async def list_uoms(
    params: ListParams = Depends(list_params),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("uom.view")),
) -> dict:
    service = UOMService(db)
    uoms, total = await service.list(q=params.q, status=params.status, page=params.page, limit=params.limit)
    return envelope(
        [UOMOut.model_validate(u) for u in uoms],
        {"page": params.page, "limit": params.limit, "total": total},
    )


@router.post("", status_code=http_status.HTTP_201_CREATED)
async def create_uom(
    payload: UOMCreate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("uom.create")),
) -> dict:
    service = UOMService(db)
    return envelope(UOMOut.model_validate(await service.create(payload)))


@router.get("/options")
async def uom_options(
    q: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission("uom.view")),
) -> dict:
    """Active-UOM options for product/POS selectors (inactive UOMs hidden)."""
    service = UOMService(db)
    rows, _total = await service.list(q=q, status="ACTIVE", page=1, limit=limit)
    return envelope([
        {
            "id": str(u.id),
            "value": str(u.id),
            "label": u.name,
            "code": u.code,
            "name": u.name,
            "symbol": u.symbol,
        }
        for u in rows
    ])


@router.get("/{uom_id}")
async def get_uom(
    uom_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("uom.view")),
) -> dict:
    service = UOMService(db)
    return envelope(UOMOut.model_validate(await service.get(uom_id)))


@router.patch("/{uom_id}")
async def update_uom(
    uom_id: UUID,
    payload: UOMUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("uom.update")),
) -> dict:
    service = UOMService(db)
    return envelope(UOMOut.model_validate(await service.update(uom_id, payload)))


@router.delete("/{uom_id}")
async def delete_uom(
    uom_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("uom.delete")),
) -> dict:
    service = UOMService(db)
    await service.delete(uom_id)
    return envelope({"message": "UOM deleted"})
