from __future__ import annotations

from pathlib import Path

from excel_reporting.audit import AuditLog, verify


def _make(path: Path) -> None:
    log = AuditLog(path, "run1")
    for i in range(4):
        log.record("event", n=i)


def test_chain_valid_and_resumes(tmp_path: Path):
    p = tmp_path / "a.jsonl"
    _make(p)
    AuditLog(p, "run2").record("later")  # new instance continues the chain
    ok, n, _ = verify(p)
    assert ok and n == 5


def test_tamper_detected(tmp_path: Path):
    p = tmp_path / "a.jsonl"
    _make(p)
    p.write_text(p.read_text().replace('"n": 1', '"n": 99'))
    assert verify(p)[0] is False


def test_deletion_detected(tmp_path: Path):
    p = tmp_path / "a.jsonl"
    _make(p)
    lines = p.read_text().splitlines()
    del lines[1]
    p.write_text("\n".join(lines) + "\n")
    ok, _, msg = verify(p)
    assert not ok and "chain" in msg
