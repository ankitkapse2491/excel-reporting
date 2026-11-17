from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from make_sample_data import make  # noqa: E402

from excel_reporting.config import AppConfig  # noqa: E402


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    d = tmp_path / "in"
    d.mkdir()
    p = d / "sales.csv"
    make(300).to_csv(p, index=False)
    return p


@pytest.fixture
def app_config(tmp_path: Path, sample_csv: Path) -> AppConfig:
    return AppConfig.model_validate(
        {
            "input": {"path": sample_csv, "allowed_root": sample_csv.parent},
            "cleaning": {
                "date_columns": ["order_date"],
                "numeric_columns": ["quantity", "unit_price", "revenue"],
                "missing_numeric": "median",
            },
            "report": {
                "title": "Test Report",
                "output_dir": tmp_path / "out",
                "group_by": ["region", "product"],
                "metrics": ["revenue"],
                "date_column": "order_date",
            },
            "audit": {"path": tmp_path / "audit" / "audit.jsonl"},
        }
    )
