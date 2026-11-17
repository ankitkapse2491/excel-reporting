"""Excel report with a styled dashboard and native Excel charts.

Security: every string cell is written with an explicit string data type, so a value
such as ``=HYPERLINK(...)`` can never be interpreted as a formula (CSV/formula injection).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import AreaChart, BarChart, DoughnutChart, LineChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.marker import Marker
from openpyxl.chart.series import DataPoint
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from ..security import atomic_target
from .context import ReportContext

_HEADER_FILL = PatternFill("solid", fgColor="2A6F97")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_PALETTE = ["2A6F97", "D1495B", "6A994E", "EDAE49", "8E7DBE", "00798C", "B5838D", "5C6B7A"]
_GRID = "E3E8ED"
_TILE_FILL = PatternFill("solid", fgColor="EEF4F8")
_MAX_TILES = 5
_MAX_SLICES = 8


# --------------------------------------------------------------------------- cells
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


# -------------------------------------------------------------------- chart helpers
def _fill(color: str) -> GraphicalProperties:
    return GraphicalProperties(solidFill=color, ln=LineProperties(solidFill=color))


def _prep(chart: Any, title: str, x_title: str | None = None, y_title: str | None = None) -> None:
    """Common look: no border, light gridlines, visible axes, thousands separators."""
    chart.title = title
    chart.height, chart.width = 8.5, 16
    chart.graphical_properties = GraphicalProperties(ln=LineProperties(noFill=True))
    if chart.legend is not None:
        chart.legend.position = "b"
    if hasattr(chart, "x_axis"):
        chart.x_axis.delete = False  # openpyxl 3.1 hides axes unless told otherwise
        chart.y_axis.delete = False
        if x_title:
            chart.x_axis.title = x_title
        if y_title:
            chart.y_axis.title = y_title
        if chart.y_axis.majorGridlines is not None:
            chart.y_axis.majorGridlines.spPr = GraphicalProperties(
                ln=LineProperties(solidFill=_GRID)
            )
        chart.y_axis.number_format = "#,##0"


def _cats(ws: Worksheet, n: int) -> Reference:
    return Reference(ws, min_col=1, min_row=2, max_row=n + 1)


def _data(ws: Worksheet, col: int, n: int, max_col: int | None = None) -> Reference:
    return Reference(ws, min_col=col, max_col=max_col or col, min_row=1, max_row=n + 1)


def _labels(fmt: str = "#,##0") -> DataLabelList:
    dl = DataLabelList()
    dl.showVal, dl.showSerName, dl.showCatName, dl.showLegendKey = True, False, False, False
    dl.numFmt = fmt
    return dl


def _column_combo(ws: Worksheet, n: int, key: str, has_metric: bool, metric: str) -> BarChart:
    """Columns for the total; a line on a secondary axis for the mean (when available)."""
    bar = BarChart()
    bar.type = "col"
    bar.gapWidth = 60
    bar.add_data(_data(ws, 3 if has_metric else 2, n), titles_from_data=True)
    bar.set_categories(_cats(ws, n))
    bar.series[0].graphicalProperties = _fill(_PALETTE[0])
    bar.dataLabels = _labels()
    title = f"{metric} by {key}" if has_metric else f"Records by {key}"
    _prep(bar, title, y_title=f"Total {metric}" if has_metric else "Records")
    if has_metric:
        line = LineChart()
        line.add_data(_data(ws, 4, n), titles_from_data=True)
        line.set_categories(_cats(ws, n))
        s = line.series[0]
        s.graphicalProperties = GraphicalProperties(ln=LineProperties(solidFill=_PALETTE[1], w=28575))
        s.marker = Marker(symbol="circle", size=7)
        s.marker.graphicalProperties = _fill(_PALETTE[1])
        s.smooth = False
        line.y_axis.axId = 200
        line.y_axis.title = f"Mean {metric}"
        line.y_axis.crosses = "max"
        line.y_axis.majorGridlines = None
        line.y_axis.delete = False
        line.y_axis.number_format = "#,##0"
        bar += line
    return bar


def _doughnut(ws: Worksheet, n: int, key: str, has_metric: bool, metric: str) -> DoughnutChart:
    n = min(n, _MAX_SLICES)
    ch = DoughnutChart()
    ch.holeSize = 55
    ch.add_data(_data(ws, 3 if has_metric else 2, n), titles_from_data=True)
    ch.set_categories(_cats(ws, n))
    for i in range(n):
        pt = DataPoint(idx=i)
        pt.graphicalProperties = GraphicalProperties(
            solidFill=_PALETTE[i % len(_PALETTE)], ln=LineProperties(solidFill="FFFFFF", w=19050)
        )
        ch.series[0].dPt.append(pt)
    dl = DataLabelList()
    dl.showPercent, dl.showVal, dl.showCatName, dl.showSerName = True, False, False, False
    dl.showLegendKey = False
    dl.numFmt = "0%"
    ch.dataLabels = dl
    _prep(ch, f"Share of {metric if has_metric else 'records'} by {key}")
    ch.legend.position = "r"
    return ch


def _ranked_bar(ws: Worksheet, n: int, key: str, has_metric: bool, metric: str) -> BarChart:
    """Horizontal ranked bars with the largest on top, one colour per bar."""
    ch = BarChart()
    ch.type = "bar"
    ch.gapWidth = 50
    ch.add_data(_data(ws, 3 if has_metric else 2, n), titles_from_data=True)
    ch.set_categories(_cats(ws, n))
    s = ch.series[0]
    s.graphicalProperties = _fill(_PALETTE[2])
    s.invertIfNegative = False
    ch.dataLabels = _labels()
    ch.legend = None
    _prep(ch, f"Top {key} by {metric if has_metric else 'records'}")
    ch.x_axis.scaling.orientation = "maxMin"  # largest first, reading top to bottom
    ch.y_axis.crosses = "max"
    return ch


def _trend_line(ws: Worksheet, n: int, n_series: int) -> LineChart:
    ch = LineChart()
    ch.add_data(_data(ws, 2, n, max_col=1 + n_series), titles_from_data=True)
    ch.set_categories(_cats(ws, n))
    for i, s in enumerate(ch.series):
        color = _PALETTE[i % len(_PALETTE)]
        s.graphicalProperties = GraphicalProperties(ln=LineProperties(solidFill=color, w=28575))
        s.marker = Marker(symbol="circle", size=6)
        s.marker.graphicalProperties = _fill(color)
        s.smooth = True
    _prep(ch, "Monthly trend", y_title="Total")
    if n_series == 1:
        ch.legend = None
    return ch


def _cumulative_area(ws: Worksheet, n: int, col: int, metric: str) -> AreaChart:
    ch = AreaChart()
    ch.grouping = "standard"
    ch.add_data(_data(ws, col, n), titles_from_data=True)
    ch.set_categories(_cats(ws, n))
    ch.series[0].graphicalProperties = GraphicalProperties(
        solidFill=_PALETTE[0], ln=LineProperties(solidFill=_PALETTE[0], w=19050)
    )
    ch.legend = None
    _prep(ch, f"Cumulative {metric}", y_title="Running total")
    return ch


# ------------------------------------------------------------------------ dashboard
def _tile(ws: Worksheet, col: int, label: str, value: float, is_int: bool) -> None:
    for r in (3, 4):
        ws.merge_cells(start_row=r, start_column=col, end_row=r, end_column=col + 1)
        for c in (col, col + 1):
            ws.cell(row=r, column=c).fill = _TILE_FILL
    _put(ws, 3, col, label)
    ws.cell(row=3, column=col).font = Font(size=10, color="5C6B7A")
    ws.cell(row=3, column=col).alignment = Alignment(horizontal="center")
    _put(ws, 4, col, value)
    v = ws.cell(row=4, column=col)
    v.font = Font(size=20, bold=True, color=_PALETTE[0])
    v.number_format = "#,##0" if is_int else "#,##0.00"
    v.alignment = Alignment(horizontal="center", vertical="center")


def _build_dashboard(
    ws: Worksheet,
    ctx: ReportContext,
    group_info: list[tuple[str, Worksheet, int]],
    trend_info: tuple[Worksheet, int, int, int] | None,
) -> None:
    a = ctx.analysis
    ws.sheet_view.showGridLines = False
    _put(ws, 1, 1, ctx.title)
    ws["A1"].font = Font(size=18, bold=True, color=_PALETTE[0])
    _put(ws, 2, 1, f"{ctx.classification}  |  generated {ctx.generated_str}")
    ws["A2"].font = Font(size=9, color="5C6B7A")
    ws.row_dimensions[4].height = 32
    for c in range(1, 21):
        ws.column_dimensions[get_column_letter(c)].width = 10

    _tile(ws, 1, "Records", float(a.overview.get("Rows", 0)), True)  # type: ignore[arg-type]
    for i, (m, total) in enumerate(list(a.totals.items())[: _MAX_TILES - 1], start=1):
        _tile(ws, 1 + 2 * i, f"Total {m}", total, False)

    metric = a.metrics[0] if a.metrics else ""
    has_metric = bool(a.metrics)
    charts: list[Any] = []
    if group_info:
        key, gws, n = group_info[0]
        if n:
            charts.append(_column_combo(gws, n, key, has_metric, metric))
        key2, gws2, n2 = group_info[1] if len(group_info) > 1 else group_info[0]
        if n2:
            charts.append(_doughnut(gws2, n2, key2, has_metric, metric))
    if trend_info:
        tws, n, n_series, cum_col = trend_info
        charts.append(_trend_line(tws, n, n_series))
        charts.append(_cumulative_area(tws, n, cum_col, metric or "records"))
    if len(group_info) > 1 and group_info[1][2]:
        key2, gws2, n2 = group_info[1]
        charts.append(_ranked_bar(gws2, n2, key2, has_metric, metric))
    elif group_info and group_info[0][2]:
        key, gws, n = group_info[0]
        charts.append(_ranked_bar(gws, n, key, has_metric, metric))

    # two charts per row: 16 cm wide ~ 10 columns, 8.5 cm high ~ 17 rows (+1 spacer)
    for idx, chart in enumerate(charts):
        col = "A" if idx % 2 == 0 else "L"
        row = 7 + (idx // 2) * 19
        ws.add_chart(chart, f"{col}{row}")


# --------------------------------------------------------------------------- writer
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

    dash = wb.create_sheet("Dashboard")  # filled once the data sheets exist
    names.append("Dashboard")

    has_metric = bool(ctx.analysis.metrics)
    metric = ctx.analysis.metrics[0] if has_metric else ""
    group_info: list[tuple[str, Worksheet, int]] = []
    for key, table in ctx.analysis.group_tables.items():
        gws = wb.create_sheet(_safe_sheet_name(f"By {key}", names))
        names.append(gws.title)
        _write_df(gws, table.round(2))
        group_info.append((key, gws, len(table)))
        if len(table):
            gws.add_chart(_ranked_bar(gws, len(table), key, has_metric, metric),
                          f"{get_column_letter(len(table.columns) + 2)}2")

    trend_info: tuple[Worksheet, int, int, int] | None = None
    if ctx.analysis.trend is not None and not ctx.analysis.trend.empty:
        tws = wb.create_sheet(_safe_sheet_name("Trend", names))
        names.append(tws.title)
        trend = ctx.analysis.trend.copy()
        trend["period"] = trend["period"].dt.strftime("%Y-%m")
        n_series = min(len(trend.columns) - 1, 3)
        first_series = trend.columns[1]
        trend[f"cumulative_{first_series}"] = trend[first_series].cumsum()
        _write_df(tws, trend.round(2))
        trend_info = (tws, len(trend), n_series, len(trend.columns))

    _build_dashboard(dash, ctx, group_info, trend_info)

    if ctx.data is not None:
        ws = wb.create_sheet(_safe_sheet_name("Data", names))
        _write_df(ws, ctx.data)
        ws.freeze_panes = "A2"

    with atomic_target(out_path) as tmp:
        wb.save(tmp)
