"""PDF report (reportlab)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Flowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..security import atomic_target
from .context import ReportContext, table_rows

_BLUE = colors.HexColor("#2a6f97")


def _table(
    header: list[str], rows: list[list[str]], col_widths: list[float] | None = None
) -> Table:
    t = Table([header, *rows], colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f6f9")]),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ]
        )
    )
    return t


def write_pdf(ctx: ReportContext, out_path: Path) -> None:
    styles = getSampleStyleSheet()
    story: list[Flowable] = [
        Paragraph(escape(ctx.title), styles["Title"]),
        Paragraph(
            f"Classification: <b>{escape(ctx.classification)}</b> &nbsp;|&nbsp; "
            f"Generated: {escape(ctx.generated_str)}",
            styles["Normal"],
        ),
        Paragraph(
            f"Source: {escape(ctx.source_name)}<br/>SHA-256: {escape(ctx.source_sha256[:32])}...",
            styles["Normal"],
        ),
        Spacer(1, 0.4 * cm),
        Paragraph("Overview", styles["Heading2"]),
        _table(["Item", "Value"], [[k, str(v)] for k, v in ctx.analysis.overview.items()],
               [5 * cm, 11 * cm]),
        Spacer(1, 0.3 * cm),
        Paragraph(
            f"Privacy: {escape(ctx.pii_action)} applied to "
            f"{escape(', '.join(ctx.pii_columns) or 'no detected PII columns')}.",
            styles["Normal"],
        ),
    ]
    for title, png in ctx.charts.items():
        story += [
            Spacer(1, 0.4 * cm),
            Paragraph(escape(title), styles["Heading3"]),
            Image(io.BytesIO(png), width=16 * cm, height=8.4 * cm),
        ]
    for key, table in ctx.analysis.group_tables.items():
        story += [Spacer(1, 0.4 * cm), Paragraph(f"Summary by {escape(key)}", styles["Heading2"])]
        rounded = table.round(2)
        story.append(_table([str(c) for c in rounded.columns], table_rows(rounded)))

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.drawString(2 * cm, 1.2 * cm, f"{ctx.classification} - generated {ctx.generated_str}")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
        canvas.restoreState()

    with atomic_target(out_path) as tmp:
        doc = SimpleDocTemplate(
            str(tmp), pagesize=A4, title=ctx.title, author="excel-reporting",
            leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        )
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
