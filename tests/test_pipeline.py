from __future__ import annotations

from pathlib import Path

import openpyxl
import pandas as pd

from excel_reporting.audit import verify
from excel_reporting.cli import main
from excel_reporting.pipeline import run
from excel_reporting.reports.excel import write_excel


def test_end_to_end_all_formats(app_config, tmp_path: Path):
    res = run(app_config)
    assert {p.suffix for p in res.outputs} == {".xlsx", ".pdf", ".html"}
    assert all(p.stat().st_size > 1000 for p in res.outputs)
    assert "customer_email" in res.pii_columns

    html = next(p for p in res.outputs if p.suffix == ".html").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in html
    assert "@example.com" not in html or "***@example.com" in html
    assert "user1@example.com" not in html

    wb = openpyxl.load_workbook(next(p for p in res.outputs if p.suffix == ".xlsx"))
    assert {"Summary", "By region", "By product", "Trend"} <= set(wb.sheetnames)
    assert "Data" not in wb.sheetnames  # data minimisation default
    assert wb["By region"]._charts  # native chart present

    ok, n, _ = verify(app_config.audit.path)
    assert ok and n >= 6


def test_dry_run_writes_nothing(app_config):
    res = run(app_config, dry_run=True)
    assert res.outputs == []
    assert not app_config.report.output_dir.exists()


def test_formula_injection_neutralised(tmp_path: Path, app_config):
    # Build a context via the pipeline pieces, then write a hostile string through the writer.
    from datetime import datetime, timezone

    from excel_reporting.analyze import Analysis
    from excel_reporting.clean import CleaningStats
    from excel_reporting.reports.context import ReportContext

    ctx = ReportContext(
        title="t", classification="X", generated_at=datetime.now(timezone.utc),
        source_name="s.csv", source_sha256="0" * 64,
        analysis=Analysis(overview={"Rows": 1}, metrics=[]),
        cleaning=CleaningStats(), pii_columns=[], pii_action="mask", charts={},
        data=pd.DataFrame({"x": ['=HYPERLINK("http://evil","x")', "+1+1", "@SUM(A1)"]}),
    )
    out = tmp_path / "f.xlsx"
    write_excel(ctx, out)
    ws = openpyxl.load_workbook(out)["Data"]
    for r in (2, 3, 4):
        assert ws.cell(row=r, column=1).data_type == "s"


def test_cli_exit_codes(app_config, tmp_path: Path, capsys):
    assert main(["verify-audit", str(tmp_path / "missing.jsonl")]) == 1
    bad = tmp_path / "bad.yaml"
    bad.write_text("input: {path: x, bogus: 1}\n")
    assert main(["validate-config", "-c", str(bad)]) == 2
    out = capsys.readouterr()
    assert "error" in out.err


def test_security_failure_is_audited(app_config, tmp_path: Path):
    import pytest

    from excel_reporting.config import AppConfig
    from excel_reporting.errors import SecurityError

    data = app_config.model_dump(mode="python")
    data["input"]["allowed_root"] = tmp_path / "elsewhere"
    cfg = AppConfig.model_validate(data)
    with pytest.raises(SecurityError):
        run(cfg)
    assert '"run_failed"' in cfg.audit.path.read_text()
