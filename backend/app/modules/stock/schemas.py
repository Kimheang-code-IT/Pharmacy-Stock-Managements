from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class ProductCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Legacy internal code: optional. Barcode is the operational identifier.
    sku: str | None = Field(default=None, max_length=100)
    barcode: str | None = Field(
        default=None,
        max_length=100,
        description="Operational product identifier. Auto-issued when omitted.",
    )
    name: str = Field(min_length=1, max_length=200)
    category_id: UUID
    uom_id: UUID
    brand_id: UUID | None = None
    supplier_id: UUID | None = Field(
        default=None, validation_alias=AliasChoices("supplier_id", "supplierId")
    )
    cost_price: Decimal = Field(default=Decimal("0.00"), ge=0)
    # Optional on create: the SPA can create the product from the General tab
    # alone (the Pricing tab appears once the product is opened) and set the
    # sale price on its Pricing tab afterwards.
    selling_price: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        validation_alias=AliasChoices("selling_price", "salePrice"),
    )
    # Pricing rows (spec 4.2 / §2.1.3 products); validated by the service.
    uom_conversions: list[dict] | None = Field(
        default=None,
        validation_alias=AliasChoices("uom_conversions", "uomConversions"),
    )
    minimum_stock: Decimal = Field(default=Decimal("0"), ge=0)
    expiry_tracking: bool = False
    # Batch/lot tracking (spec: batch management): Stock In lines MUST carry
    # a batch_no when enabled.
    track_batch: bool = False
    # FIFO costing option (see Product.fifo).
    fifo: bool = False
    image_object_key: str | None = Field(default=None, max_length=500)
    status: str = Field(default="ACTIVE", pattern="^(ACTIVE|INACTIVE)$")
    note: str | None = None

    @field_validator("sku", "barcode", "name")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

class ProductUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sku: str | None = Field(default=None, max_length=100)
    barcode: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: UUID | None = None
    uom_id: UUID | None = None
    brand_id: UUID | None = None
    supplier_id: UUID | None = Field(
        default=None, validation_alias=AliasChoices("supplier_id", "supplierId")
    )
    cost_price: Decimal | None = Field(default=None, ge=0)
    # The UI sends salePrice; changing it adds + activates a new price version.
    selling_price: Decimal | None = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices("selling_price", "salePrice"),
    )
    uom_conversions: list[dict] | None = Field(
        default=None,
        validation_alias=AliasChoices("uom_conversions", "uomConversions"),
    )
    minimum_stock: Decimal | None = Field(default=None, ge=0)
    expiry_tracking: bool | None = None
    track_batch: bool | None = None
    fifo: bool | None = None
    image_object_key: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")
    note: str | None = None

    @field_validator("sku", "name")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


# ---------------------------------------------------------------- stock operations


class StockInItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: UUID
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)
    batch_no: str | None = Field(default=None, max_length=100)
    expiry_date: date | None = None
    # Pricing Original UOM (spec §2.1.3): qty/cost are per the SELECTED UOM and
    # are converted to the product base UOM before the stock mutation.
    uom_id: UUID | None = Field(
        default=None, validation_alias=AliasChoices("uom_id", "uomId")
    )
    # Line UOM symbol snapshot for lists/history/invoice display.
    uom_symbol: str | None = Field(
        default=None, max_length=20, validation_alias=AliasChoices("uom_symbol", "uomSymbol")
    )
    factor_to_base: Decimal | None = Field(
        default=None, gt=0, validation_alias=AliasChoices("factor_to_base", "factorToBase")
    )

class StockInRequest(BaseModel):
    """POST /stock/in — Stock In = purchase (spec 2.1.x).

    payment_method is the canonical POS tender vocabulary (CASH | BANK_QR);
    it labels the payment row recorded when paid_amount > 0."""

    model_config = ConfigDict(populate_by_name=True)

    supplier_id: UUID | None = Field(
        default=None, validation_alias=AliasChoices("supplier_id", "supplierId")
    )
    transaction_date: datetime | None = None
    reference_no: str | None = Field(default=None, max_length=100)
    note: str | None = None
    paid_amount: Decimal = Field(
        default=Decimal("0"), ge=0, validation_alias=AliasChoices("paid_amount", "paidAmount")
    )
    payment_method: str = Field(default="CASH", validation_alias=AliasChoices("payment_method", "paymentMethod"))
    # Document-level adjustments (purchase form footer): discount is
    # subtracted from the line subtotal, tax is added afterwards.
    discount_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        validation_alias=AliasChoices("discount_amount", "discountAmount"),
    )
    tax_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        validation_alias=AliasChoices("tax_amount", "taxAmount"),
    )
    # Document currency: every amount (lines, discount, tax, paid, debt) is
    # in THIS currency. exchange_rate = KHR per 1 USD (1 for USD documents).
    currency: str = Field(default="USD", pattern="^(USD|KHR)$")
    exchange_rate: Decimal = Field(
        default=Decimal("1"),
        gt=0,
        validation_alias=AliasChoices("exchange_rate", "exchangeRate"),
    )
    items: list[StockInItem] = Field(min_length=1, validation_alias=AliasChoices("items", "lines"))

class StockInUpdateRequest(BaseModel):
    """PATCH /stock/in/{id} — edit a confirmed Stock In (no purchase returns).

    The original received quantities are reversed (batch + compensating
    PURCHASE_RETURN movement) before the new lines are received. The supplier
    and immutable payments stay; the outstanding supplier debt is recalculated.
    """

    model_config = ConfigDict(populate_by_name=True)

    transaction_date: datetime | None = None
    reference_no: str | None = Field(default=None, max_length=100)
    note: str | None = None
    discount_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        validation_alias=AliasChoices("discount_amount", "discountAmount"),
    )
    tax_amount: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        validation_alias=AliasChoices("tax_amount", "taxAmount"),
    )
    currency: str = Field(default="USD", pattern="^(USD|KHR)$")
    exchange_rate: Decimal = Field(
        default=Decimal("1"),
        gt=0,
        validation_alias=AliasChoices("exchange_rate", "exchangeRate"),
    )
    items: list[StockInItem] = Field(min_length=1, validation_alias=AliasChoices("items", "lines"))

class AdjustmentItem(BaseModel):
    product_id: UUID
    system_quantity: Decimal | None = Field(default=None, ge=0)
    actual_quantity: Decimal = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
    note: str | None = None

class StockAdjustmentRequest(BaseModel):
    transaction_date: datetime | None = None
    reference_no: str | None = Field(default=None, max_length=100)
    note: str | None = None
    items: list[AdjustmentItem] = Field(min_length=1)

class DamageItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: UUID
    # Entered quantity per the selected UOM (base qty = qty × factor_to_base).
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    reason: str = Field(min_length=1, max_length=500)
    batch_no: str | None = Field(default=None, max_length=100)
    note: str | None = None
    # Damage accepts an alternate Pricing UOM: entered qty converts to base
    # server-side (the frontend factor is validated, never trusted).
    uom_id: UUID | None = Field(
        default=None, validation_alias=AliasChoices("uom_id", "uomId")
    )
    uom_symbol: str | None = Field(
        default=None, max_length=20, validation_alias=AliasChoices("uom_symbol", "uomSymbol")
    )
    factor_to_base: Decimal | None = Field(
        default=None, gt=0, validation_alias=AliasChoices("factor_to_base", "factorToBase")
    )

class StockDamageRequest(BaseModel):
    transaction_date: datetime | None = None
    reference_no: str | None = Field(default=None, max_length=100)
    note: str | None = None
    items: list[DamageItem] = Field(min_length=1)

class ExpireItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: UUID
    # Entered quantity per the selected UOM (base qty = qty × factor_to_base).
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)
    batch_no: str | None = Field(default=None, max_length=100)
    expiry_date: date | None = None
    note: str | None = None
    # Expiry accepts an alternate Pricing UOM: entered qty converts to base
    # server-side and is validated against the batch remaining quantity.
    uom_id: UUID | None = Field(
        default=None, validation_alias=AliasChoices("uom_id", "uomId")
    )
    uom_symbol: str | None = Field(
        default=None, max_length=20, validation_alias=AliasChoices("uom_symbol", "uomSymbol")
    )
    factor_to_base: Decimal | None = Field(
        default=None, gt=0, validation_alias=AliasChoices("factor_to_base", "factorToBase")
    )

class StockExpireRequest(BaseModel):
    transaction_date: datetime | None = None
    reference_no: str | None = Field(default=None, max_length=100)
    note: str | None = None
    items: list[ExpireItem] = Field(min_length=1)

class PurchaseReturnItemRequest(BaseModel):
    """One line of POST /stock/in/{id}/return (spec 2.1.x Return to supplier)."""

    model_config = ConfigDict(populate_by_name=True)

    stock_transaction_item_id: UUID = Field(
        validation_alias=AliasChoices("stock_transaction_item_id", "stockTransactionItemId")
    )
    quantity: Decimal = Field(gt=0)

class PurchaseReturnRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reason: str = Field(min_length=1, max_length=1000)
    lines: list[PurchaseReturnItemRequest] = Field(
        min_length=1, validation_alias=AliasChoices("lines", "items")
    )
    return_date: datetime | None = None

class PurchaseReturnItemOut(BaseModel):
    id: UUID
    stock_transaction_item_id: UUID
    product_id: UUID
    product_name: str | None = None
    quantity: Decimal
    unit_cost: Decimal
    line_refund: Decimal

class PurchaseReturnOut(BaseModel):
    id: UUID
    return_no: str
    stock_transaction_id: UUID
    document_no: str | None = None
    supplier_id: UUID | None = None
    return_date: datetime
    refund_amount: Decimal
    debt_reduction: Decimal = Decimal("0.00")
    credit_amount: Decimal = Decimal("0.00")
    reason: str
    items: list[PurchaseReturnItemOut]

class OperationItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    product_name: str | None = None
    sku: str | None = None
    # Line UOM symbol snapshot (selected Pricing UOM for Stock In lines).
    uom_symbol: str | None = None
    quantity: Decimal
    unit_cost: Decimal
    system_quantity: Decimal | None
    actual_quantity: Decimal | None
    batch_no: str | None
    expiry_date: date | None
    reason: str | None
    line_total: Decimal
    # Entered-UOM traceability of the operator on outbound lines (Damage /
    # Expiry / Purchase Return): entered_quantity = base quantity ÷ factor.
    entered_quantity: Decimal | None = None
    entered_uom_symbol: str | None = None
    entered_factor_to_base: Decimal | None = None

class StockOperationOut(BaseModel):
    id: UUID
    document_no: str
    transaction_type: str
    supplier_id: UUID | None
    transaction_date: datetime
    reference_no: str | None
    note: str | None
    status: str
    total_amount: Decimal
    paid_amount: Decimal
    discount_amount: Decimal = Decimal("0.00")
    tax_amount: Decimal = Decimal("0.00")
    currency: str = "USD"
    exchange_rate: Decimal = Decimal("1")
    debt_created: bool = False
    debt_id: UUID | None = None
    items: list[OperationItemOut]

class QuickStockOperationRequest(BaseModel):
    """Single-product quick operation from the Stock list
    (`type`: stock_in | adjustment | damage | expiry)."""

    model_config = ConfigDict(populate_by_name=True)

    type: str = Field(default="stock_in", pattern="^(stock_in|adjustment|damage|expiry)$")
    product_id: UUID = Field(validation_alias=AliasChoices("product_id", "productId"))
    quantity: Decimal
    note: str | None = Field(default=None, max_length=1000)
    transaction_date: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("transaction_date", "transactionDate", "date"),
    )
    unit_cost: Decimal | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("unit_cost", "unitCost"),
    )
    uom_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("uom_id", "uomId"),
    )
    uom_symbol: str | None = Field(
        default=None,
        validation_alias=AliasChoices("uom_symbol", "uomSymbol"),
    )
    factor_to_base: Decimal | None = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices("factor_to_base", "factorToBase"),
    )

class MovementOut(BaseModel):
    """GET /stock/movements row (Stock Movements page).

    Quantities stay in the product base UOM (like the ledger); ``uom_symbol``
    is the line snapshot when present, else the product's base UOM symbol.
    ``qty_in``/``qty_out`` are unsigned convenience projections of the signed
    ``quantity_delta``; ``balance_before``/``balance_after`` are derived from
    the immutable movement ledger (never persisted).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    product_name: str | None = None
    barcode: str | None = None
    movement_type: str
    quantity_delta: Decimal
    qty_in: Decimal = Decimal("0")
    qty_out: Decimal = Decimal("0")
    balance_before: Decimal = Decimal("0")
    balance_after: Decimal = Decimal("0")
    unit_cost: Decimal
    reference_type: str
    reference_id: UUID
    document_no: str | None
    source_reference: str | None = None
    batch_no: str | None
    expiry_date: date | None
    # Batch lot link (single-batch movements; multi-batch outflows stay NULL).
    batch_id: UUID | None = None
    # Line UOM symbol snapshot (display only; falls back to the base UOM).
    uom_symbol: str | None = None
    note: str | None
    user: str | None = None
    created_by: UUID | None = None
    created_at: datetime


# ---------------------------------------------------------------- sale prices


class SalePriceUomIn(BaseModel):
    """One UOM sale price row inside a price version (pcs / pack / box…)."""

    model_config = ConfigDict(populate_by_name=True)

    uom_id: UUID = Field(validation_alias=AliasChoices("uom_id", "uomId"))
    uom_symbol: str | None = Field(
        default=None,
        max_length=50,
        validation_alias=AliasChoices("uom_symbol", "uomSymbol"),
    )
    factor_to_base: Decimal = Field(
        default=Decimal("1"),
        gt=0,
        max_digits=18,
        decimal_places=6,
        validation_alias=AliasChoices("factor_to_base", "factorToBase"),
    )
    sale_price: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=2,
        validation_alias=AliasChoices("sale_price", "salePrice"),
    )
    is_default_sale: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("is_default_sale", "isDefaultSale"),
    )

class SalePriceCreate(BaseModel):
    """Add Sale Price payload (snake_case and camelCase accepted)."""

    model_config = ConfigDict(populate_by_name=True)

    sale_price: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=2,
        validation_alias=AliasChoices("sale_price", "salePrice", "price"),
    )
    effective_date: date | None = Field(
        default=None,
        validation_alias=AliasChoices("effective_date", "effectiveDate", "date"),
    )
    product_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("product_id", "productId"),
    )
    # Optional batch scope: NULL/blank = general pricing (all lots).
    batch_no: str | None = Field(
        default=None,
        max_length=120,
        validation_alias=AliasChoices("batch_no", "batchNo", "batch"),
    )
    purchase_date: date | None = Field(
        default=None,
        validation_alias=AliasChoices("purchase_date", "purchaseDate"),
    )
    expiry_date: date | None = Field(
        default=None,
        validation_alias=AliasChoices("expiry_date", "expiryDate"),
    )
    # Per-UOM prices of THIS version; falls back to a single base-UOM row at
    # `sale_price` when omitted (legacy single-price payload keeps working).
    uom_prices: list[SalePriceUomIn] | None = Field(
        default=None,
        validation_alias=AliasChoices("uom_prices", "uomPrices"),
    )

class SalePriceUpdate(BaseModel):
    """PATCH payload: `{isActive: true}` runs the activate transaction."""

    model_config = ConfigDict(populate_by_name=True)

    is_active: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("is_active", "isActive"),
    )
