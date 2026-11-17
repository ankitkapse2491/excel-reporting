"""Deterministic data cleaning."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

import pandas as pd

from .config import CleaningConfig
from .errors import ConfigError


def normalize_name(name: object) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", str(name)).strip("_").lower()
    return s or "column"


@dataclass
class CleaningStats:
    rows_in: int = 0
    rows_out: int = 0
    empty_rows_dropped: int = 0
    duplicates_dropped: int = 0
    missing_dropped: int = 0
    unparseable_dates: int = 0
    unparseable_numbers: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def clean(df: pd.DataFrame, cfg: CleaningConfig) -> tuple[pd.DataFrame, CleaningStats]:
    stats = CleaningStats(rows_in=len(df))
    df = df.copy()

    if cfg.normalize_columns:
        new_cols: list[str] = []
        for c in df.columns:
            base = normalize_name(c)
            name, i = base, 2
            while name in new_cols:  # keep names unique
                name, i = f"{base}_{i}", i + 1
            new_cols.append(name)
        df.columns = new_cols

    def col(name: str) -> str:
        key = normalize_name(name) if cfg.normalize_columns else name
        if key not in df.columns:
            raise ConfigError("Configured column not found in data (check names/normalisation)")
        return key

    if cfg.strip_strings:
        for c in df.select_dtypes(include=["object", "string"]).columns:
            df[c] = df[c].map(lambda v: v.strip() if isinstance(v, str) else v)
            df[c] = df[c].replace("", pd.NA)

    if cfg.drop_empty_rows:
        before = len(df)
        df = df.dropna(how="all")
        stats.empty_rows_dropped = before - len(df)

    for name in cfg.date_columns:
        c = col(name)
        parsed = pd.to_datetime(df[c], errors="coerce", format="mixed")
        stats.unparseable_dates += int((parsed.isna() & df[c].notna()).sum())
        df[c] = parsed

    for name in cfg.numeric_columns:
        c = col(name)
        parsed_n = pd.to_numeric(df[c], errors="coerce")
        stats.unparseable_numbers += int((parsed_n.isna() & df[c].notna()).sum())
        df[c] = parsed_n

    num_cols = df.select_dtypes(include="number").columns
    if cfg.missing_numeric == "drop" and len(num_cols):
        before = len(df)
        df = df.dropna(subset=list(num_cols))
        stats.missing_dropped = before - len(df)
    elif cfg.missing_numeric in {"zero", "median", "mean"}:
        for c in num_cols:
            fill = {
                "zero": 0,
                "median": df[c].median(),
                "mean": df[c].mean(),
            }[cfg.missing_numeric]
            df[c] = df[c].fillna(fill)

    if cfg.missing_text is not None:
        for c in df.select_dtypes(include=["object", "string"]).columns:
            df[c] = df[c].fillna(cfg.missing_text)

    if cfg.drop_duplicates:
        before = len(df)
        df = df.drop_duplicates()
        stats.duplicates_dropped = before - len(df)

    df = df.reset_index(drop=True)
    stats.rows_out = len(df)
    return df, stats
