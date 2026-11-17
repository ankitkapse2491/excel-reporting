"""Summary statistics for reports."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .clean import normalize_name
from .config import ReportConfig
from .errors import ConfigError

SUPPRESSED_LABEL = "Suppressed (small n)"
_MAX_AUTO_METRICS = 5


@dataclass
class Analysis:
    overview: dict[str, object]
    metrics: list[str]
    group_tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    trend: pd.DataFrame | None = None
    describe: pd.DataFrame | None = None
    date_column: str | None = None
    totals: dict[str, float] = field(default_factory=dict)


def _resolve(name: str, df: pd.DataFrame, what: str) -> str:
    for cand in (name, normalize_name(name)):
        if cand in df.columns:
            return cand
    raise ConfigError(f"{what} column not found in data")


def analyze(df: pd.DataFrame, cfg: ReportConfig) -> Analysis:
    date_col = _resolve(cfg.date_column, df, "date") if cfg.date_column else None
    if date_col and not pd.api.types.is_datetime64_any_dtype(df[date_col]):
        raise ConfigError("date_column must be listed in cleaning.date_columns")

    if cfg.metrics:
        metrics = [_resolve(m, df, "metric") for m in cfg.metrics]
        for m in metrics:
            if not pd.api.types.is_numeric_dtype(df[m]):
                raise ConfigError("Metric columns must be numeric")
    else:
        metrics = list(df.select_dtypes(include="number").columns)[:_MAX_AUTO_METRICS]

    groups = [_resolve(g, df, "group_by") for g in cfg.group_by]
    overview: dict[str, object] = {
        "Rows": len(df),
        "Columns": df.shape[1],
        "Missing cells": int(df.isna().sum().sum()),
        "Metrics": ", ".join(metrics) or "(none)",
    }
    if date_col and df[date_col].notna().any():
        overview["Date range"] = f"{df[date_col].min():%Y-%m-%d} to {df[date_col].max():%Y-%m-%d}"

    result = Analysis(overview=overview, metrics=metrics, date_column=date_col)
    result.totals = {m: float(df[m].sum()) for m in metrics}
    for g in groups:
        result.group_tables[g] = _group_table(df, g, metrics, cfg.top_n, cfg.min_group_size)
    if metrics:
        result.describe = df[metrics].describe().T.reset_index(names="metric")
    if date_col:
        tmp = df.dropna(subset=[date_col]).set_index(date_col)
        if metrics:
            trend = tmp[metrics].resample("MS").sum()
        else:
            trend = tmp.iloc[:, 0].resample("MS").size().rename("count").to_frame()
        result.trend = trend.reset_index().rename(columns={date_col: "period"})
    return result


def _agg(frame: pd.DataFrame, key: str, metrics: list[str]) -> pd.DataFrame:
    grp = frame.groupby(key, dropna=False, observed=True)
    out = grp.size().rename("count").to_frame()
    for m in metrics:
        out[f"{m}_sum"] = grp[m].sum()
        out[f"{m}_mean"] = grp[m].mean()
    out = out.reset_index()
    out[key] = out[key].astype(str)
    result: pd.DataFrame = out
    return result


def _group_table(
    df: pd.DataFrame, key: str, metrics: list[str], top_n: int, min_size: int
) -> pd.DataFrame:
    table = _agg(df, key, metrics)
    if min_size > 1:
        small_values = set(table.loc[table["count"] < min_size, key])
        if small_values:
            as_str = df[key].astype(str)
            relabeled = as_str.where(~as_str.isin(small_values), SUPPRESSED_LABEL)
            table = _agg(df.assign(**{key: relabeled}), key, metrics)
    sort_col = f"{metrics[0]}_sum" if metrics else "count"
    table = table.sort_values(sort_col, ascending=False)
    top: pd.DataFrame = table.head(top_n).reset_index(drop=True)
    return top
