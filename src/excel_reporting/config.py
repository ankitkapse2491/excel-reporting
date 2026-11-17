"""Strictly validated, declarative configuration (YAML parsed with safe_load)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .errors import ConfigError

_MAX_CONFIG_BYTES = 256 * 1024


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InputConfig(_Base):
    path: Path
    allowed_root: Path | None = Field(
        default=None,
        description="Input must resolve inside this directory. Defaults to the file's parent.",
    )
    sheet: str | int = 0
    encoding: str = "utf-8"
    delimiter: str = Field(",", min_length=1, max_length=1)
    max_file_mb: int = Field(50, ge=1, le=1024)
    max_uncompressed_mb: int = Field(500, ge=1, le=4096)
    max_rows: int = Field(1_000_000, ge=1)


class CleaningConfig(_Base):
    normalize_columns: bool = True
    strip_strings: bool = True
    drop_empty_rows: bool = True
    drop_duplicates: bool = True
    date_columns: list[str] = Field(default_factory=list)
    numeric_columns: list[str] = Field(default_factory=list)
    missing_numeric: Literal["none", "zero", "median", "mean", "drop"] = "none"
    missing_text: str | None = "Unknown"


class PiiConfig(_Base):
    enabled: bool = True
    action: Literal["mask", "hash", "drop"] = "mask"
    columns: list[str] = Field(default_factory=list, description="Explicit PII columns.")
    auto_detect: bool = True
    salt_env: str = Field(
        "REPORT_PII_SALT", description="Env var holding the HMAC key (hash action only)."
    )


class ReportConfig(_Base):
    title: str = Field("Automated Report", min_length=1, max_length=120)
    output_dir: Path
    formats: list[Literal["xlsx", "pdf", "html"]] = Field(
        default=["xlsx", "pdf", "html"], min_length=1
    )
    group_by: list[str] = Field(default_factory=list, max_length=5)
    metrics: list[str] = Field(default_factory=list, max_length=10)
    date_column: str | None = None
    top_n: int = Field(10, ge=1, le=100)
    min_group_size: int = Field(
        1, ge=1, description="Groups smaller than this are merged into 'Suppressed (small n)'."
    )
    include_data_sheet: bool = Field(
        False, description="Data minimisation: row-level data is excluded by default."
    )
    data_sheet_max_rows: int = Field(100_000, ge=1, le=1_000_000)
    classification: str = Field("INTERNAL", max_length=40)


class AuditConfig(_Base):
    path: Path = Path("audit/audit.jsonl")


class AppConfig(_Base):
    input: InputConfig
    cleaning: CleaningConfig = CleaningConfig()
    pii: PiiConfig = PiiConfig()
    report: ReportConfig
    audit: AuditConfig = AuditConfig()
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


def load_config(path: str | Path) -> AppConfig:
    p = Path(path)
    try:
        if not p.is_file():
            raise ConfigError(f"Config file not found: {p.name}")
        if p.stat().st_size > _MAX_CONFIG_BYTES:
            raise ConfigError("Config file too large")
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a mapping")
    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        # Pydantic error text may echo input values; report locations + types only.
        details = "; ".join(
            f"{'.'.join(map(str, e['loc']))}: {e['type']}" for e in exc.errors()
        )
        raise ConfigError(f"Invalid configuration: {details}") from exc
