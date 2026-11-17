"""Exception hierarchy. Each maps to a distinct CLI exit code."""


class ReportingError(Exception):
    """Base error. Messages must never contain row-level data values."""

    exit_code = 1


class ConfigError(ReportingError):
    exit_code = 2


class SecurityError(ReportingError):
    exit_code = 3


class DataError(ReportingError):
    exit_code = 4
