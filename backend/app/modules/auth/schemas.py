from datetime import datetime
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class SetupRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=1, max_length=128)
    telegram_chat_id: str | None = Field(default=None, max_length=100)

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, value, info):
        if info.data.get("password") != value:
            raise ValueError("Passwords do not match")
        return value


class SetupStatusResponse(BaseModel):
    setup_completed: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: EmailStr
    telegram_chat_id: str | None
    telegram_name: str | None = None
    telegram_verified: bool
    status: str
    role: str | None = None
    permissions: list[str] = []
    last_login_at: datetime | None = None
    avatar: str | None = None
    # True when the account must change its password before doing anything else
    # (admin-forced change or an expired password).
    must_change_password: bool = False


def auth_user_payload(user) -> dict:
    """`user` payload for /auth/me and login: snake_case keys (existing API
    contract) plus the camelCase/alias keys the SPA reads (AuthUser).

    Accepts either a `UserOut` or an ORM `User`; the ORM object has no
    `role`/`permissions` attributes, so it is projected first.
    """
    if not isinstance(user, UserOut):
        from app.modules.auth.service import user_to_out

        user = user_to_out(user)
    data = user.model_dump(mode="json")
    data.update(
        {
            "name": data["full_name"],
            "telegramLinked": bool(data["telegram_verified"] and data["telegram_chat_id"]),
            "telegramChatId": data["telegram_chat_id"],
            "telegramName": data.get("telegram_name"),
            "effectivePermissions": list(data["permissions"]),
            "mustChangePassword": bool(data.get("must_change_password")),
        }
    )
    return data


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


def token_pair_payload(tokens: TokenPairResponse) -> dict:
    """Token response with snake_case keys (existing contract) plus the
    camelCase keys the SPA token layer reads (accessToken/refreshToken/…)."""
    data = tokens.model_dump(mode="json")
    data.update(
        {
            "accessToken": data["access_token"],
            "refreshToken": data["refresh_token"],
            "tokenType": data["token_type"],
            "expiresIn": data["expires_in"],
            "user": auth_user_payload(tokens.user),
        }
    )
    return data

class RefreshRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    refresh_token: str = Field(
        min_length=1, max_length=2048,
        validation_alias=AliasChoices("refresh_token", "refreshToken"),
    )


class LogoutRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    refresh_token: str | None = Field(
        default=None, max_length=2048,
        validation_alias=AliasChoices("refresh_token", "refreshToken"),
    )


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    """Result of a reset request.

    `channel` is `telegram` when the code was delivered to a linked chat, or
    `telegram_link` when the account has no linked chat yet — then `link_code`
    is a one-time code the user sends to the bot (`/link CODE`) and the bot
    replies with the reset code.
    """

    message: str
    channel: str = "telegram"
    link_code: str | None = None
    linkCode: str | None = None
    expires_in: int = 0
    expiresIn: int = 0

    @model_validator(mode="after")
    def _sync_aliases(self):
        if self.linkCode is None and self.link_code is not None:
            self.linkCode = self.link_code
        if not self.expiresIn and self.expires_in:
            self.expiresIn = self.expires_in
        return self


class VerifyResetCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class VerifyResetCodeResponse(BaseModel):
    reset_token: str
    resetToken: str = ""
    expires_in: int = 0
    expiresIn: int = 0


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reset_token: str = Field(
        min_length=1, max_length=2048, validation_alias=AliasChoices("reset_token", "resetToken")
    )
    new_password: str = Field(
        min_length=8, max_length=128, validation_alias=AliasChoices("new_password", "newPassword", "password")
    )
    confirm_password: str = Field(
        default="",
        min_length=0,
        max_length=128,
        validation_alias=AliasChoices("confirm_password", "confirmPassword", "passwordConfirmation"),
    )

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, value, info):
        if value and info.data.get("new_password") != value:
            raise ValueError("Passwords do not match")
        return value


class MessageResponse(BaseModel):
    message: str


class ChangePasswordRequest(BaseModel):
    """POST /auth/change-password (authenticated)."""

    current_password: str = Field(
        min_length=1, max_length=128, validation_alias=AliasChoices("current_password", "currentPassword")
    )
    new_password: str = Field(
        min_length=8, max_length=128, validation_alias=AliasChoices("new_password", "newPassword", "password")
    )
    model_config = ConfigDict(populate_by_name=True)


class ProfileAvatarRequest(BaseModel):
    """PATCH /auth/profile/avatar — null/empty clears the avatar."""

    avatar: str | None = Field(default=None, max_length=2_100_000)


class HandoffExchangeRequest(BaseModel):
    """POST /auth/forgot-password/handoff — exchange a Telegram handoff token."""

    handoff: str = Field(min_length=16, max_length=256)


class HandoffExchangeResponse(BaseModel):
    email: EmailStr
    reset_token: str
    resetToken: str = ""
    expires_in: int = 0
    expiresIn: int = 0


class ResendResetCodeRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResetRequest(BaseModel):
    """POST /auth/forgot-password/reset — camelCase body used by the UI."""

    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr
    reset_token: str = Field(
        min_length=1, max_length=2048, validation_alias=AliasChoices("reset_token", "resetToken")
    )
    new_password: str = Field(
        min_length=8, max_length=128, validation_alias=AliasChoices("new_password", "newPassword", "password")
    )


class TelegramLinkCodeResponse(BaseModel):
    code: str
    expires_in: int = 0
    expiresIn: int = 0
