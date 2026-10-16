from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field


class CustomerCreate(BaseModel):
    code: str | None = Field(default=None, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = None
    address: str | None = None
    note: str | None = None
    status: str = Field(default="ACTIVE", pattern="^(ACTIVE|INACTIVE)$")


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = None
    address: str | None = None
    note: str | None = None
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    phone: str | None
    address: str | None
    note: str | None
    status: str
    is_walk_in: bool
    created_at: datetime
    # Open debt remaining per document currency (live), e.g. {"USD": "35.0000"}.
    # The Customers list renders 'Outstanding Debt' from this — never summed
    # across currencies.
    debt_balances: dict[str, str] = Field(default_factory=dict)

    @computed_field
    @property
    def location(self) -> str | None:
        return self.address
