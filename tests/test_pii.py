from __future__ import annotations

import pandas as pd
import pytest

from excel_reporting.config import PiiConfig
from excel_reporting.errors import ConfigError
from excel_reporting.pii import protect


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "customer_email": ["a@x.com", "b@y.org"],
            "contact": ["123-45-6789", "987-65-4321"],  # detected by content (SSN pattern)
            "card_no": ["4111 1111 1111 1111", "5500 0000 0000 0004"],
            "region": ["N", "S"],
            "revenue": [10.0, 20.0],
        }
    )


def test_mask_detects_and_masks(df):
    out, rep = protect(df, PiiConfig())
    assert set(rep.columns) == {"customer_email", "contact", "card_no"}
    assert out["customer_email"].tolist() == ["***@x.com", "***@y.org"]
    assert out["card_no"].iloc[0] == "****-****-****-1111"
    assert "123-45-6789" not in out["contact"].tolist()
    assert out["region"].tolist() == ["N", "S"]


def test_drop(df):
    out, _ = protect(df, PiiConfig(action="drop"))
    assert list(out.columns) == ["region", "revenue"]


def test_hash_requires_key(df, monkeypatch):
    monkeypatch.delenv("REPORT_PII_SALT", raising=False)
    with pytest.raises(ConfigError):
        protect(df, PiiConfig(action="hash"))


def test_hash_is_keyed_and_deterministic(df, monkeypatch):
    monkeypatch.setenv("REPORT_PII_SALT", "k" * 32)
    a, _ = protect(df, PiiConfig(action="hash"))
    b, _ = protect(df, PiiConfig(action="hash"))
    assert a["customer_email"].tolist() == b["customer_email"].tolist()
    assert a["customer_email"].iloc[0].startswith("h_")
    monkeypatch.setenv("REPORT_PII_SALT", "z" * 32)
    c, _ = protect(df, PiiConfig(action="hash"))
    assert c["customer_email"].iloc[0] != a["customer_email"].iloc[0]


def test_explicit_missing_column_errors(df):
    with pytest.raises(ConfigError):
        protect(df, PiiConfig(columns=["nope"]))


def test_disabled_passthrough(df):
    out, rep = protect(df, PiiConfig(enabled=False))
    assert out.equals(df) and rep.action == "disabled"
