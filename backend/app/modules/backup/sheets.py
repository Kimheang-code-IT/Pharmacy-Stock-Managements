"""Google Sheets gateway.

The backup service talks to Sheets through `SheetsGateway`, an async interface
implemented by `GoogleSheetsGateway` (gspread, executed in a worker thread) and
by a fake in tests. Every remote call is wrapped in a retry with exponential
backoff so a transient Google API error does not fail a whole backup run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Protocol, runtime_checkable

from app.core.exceptions import ServiceUnavailableError, ValidationError

logger = logging.getLogger("stock_pos.backup.sheets")

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"

# Google Sheets limits a tab name to 100 chars and forbids these characters.
_INVALID_TITLE_CHARS = set("[]:*?/\\")


def normalize_tab_title(table_name: str) -> str:
    title = "".join("_" if char in _INVALID_TITLE_CHARS else char for char in str(table_name))
    return title[:100] or "sheet"


def _is_retryable(exc: Exception) -> bool:
    """Auth/permission/not-found errors are terminal; everything else retries."""
    text = str(exc).lower()
    if isinstance(exc, (PermissionError, ValidationError)):
        return False
    if "worksheetnotfound" in type(exc).__name__.lower():
        return False
    for marker in ("401", "403", "invalid_grant", "invalid credentials", "permission"):
        if marker in text:
            return False
    return True


class SheetsGatewayError(ServiceUnavailableError):
    """Google Sheets could not be reached or rejected the request."""


@runtime_checkable
class SheetsGateway(Protocol):
    async def ensure_worksheet(self, title: str, header: list[str]) -> bool:
        """Ensure the tab exists with `header`; return True when it changed."""

    async def read_rows(self, title: str) -> list[list[str]]:
        """Return every cell of the tab (including the header row)."""

    async def append_rows(self, title: str, rows: list[list[str]]) -> None:
        """Append data rows after the last populated row."""

    async def test_connection(self) -> dict:
        """Open the spreadsheet and report its title + tab names."""

    async def list_titles(self) -> list[str]:
        """Existing tab names in the spreadsheet."""


class GoogleSheetsGateway:
    """gspread-backed gateway. gspread is synchronous, so calls run in a thread."""

    def __init__(
        self,
        *,
        sheet_id: str,
        service_account_json: str,
        auto_retry: bool = True,
        retry_attempts: int = 3,
        retry_base_delay: float = 1.5,
    ) -> None:
        self.sheet_id = (sheet_id or "").strip()
        self.service_account_json = service_account_json or ""
        self.auto_retry = auto_retry
        self.retry_attempts = max(1, int(retry_attempts or 1))
        self.retry_base_delay = max(0.1, float(retry_base_delay or 1.5))

    # --------------------------------------------------------------- plumbing

    def _credentials(self):
        if not self.service_account_json.strip():
            raise ValidationError(
                "A Google service account key is required",
                field_errors={"service_account_json": "Paste the service account JSON key"},
            )
        try:
            info = json.loads(self.service_account_json)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "The Google service account key is not valid JSON",
                field_errors={"service_account_json": "Invalid service account JSON"},
            ) from exc
        try:
            from google.oauth2.service_account import Credentials
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise SheetsGatewayError("The Google client library is not installed") from exc
        try:
            return Credentials.from_service_account_info(info, scopes=[SHEETS_SCOPE])
        except Exception as exc:
            raise ValidationError(
                "The Google service account key is invalid",
                field_errors={"service_account_json": "Invalid service account key"},
            ) from exc

    def _open(self):
        if not self.sheet_id:
            raise ValidationError(
                "A Google Sheet ID is required",
                field_errors={"sheet_id": "Paste the spreadsheet ID"},
            )
        try:
            import gspread
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise SheetsGatewayError("The Google Sheets client library is not installed") from exc
        client = gspread.authorize(self._credentials())
        try:
            return client.open_by_key(self.sheet_id)
        except Exception as exc:
            raise SheetsGatewayError(
                f"Could not open the Google Sheet: {exc}"
            ) from exc

    def _with_retry(self, operation):
        attempts = self.retry_attempts if self.auto_retry else 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return operation()
            except Exception as exc:  # noqa: BLE001 - retried or re-raised below
                last_error = exc
                if attempt >= attempts or not _is_retryable(exc):
                    break
                delay = self.retry_base_delay * (2 ** (attempt - 1))
                delay += random.uniform(0, delay * 0.25)
                logger.warning(
                    "Google Sheets call failed (attempt %s/%s): %s; retrying in %.1fs",
                    attempt,
                    attempts,
                    exc,
                    delay,
                )
                time.sleep(delay)
        assert last_error is not None
        raise SheetsGatewayError(f"Google Sheets request failed: {last_error}") from last_error

    async def _run(self, operation):
        return await asyncio.to_thread(self._with_retry, operation)

    @staticmethod
    def _worksheet(spreadsheet, title: str):
        import gspread

        try:
            return spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            return None

    # ------------------------------------------------------------------- API

    async def ensure_worksheet(self, title: str, header: list[str]) -> bool:
        tab = normalize_tab_title(title)

        def operation() -> bool:
            spreadsheet = self._open()
            worksheet = self._worksheet(spreadsheet, tab)
            if worksheet is None:
                worksheet = spreadsheet.add_worksheet(
                    title=tab, rows=max(1000, 2), cols=max(len(header), 1)
                )
                worksheet.append_row(header, value_input_option="RAW")
                try:
                    worksheet.freeze(rows=1)
                except Exception:  # noqa: BLE001 - cosmetic only
                    pass
                return True
            current = worksheet.row_values(1)
            if current[: len(header)] != header or len(current) != len(header):
                worksheet.update(values=[header], range_name="A1")
                return True
            return False

        return bool(await self._run(operation))

    async def read_rows(self, title: str) -> list[list[str]]:
        tab = normalize_tab_title(title)

        def operation():
            worksheet = self._worksheet(self._open(), tab)
            return worksheet.get_all_values() if worksheet is not None else []

        return await self._run(operation)

    async def append_rows(self, title: str, rows: list[list[str]]) -> None:
        if not rows:
            return
        tab = normalize_tab_title(title)

        def operation():
            spreadsheet = self._open()
            worksheet = self._worksheet(spreadsheet, tab)
            if worksheet is None:
                worksheet = spreadsheet.add_worksheet(
                    title=tab, rows=max(1000, len(rows) + 1), cols=max(len(rows[0]), 1)
                )
            # Chunked to stay well under the per-request cell budget.
            for start in range(0, len(rows), 500):
                worksheet.append_rows(
                    rows[start : start + 500], value_input_option="RAW"
                )

        await self._run(operation)

    async def test_connection(self) -> dict:
        def operation():
            spreadsheet = self._open()
            return {
                "title": spreadsheet.title,
                "tabs": [worksheet.title for worksheet in spreadsheet.worksheets()],
            }

        return await self._run(operation)

    async def list_titles(self) -> list[str]:
        def operation():
            return [worksheet.title for worksheet in self._open().worksheets()]

        return await self._run(operation)
