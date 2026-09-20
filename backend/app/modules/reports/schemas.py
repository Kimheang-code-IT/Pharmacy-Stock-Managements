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
    # Legacy internal code: nullable since 0021 (barcode is operational).
    sku: str | None = None
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
    # Legacy internal code: nullable since 0021 (barcode is operational).
    sku: str | None = None
    quantity: Decimal
    returned_quantity: Decimal = Decimal("0")
    returnable_quantity: Decimal = Decimal("0")
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


class FinanceReportOut(BaseModel):
    """Finance summary cards (spec 2.1.10). Net Result includes operating
    expenses recorded via Add Expense on the Finance Report.

    `income/expense/net/outstanding` are aliases the frontend financeSummary
    mapper reads; they match the canonical cards exactly.
    """

    period_start: date
    period_end: date
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
    net_result: Decimal

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
