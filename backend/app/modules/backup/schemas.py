from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class BackupSettingsUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool | None = None
    sheet_id: str | None = Field(
        default=None, validation_alias=AliasChoices("sheetId", "sheet_id")
    )
    service_account_json: str | None = Field(
        default=None, validation_alias=AliasChoices("serviceAccountJson", "service_account_json")
    )
    frequency_hours: int | None = Field(
        default=None, validation_alias=AliasChoices("frequencyHours", "frequency_hours")
    )
    backup_new_records: bool | None = Field(
        default=None, validation_alias=AliasChoices("backupNewRecords", "backup_new_records")
    )
    backup_changed_records: bool | None = Field(
        default=None, validation_alias=AliasChoices("backupChangedRecords", "backup_changed_records")
    )
    auto_retry: bool | None = Field(
        default=None, validation_alias=AliasChoices("autoRetry", "auto_retry")
    )
    retry_attempts: int | None = Field(
        default=None, validation_alias=AliasChoices("retryAttempts", "retry_attempts")
    )
    telegram_notify: bool | None = Field(
        default=None, validation_alias=AliasChoices("telegramNotify", "telegram_notify")
    )

    def to_payload(self) -> dict:
        # Pydantic's `by_alias` only applies `serialization_alias`, so map the
        # snake_case field names onto the camelCase keys the service expects.
        aliases = {
            "sheet_id": "sheetId",
            "service_account_json": "serviceAccountJson",
            "frequency_hours": "frequencyHours",
            "backup_new_records": "backupNewRecords",
            "backup_changed_records": "backupChangedRecords",
            "auto_retry": "autoRetry",
            "retry_attempts": "retryAttempts",
            "telegram_notify": "telegramNotify",
        }
        return {
            aliases.get(name, name): value
            for name, value in self.model_dump(exclude_none=True).items()
        }


class BackupRestoreRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    confirmation_token: str | None = Field(
        default=None, validation_alias=AliasChoices("confirmationToken", "confirmation_token")
    )
    confirmation_phrase: str | None = Field(
        default=None, validation_alias=AliasChoices("confirmationPhrase", "confirmation_phrase")
    )
    tables: list[str] | None = None
