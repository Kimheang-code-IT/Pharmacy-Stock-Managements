from uuid import UUID

from fastapi import APIRouter, Depends, Query, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ListParams,
    envelope,
    get_current_user,
    get_db_session,
    list_params,
    require_permission,
)
from app.modules.auth.models import User
from app.modules.stock.schemas import (
    MovementOut,
    ProductCreate,
    ProductUpdate,
    PurchaseReturnRequest,
    QuickStockOperationRequest,
    SalePriceCreate,
    SalePriceUpdate,
    StockAdjustmentRequest,
    StockDamageRequest,
    StockExpireRequest,
    StockInRequest,
)
from app.modules.stock.service import (
    ProductService,
    StockOperationService,
    movement_to_out,
)
from app.shared.pagination.params import list_meta

products_router = APIRouter(tags=["products"])
router = APIRouter(prefix="/stock", tags=["stock"])


# ---------------------------------------------------------------- products


@products_router.get("/products")
async def list_products(
    params: ListParams = Depends(list_params),
    category_id: UUID | None = None,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(get_current_user),
) -> dict:
    service = ProductService(db)
    products, total = await service.list(
        q=params.q, category_id=category_id, status=params.status, page=params.page, limit=params.limit
    )
    return envelope(products, {"page": params.page, "limit": params.limit, "total": total})


@products_router.post("/products", status_code=http_status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("product.create")),
) -> dict:
    service = ProductService(db)
    return envelope(await service.create(payload))


# ------------------------------------------------- product sale prices (v1)
# Registered BEFORE /products/{product_id} so the static collection paths win.


@products_router.get("/products/sale-prices")
async def list_sale_prices(
    params: ListParams = Depends(list_params),
    product_id: UUID | None = Query(default=None, alias="productId"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("stock.view")),
) -> dict:
    """Versioned POS sale prices (spec: product_sale_prices), newest first."""
    from app.modules.stock import sale_prices as sale_price_service

    rows, total = await sale_price_service.list_sale_prices(
        db,
        product_id=product_id,
        q=params.q,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    return envelope(rows, list_meta(params.page, params.limit, total))


@products_router.post("/products/sale-prices", status_code=http_status.HTTP_201_CREATED)
async def create_sale_price(
    payload: SalePriceCreate,
    product_id: UUID | None = Query(default=None, alias="productId"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("product.update")),
) -> dict:
    """Add version MAX(version)+1 and make it the ONLY POS-active row."""
    from app.core.exceptions import ValidationError
    from app.modules.stock import sale_prices as sale_price_service

    target = payload.product_id or product_id
    if target is None:
        raise ValidationError("productId is required", field_errors={"productId": "Required"})
    return envelope(
        await sale_price_service.add_sale_price(
            db,
            product_id=target,
            sale_price=payload.sale_price,
            effective_date=payload.effective_date,
            actor=actor,
        )
    )


@products_router.patch("/products/sale-prices/{price_id}")
async def patch_sale_price(
    price_id: UUID,
    payload: SalePriceUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("product.update")),
) -> dict:
    """`{isActive: true}` runs the activate transaction; false deactivates."""
    from app.modules.stock import sale_prices as sale_price_service

    return envelope(await sale_price_service.patch_sale_price(db, price_id=price_id, payload=payload, actor=actor))


@products_router.post("/products/sale-prices/{price_id}/activate")
async def activate_sale_price(
    price_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("product.update")),
) -> dict:
    """Make exactly this version POS-active and copy it onto selling_price."""
    from app.modules.stock import sale_prices as sale_price_service

    return envelope(await sale_price_service.activate_sale_price(db, price_id=price_id, actor=actor))


@products_router.post("/products/{product_id}/sale-prices/{price_id}/activate")
async def activate_product_sale_price(
    product_id: UUID,
    price_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("product.update")),
) -> dict:
    """Spec route: activates a version, rejecting rows of another product."""
    from app.core.exceptions import NotFoundError
    from app.modules.stock import sale_prices as sale_price_service

    row = await db.get(sale_price_service.ProductSalePrice, price_id)
    if row is None or row.product_id != product_id:
        raise NotFoundError("Sale price version not found for this product")
    return envelope(await sale_price_service.activate_sale_price(db, price_id=price_id, actor=actor))


@products_router.get("/products/{product_id}")
async def get_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(get_current_user),
) -> dict:
    service = ProductService(db)
    return envelope(await service.get(product_id))


@products_router.patch("/products/{product_id}")
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("product.update")),
) -> dict:
    service = ProductService(db)
    return envelope(await service.update(product_id, payload, actor=actor))


@products_router.delete("/products/{product_id}")
async def delete_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("product.delete")),
) -> dict:
    service = ProductService(db)
    await service.delete(product_id)
    return envelope({"message": "Product deleted"})


@products_router.get("/products/{product_id}/sale-prices")
async def list_product_sale_prices(
    product_id: UUID,
    params: ListParams = Depends(list_params),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("stock.view")),
) -> dict:
    from app.modules.stock import sale_prices as sale_price_service

    rows, total = await sale_price_service.list_sale_prices(
        db,
        product_id=product_id,
        q=params.q,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    return envelope(rows, list_meta(params.page, params.limit, total))


@products_router.post("/products/{product_id}/sale-prices", status_code=http_status.HTTP_201_CREATED)
async def add_product_sale_price(
    product_id: UUID,
    payload: SalePriceCreate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("product.update")),
) -> dict:
    from app.modules.stock import sale_prices as sale_price_service

    return envelope(
        await sale_price_service.add_sale_price(
            db,
            product_id=product_id,
            sale_price=payload.sale_price,
            effective_date=payload.effective_date,
            actor=actor,
        )
    )


@router.get("/products/{product_id}/cost-history")
async def product_cost_history(
    product_id: UUID,
    params: ListParams = Depends(list_params),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("stock.view")),
) -> dict:
    """Read-only Cost Price history: confirmed Stock In lots, versioned
    oldest → newest and returned newest first. No write path exists."""
    from app.modules.stock import sale_prices as sale_price_service

    rows, total = await sale_price_service.product_cost_history(
        db,
        product_id=product_id,
        q=params.q,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    return envelope(rows, list_meta(params.page, params.limit, total))


# ------------------------------------------------------- stock operations


@router.get("/operations")
async def list_stock_operations(
    params: ListParams = Depends(list_params),
    type: str = Query(default="STOCK_IN"),
    supplier_id: UUID | None = Query(default=None, alias="supplierId"),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("stock.view")),
) -> dict:
    """Stock operation documents (Stock In / purchase list read model)."""
    from app.modules.suppliers.repository import SupplierRepository

    service = StockOperationService(db)
    transactions, total = await service.list_operations(
        q=params.q,
        operation_type=(type or "STOCK_IN").upper(),
        supplier_id=supplier_id,
        status=status,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    suppliers = SupplierRepository(db)
    rows = []
    for transaction in transactions:
        supplier_name = None
        if transaction.supplier_id is not None:
            supplier = await suppliers.get(transaction.supplier_id)
            supplier_name = supplier.name if supplier else None
        rows.append(service.operation_document_out(transaction, supplier_name))
    return envelope(rows, list_meta(params.page, params.limit, total))


@router.post("/operations", status_code=http_status.HTTP_201_CREATED)
async def quick_stock_operation(
    payload: QuickStockOperationRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(get_current_user),
) -> dict:
    """Single-product quick operation (Stock In / Adjustment / Damage / Expiry).
    Permission is chosen by type, mirroring the individual endpoints."""
    from app.core.exceptions import AccessDeniedError
    from app.core.permissions import user_has_permission
    from app.modules.stock.service import StockOperationService

    permission = {
        "stock_in": "stock.in",
        "adjustment": "stock.adjust",
        "damage": "stock.damage",
        "expiry": "stock.expire",
    }[payload.type]
    if not user_has_permission(actor, permission):
        raise AccessDeniedError("You do not have permission for this operation")
    service = StockOperationService(db)
    return envelope(await service.quick_operation(payload=payload, actor=actor))


@router.post("/in", status_code=http_status.HTTP_201_CREATED)
async def stock_in(
    payload: StockInRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("stock.in")),
) -> dict:
    service = StockOperationService(db)
    result = await service.stock_in(payload, actor=actor)
    return envelope(result)


@router.post("/in/{stock_transaction_id}/return", status_code=http_status.HTTP_201_CREATED)
async def purchase_return(
    stock_transaction_id: UUID,
    payload: PurchaseReturnRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("stock.in")),
) -> dict:
    """Return to supplier against a confirmed Stock In (spec: Purchase Return
    Transaction). Immutable PRT- document; PURCHASE_RETURN stock out; supplier
    debt reduction / credit; no Stock In edit."""
    service = StockOperationService(db)
    result = await service.purchase_return(stock_transaction_id, payload, actor=actor)
    return envelope(result.model_dump())


@router.post("/adjust", status_code=http_status.HTTP_201_CREATED)
async def stock_adjust(
    payload: StockAdjustmentRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("stock.adjust")),
) -> dict:
    service = StockOperationService(db)
    result = await service.adjust(payload, actor=actor)
    return envelope(result)


@router.post("/damage", status_code=http_status.HTTP_201_CREATED)
async def stock_damage(
    payload: StockDamageRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("stock.damage")),
) -> dict:
    service = StockOperationService(db)
    result = await service.damage(payload, actor=actor)
    return envelope(result)


@router.post("/expire", status_code=http_status.HTTP_201_CREATED)
async def stock_expire(
    payload: StockExpireRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("stock.expire")),
) -> dict:
    service = StockOperationService(db)
    result = await service.expire(payload, actor=actor)
    return envelope(result)


@router.get("/movements")
async def list_movements(
    params: ListParams = Depends(list_params),
    product_id: UUID | None = Query(default=None),
    movement_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("stock.view")),
) -> dict:
    service = StockOperationService(db)
    movements, total = await service.list_movements(
        q=params.q,
        product_id=product_id,
        movement_type=movement_type,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    return envelope([movement_to_out(m) for m in movements], list_meta(params.page, params.limit, total))


@router.get("/products/{product_id}/history")
async def product_history(
    product_id: UUID,
    params: ListParams = Depends(list_params),
    type: str = Query(default="all", pattern="^(stock_in|stock_out|damage|all)$"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("stock.view")),
) -> dict:
    """Compact stock-history rows for the product history dialogs.

    ``type`` maps to the Stock list columns: stock_in | stock_out | damage | all
    (``all`` is the full movement history behind Current Stock).
    """
    from app.core.exceptions import NotFoundError
    from app.modules.stock.history import product_history as fetch_history
    from app.modules.stock.repository import ProductRepository

    if await ProductRepository(db).get(product_id) is None:
        raise NotFoundError("Product not found")
    rows, total = await fetch_history(
        db,
        product_id=product_id,
        kind=type,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    return envelope(rows, list_meta(params.page, params.limit, total))
