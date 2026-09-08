from uuid import UUID

from fastapi import APIRouter, Depends, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ListParams, envelope, get_db_session, list_params, require_permission
from app.modules.auth.models import User
from app.modules.categories.schemas import CategoryCreate, CategoryOut, CategoryUpdate
from app.modules.categories.service import CategoryService

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
async def list_categories(
    params: ListParams = Depends(list_params),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("category.view")),
) -> dict:
    service = CategoryService(db)
    categories, total = await service.list(q=params.q, status=params.status, page=params.page, limit=params.limit)
    return envelope(
        [CategoryOut.model_validate(c) for c in categories],
        {"page": params.page, "limit": params.limit, "total": total},
    )


@router.post("", status_code=http_status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("category.create")),
) -> dict:
    service = CategoryService(db)
    return envelope(CategoryOut.model_validate(await service.create(payload)))


@router.get("/options")
async def category_options(
    q: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission("category.view")),
) -> dict:
    """Active-category options for product form selectors."""
    service = CategoryService(db)
    rows, _total = await service.list(q=q, status="ACTIVE", page=1, limit=limit)
    return envelope([
        {"id": str(c.id), "value": str(c.id), "label": c.name, "name": c.name}
        for c in rows
    ])


@router.get("/{category_id}")
async def get_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("category.view")),
) -> dict:
    service = CategoryService(db)
    return envelope(CategoryOut.model_validate(await service.get(category_id)))


@router.patch("/{category_id}")
async def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("category.update")),
) -> dict:
    service = CategoryService(db)
    return envelope(CategoryOut.model_validate(await service.update(category_id, payload)))


@router.delete("/{category_id}")
async def delete_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("category.delete")),
) -> dict:
    service = CategoryService(db)
    await service.delete(category_id)
    return envelope({"message": "Category deleted"})
