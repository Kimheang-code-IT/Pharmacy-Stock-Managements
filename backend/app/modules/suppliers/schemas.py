from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field


class SupplierCreate(BaseModel):
    code: str | None = Field(default=None, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = None
    address: str | None = None
    contact_person: str | None = Field(default=None, max_length=200)
    note: str | None = None
    status: str = Field(default="ACTIVE", pattern="^(ACTIVE|INACTIVE)$")


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    company_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = None
    address: str | None = None
    contact_person: str | None = Field(default=None, max_length=200)
    note: str | None = None
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    company_name: str | None
    phone: str | None
    address: str | None
    contact_person: str | None
    note: str | None
    status: str
    created_at: datetime

    @computed_field
    @property
    def location(self) -> str | None:
        return self.address


class SupplierDebtOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    supplier_id: UUID
    stock_transaction_id: UUID
    document_no: str
    original_amount: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    due_date: date | None
    status: str
    created_at: datetime


class SupplierDebtPaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    payment_method: str = Field(pattern="^(CASH|BANK_QR)$")
    reference_no: str | None = Field(default=None, max_length=100)
    note: str | None = None
