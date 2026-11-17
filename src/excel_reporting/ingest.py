"""Read CSV / XLSX files safely with row limits."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import InputConfig
from .errors import DataError
from .security import validate_input_file

_CHUNK = 100_000


def load_dataframe(cfg: InputConfig) -> tuple[pd.DataFrame, Path]:
    path = validate_input_file(cfg)
    try:
        if path.suffix.lower() == ".csv":
            df = _read_csv(path, cfg)
        else:
            # pandas opens workbooks via openpyxl in read-only, values-only mode
            # (formulas are never evaluated; defusedxml guards against XML attacks).
            df = pd.read_excel(
                path, sheet_name=cfg.sheet, engine="openpyxl", nrows=cfg.max_rows + 1
            )
    except DataError:
        raise
    except (ValueError, KeyError, UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise DataError(f"Could not parse input file: {type(exc).__name__}") from exc
    if len(df) > cfg.max_rows:
        raise DataError(f"Input exceeds row limit of {cfg.max_rows}")
    if df.empty:
        raise DataError("Input contains no data rows")
    return df, path


def _read_csv(path: Path, cfg: InputConfig) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    rows = 0
    reader = pd.read_csv(
        path,
        encoding=cfg.encoding,
        sep=cfg.delimiter,
        chunksize=_CHUNK,
        on_bad_lines="error",
        skipinitialspace=True,
    )
    for chunk in reader:
        rows += len(chunk)
        if rows > cfg.max_rows:
            raise DataError(f"Input exceeds row limit of {cfg.max_rows}")
        parts.append(chunk)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
