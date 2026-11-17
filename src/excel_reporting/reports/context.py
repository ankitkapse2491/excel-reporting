"""Shared report inputs and formatting helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from ..analyze import Analysis
from ..clean import CleaningStats


@dataclass
class ReportContext:
    title: str
    classification: str
    generated_at: datetime
    source_name: str
    source_sha256: str
    analysis: Analysis
    cleaning: CleaningStats
    pii_columns: list[str]
    pii_action: str
    charts: dict[str, bytes]
    data: pd.DataFrame | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def generated_str(self) -> str:
        return self.generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")


def fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    if isinstance(value, pd.Timestamp):
        return f"{value:%Y-%m-%d}"
    return "" if value is None or (not isinstance(value, str) and pd.isna(value)) else str(value)


def table_rows(df: pd.DataFrame) -> list[list[str]]:
    return [[fmt(v) for v in row] for row in df.itertuples(index=False, name=None)]
