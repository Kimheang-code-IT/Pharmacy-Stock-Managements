"""Report row schemas — spec section 2.1.10."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field


class SalesReportRow(BaseModel):
    sale_id: UUID
    sale_item_id: UUID | None = None
    product_id: UUID | None = None
    sale_date: datetime
    invoice_no: str
    customer_name: str | None
    product_name: str
    quantity: Decimal
    returned_quantity: Decimal = Decimal("0")
    returnable_quantity: Decimal = Decimal("0")
    selling_price: Decimal
    # Line discount (this sold line only).
    discount_amount: Decimal
    sales_amount: Decimal
    return_amount: Decimal
    net_quantity: Decimal
    cost: Decimal
    gross_profit: Decimal
    # Header debt of the parent sale (repeated per line for grouping).
    debt_amount: Decimal = Decimal("0")
    cashier_name: str | None
    payment_method: str
    # Document currency snapshot (reprints / grouped rows keep the stored rate).
    currency: str = "USD"
    exchange_rate: Decimal = Decimal("1")
    # Saved sale header (authoritative checkout values, repeated per line so the
    # SPA groups without recomputing from current product prices).
    subtotal: Decimal = Decimal("0")
    # Sale-level discount total (line + header) = sales.discount_amount.
    sale_discount: Decimal = Decimal("0")
    delivery_price: Decimal = Decimal("0")
    grand_total: Decimal = Decimal("0")
    paid_amount: Decimal = Decimal("0")
    payment_status: str | None = None
    note: str | None = None
    due_date: date | None = None


class PurchaseReportRow(BaseModel):
    transaction_id: UUID
    stock_transaction_item_id: UUID | None = None
    product_id: UUID | None = None
    document_no: str
    transaction_date: datetime
    supplier_name: str | None
    product_name: str
    quantity: Decimal
    returned_quantity: Decimal = Decimal("0")
    returnable_quantity: Decimal = Decimal("0")
    # Quantity still physically in stock for this line's lot.
    available_quantity: Decimal = Decimal("0")
    return_amount: Decimal = Decimal("0")
    cost_price: Decimal
    total_cost: Decimal
    # Batch traceability: the lot/expiry the line was received into (reloaded
    # by the purchase Edit form so the original lot is shown again).
    batch_no: str | None = None
    expiry_date: date | None = None
    paid_amount: Decimal
    remaining_debt: Decimal
    status: str
    # Document currency + saved rate (returns keep the stored snapshot).
    currency: str = "USD"
    exchange_rate: Decimal = Decimal("1")
    # Header fields the purchase Edit form reloads (repeated per line; the SPA
    # groups rows client-side).
    note: str | None = None
    discount_amount: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    # Tender recorded for the stock-in (earliest purchase/supplier-debt payment).
    payment_method: str | None = None


class CustomerDebtReportRow(BaseModel):
    debt_id: UUID
    customer_id: UUID
    customer_name: str
    customer_code: str
    date: datetime
    invoice_no: str
    invoice_total: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    due_date: date | None
    status: str
    currency: str = "USD"
    exchange_rate: Decimal = Decimal("1")
    # Staff (cashier) who created the source sale — export/report user filter.
    user_id: UUID | None = None
    user_name: str | None = None
    created_at: datetime


class SupplierDebtReportRow(BaseModel):
    debt_id: UUID
    supplier_id: UUID
    supplier_name: str
    supplier_code: str
    date: datetime
    document_no: str
    total_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    due_date: date | None
    status: str
    currency: str = "USD"
    exchange_rate: Decimal = Decimal("1")
    # Staff who created the source Stock In — export/report user filter.
    user_id: UUID | None = None
    user_name: str | None = None
    created_at: datetime


class ProfitAndLossOut(BaseModel):
    """Accrual/accounting view. COGS already recognizes inventory cost, so
    supplier payments never appear here (spec: no double counting)."""

    gross_sales: Decimal
    sale_returns: Decimal
    net_sales: Decimal
    cost_of_goods_sold: Decimal
    gross_profit: Decimal
    operating_expenses: Decimal
    stock_damage_loss: Decimal
    stock_expire_loss: Decimal
    operating_profit: Decimal


class CashFlowOut(BaseModel):
    """Cash-basis view: only money that actually moved. Unpaid credit sales are
    not inflow; unpaid purchases are not outflow."""

    sale_receipts: Decimal = Decimal("0")
    debt_collections: Decimal = Decimal("0")
    supplier_refunds_received: Decimal = Decimal("0")
    total_inflow: Decimal = Decimal("0")
    supplier_payments: Decimal = Decimal("0")
    customer_refunds_paid: Decimal = Decimal("0")
    operating_expenses: Decimal = Decimal("0")
    total_outflow: Decimal = Decimal("0")
    net_cash_flow: Decimal = Decimal("0")


class FinanceReportOut(BaseModel):
    """Finance summary cards (spec 2.1.10), split into two unambiguous views:
    `profit_and_loss` (accounting) and `cash_flow` (cash basis).

    `income/expense/net/outstanding` are aliases the frontend financeSummary
    mapper reads; `net_result` is the P&L operating profit (supplier payments
    do NOT reduce it).
    """

    period_start: date
    period_end: date
    report_currency: str = "USD"
    total_sales: Decimal
    total_expense: Decimal
    total_purchase_cost: Decimal
    total_customer_debt: Decimal
    total_supplier_debt: Decimal
    cost_of_goods_sold: Decimal
    stock_damage_loss: Decimal
    stock_expire_loss: Decimal
    gross_profit: Decimal
    operating_expenses: Decimal
    # Cash paid to suppliers in the period (purchase payments + debt repayments).
    supplier_payments: Decimal = Decimal("0")
    # P&L operating profit: gross profit - losses - operating expenses.
    net_result: Decimal
    profit_and_loss: ProfitAndLossOut | None = None
    cash_flow: CashFlowOut | None = None

    @computed_field
    @property
    def income(self) -> Decimal:
        return self.total_sales

    @computed_field
    @property
    def expense(self) -> Decimal:
        return self.total_expense

    @computed_field
    @property
    def net(self) -> Decimal:
        return self.net_result

    @computed_field
    @property
    def outstanding(self) -> Decimal:
        return self.total_customer_debt + self.total_supplier_debt


class ExpenseCreate(BaseModel):
    """Add Expense payload — allowed on the Finance Report only."""

    date: date
    category: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    reference: str | None = Field(default=None, max_length=100)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    payment_method: Literal["CASH", "BANK_QR", "CARD", "OTHER"] | None = Field(
        default=None,
        validation_alias=AliasChoices("payment_method", "paymentMethod"),
    )
    # Document currency: amount is in THIS currency. exchange_rate = KHR per
    # 1 USD (1 for USD documents); the Finance summary normalizes via it.
    currency: str = Field(default="USD", pattern="^(USD|KHR)$")
    exchange_rate: Decimal = Field(
        default=Decimal("1"),
        gt=0,
        validation_alias=AliasChoices("exchange_rate", "exchangeRate"),
    )
    # Lifecycle: POSTED affects reports/cash flow; DRAFT does not. Default
    # POSTED keeps the historical "recorded expense" behavior.
    status: Literal["DRAFT", "POSTED"] = "POSTED"
    posting_date: date | None = Field(
        default=None,
        validation_alias=AliasChoices("posting_date", "postingDate"),
    )
    attachment_object_key: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("attachment_object_key", "attachmentObjectKey", "attachment"),
    )


class ExpenseUpdate(BaseModel):
    """PATCH a DRAFT expense only (posted expenses are immutable)."""

    model_config = ConfigDict(populate_by_name=True)

    expense_date: date | None = Field(
        default=None,
        validation_alias=AliasChoices("date", "expense_date", "expenseDate"),
    )
    category: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    reference: str | None = Field(default=None, max_length=100)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    payment_method: str | None = None
    currency: str | None = Field(default=None, pattern="^(USD|KHR)$")
    exchange_rate: Decimal | None = Field(default=None, gt=0)
    attachment_object_key: str | None = Field(default=None, max_length=500)


class ExpenseVoidRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reason: str = Field(min_length=1, max_length=2000)


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    expense_date: date
    category: str
    description: str | None
    amount: Decimal
    payment_method: str | None
    currency: str = "USD"
    exchange_rate: Decimal = Decimal("1")
    status: str = "POSTED"
    posting_date: date | None = None
    approved_by: UUID | None = None
    approved_at: datetime | None = None
    void_reason: str | None = None
    voided_by: UUID | None = None
    voided_at: datetime | None = None
    attachment_object_key: str | None = None
    created_by: UUID | None = None
    created_by_name: str | None = None
    created_at: datetime


class FinanceEntryRow(BaseModel):
    """One combined income/expense ledger row of the Finance table.

    `type` is lowercase income/expense for the HTTP mapper; `category`,
    `paymentMethod` and `user` are the camelCase keys the mapper reads.
    """

    id: UUID
    date: datetime
    type: Literal["income", "expense"]
    reference: str
    category: str | None = None
    description: str | None
    amount: Decimal
    payment_method: str | None = None
    paymentMethod: str | None = None
    currency: str = "USD"
    exchange_rate: Decimal = Decimal("1")
    created_by_name: str | None = None
    user: str | None = None
    created_at: datetime


class SaleReturnRow(BaseModel):
    """One customer-return document (sale_returns) for the returns history."""

    return_id: UUID
    return_no: str
    sale_id: UUID
    sale_no: str
    return_date: datetime
    customer_name: str | None
    item_count: int
    refund_amount: Decimal
    restocked_quantity: Decimal = Decimal("0")
    reason: str
    user_name: str | None


class PurchaseReturnRow(BaseModel):
    """One supplier-return document (purchase_returns) for the returns history."""

    return_id: UUID
    return_no: str
    stock_transaction_id: UUID
    document_no: str
    return_date: datetime
    supplier_name: str | None
    item_count: int
    refund_amount: Decimal
    debt_reduction: Decimal = Decimal("0")
    credit_amount: Decimal = Decimal("0")
    reason: str
    user_name: str | None
