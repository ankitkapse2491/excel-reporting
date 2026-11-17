from __future__ import annotations

import pandas as pd
import pytest

from excel_reporting.analyze import SUPPRESSED_LABEL, analyze
from excel_reporting.clean import clean, normalize_name
from excel_reporting.config import CleaningConfig, ReportConfig
from excel_reporting.errors import ConfigError


def test_normalize_name():
    assert normalize_name(" Order Date (UTC)") == "order_date_utc"


def test_clean_pipeline():
    df = pd.DataFrame(
        {
            "Region ": [" N ", "N", "N", None, None],
            "Amount": ["1", "1", "x", "5", None],
            "When": ["2025-01-01", "2025-01-01", "bad", "2025-02-01", None],
        }
    )
    out, stats = clean(
        df,
        CleaningConfig(date_columns=["when"], numeric_columns=["amount"], missing_numeric="zero"),
    )
    assert list(out.columns) == ["region", "amount", "when"]
    assert stats.duplicates_dropped == 1
    assert stats.unparseable_numbers == 1 and stats.unparseable_dates == 1
    assert stats.empty_rows_dropped == 1
    assert out["amount"].notna().all()


def test_clean_unknown_column_raises():
    with pytest.raises(ConfigError):
        clean(pd.DataFrame({"a": [1]}), CleaningConfig(numeric_columns=["zzz"]))


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "g": ["a"] * 6 + ["b"] * 5 + ["c"],
            "v": range(12),
            "d": pd.date_range("2025-01-01", periods=12, freq="15D"),
        }
    )


def test_group_and_trend():
    a = analyze(_frame(), ReportConfig(output_dir=".", group_by=["g"], metrics=["v"], date_column="d"))
    t = a.group_tables["g"]
    assert t.iloc[0]["g"] == "a" or t.iloc[0]["v_sum"] >= t.iloc[-1]["v_sum"]
    assert a.trend is not None and len(a.trend) >= 5


def test_small_cell_suppression():
    a = analyze(_frame(), ReportConfig(output_dir=".", group_by=["g"], metrics=["v"], min_group_size=5))
    labels = set(a.group_tables["g"]["g"])
    assert "c" not in labels and SUPPRESSED_LABEL in labels


def test_non_numeric_metric_rejected():
    with pytest.raises(ConfigError):
        analyze(_frame(), ReportConfig(output_dir=".", metrics=["g"]))
