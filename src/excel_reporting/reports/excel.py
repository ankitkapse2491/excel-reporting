"""Excel report with native charts.

Security: every string cell is written with an explicit string data type, so a value
such as ``=HYPERLINK(...)`` can never be interpreted as a formula (CSV/formula injection).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from ..security import atomic_target
from .context import ReportContext

_HEADER_FILL = PatternFill("solid", fgColor="2A6F97")
_HEADER_FONT = Font(bold=True, color="FFFFFF")


def _safe_sheet_name(name: str, existing: list[str]) -> str:
    base = re.sub(r"[\[\]\*\?/\\:]", "_", name)[:28] or "Sheet"
    candidate, i = base, 2
    while candidate in existing:
        candidate, i = f"{base}_{i}", i + 1
    return candidate


def _put(ws: Worksheet, row: int, col: int, value: Any) -> None:
    if value is not None and not isinstance(value, str) and pd.isna(value):
        value = None
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    cell = ws.cell(row=row, column=col, value=value)
    if isinstance(value, str):
        cell.data_type = "s"  # never a formula


def _write_df(ws: Worksheet, df: pd.DataFrame, start_row: int = 1) -> int:
    for j, name in enumerate(df.columns, start=1):
        _put(ws, start_row, j, str(name))
        c = ws.cell(row=start_row, column=j)
        c.fill, c.font = _HEADER_FILL, _HEADER_FONT
        c.alignment = Alignment(horizontal="center")
    for i, row in enumerate(df.itertuples(index=False, name=None), start=start_row + 1):
        for j, v in enumerate(row, start=1):
            _put(ws, i, j, v)
    for j, name in enumerate(df.columns, start=1):
        sample = [len(str(name))] + [len(str(v)) for v in df.iloc[:200, j - 1]]
        ws.column_dimensions[get_column_letter(j)].width = min(max(sample) + 2, 50)
    return start_row + len(df)


def write_excel(ctx: ReportContext, out_path: Path) -> None:
    wb = Workbook()
    wb.properties.creator = "excel-reporting"
    wb.properties.title = ctx.title
    names: list[str] = []

    ws = wb.active
    assert ws is not None
    ws.title = "Summary"
    names.append("Summary")
    _put(ws, 1, 1, ctx.title)
    ws["A1"].font = Font(size=16, bold=True)
    meta = [
        ("Classification", ctx.classification),
        ("Generated", ctx.generated_str),
        ("Source file", ctx.source_name),
        ("Source SHA-256", ctx.source_sha256),
        ("PII handling", f"{ctx.pii_action}: {', '.join(ctx.pii_columns) or 'none detected'}"),
        *list(ctx.analysis.overview.items()),
        *[(k.replace("_", " ").capitalize(), v) for k, v in ctx.cleaning.as_dict().items()],
    ]
    for i, (k, v) in enumerate(meta, start=3):
        _put(ws, i, 1, k)
        ws.cell(row=i, column=1).font = Font(bold=True)
        _put(ws, i, 2, v)
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 70
    if ctx.analysis.describe is not None:
        start = len(meta) + 5
        _put(ws, start - 1, 1, "Metric statistics")
        ws.cell(row=start - 1, column=1).font = Font(bold=True)
        _write_df(ws, ctx.analysis.describe.round(2), start_row=start)

    for key, table in ctx.analysis.group_tables.items():
        ws = wb.create_sheet(_safe_sheet_name(f"By {key}", names))
        names.append(ws.title)
        last = _write_df(ws, table.round(2))
        if len(table) and len(table.columns) > 1:
            val_col = 2 if len(table.columns) == 2 else 3  # count, or first *_sum column
            chart = BarChart()
            chart.type = "bar"
            chart.title = f"{table.columns[val_col - 1]} by {key}"
            chart.add_data(
                Reference(ws, min_col=val_col, min_row=1, max_row=last), titles_from_data=True
            )
            chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=last))
            chart.legend = None
            chart.height, chart.width = 9, 18
            ws.add_chart(chart, f"{get_column_letter(len(table.columns) + 2)}2")

    if ctx.analysis.trend is not None and not ctx.analysis.trend.empty:
        ws = wb.create_sheet(_safe_sheet_name("Trend", names))
        names.append(ws.title)
        trend = ctx.analysis.trend.copy()
        trend["period"] = trend["period"].dt.strftime("%Y-%m")
        last = _write_df(ws, trend.round(2))
        line = LineChart()
        line.title = "Monthly trend"
        line.add_data(
            Reference(ws, min_col=2, max_col=min(len(trend.columns), 4), min_row=1, max_row=last),
            titles_from_data=True,
        )
        line.set_categories(Reference(ws, min_col=1, min_row=2, max_row=last))
        line.height, line.width = 9, 18
        ws.add_chart(line, f"{get_column_letter(len(trend.columns) + 2)}2")

    if ctx.data is not None:
        ws = wb.create_sheet(_safe_sheet_name("Data", names))
        _write_df(ws, ctx.data)
        ws.freeze_panes = "A2"

    with atomic_target(out_path) as tmp:
        wb.save(tmp)
