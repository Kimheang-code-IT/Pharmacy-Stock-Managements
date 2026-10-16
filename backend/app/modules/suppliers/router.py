from uuid import UUID

from fastapi import APIRouter, Depends, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ListParams,
    envelope,
    get_db_session,
    list_params,
    require_permission,
)
from app.modules.auth.models import User
from app.modules.pos.schemas import PaymentOut
from app.modules.suppliers.schemas import (
    SupplierCreate,
    SupplierDebtPaymentRequest,
    SupplierOut,
    SupplierUpdate,
)
from app.modules.suppliers.service import SupplierService

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def _supplier_out(supplier, balances: dict) -> SupplierOut:
    """Supplier row + live per-currency open-debt balances (Outstanding Debt)."""
    out = SupplierOut.model_validate(supplier)
    totals = balances.get(supplier.id) or {}
    out.debt_balances = {
        currency: str(total) for currency, total in sorted(totals.items())
    }
    return out


@router.get("")
async def list_suppliers(
    params: ListParams = Depends(list_params),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("supplier.view")),
) -> dict:
    service = SupplierService(db)
    suppliers, total = await service.list(q=params.q, status=params.status, page=params.page, limit=params.limit)
    balances = await service.debt_balances([s.id for s in suppliers])
    return envelope(
        [_supplier_out(s, balances) for s in suppliers],
        {"page": params.page, "limit": params.limit, "total": total},
    )


@router.post("", status_code=http_status.HTTP_201_CREATED)
async def create_supplier(
    payload: SupplierCreate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("supplier.create")),
) -> dict:
    service = SupplierService(db)
    return envelope(SupplierOut.model_validate(await service.create(payload)))


@router.get("/options")
async def supplier_options(
    q: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("supplier.view")),
) -> dict:
    """Active-supplier options for stock-in / purchase selectors."""
    service = SupplierService(db)
    suppliers, _total = await service.list(q=q, status="ACTIVE", page=1, limit=limit)
    return envelope([
        {"id": str(s.id), "value": str(s.id), "label": s.name, "name": s.name}
        for s in suppliers
    ])


@router.get("/{supplier_id}")
async def get_supplier(
    supplier_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("supplier.view")),
) -> dict:
    service = SupplierService(db)
    supplier = await service.get(supplier_id)
    balances = await service.debt_balances([supplier.id])
    return envelope(_supplier_out(supplier, balances))


@router.patch("/{supplier_id}")
async def update_supplier(
    supplier_id: UUID,
    payload: SupplierUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("supplier.update")),
) -> dict:
    service = SupplierService(db)
    return envelope(SupplierOut.model_validate(await service.update(supplier_id, payload)))


@router.delete("/{supplier_id}")
async def delete_supplier(
    supplier_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("supplier.delete")),
) -> dict:
    service = SupplierService(db)
    await service.delete(supplier_id)
    return envelope({"message": "Supplier deleted"})


@router.get("/{supplier_id}/debts")
async def list_supplier_debts(
    supplier_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("supplier.view")),
) -> dict:
    from app.modules.suppliers.schemas import SupplierDebtOut

    service = SupplierService(db)
    debts = await service.list_debts(supplier_id)
    rows = []
    for debt, transaction_date in debts:
        row = SupplierDebtOut.model_validate(debt).model_dump(mode="json")
        row["date"] = transaction_date
        rows.append(row)
    return envelope(rows)


@router.get("/{supplier_id}/payments")
async def list_supplier_payments(
    supplier_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("supplier.view")),
) -> dict:
    service = SupplierService(db)
    payments = await service.list_payments(supplier_id)
    return envelope([PaymentOut.model_validate(p) for p in payments])


@router.post("/{supplier_id}/payments", status_code=http_status.HTTP_201_CREATED)
async def pay_supplier_open_debts(
    supplier_id: UUID,
    payload: SupplierDebtPaymentRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("supplier.debt.pay")),
) -> dict:
    """Settle a supplier's open debts oldest-first (frontend fallback when no
    specific debt row is selected). Immutable payments, one transaction."""
    service = SupplierService(db)
    payments = await service.pay_open_debts(supplier_id, payload, actor=actor)
    return envelope([PaymentOut.model_validate(p) for p in payments])


@router.get("/{supplier_id}/debts/{debt_id}/payments")
async def list_supplier_debt_payments(
    supplier_id: UUID,
    debt_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("supplier.view")),
) -> dict:
    service = SupplierService(db)
    payments = await service.list_debt_payments(supplier_id, debt_id)
    return envelope([PaymentOut.model_validate(p) for p in payments])


@router.post("/{supplier_id}/debts/{debt_id}/payments", status_code=http_status.HTTP_201_CREATED)
async def pay_supplier_debt(
    supplier_id: UUID,
    debt_id: UUID,
    payload: SupplierDebtPaymentRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("supplier.debt.pay")),
) -> dict:
    service = SupplierService(db)
    payment = await service.pay_debt(supplier_id, debt_id, payload, actor=actor)
    return envelope(PaymentOut.model_validate(payment))


@router.get("/{supplier_id}/history")
async def supplier_history(
    supplier_id: UUID,
    params: ListParams = Depends(list_params),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("supplier.view")),
) -> dict:
    from app.modules.stock.service import list_stock_in_transactions_for_supplier

    data, total = await list_stock_in_transactions_for_supplier(
        db, supplier_id, page=params.page, limit=params.limit
    )
    return envelope(data, {"page": params.page, "limit": params.limit, "total": total})
