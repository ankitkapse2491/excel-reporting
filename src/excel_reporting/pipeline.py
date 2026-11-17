"""End-to-end orchestration: ingest -> clean -> protect PII -> analyse -> charts -> reports."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import pii
from .analyze import analyze
from .audit import AuditLog
from .charts import build_charts, build_histogram
from .clean import clean
from .config import AppConfig
from .errors import ReportingError
from .ingest import load_dataframe
from .reports.context import ReportContext
from .reports.excel import write_excel
from .reports.html import write_html
from .reports.pdf import write_pdf
from .security import resolve_within, sha256_file, slugify

log = logging.getLogger("excel_reporting.pipeline")

_WRITERS = {"xlsx": write_excel, "pdf": write_pdf, "html": write_html}


@dataclass
class RunResult:
    run_id: str
    rows_in: int
    rows_out: int
    pii_columns: list[str]
    outputs: list[Path] = field(default_factory=list)


def run(cfg: AppConfig, dry_run: bool = False) -> RunResult:
    run_id = uuid.uuid4().hex[:12]
    audit = AuditLog(cfg.audit.path, run_id)
    out_dir = cfg.report.output_dir.expanduser().resolve()
    audit.record("run_started", dry_run=dry_run, formats=cfg.report.formats,
                 pii_action=cfg.pii.action if cfg.pii.enabled else "disabled")
    try:
        df, src = load_dataframe(cfg.input)
        src_hash = sha256_file(src)
        audit.record("input_read", file=src.name, sha256=src_hash, rows=len(df), cols=df.shape[1])
        log.info("input read", extra={"ctx": {"run_id": run_id, "rows": len(df)}})

        df, stats = clean(df, cfg.cleaning)
        audit.record("data_cleaned", **stats.as_dict())

        df, pii_report = pii.protect(df, cfg.pii)
        audit.record("pii_protected", action=pii_report.action, columns=pii_report.columns,
                     categories=sorted(set(pii_report.protected.values())))

        analysis = analyze(df, cfg.report)
        charts = build_charts(analysis)
        if analysis.metrics:
            charts[f"Distribution of {analysis.metrics[0]}"] = build_histogram(df, analysis.metrics[0])

        now = datetime.now(timezone.utc)
        data = None
        if cfg.report.include_data_sheet:
            data = df.head(cfg.report.data_sheet_max_rows)
            audit.record("row_level_data_included", rows=len(data))

        ctx = ReportContext(
            title=cfg.report.title, classification=cfg.report.classification,
            generated_at=now, source_name=src.name, source_sha256=src_hash,
            analysis=analysis, cleaning=stats, pii_columns=pii_report.columns,
            pii_action=pii_report.action, charts=charts, data=data,
        )
        result = RunResult(run_id, stats.rows_in, stats.rows_out, pii_report.columns)
        if not dry_run:
            stem = f"{slugify(cfg.report.title)}_{now:%Y%m%dT%H%M%SZ}"
            for fmt in cfg.report.formats:
                target = resolve_within(out_dir / f"{stem}.{fmt}", out_dir)
                _WRITERS[fmt](ctx, target)
                result.outputs.append(target)
                audit.record("report_written", format=fmt, file=target.name,
                             sha256=sha256_file(target))
        audit.record("run_completed", outputs=len(result.outputs))
        return result
    except ReportingError as exc:
        audit.record("run_failed", error_type=type(exc).__name__, message=str(exc))
        raise
    except Exception as exc:
        audit.record("run_failed", error_type=type(exc).__name__)
        raise
