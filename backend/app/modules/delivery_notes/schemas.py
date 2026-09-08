from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

DELIVERY_STATUSES = ("DRAFT", "CONFIRMED", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED")


class DeliveryNoteLineCreate(BaseModel):
    """One delivery line — parent sale + sale line + qty (spec §2.1.9)."""

    model_config = ConfigDict(populate_by_name=True)

    sale_id: UUID = Field(validation_alias=AliasChoices("sale_id", "saleId"))
    sale_item_id: UUID = Field(validation_alias=AliasChoices("sale_item_id", "saleItemId"))
    qty_to_deliver: Decimal = Field(
        gt=0, validation_alias=AliasChoices("qty_to_deliver", "qtyToDeliver")
    )


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
    note: str | None = None
    confirm: bool = False
    lines: list[DeliveryNoteLineCreate] = Field(
        min_length=1, validation_alias=AliasChoices("items", "lines")
    )


class DeliveryNoteUpdate(BaseModel):
    """Draft-only edits (lines/qty, phone, location)."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    delivery_phone: str | None = Field(
        default=None, max_length=50, validation_alias=AliasChoices("delivery_phone", "deliveryPhone")
    )
    delivery_location: str | None = Field(
        default=None,
        validation_alias=AliasChoices("delivery_location", "deliveryLocation", "delivery_address", "deliveryAddress"),
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
    """Body of POST /delivery-notes/{id}/status (spec §5.13 Update Status).

    `status` is the canonical field (CONFIRMED / OUT_FOR_DELIVERY / DELIVERED
    / CANCELLED); the legacy `action` verbs (confirm / out_for_delivery /
    deliver / cancel) remain accepted aliases of the same transition service.
    """

    model_config = ConfigDict(populate_by_name=True)

    status: str | None = Field(
        default=None,
        pattern="^(CONFIRMED|OUT_FOR_DELIVERY|DELIVERED|CANCELLED|DRAFT"
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
    sku: str
    uom_symbol: str | None
    qty_ordered: Decimal
    qty_returned: Decimal
    qty_allocated: Decimal
    qty_delivered: Decimal
    qty_remaining: Decimal


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
    qty_remaining: Decimal
    items: list[DeliverableItemOut]
