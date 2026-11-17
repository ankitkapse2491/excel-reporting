"""PII detection and protection (mask / keyed-hash / drop).

Detection combines column-name heuristics with content sampling. Findings record
only column names and categories, never values. Protection runs *before* analysis
and report generation so raw identifiers never reach any output (data minimisation).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .clean import normalize_name
from .config import PiiConfig
from .errors import ConfigError

_NAME_HINTS: dict[str, tuple[str, ...]] = {
    "email": ("email", "e_mail"),
    "phone": ("phone", "mobile", "tel", "fax"),
    "ssn": ("ssn", "social_security", "national_id", "passport", "tax_id", "nino"),
    "card": ("card", "pan", "credit", "cc_num", "iban", "account_number"),
    "name": ("first_name", "last_name", "full_name", "surname", "customer_name", "patient"),
    "address": ("address", "street", "postcode", "zip", "postal"),
    "dob": ("dob", "birth"),
    "ip": ("ip_address", "ip_addr"),
    "health": ("diagnosis", "mrn", "medical", "insurance_id", "policy_number"),
}

_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"),
    "ssn": re.compile(r"^\d{3}-\d{2}-\d{4}$"),
    "phone": re.compile(r"^\+?[\d\s().-]{9,18}$"),
    "ip": re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$"),
    "card": re.compile(r"^\d[\d -]{11,22}\d$"),
}
_SAMPLE = 1000
_MATCH_RATIO = 0.6


def _luhn(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d *= 2
            d -= 9 if d > 9 else 0
        total += d
    return total % 10 == 0


@dataclass
class PiiReport:
    protected: dict[str, str] = field(default_factory=dict)  # column -> category
    action: str = "none"

    @property
    def columns(self) -> list[str]:
        return sorted(self.protected)


def detect_pii(df: pd.DataFrame, explicit: list[str], auto: bool) -> dict[str, str]:
    found: dict[str, str] = {}
    for name in explicit:
        key = normalize_name(name)
        if key not in df.columns and name not in df.columns:
            raise ConfigError("Configured PII column not found in data")
        found[key if key in df.columns else name] = "explicit"
    if not auto:
        return found
    for c in df.columns:
        if c in found:
            continue
        for category, hints in _NAME_HINTS.items():
            if any(h in c for h in hints):
                found[c] = category
                break
        else:
            if df[c].dtype == object or str(df[c].dtype) == "string":
                sample = df[c].dropna().astype(str).head(_SAMPLE)
                if sample.empty:
                    continue
                for category, pat in _PATTERNS.items():
                    ratio = sample.map(lambda v, p=pat: bool(p.match(v))).mean()
                    if ratio >= _MATCH_RATIO:
                        if category == "card" and sample.map(_luhn).mean() < _MATCH_RATIO:
                            continue
                        found[c] = category
                        break
    return found


def _mask(value: Any, category: str) -> Any:
    if pd.isna(value):
        return value
    s = str(value)
    if category == "email" and "@" in s:
        return "***@" + s.rsplit("@", 1)[1]
    if category == "card":
        digits = re.sub(r"\D", "", s)
        return "****-****-****-" + digits[-4:] if len(digits) >= 4 else "****"
    return "***MASKED***"


def _get_key(env_name: str) -> bytes:
    key = os.environ.get(env_name, "")
    if len(key) < 16:
        raise ConfigError(
            f"PII action 'hash' requires environment variable {env_name} (>=16 characters)"
        )
    return key.encode("utf-8")


def protect(df: pd.DataFrame, cfg: PiiConfig) -> tuple[pd.DataFrame, PiiReport]:
    if not cfg.enabled:
        return df, PiiReport(action="disabled")
    found = detect_pii(df, cfg.columns, cfg.auto_detect)
    report = PiiReport(protected=found, action=cfg.action)
    if not found:
        return df, report
    df = df.copy()
    if cfg.action == "drop":
        return df.drop(columns=list(found)), report
    if cfg.action == "hash":
        key = _get_key(cfg.salt_env)

        def h(v: Any) -> Any:
            if pd.isna(v):
                return v
            return "h_" + hmac.new(key, str(v).encode(), hashlib.sha256).hexdigest()[:16]

        for c in found:
            df[c] = df[c].map(h)
    else:
        for c, category in found.items():
            df[c] = df[c].map(lambda v, cat=category: _mask(v, cat))
    return df, report
