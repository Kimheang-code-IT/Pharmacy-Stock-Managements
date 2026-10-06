"""Generic table export — the SPA posts the page's filtered rows and downloads
an Excel (.xlsx) or PDF file. Authentication is required; the rows are the ones
the signed-in user already sees, so page-level permissions still apply."""

from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.exceptions import ValidationError
from app.modules.auth.models import User
from app.shared.export.render import export_filename, render_table

router = APIRouter(prefix="/export", tags=["export"])

MAX_EXPORT_ROWS = 20000


class ExportColumn(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=200)
    # text | number | money | date — drives alignment, Excel formats and totals.
    type: Literal["text", "number", "money", "date"] = "text"


class ExportTableRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(default="Stock & POS", max_length=200)
    format: Literal["xlsx", "pdf"] = "xlsx"
    subtitle: str | None = Field(default=None, max_length=300)
    numberFormat: str = Field(default="#,##0.####", max_length=30)
    columns: list[ExportColumn] = Field(min_length=1, max_length=80)
    # Rows are the resolved, already-filtered page rows (capped for safety).
    rows: list[dict] = Field(default_factory=list, max_length=MAX_EXPORT_ROWS)


@router.post("/table")
async def export_table(
    payload: ExportTableRequest,
    actor: User = Depends(get_current_user),
) -> Response:
    """Render the posted table to Excel or PDF and stream it as a download."""
    columns = [{"key": column.key, "label": column.label, "type": column.type} for column in payload.columns]
    try:
        content, media_type, extension = render_table(
            fmt=payload.format,
            title=payload.title,
            columns=columns,
            rows=payload.rows,
            subtitle=payload.subtitle,
            company=payload.company,
            number_format=payload.numberFormat,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    filename = export_filename(payload.title, extension)
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )
