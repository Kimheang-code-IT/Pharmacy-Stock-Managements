from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BrandCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    logo_object_key: str | None = Field(default=None, max_length=500)
    status: str = Field(default="ACTIVE", pattern="^(ACTIVE|INACTIVE)$")

    class Config:
        str_strip_whitespace = True


class BrandUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    logo_object_key: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")

    class Config:
        str_strip_whitespace = True


class BrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None
    logo_object_key: str | None
    status: str
    created_at: datetime
