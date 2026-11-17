"""Tamper-evident audit trail: append-only JSONL, each entry hash-chained to the previous.

Entries record *metadata only* (who/when/what file hash/which columns/counts) and never
row-level data. Editing, deleting or reordering any line breaks the chain, which
``verify`` detects. For stronger guarantees ship the log to WORM/immutable storage or a SIEM.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_GENESIS = "0" * 64


def _digest(prev: str, body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256((prev + canonical).encode()).hexdigest()


def _actor() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001  # pragma: no cover
        return "unknown"


class AuditLog:
    def __init__(self, path: Path, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seq, self._prev = self._tail()

    def _tail(self) -> tuple[int, str]:
        if not self.path.exists():
            return 0, _GENESIS
        last = None
        with self.path.open("rb") as fh:
            for line in fh:
                if line.strip():
                    last = line
        if last is None:
            return 0, _GENESIS
        entry = json.loads(last)
        return int(entry["seq"]), str(entry["hash"])

    def record(self, event: str, **details: Any) -> None:
        self._seq += 1
        body = {
            "seq": self._seq,
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "run_id": self.run_id,
            "actor": _actor(),
            "host": platform.node(),
            "event": event,
            "details": details,
            "prev": self._prev,
        }
        entry_hash = _digest(self._prev, body)
        entry = {**body, "hash": entry_hash}
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        fd = os.open(self.path, flags, 0o640)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True, ensure_ascii=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._prev = entry_hash


def verify(path: Path) -> tuple[bool, int, str]:
    """Return (ok, entries_checked, message)."""
    if not path.is_file():
        return False, 0, "audit log not found"
    prev, expected_seq = _GENESIS, 1
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                claimed = entry.pop("hash")
            except (ValueError, KeyError):
                return False, n - 1, f"line {n}: malformed entry"
            if entry.get("seq") != expected_seq or entry.get("prev") != prev:
                return False, n - 1, f"line {n}: chain broken (entry removed/reordered)"
            if _digest(prev, entry) != claimed:
                return False, n - 1, f"line {n}: hash mismatch (entry modified)"
            prev, expected_seq = claimed, expected_seq + 1
    return True, expected_seq - 1, "chain intact"
