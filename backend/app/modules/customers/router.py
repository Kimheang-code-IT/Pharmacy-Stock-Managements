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
from app.modules.customers.schemas import CustomerCreate, CustomerOut, CustomerUpdate
from app.modules.customers.service import CustomerService
from app.modules.pos.schemas import CustomerDebtOut, DebtPaymentRequest, PaymentOut

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
async def list_customers(
    params: ListParams = Depends(list_params),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("customer.view")),
) -> dict:
    service = CustomerService(db)
    customers, total = await service.list(q=params.q, status=params.status, page=params.page, limit=params.limit)
    return envelope(
        [CustomerOut.model_validate(c) for c in customers],
        {"page": params.page, "limit": params.limit, "total": total},
    )


@router.post("", status_code=http_status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("customer.create")),
) -> dict:
    service = CustomerService(db)
    return envelope(CustomerOut.model_validate(await service.create(payload)))


@router.get("/{customer_id}")
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("customer.view")),
) -> dict:
    service = CustomerService(db)
    return envelope(CustomerOut.model_validate(await service.get(customer_id)))


@router.patch("/{customer_id}")
async def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("customer.update")),
) -> dict:
    service = CustomerService(db)
    return envelope(CustomerOut.model_validate(await service.update(customer_id, payload)))


@router.delete("/{customer_id}")
async def delete_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("customer.delete")),
) -> dict:
    service = CustomerService(db)
    await service.delete(customer_id)
    return envelope({"message": "Customer deleted"})


@router.get("/{customer_id}/debts")
async def list_customer_debts(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("customer.view")),
) -> dict:
    service = CustomerService(db)
    debts = await service.list_debts(customer_id)
    rows = []
    for debt, sale_date in debts:
        row = CustomerDebtOut.model_validate(debt).model_dump(mode="json")
        row["date"] = sale_date
        row["sale_date"] = sale_date
        rows.append(row)
    return envelope(rows)


@router.get("/{customer_id}/purchase-history")
async def customer_purchase_history(
    customer_id: UUID,
    params: ListParams = Depends(list_params),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("customer.view")),
) -> dict:
    service = CustomerService(db)
    history, total = await service.purchase_history(
        customer_id, page=params.page, limit=params.limit
    )
    return envelope(history, {"page": params.page, "limit": params.limit, "total": total})


@router.get("/{customer_id}/payments")
async def list_customer_payments(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("customer.view")),
) -> dict:
    service = CustomerService(db)
    payments = await service.list_payments(customer_id)
    return envelope([PaymentOut.model_validate(p) for p in payments])


@router.post("/{customer_id}/payments", status_code=http_status.HTTP_201_CREATED)
async def pay_customer_open_debts(
    customer_id: UUID,
    payload: DebtPaymentRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("customer.debt.pay")),
) -> dict:
    """Settle a customer's open debts oldest-first (frontend fallback when no
    specific debt row is selected). Immutable payments, one transaction."""
    service = CustomerService(db)
    payments = await service.pay_open_debts(customer_id, payload, actor=actor)
    return envelope([PaymentOut.model_validate(p) for p in payments])


@router.get("/{customer_id}/debts/{debt_id}/payments")
async def list_customer_debt_payments(
    customer_id: UUID,
    debt_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("customer.view")),
) -> dict:
    service = CustomerService(db)
    payments = await service.list_debt_payments(customer_id, debt_id)
    return envelope([PaymentOut.model_validate(p) for p in payments])


@router.post("/{customer_id}/debts/{debt_id}/payments", status_code=http_status.HTTP_201_CREATED)
async def pay_customer_debt(
    customer_id: UUID,
    debt_id: UUID,
    payload: DebtPaymentRequest,
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("customer.debt.pay")),
) -> dict:
    service = CustomerService(db)
    payment = await service.pay_debt(customer_id, debt_id, payload, actor=actor)
    return envelope(PaymentOut.model_validate(payment))
