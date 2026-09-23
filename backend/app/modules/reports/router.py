"""Report endpoints — spec section 2.1.10 (five approved reports, CSV export)."""

import csv
import io
from collections.abc import Iterable, Iterator
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ListParams, envelope, get_db_session, list_params, require_permission
from app.modules.auth.models import User
from app.modules.reports.schemas import (
    ExpenseUpdate,
    ExpenseVoidRequest,
    CustomerDebtReportRow,
    ExpenseCreate,
    ExpenseOut,
    FinanceEntryRow,
    FinanceReportOut,
    PurchaseReportRow,
    PurchaseReturnRow,
    SalesReportRow,
    SaleReturnRow,
    SupplierDebtReportRow,
)
from app.modules.reports.service import EXPORT_ROW_LIMIT, ReportsService

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
    # Optional document-currency filter (USD | KHR); rows are never mixed.
    currency: str | None = Query(default=None, pattern="^(USD|KHR)$"),
    # Optional staff filter: the cashier who created the source sale.
    user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.customer_debt")),
) -> dict:
    service = ReportsService(db)
    rows, total = await service.customer_debt_report(
        q=params.q,
        customer_id=customer_id,
        status=status,
        currency=currency,
        user_id=user_id,
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
    # Optional document-currency filter (USD | KHR); rows are never mixed.
    currency: str | None = Query(default=None, pattern="^(USD|KHR)$"),
    # Optional staff filter: the user who created the source Stock In.
    user_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.supplier_debt")),
) -> dict:
    service = ReportsService(db)
    rows, total = await service.supplier_debt_report(
        q=params.q,
        supplier_id=supplier_id,
        status=status,
        currency=currency,
        user_id=user_id,
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


@router.patch("/finance/expenses/{expense_id}")
async def update_expense(
    expense_id: UUID,
    payload: ExpenseUpdate,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission("report.finance")),
    actor: User = Depends(require_permission("expense.create")),
) -> dict:
    """Edit a DRAFT expense (posted expenses are immutable)."""
    expense = await ReportsService(db).update_expense(expense_id, payload, actor=actor)
    return envelope(ExpenseOut.model_validate(expense))


@router.post("/finance/expenses/{expense_id}/post")
async def post_expense(
    expense_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission("report.finance")),
    actor: User = Depends(require_permission("expense.approve")),
) -> dict:
    """Approve/post a draft expense so it affects reports and cash flow."""
    expense = await ReportsService(db).post_expense(expense_id, actor=actor)
    return envelope(ExpenseOut.model_validate(expense))


@router.post("/finance/expenses/{expense_id}/void")
async def void_expense(
    expense_id: UUID,
    payload: ExpenseVoidRequest,
    db: AsyncSession = Depends(get_db_session),
    _: User = Depends(require_permission("report.finance")),
    actor: User = Depends(require_permission("expense.void")),
) -> dict:
    """Void an expense (immutable history; corrections use void + replacement)."""
    expense = await ReportsService(db).void_expense(expense_id, payload.reason, actor=actor)
    return envelope(ExpenseOut.model_validate(expense))


# ------------------------------------------------------------------- exports


def _csv_response(filename: str, header: list[str], rows: Iterable[list]) -> StreamingResponse:
    """Stream CSV in chunks: the body is never fully buffered in memory (P4)."""
    chunk_rows = 500

    def generate() -> Iterator[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        count = 0
        for row in rows:
            writer.writerow(row)
            count += 1
            if count % chunk_rows == 0:
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)
        if buffer.tell():
            yield buffer.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/sale-returns")
async def sale_returns_report(
    params: ListParams = Depends(list_params),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.sales")),
) -> dict:
    """Customer-return history (immutable sale_returns documents)."""
    service = ReportsService(db)
    rows, total = await service.sale_returns_report(
        q=params.q,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    return envelope(
        [SaleReturnRow.model_validate(row) for row in rows],
        {"page": params.page, "limit": params.limit, "total": total},
    )


@router.get("/purchase-returns")
async def purchase_returns_report(
    params: ListParams = Depends(list_params),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.purchase")),
) -> dict:
    """Supplier-return history (immutable purchase_returns documents)."""
    service = ReportsService(db)
    rows, total = await service.purchase_returns_report(
        q=params.q,
        start=params.start_date,
        end=params.end_date,
        page=params.page,
        limit=params.limit,
    )
    return envelope(
        [PurchaseReturnRow.model_validate(row) for row in rows],
        {"page": params.page, "limit": params.limit, "total": total},
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
        limit=EXPORT_ROW_LIMIT,
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
    currency: str | None = Query(default=None, pattern="^(USD|KHR)$"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.customer_debt")),
):
    service = ReportsService(db)
    rows, _ = await service.customer_debt_report(
        q=params.q,
        customer_id=customer_id,
        status=status,
        currency=currency,
        start=params.start_date,
        end=params.end_date,
        page=1,
        limit=EXPORT_ROW_LIMIT,
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
    currency: str | None = Query(default=None, pattern="^(USD|KHR)$"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.supplier_debt")),
):
    service = ReportsService(db)
    rows, _ = await service.supplier_debt_report(
        q=params.q,
        supplier_id=supplier_id,
        status=status,
        currency=currency,
        start=params.start_date,
        end=params.end_date,
        page=1,
        limit=EXPORT_ROW_LIMIT,
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


# ------------------------------------------------ valuation / reconciliation


@router.get("/inventory-valuation")
async def inventory_valuation(
    as_of: date | None = Query(default=None, alias="asOf"),
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.stock_valuation")),
) -> dict:
    """Batch-level inventory valuation (optionally as of a date)."""
    return envelope(await ReportsService(db).inventory_valuation(as_of=as_of))


@router.get("/stock-reconciliation")
async def stock_reconciliation(
    db: AsyncSession = Depends(get_db_session),
    actor: User = Depends(require_permission("report.stock_valuation")),
) -> dict:
    """Reconcile stock balances vs batch remaining vs the movement ledger."""
    return envelope(await ReportsService(db).stock_reconciliation())


