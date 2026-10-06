"""Server-side report renderers: Excel (.xlsx via openpyxl) and PDF (fpdf2).

The PDF path uses fpdf2 with HarfBuzz text shaping (uharfbuzz) and an embedded
Noto Sans Khmer font, because reportlab cannot shape Khmer and drew blank /
garbled text. The SPA posts the page's filtered rows, so the exported file
contains exactly the data on screen (after search + date filters).
"""

from __future__ import annotations

import glob
import io
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger("stock_pos.export")

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MEDIA_TYPE = "application/pdf"
SUPPORTED_FORMATS = ("xlsx", "pdf")

# Hanuman (OFL, vendored under app/assets/fonts) covers Khmer *and* Latin in a
# single font, so fpdf2 needs no fallback font (its fallback+shaping leaked the
# Khmer font into neighbouring cells and dropped digits). The Noto Khmer family
# has no Latin glyphs, which is why the report PDF previously lost all numbers.
_VENDORED_FONTS = Path(__file__).resolve().parents[2] / "assets" / "fonts"
_REPORT_REGULAR_CANDIDATES = (
    str(_VENDORED_FONTS / "Hanuman-Regular.ttf"),
    "/usr/share/fonts/**/Hanuman-Regular.ttf",
)
_REPORT_BOLD_CANDIDATES = (
    str(_VENDORED_FONTS / "Hanuman-Bold.ttf"),
    "/usr/share/fonts/**/Hanuman-Bold.ttf",
)

_NUMERIC_TYPES = ("number", "money")
_MONEY_FORMAT = '#,##0.00'
_NUMBER_FORMAT = '#,##0.####'
_DATE_FORMAT = 'yyyy-mm-dd'
_NUMBER_FORMAT_PATTERN = re.compile(r"^[#,##0]+(?:\.[0#]+)?$")


def _as_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _text(value) -> str:
    return "" if value is None else str(value)


def _first_existing(candidates: tuple[str, ...]) -> str | None:
    for pattern in candidates:
        for path in glob.glob(pattern, recursive=True):
            return path
    return None


def _safe_sheet_name(title: str) -> str:
    cleaned = re.sub(r"[\[\]:*?/\\]", " ", str(title or "Sheet")).strip()
    return (cleaned or "Sheet")[:31]


def _column_type(column: dict, rows: list[dict]) -> str:
    explicit = str(column.get("type") or "").strip().lower()
    if explicit in ("text", "number", "money", "date"):
        return explicit
    # Infer when the caller did not classify the column.
    values = [row.get(column.get("key")) for row in rows]
    non_empty = [value for value in values if value not in (None, "")]
    if non_empty and all(_as_number(value) for value in non_empty):
        return "number"
    return "text"


def _format_money(value) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return _text(value)


def _safe_number_format(value: str | None) -> str:
    pattern = str(value or "").strip()
    return pattern if _NUMBER_FORMAT_PATTERN.fullmatch(pattern) else _NUMBER_FORMAT


def _parse_date(value):
    if isinstance(value, (datetime, date)):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _totals(columns: list[dict], rows: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for column in columns:
        if _column_type(column, rows) not in _NUMERIC_TYPES:
            continue
        total = 0.0
        found = False
        for row in rows:
            value = row.get(column.get("key"))
            if value in (None, ""):
                continue
            try:
                total += float(value)
                found = True
            except (TypeError, ValueError):
                continue
        if found:
            totals[str(column.get("key"))] = total
    return totals


def _summary_lines(
    *, company: str, title: str, subtitle: str | None, generated_at: datetime, row_count: int
) -> list[str]:
    lines = [company, f"របាយការណ៍: {title}"]
    if subtitle:
        lines.append(subtitle)
    lines.append(
        f"កាលបរិច្ឆេទនាំចេញ: {generated_at.strftime('%Y-%m-%d %H:%M')} · "
        f"ចំនួនប្រតិបត្តិការ: {row_count}"
    )
    return lines


# --------------------------------------------------------------------- excel


def render_xlsx(
    *,
    title: str,
    columns: list[dict],
    rows: list[dict],
    subtitle: str | None = None,
    company: str = "Stock & POS",
    number_format: str = _NUMBER_FORMAT,
) -> bytes:
    """Styled spreadsheet: title, filter info, bold header, auto-filter, freeze,
    typed number/date formats, real SUM formulas, and A4 fit-to-width printing."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.properties import PageSetupProperties

    generated_at = datetime.now(timezone.utc)
    number_format = _safe_number_format(number_format)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = _safe_sheet_name(title)

    summary = _summary_lines(
        company=company, title=title, subtitle=subtitle, generated_at=generated_at, row_count=len(rows)
    )
    row = 1
    for index, line in enumerate(summary):
        cell = sheet.cell(row=row, column=1, value=line)
        if index == 0:
            cell.font = Font(bold=True, size=12, color="FF1E293B")
        elif index == 1:
            cell.font = Font(bold=True, size=14, color="FF2563EB")
        else:
            cell.font = Font(size=9, color="FF64748B")
        row += 1
    row += 1

    header_row = row
    header_font = Font(bold=True, color="FFFFFFFF")
    header_fill = PatternFill("solid", fgColor="FF2563EB")
    thin = Side(style="thin", color="FFCBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for index, column in enumerate(columns, start=1):
        cell = sheet.cell(row=header_row, column=index, value=str(column.get("label", "")))
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

    types = {str(column.get("key")): _column_type(column, rows) for column in columns}
    first_data_row = header_row + 1
    for offset, data_row in enumerate(rows, start=first_data_row):
        for index, column in enumerate(columns, start=1):
            key = str(column.get("key"))
            value = data_row.get(key)
            cell = sheet.cell(row=offset, column=index)
            column_kind = types[key]
            if column_kind in _NUMERIC_TYPES and _as_number(value):
                cell.value = value
                cell.number_format = _MONEY_FORMAT if column_kind == "money" else number_format
                cell.alignment = Alignment(horizontal="right", vertical="top")
            elif column_kind == "date" and _parse_date(value) is not None:
                cell.value = _parse_date(value)
                cell.number_format = _DATE_FORMAT
                cell.alignment = Alignment(horizontal="left", vertical="top")
            else:
                cell.value = _text(value)
                cell.alignment = Alignment(vertical="top", wrap_text=False)
            cell.border = border
    last_data_row = first_data_row + len(rows) - 1

    # Totals row with real SUM formulas for numeric columns.
    if rows and any(kind in _NUMERIC_TYPES for kind in types.values()):
        total_row = last_data_row + 1
        total_font = Font(bold=True)
        for index, column in enumerate(columns, start=1):
            key = str(column.get("key"))
            cell = sheet.cell(row=total_row, column=index)
            cell.font = total_font
            cell.border = border
            if types[key] in _NUMERIC_TYPES:
                letter = get_column_letter(index)
                cell.value = f"=SUM({letter}{first_data_row}:{letter}{last_data_row})"
                cell.number_format = _MONEY_FORMAT if types[key] == "money" else number_format
                cell.alignment = Alignment(horizontal="right")
            elif index == 1:
                cell.value = "សរុប"
        last_data_row = total_row

    for index, column in enumerate(columns, start=1):
        width = len(str(column.get("label", ""))) + 2
        for data_row in rows[:200]:
            width = max(width, len(_text(data_row.get(str(column.get("key"))))) + 2)
        sheet.column_dimensions[get_column_letter(index)].width = min(max(width, 10), 45)

    sheet.freeze_panes = sheet.cell(row=header_row + 1, column=1)
    if rows:
        last_column = get_column_letter(len(columns))
        sheet.auto_filter.ref = f"A{header_row}:{last_column}{last_data_row}"
        sheet.print_area = f"A1:{last_column}{last_data_row}"
    sheet.print_title_rows = f"{header_row}:{header_row}"
    sheet.page_setup.orientation = "landscape" if len(columns) > 6 else "portrait"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    sheet.page_margins.left = 0.5
    sheet.page_margins.right = 0.5
    sheet.page_margins.top = 0.5
    sheet.page_margins.bottom = 0.5

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ----------------------------------------------------------------------- pdf


def _report_fonts() -> tuple[str | None, str | None]:
    return _first_existing(_REPORT_REGULAR_CANDIDATES), _first_existing(_REPORT_BOLD_CANDIDATES)


def render_pdf(
    *,
    title: str,
    columns: list[dict],
    rows: list[dict],
    subtitle: str | None = None,
    company: str = "Stock & POS",
) -> bytes:
    """A4 report (portrait, landscape when many columns) with a Khmer font,
    repeating header, wrapped cells, right-aligned numbers, totals and page
    numbers (ទំព័រ X / Y)."""
    from fpdf import FPDF
    from fpdf.enums import Align, XPos, YPos

    generated_at = datetime.now(timezone.utc)
    landscape = len(columns) > 6
    regular, bold = _report_fonts()
    unicode_ok = regular is not None

    def safe(value) -> str:
        """Fall back to Latin text when no Unicode (Khmer) font is available."""
        text = _text(value)
        if unicode_ok:
            return text
        return text.encode("latin-1", "replace").decode("latin-1")

    total_label = "សរុប" if unicode_ok else "Total"

    class _ReportPDF(FPDF):
        def footer(self) -> None:  # page numbers on every page
            self.set_y(-12)
            self.set_font(family, "", 8)
            self.set_text_color(120, 120, 120)
            width = (self.w - self.l_margin - self.r_margin) / 2
            page_text = (
                f"ទំព័រ {self.page_no()} / {{nb}}"
                if unicode_ok
                else f"Page {self.page_no()} / {{nb}}"
            )
            self.set_x(self.l_margin)
            self.cell(width, 6, safe(company), align=Align.L)
            self.cell(width, 6, page_text, align=Align.R)

    pdf = _ReportPDF(orientation="L" if landscape else "P", unit="mm", format="A4")
    pdf.set_margins(12, 12, 12)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.alias_nb_pages()

    family = "helvetica"
    if regular:
        pdf.add_font(family="report", style="", fname=regular)
        if bold:
            pdf.add_font(family="report", style="B", fname=bold)
        family = "report"
        try:
            pdf.set_text_shaping(True)
        except Exception:  # noqa: BLE001 - shaping optional; still renders with the font
            logger.warning("Text shaping unavailable; Khmer may render imperfectly")

    bold_style = "B" if (regular and bold) else ""
    width = pdf.epw

    pdf.add_page()
    # Company / system name, then the report title (Khmer) and filter info.
    pdf.set_font(family, "", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.multi_cell(width, 5, safe(company), align=Align.C, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(family, bold_style, 15)
    pdf.set_text_color(30, 41, 59)
    pdf.multi_cell(width, 9, safe(title), align=Align.C, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(family, "", 9)
    pdf.set_text_color(100, 116, 139)
    if subtitle:
        pdf.multi_cell(width, 5, safe(subtitle), align=Align.C, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    meta_label = "កាលបរិច្ឆេទនាំចេញ" if unicode_ok else "Exported"
    rows_label = "ចំនួនប្រតិបត្តិការ" if unicode_ok else "Rows"
    pdf.multi_cell(
        width,
        5,
        f"{meta_label}: {generated_at.strftime('%Y-%m-%d %H:%M')} · {rows_label}: {len(rows)}",
        align=Align.C,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(3)

    types = {str(column.get("key")): _column_type(column, rows) for column in columns}
    aligns: list[Align] = []
    headings: list[str] = []
    for column in columns:
        key = str(column.get("key"))
        aligns.append(Align.R if types[key] in _NUMERIC_TYPES else Align.L)
        headings.append(safe(column.get("label", "")))

    def cell_text(key: str, value) -> str:
        if value in (None, ""):
            return ""
        if types[key] in _NUMERIC_TYPES:
            return _format_money(value)
        return safe(value)

    totals = _totals(columns, rows)
    pdf.set_font(family, "", 8)
    pdf.set_draw_color(203, 213, 225)
    pdf.set_text_color(15, 23, 42)
    with pdf.table(
        text_align=tuple(aligns),
        line_height=5,
        padding=1.2,
        width=pdf.epw,
        first_row_as_headings=True,
    ) as table:
        table.row(headings)
        for data_row in rows:
            table.row([cell_text(str(column.get("key")), data_row.get(str(column.get("key")))) for column in columns])
        if totals:
            total_cells = []
            for index, column in enumerate(columns):
                key = str(column.get("key"))
                if key in totals:
                    total_cells.append(_format_money(totals[key]))
                elif index == 0:
                    total_cells.append(total_label)
                else:
                    total_cells.append("")
            table.row(total_cells)

    return bytes(pdf.output())


def render_table(
    *,
    fmt: str,
    title: str,
    columns: list[dict],
    rows: list[dict],
    subtitle: str | None = None,
    company: str = "Stock & POS",
    number_format: str = _NUMBER_FORMAT,
) -> tuple[bytes, str, str]:
    """Render one table; returns (content, media_type, extension)."""
    normalized = str(fmt or "").strip().lower()
    if normalized not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported export format: {fmt}")
    if normalized == "xlsx":
        content = render_xlsx(
            title=title,
            columns=columns,
            rows=rows,
            subtitle=subtitle,
            company=company,
            number_format=number_format,
        )
        return content, XLSX_MEDIA_TYPE, "xlsx"
    content = render_pdf(title=title, columns=columns, rows=rows, subtitle=subtitle, company=company)
    return content, PDF_MEDIA_TYPE, "pdf"


def export_filename(title: str, extension: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", str(title or "export")).strip("-") or "export"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{base}-{stamp}.{extension}"
