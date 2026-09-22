from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

PAYMENT_METHODS = {"CASH", "BANK_QR", "CUSTOMER_DEBT"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------- search


class UomConversionOut(BaseModel):
    """One product Pricing row (spec 4.2 / §2.1.3 products.uom_conversions).

    Original UOM (`uom_id`) is the POS-selectable sell unit; Convert UOM is
    usually the product base UOM; exactly one row is the default sale.
    """

    uom_id: UUID
    uom_symbol: str | None = None
    convert_uom_id: UUID | None = None
    convert_uom_symbol: str | None = None
    factor_to_base: Decimal
    cost_price: Decimal | None = None
    sale_price: Decimal | None = None
    is_default_sale: bool = False
    # POS-active flag of the Pricing row (inactive rows are not offered).
    is_active: bool = True


class POSProductOut(BaseModel):
    id: UUID
    sku: str | None
    barcode: str
    name: str
    category_id: UUID | None
    category_name: str | None = None
    selling_price: Decimal
    quantity: Decimal = Decimal("0")
    # Sellable stock = sum of active, unexpired lots (spec: POS product card).
    sellable_stock: Decimal = Decimal("0")
    sellableStock: Decimal = Decimal("0")
    # FEFO-first lot and whether a sale price exists for the base UOM.
    next_batch_no: str | None = None
    nextBatchNo: str | None = None
    price_configured: bool = True
    priceConfigured: bool = True
    image_object_key: str | None
    image_url: str | None = None
    uom_id: UUID | None = None
    uom_symbol: str | None = None
    # Convert-UOM rows offered on POS plus the base UOM row.
    uom_conversions: list[UomConversionOut] = Field(default_factory=list)
    uomConversions: list[UomConversionOut] = Field(default_factory=list)
    status: str


# --------------------------------------------------------------------- sale


class BatchAllocationRequest(BaseModel):
    """Optional client batch-allocation hint (spec 5.10). The server NEVER
    trusts it: FEFO allocation and per-batch pricing are recomputed
    authoritatively at checkout; the field is accepted so clients can send the
    allocation they displayed and is validated for shape only."""

    model_config = ConfigDict(populate_by_name=True)

    batch_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("batch_id", "batchId"),
    )
    batch_no: str | None = Field(
        default=None,
        max_length=100,
        validation_alias=AliasChoices("batch_no", "batchNo"),
    )
    qty: Decimal = Field(gt=0)
    unit_price: Decimal | None = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices("unit_price", "unitPrice"),
    )


class SaleItemRequest(BaseModel):
    """One POS cart line (snake_case and camelCase accepted).

    Stock is always mutated in the base UOM: base_qty = quantity ×
    factor_to_base. unit_price defaults to the product's POS-active sale
    price (products.selling_price) for the base UOM, or the conversion row's
    sale_price for a convert UOM.
    """

    model_config = ConfigDict(populate_by_name=True)

    product_id: UUID = Field(validation_alias=AliasChoices("product_id", "productId"))
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal | None = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices("unit_price", "unitPrice"),
    )
    discount_percent: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        le=100,
        validation_alias=AliasChoices("discount_percent", "discountPercent"),
    )
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    uom_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("uom_id", "uomId"),
    )
    uom_symbol: str | None = Field(
        default=None,
        max_length=20,
        validation_alias=AliasChoices("uom_symbol", "uomSymbol"),
    )
    factor_to_base: Decimal = Field(
        default=Decimal("1"),
        gt=0,
        validation_alias=AliasChoices("factor_to_base", "factorToBase"),
    )
    # Server recomputes FEFO allocation + per-batch pricing; accepted for
    # client/server agreement and validated for shape only.
    allocations: list[BatchAllocationRequest] = Field(default_factory=list)


class SaleCreateRequest(BaseModel):
    """PosCompleteSaleInput — camelCase keys from the frontend, snake_case
    accepted too.

    `amount_received` / paidAmount is payment for THIS sale only (grand_total =
    subtotal − discount + delivery). `deposit` is the separate budget applied
    to selected prior customer debts via included_debt_ids and never inflates
    the current sale total.

    Canonical payment methods: CASH | BANK_QR | CUSTOMER_DEBT. The UI's
    display labels map one-to-one: Cash→CASH, Card / Mobile Payment /
    Bank Transfer→BANK_QR (cashless tender), Credit→CUSTOMER_DEBT."""

    model_config = ConfigDict(populate_by_name=True)

    customer_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("customer_id", "customerId"),
    )
    sale_date: datetime | None = None
    payment_method: str = Field(
        default="CASH",
        validation_alias=AliasChoices("payment_method", "paymentMethod"),
    )
    amount_received: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        validation_alias=AliasChoices("amount_received", "paidAmount", "paid_amount"),
    )
    # Header discount on the sale lines (currency amount).
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    delivery_price: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        validation_alias=AliasChoices("delivery_price", "deliveryPrice"),
    )
    # Open customer-debt rows settled in this transaction from `deposit`
    # (separate from amount_received / current-sale payment).
    included_debt_ids: list[UUID] = Field(
        default_factory=list,
        validation_alias=AliasChoices("included_debt_ids", "includedDebtIds"),
    )
    # Budget for settling included prior debts (not part of sale grand_total).
    deposit: Decimal = Field(default=Decimal("0"), ge=0)
    deposit_method: str | None = Field(default=None, pattern="^(CASH|BANK_QR)$")
    reference_no: str | None = Field(default=None, max_length=100)
    note: str | None = None
    due_date: date | None = Field(
        default=None,
        validation_alias=AliasChoices("due_date", "dueDate"),
    )
    # Document currency: every amount on this sale (lines, discount, delivery,
    # paid, debt) is in THIS currency. exchange_rate = KHR per 1 USD.
    currency: str = Field(default="USD", pattern="^(USD|KHR)$")
    exchange_rate: Decimal = Field(
        default=Decimal("1"),
        gt=0,
        validation_alias=AliasChoices("exchange_rate", "exchangeRate"),
    )
    items: list[SaleItemRequest] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_request(self):
        if self.payment_method not in PAYMENT_METHODS:
            raise ValueError("payment_method must be CASH, BANK_QR or CUSTOMER_DEBT")
        if self.payment_method == "CUSTOMER_DEBT" and self.deposit_method is None:
            self.deposit_method = "CASH"
        # A tender of 0 is allowed for every method: it means the whole sale is
        # unpaid and becomes customer debt. The service still rejects a debt
        # sale to the walk-in customer when amount_received is short.
        return self


class SaleUpdateRequest(BaseModel):
    """PATCH /pos/sales/{id} — edit a completed sale (no returns).

    Items/quantities/prices/discounts/delivery are re-applied; the original
    stock is reversed (restored to its batches) before the new lines are
    applied. The customer and any recorded payments stay untouched — the
    outstanding customer debt is recalculated from the new grand total.
    """

    model_config = ConfigDict(populate_by_name=True)

    sale_date: datetime | None = None
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    delivery_price: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        validation_alias=AliasChoices("delivery_price", "deliveryPrice"),
    )
    note: str | None = None
    currency: str = Field(default="USD", pattern="^(USD|KHR)$")
    exchange_rate: Decimal = Field(
        default=Decimal("1"),
        gt=0,
        validation_alias=AliasChoices("exchange_rate", "exchangeRate"),
    )
    items: list[SaleItemRequest] = Field(min_length=1)


class SaleItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # Null when the product was hard-deleted (sale_items.product_id is SET NULL).
    product_id: UUID | None = None
    product_name: str
    sku: str | None
    barcode: str | None
    uom_id: UUID | None = None
    uom_code: str | None = None
    uom_symbol: str | None = None
    factor_to_base: Decimal = Decimal("1")
    quantity: Decimal
    unit_price: Decimal
    unit_cost: Decimal
    discount_percent: Decimal = Decimal("0")
    discount_amount: Decimal
    line_total: Decimal
    returned_quantity: Decimal


class SaleOut(BaseModel):
    id: UUID
    invoice_no: str
    customer_id: UUID
    customer_name: str | None = None
    sale_date: datetime
    subtotal: Decimal
    discount_amount: Decimal
    delivery_price: Decimal = Decimal("0")
    deliveryPrice: Decimal = Decimal("0")
    grand_total: Decimal
    paid_amount: Decimal
    debt_amount: Decimal
    payment_status: str
    sale_status: str
    cashier_id: UUID
    note: str | None
    change_amount: Decimal = Decimal("0")
    currency: str = "USD"
    exchange_rate: Decimal = Decimal("1")
    items: list[SaleItemOut]


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_no: str
    payment_type: str
    payment_method: str
    amount: Decimal
    reference_no: str | None
    customer_debt_id: UUID | None = None
    supplier_debt_id: UUID | None = None
    note: str | None = None
    created_at: datetime


# ------------------------------------------------------------------- return


class SaleReturnItemRequest(BaseModel):
    """One return line; camelCase keys accepted (UI adapter contract)."""

    model_config = ConfigDict(populate_by_name=True)

    sale_item_id: UUID = Field(validation_alias=AliasChoices("sale_item_id", "saleItemId"))
    quantity: Decimal = Field(gt=0)
    restock: bool = True


class SaleReturnRequest(BaseModel):
    """POST /pos/sales/{id}/return body. `items` is canonical; `lines` is an
    accepted alias so both API dialects work (spec 2.1.7)."""

    reason: str = Field(min_length=1, max_length=1000)
    items: list[SaleReturnItemRequest] = Field(
        min_length=1, validation_alias=AliasChoices("items", "lines")
    )
    return_date: datetime | None = None


class SaleReturnItemOut(BaseModel):
    id: UUID
    sale_item_id: UUID
    # Null when the product was hard-deleted (sale_return_items.product_id is SET NULL).
    product_id: UUID | None = None
    product_name: str | None = None
    quantity: Decimal
    refund_amount: Decimal
    restock: bool


class SaleReturnOut(BaseModel):
    id: UUID
    return_no: str
    sale_id: UUID
    invoice_no: str | None = None
    return_date: datetime
    refund_amount: Decimal
    reason: str
    items: list[SaleReturnItemOut]


# -------------------------------------------------------------------- debts


class DebtPaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    payment_method: str = Field(pattern="^(CASH|BANK_QR)$")
    reference_no: str | None = Field(default=None, max_length=100)
    note: str | None = None


class CustomerDebtOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    sale_id: UUID
    invoice_no: str
    original_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    due_date: date | None
    status: str
    currency: str = "USD"
    exchange_rate: Decimal = Decimal("1")
    created_at: datetime
