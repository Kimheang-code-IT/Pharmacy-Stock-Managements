from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

DELIVERY_STATUSES = (
    "PENDING",
    "PREPARING",
    "OUT_FOR_DELIVERY",
    "PARTIALLY_DELIVERED",
    "DELIVERED",
    "FAILED",
    "RETURNED",
)
CURRENCIES = ("USD", "KHR")

# Canonical status patterns accepted on create (initial) and /status targets.
_INITIAL_STATUSES = ("PENDING", "PREPARING", "OUT_FOR_DELIVERY", "DELIVERED")
_TARGET_STATUSES = (
    "PREPARING",
    "OUT_FOR_DELIVERY",
    "PARTIALLY_DELIVERED",
    "DELIVERED",
    "FAILED",
    "RETURNED",
)


class DeliveryNoteLineCreate(BaseModel):
    """One delivery line — parent sale + sale line + qty (spec §2.1.9).

    `sale_id` may be omitted when the note is created from ONE sale (the
    header `sale_id` applies to every line). `note` is an optional per-line
    note shown on the Lines to deliver table."""

    model_config = ConfigDict(populate_by_name=True)

    sale_id: UUID | None = Field(default=None, validation_alias=AliasChoices("sale_id", "saleId"))
    sale_item_id: UUID = Field(validation_alias=AliasChoices("sale_item_id", "saleItemId"))
    qty_to_deliver: Decimal = Field(
        gt=0, validation_alias=AliasChoices("qty_to_deliver", "qtyToDeliver")
    )
    note: str | None = Field(default=None, max_length=500)


class DeliveryNoteCreate(BaseModel):
    """Create from one or many confirmed invoices of the SAME customer.

    `sale_id` (optional) is the POS auto-entry shortcut: when set, lines may
    omit their sale_id. Phone/location default from the customer snapshot.
    """

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    customer_id: UUID | None = Field(
        default=None, validation_alias=AliasChoices("customer_id", "customerId")
    )
    sale_id: UUID | None = Field(default=None, validation_alias=AliasChoices("sale_id", "saleId"))
    delivery_phone: str | None = Field(
        default=None, max_length=50, validation_alias=AliasChoices("delivery_phone", "deliveryPhone")
    )
    delivery_location: str | None = Field(
        default=None,
        validation_alias=AliasChoices("delivery_location", "deliveryLocation", "delivery_address", "deliveryAddress"),
    )
    driver_name: str | None = Field(
        default=None, max_length=120, validation_alias=AliasChoices("driver_name", "driverName")
    )
    vehicle_no: str | None = Field(
        default=None, max_length=60, validation_alias=AliasChoices("vehicle_no", "vehicleNo")
    )
    delivery_date: datetime | None = Field(
        default=None, validation_alias=AliasChoices("delivery_date", "deliveryDate")
    )
    delivery_fee: Decimal | None = Field(
        default=None, ge=0, validation_alias=AliasChoices("delivery_fee", "deliveryFee")
    )
    received_by: str | None = Field(
        default=None, max_length=120, validation_alias=AliasChoices("received_by", "receivedBy")
    )
    currency: str | None = Field(
        default=None,
        pattern="^(USD|KHR)$",
        validation_alias=AliasChoices("currency", "currencyCode"),
    )
    status: str | None = Field(
        default=None,
        pattern="^(" + "|".join(_INITIAL_STATUSES) + ")$",
        validation_alias=AliasChoices("status", "deliveryStatus", "delivery_status"),
    )
    note: str | None = None
    confirm: bool = False
    lines: list[DeliveryNoteLineCreate] = Field(
        min_length=1, validation_alias=AliasChoices("items", "lines")
    )


class DeliveryNoteFromSaleCreate(BaseModel):
    """POST /pos/sales/{sale_id}/delivery (POS auto-entry).

    Everything is optional: with no lines the note covers every sale line's
    remaining undelivered qty; phone/location default from the customer."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    delivery_phone: str | None = Field(
        default=None, max_length=50, validation_alias=AliasChoices("delivery_phone", "deliveryPhone")
    )
    delivery_location: str | None = Field(
        default=None,
        validation_alias=AliasChoices("delivery_location", "deliveryLocation", "delivery_address", "deliveryAddress"),
    )
    driver_name: str | None = Field(
        default=None, max_length=120, validation_alias=AliasChoices("driver_name", "driverName")
    )
    # Delivery price captured at POS checkout (the invoice already charged it).
    delivery_fee: Decimal | None = Field(
        default=None, ge=0, validation_alias=AliasChoices("delivery_fee", "deliveryFee")
    )
    note: str | None = None
    confirm: bool = False
    lines: list[DeliveryNoteLineCreate] | None = Field(
        default=None, validation_alias=AliasChoices("items", "lines")
    )


class DeliveryNoteUpdate(BaseModel):
    """Pending-only edits (lines/qty, contact + fulfillment fields)."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    delivery_phone: str | None = Field(
        default=None, max_length=50, validation_alias=AliasChoices("delivery_phone", "deliveryPhone")
    )
    delivery_location: str | None = Field(
        default=None,
        validation_alias=AliasChoices("delivery_location", "deliveryLocation", "delivery_address", "deliveryAddress"),
    )
    driver_name: str | None = Field(
        default=None, max_length=120, validation_alias=AliasChoices("driver_name", "driverName")
    )
    vehicle_no: str | None = Field(
        default=None, max_length=60, validation_alias=AliasChoices("vehicle_no", "vehicleNo")
    )
    delivery_date: datetime | None = Field(
        default=None, validation_alias=AliasChoices("delivery_date", "deliveryDate")
    )
    delivery_fee: Decimal | None = Field(
        default=None, ge=0, validation_alias=AliasChoices("delivery_fee", "deliveryFee")
    )
    received_by: str | None = Field(
        default=None, max_length=120, validation_alias=AliasChoices("received_by", "receivedBy")
    )
    note: str | None = None
    lines: list[DeliveryNoteLineCreate] | None = Field(
        default=None, validation_alias=AliasChoices("items", "lines")
    )


class DeliveryNoteCancelRequest(BaseModel):
    """Cancel body: a reason is mandatory (spec §2.1.9)."""

    model_config = ConfigDict(populate_by_name=True)

    reason: str = Field(
        min_length=1,
        max_length=1000,
        validation_alias=AliasChoices("reason", "cancel_reason", "cancelReason"),
    )


class DeliveryNoteStatusRequest(BaseModel):
    """Body of POST /delivery/{id}/status (spec §5.13 Update Status).

    `status` is the canonical field from the extended vocabulary (PREPARING /
    OUT_FOR_DELIVERY / PARTIALLY_DELIVERED / DELIVERED / FAILED / RETURNED);
    legacy aliases (CONFIRMED, DRAFT, CANCELLED and the verb forms confirm /
    out_for_delivery / deliver / cancel) map onto the same transition service.
    """

    model_config = ConfigDict(populate_by_name=True)

    status: str | None = Field(
        default=None,
        pattern="^(PREPARING|OUT_FOR_DELIVERY|PARTIALLY_DELIVERED|DELIVERED|FAILED|RETURNED"
                "|CONFIRMED|DRAFT|CANCELLED"
                "|confirm|out_for_delivery|outForDelivery|deliver|cancel)$",
        validation_alias=AliasChoices("status", "action"),
    )
    cancel_reason: str | None = Field(
        default=None, max_length=1000, validation_alias=AliasChoices("cancel_reason", "cancelReason", "reason")
    )


class DeliveryNoteSaleOut(BaseModel):
    """One linked invoice (spec §2.1.9 delivery_note_sales)."""

    sale_id: UUID
    invoice_no: str
    # Invoice date snapshot (Sale.sale_date) shown on the delivery line table.
    sale_date: datetime | None = None
    saleDate: datetime | None = None
    # Derived from delivered quantities across all non-cancelled notes —
    # NOT_DELIVERED | PARTIALLY_DELIVERED | FULLY_DELIVERED.
    delivery_status: str = "NOT_DELIVERED"
    deliveryStatus: str = "NOT_DELIVERED"


class DeliveryNoteItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sale_id: UUID
    sale_item_id: UUID
    product_id: UUID
    product_name: str
    uom_symbol: str | None
    qty_ordered: Decimal
    qty_to_deliver: Decimal
    qty_delivered: Decimal
    note: str | None = None


class DeliveryNoteOut(BaseModel):
    id: UUID
    delivery_no: str
    customer_id: UUID
    customer_name: str | None = None
    # Linked invoices: snake/camel structured list + comma-joined display string.
    sales: list[DeliveryNoteSaleOut] = Field(default_factory=list)
    invoice_nos: list[str] = Field(default_factory=list)
    invoiceNo: list[str] = Field(default_factory=list)
    invoice_no: str = ""
    delivery_phone: str | None
    deliveryPhone: str | None
    delivery_location: str | None
    deliveryLocation: str | None
    driver_name: str | None = None
    driverName: str | None = None
    vehicle_no: str | None = None
    vehicleNo: str | None = None
    delivery_date: datetime | None = None
    deliveryDate: datetime | None = None
    delivery_fee: Decimal = Decimal("0")
    deliveryFee: Decimal = Decimal("0")
    received_by: str | None = None
    receivedBy: str | None = None
    currency: str = "USD"
    delivered_at: datetime | None
    deliveredAt: datetime | None
    status: str
    note: str | None
    cancel_reason: str | None
    created_by: UUID
    created_at: datetime
    items_count: int = 0
    items: list[DeliveryNoteItemOut]


class DeliverableItemOut(BaseModel):
    """What remains deliverable for one sale line across all delivery notes."""

    sale_item_id: UUID
    product_id: UUID
    product_name: str
    # Legacy internal code: nullable since 0021 (barcode is operational).
    sku: str | None = None
    uom_symbol: str | None
    qty_ordered: Decimal
    qty_returned: Decimal
    qty_allocated: Decimal
    qty_delivered: Decimal
    qty_remaining: Decimal
    note: str | None = None


class DeliverableItemsOut(BaseModel):
    sale_id: UUID
    invoice_no: str
    sale_status: str
    customer_id: UUID
    items: list[DeliverableItemOut]


class DeliverableInvoiceOut(BaseModel):
    """One confirmed sale with remaining deliverable qty (create-page picker)."""

    sale_id: UUID
    saleId: UUID
    invoice_no: str
    invoiceNo: str
    sale_date: datetime | None
    sale_status: str
    customer_id: UUID
    customer_name: str | None
    phone: str | None
    location: str | None
    currency: str = "USD"
    # Invoice grand total (snapshot for the selector's Total Amount column).
    grand_total: Decimal = Decimal("0")
    grandTotal: Decimal = Decimal("0")
    # Derived delivery status (NOT_DELIVERED | PARTIALLY_DELIVERED |
    # FULLY_DELIVERED) from delivered quantities across all non-cancelled
    # notes; fully delivered invoices are excluded from the picker.
    delivery_status: str = "NOT_DELIVERED"
    deliveryStatus: str = "NOT_DELIVERED"
    qty_remaining: Decimal
    items: list[DeliverableItemOut]
