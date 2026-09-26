from datetime import datetime
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, model_validator


# ---------------------------------------------------------------- users


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role_id: UUID
    telegram_chat_id: str | None = Field(default=None, max_length=100)
    telegram_name: str | None = Field(default=None, max_length=150)
    status: str = Field(default="ACTIVE", pattern="^(ACTIVE|DISABLED)$")


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    role_id: UUID | None = None
    telegram_chat_id: str | None = Field(default=None, max_length=100)
    telegram_name: str | None = Field(default=None, max_length=150)
    status: str | None = Field(default=None, pattern="^(ACTIVE|DISABLED)$")


class UserPasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: EmailStr
    telegram_chat_id: str | None
    telegram_name: str | None = None
    telegram_verified: bool
    status: str
    role_id: UUID
    role: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime


# ---------------------------------------------------------------- roles


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    permissions: list[str] | None = None
    status: str | None = Field(default=None, pattern="^(ACTIVE|DISABLED)$")


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_system: bool
    status: str
    permissions: list[str] = []


# ---------------------------------------------------------------- sequences


class SequenceCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_type: str = Field(
        min_length=1,
        max_length=50,
        validation_alias=AliasChoices("document_type", "documentType"),
    )
    prefix: str = Field(min_length=1, max_length=20)
    number_length: int = Field(
        default=6,
        ge=1,
        le=12,
        validation_alias=AliasChoices("number_length", "paddingLength"),
    )
    reset_type: str | None = Field(default=None, max_length=20)
    status: str = Field(default="ACTIVE", pattern="^(ACTIVE|INACTIVE)$")


class SequenceUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    prefix: str | None = Field(default=None, min_length=1, max_length=20)
    next_number: int | None = Field(default=None, ge=1)
    number_length: int | None = Field(
        default=None,
        ge=1,
        le=12,
        validation_alias=AliasChoices("number_length", "paddingLength"),
    )
    reset_type: str | None = Field(default=None, max_length=20)
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")


class SequenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_type: str
    prefix: str
    next_number: int
    number_length: int
    reset_type: str | None
    status: str
    updated_at: datetime


# ---------------------------------------------------------------- settings


class SettingsPatch(BaseModel):
    """Grouped settings patch: {"shop": {"shop_name": "..."}, ...}."""

    values: dict[str, dict[str, object]]


class SettingsOut(BaseModel):
    groups: dict[str, dict[str, object]]


# ----------------------------------------------------- maintenance / reset


class MaintenanceReauthRequest(BaseModel):
    """Verify the password and mint a token for database restore."""

    password: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=40)


class MaintenanceReauthResponse(BaseModel):
    confirmation_token: str
    confirmationToken: str = ""
    expires_in: int = 0
    expiresIn: int = 0
    phrase: str = ""

    @model_validator(mode="after")
    def _sync_aliases(self):
        if not self.confirmationToken:
            self.confirmationToken = self.confirmation_token
        if not self.expiresIn:
            self.expiresIn = self.expires_in
        return self


class DestructiveActionRequest(BaseModel):
    """Confirmation phrase for reset-data / clear-transactions."""

    model_config = ConfigDict(populate_by_name=True)

    confirmation_phrase: str = Field(
        min_length=1,
        max_length=80,
        validation_alias=AliasChoices("confirmation_phrase", "confirmationPhrase"),
    )
