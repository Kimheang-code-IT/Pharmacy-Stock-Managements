"""Dashboard response schemas — spec section 2.1.1.

Money values are `Decimal`; the JSON layer serializes them as fixed-precision
strings (e.g. "20.00") so no binary floating point ever reaches clients.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    """Standard API envelope: `{"data": ..., "meta": ...}`."""

    data: T
    meta: dict = {}


class CardsOut(BaseModel):
    today_sales: Decimal
    today_sales_count: int
    gross_profit: Decimal | None = None
    total_products: int
    customer_debt: Decimal
    supplier_debt: Decimal


class ChartPointOut(BaseModel):
    date: date
    sales_count: int
    income: Decimal
    expense: Decimal


class SummaryOut(BaseModel):
    total_income: Decimal
    total_expense: Decimal
    gross_profit: Decimal | None = None
    net_income: Decimal | None = None
    sales_this_month_count: int
    sales_this_month_amount: Decimal
    customer_debt: Decimal
    supplier_debt: Decimal
    damage_loss: Decimal
    expiry_loss: Decimal
    pending_delivery_notes_count: int


class RecentSaleOut(BaseModel):
    id: UUID
    invoice_no: str
    customer_name: str | None
    sale_date: datetime
    grand_total: Decimal
    payment_status: str


class RecentStockActivityOut(BaseModel):
    id: UUID
    product_name: str
    movement_type: str
    quantity_delta: Decimal
    document_no: str | None
    created_at: datetime


class TopProductOut(BaseModel):
    product_id: UUID
    product_name: str
    quantity_sold: Decimal
    sales_amount: Decimal


class ExtrasOut(BaseModel):
    low_stock_count: int
    out_of_stock_count: int
    recent_sales: list[RecentSaleOut]
    recent_stock_activity: list[RecentStockActivityOut]
    top_products: list[TopProductOut]


class DashboardOut(BaseModel):
    period_start: date
    period_end: date
    profit_visible: bool
    cards: CardsOut
    chart: list[ChartPointOut]
    summary: SummaryOut
    extras: ExtrasOut
