"""Report endpoints — spec section 2.1.10 (five approved reports, CSV export)."""

import csv
import io
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ListParams, envelope, get_db_session, list_params, require_permission
from app.modules.auth.models import User
from app.modules.reports.schemas import (
    CustomerDebtReportRow,
    ExpenseCreate,
    ExpenseOut,
    FinanceEntryRow,
    FinanceReportOut,
    PurchaseReportRow,
    SalesReportRow,
    SupplierDebtReportRow,
)
from app.modules.reports.service import ReportsService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/sales")
async def sales_report(
    params: ListParams = Depends(list_params),
    customer_id: UUID | None = Query(default=None),
    product_id: UUID | None = Query(default=None),
    category_id: UUID | None = Query(default=None),
    cashier_id: UUID | None = Query(default=None),
    payment_method: str | None = Query(default=None, pattern="^(CASH|BANK_QR|CUSTOMER_DEBT)$"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.sales")),
) -> dict:
    service = ReportsService(db)
    rows, total = await service.sales_report(
        q=params.q,
        customer_id=customer_id,
        product_id=product_id,
        category_id=category_id,
        cashier_id=cashier_id,
        payment_method=payment_method,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    return envelope(
        [SalesReportRow.model_validate(row) for row in rows],
        {"page": params.page, "limit": params.limit, "total": total},
    )


# `/purchase` and `/purchases` serve the same Purchase Report (frontend uses
# the plural path; spec section 7 documents the singular one).
@router.get("/purchase")
@router.get("/purchases")
async def purchase_report(
    params: ListParams = Depends(list_params),
    supplier_id: UUID | None = Query(default=None),
    product_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.purchase")),
) -> dict:
    service = ReportsService(db)
    rows, total = await service.purchase_report(
        q=params.q,
        supplier_id=supplier_id,
        product_id=product_id,
        status=status,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    return envelope(
        [PurchaseReportRow.model_validate(row) for row in rows],
        {"page": params.page, "limit": params.limit, "total": total},
    )


@router.get("/customer-debts")
async def customer_debt_report(
    params: ListParams = Depends(list_params),
    customer_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(UNPAID|PARTIAL|PAID)$"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.customer_debt")),
) -> dict:
    service = ReportsService(db)
    rows, total = await service.customer_debt_report(
        q=params.q,
        customer_id=customer_id,
        status=status,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    return envelope(
        [CustomerDebtReportRow.model_validate(row) for row in rows],
        {"page": params.page, "limit": params.limit, "total": total},
    )


@router.get("/supplier-debts")
async def supplier_debt_report(
    params: ListParams = Depends(list_params),
    supplier_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(UNPAID|PARTIAL|PAID)$"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.supplier_debt")),
) -> dict:
    service = ReportsService(db)
    rows, total = await service.supplier_debt_report(
        q=params.q,
        supplier_id=supplier_id,
        status=status,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    return envelope(
        [SupplierDebtReportRow.model_validate(row) for row in rows],
        {"page": params.page, "limit": params.limit, "total": total},
    )


@router.get("/finance")
async def finance_report(
    start_date: date | None = Query(default=None, alias="startDate"),
    end_date: date | None = Query(default=None, alias="endDate"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.finance")),
) -> dict:
    """Finance summary cards (Income, Expense, Net Result, debts, losses)."""
    service = ReportsService(db)
    data = await service.finance_report(start=start_date, end=end_date)
    return envelope(FinanceReportOut.model_validate(data))


@router.get("/finance/summary")
async def finance_summary(
    start_date: date | None = Query(default=None, alias="startDate"),
    end_date: date | None = Query(default=None, alias="endDate"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.finance")),
) -> dict:
    """Alias of GET /reports/finance — the endpoint the frontend calls."""
    return await finance_report(
        start_date=start_date,
        end_date=end_date,
        db=db,
        actor=actor,
    )


@router.get("/finance/entries")
async def finance_entries(
    params: ListParams = Depends(list_params),
    type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.finance")),
) -> dict:
    """Combined income/expense ledger table (income derived from POS sales)."""
    normalized_type = (type or "").strip().upper() or None
    if normalized_type not in (None, "INCOME", "EXPENSE"):
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="type must be INCOME or EXPENSE")
    service = ReportsService(db)
    rows, total = await service.finance_entries(
        q=params.q,
        entry_type=normalized_type,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    return envelope(
        [FinanceEntryRow.model_validate(row) for row in rows],
        {"page": params.page, "limit": params.limit, "total": total},
    )


@router.post("/finance/expenses", status_code=201)
async def create_expense(
    payload: ExpenseCreate,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission("report.finance")),
    actor: User = Depends(require_permission("expense.create")),
) -> dict:
    """Record an operating expense (Finance Report only — no Expense page)."""
    service = ReportsService(db)
    expense = await service.create_expense(payload=payload, actor=actor)
    return envelope(ExpenseOut.model_validate(expense))


# ------------------------------------------------------------------- exports


def _csv_response(filename: str, header: list[str], rows: list[list]) -> StreamingResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sales/export")
async def sales_report_export(
    params: ListParams = Depends(list_params),
    customer_id: UUID | None = Query(default=None),
    product_id: UUID | None = Query(default=None),
    category_id: UUID | None = Query(default=None),
    cashier_id: UUID | None = Query(default=None),
    payment_method: str | None = Query(default=None, pattern="^(CASH|BANK_QR|CUSTOMER_DEBT)$"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.sales")),
):
    service = ReportsService(db)
    rows = await service.sales_report_export(
        q=params.q,
        customer_id=customer_id,
        product_id=product_id,
        category_id=category_id,
        cashier_id=cashier_id,
        payment_method=payment_method,
        start=params.start_date,
        end=params.end_date,
    )
    return _csv_response(
        "sales-report.csv",
        [
            "Date", "Invoice No.", "Customer", "Product", "Quantity", "Selling Price",
            "Discount", "Sales Amount", "Return Amount", "Cost", "Gross Profit",
            "Cashier", "Payment Method",
        ],
        [
            [
                str(row["sale_date"]), row["invoice_no"], row["customer_name"] or "", row["product_name"],
                str(row["quantity"]), str(row["selling_price"]), str(row["discount_amount"]),
                str(row["sales_amount"]), str(row["return_amount"]), str(row["cost"]),
                str(row["gross_profit"]), row["cashier_name"] or "", row["payment_method"],
            ]
            for row in rows
        ],
    )


@router.get("/purchase/export")
@router.get("/purchases/export")
async def purchase_report_export(
    params: ListParams = Depends(list_params),
    supplier_id: UUID | None = Query(default=None),
    product_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.purchase")),
):
    service = ReportsService(db)
    rows, _ = await service.purchase_report(
        q=params.q,
        supplier_id=supplier_id,
        product_id=product_id,
        status=status,
        start=params.start_date,
        end=params.end_date,
        page=1,
        limit=100000,
    )
    return _csv_response(
        "purchase-report.csv",
        [
            "Stock In / Purchase No.", "Date", "Supplier", "Product", "Quantity",
            "Cost Price", "Total Cost", "Paid", "Remaining Supplier Debt", "Status",
        ],
        [
            [
                row["document_no"], str(row["transaction_date"]), row["supplier_name"] or "",
                row["product_name"], str(row["quantity"]), str(row["cost_price"]),
                str(row["total_cost"]), str(row["paid_amount"]), str(row["remaining_debt"]),
                row["status"],
            ]
            for row in rows
        ],
    )


@router.get("/customer-debts/export")
async def customer_debt_report_export(
    params: ListParams = Depends(list_params),
    customer_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(UNPAID|PARTIAL|PAID)$"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.customer_debt")),
):
    service = ReportsService(db)
    rows, _ = await service.customer_debt_report(
        q=params.q,
        customer_id=customer_id,
        status=status,
        start=params.start_date,
        end=params.end_date,
        page=1,
        limit=100000,
    )
    return _csv_response(
        "customer-debt-report.csv",
        [
            "Date", "Customer", "Invoice No.", "Invoice Total", "Paid Amount",
            "Remaining Amount", "Due Date", "Status",
        ],
        [
            [
                str(row["date"]), row["customer_name"], row["invoice_no"], str(row["invoice_total"]),
                str(row["paid_amount"]), str(row["remaining_amount"]),
                str(row["due_date"] or ""), row["status"],
            ]
            for row in rows
        ],
    )


@router.get("/supplier-debts/export")
async def supplier_debt_report_export(
    params: ListParams = Depends(list_params),
    supplier_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(UNPAID|PARTIAL|PAID)$"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.supplier_debt")),
):
    service = ReportsService(db)
    rows, _ = await service.supplier_debt_report(
        q=params.q,
        supplier_id=supplier_id,
        status=status,
        start=params.start_date,
        end=params.end_date,
        page=1,
        limit=100000,
    )
    return _csv_response(
        "supplier-debt-report.csv",
        [
            "Date", "Supplier", "Stock In / Purchase No.", "Total Amount", "Paid Amount",
            "Remaining Amount", "Due Date", "Status",
        ],
        [
            [
                str(row["date"]), row["supplier_name"], row["document_no"], str(row["total_amount"]),
                str(row["paid_amount"]), str(row["remaining_amount"]),
                str(row["due_date"] or ""), row["status"],
            ]
            for row in rows
        ],
    )
