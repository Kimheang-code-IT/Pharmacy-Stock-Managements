from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

PAYMENT_METHODS = {"CASH", "BANK_QR", "CUSTOMER_DEBT"}
TENDER_METHODS = {"CASH", "BANK_QR"}


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


class POSProductOut(BaseModel):
    id: UUID
    sku: str
    barcode: str | None
    name: str
    category_id: UUID | None
    category_name: str | None = None
    selling_price: Decimal
    quantity: Decimal = Decimal("0")
    image_object_key: str | None
    image_url: str | None = None
    uom_id: UUID | None = None
    uom_symbol: str | None = None
    # Convert-UOM rows offered on POS plus the base UOM row.
    uom_conversions: list[UomConversionOut] = Field(default_factory=list)
    uomConversions: list[UomConversionOut] = Field(default_factory=list)
    status: str


# --------------------------------------------------------------------- sale


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


class SaleCreateRequest(BaseModel):
    """PosCompleteSaleInput — camelCase keys from the frontend, snake_case
    accepted too. `deposit` (selected open debts) is settled from the paid
    amount via included_debt_ids; delivery_price is added to grand_total."""

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
    # Open customer-debt rows included on this invoice and settled from the
    # paid amount in the same transaction.
    included_debt_ids: list[UUID] = Field(
        default_factory=list,
        validation_alias=AliasChoices("included_debt_ids", "includedDebtIds"),
    )
    # Extra amount due on this invoice (informational; the settled debts use
    # their authoritative remaining amounts from the database).
    deposit: Decimal = Field(default=Decimal("0"), ge=0)
    deposit_method: str | None = Field(default=None, pattern="^(CASH|BANK_QR)$")
    reference_no: str | None = Field(default=None, max_length=100)
    note: str | None = None
    due_date: date | None = Field(
        default=None,
        validation_alias=AliasChoices("due_date", "dueDate"),
    )
    items: list[SaleItemRequest] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_request(self):
        if self.payment_method not in PAYMENT_METHODS:
            raise ValueError("payment_method must be CASH, BANK_QR or CUSTOMER_DEBT")
        if self.payment_method == "CUSTOMER_DEBT" and self.deposit_method is None:
            self.deposit_method = "CASH"
        if self.payment_method in TENDER_METHODS and self.amount_received <= 0:
            raise ValueError("amount_received must be greater than zero")
        return self


class SaleItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    product_name: str
    sku: str
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
    sale_item_id: UUID
    quantity: Decimal = Field(gt=0)
    restock: bool = True


class SaleReturnRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    items: list[SaleReturnItemRequest] = Field(min_length=1)
    return_date: datetime | None = None


class SaleReturnItemOut(BaseModel):
    id: UUID
    sale_item_id: UUID
    product_id: UUID
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
    created_at: datetime


class CustomerHistoryOut(BaseModel):
    id: UUID
    invoice_no: str
    sale_date: datetime
    grand_total: Decimal
    paid_amount: Decimal
    debt_amount: Decimal
    payment_status: str
    sale_status: str
