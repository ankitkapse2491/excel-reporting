"""Input/output hardening: path confinement, file validation, atomic writes, hashing."""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

from .config import InputConfig
from .errors import SecurityError

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}
_MAX_ZIP_ENTRIES = 10_000
_MAX_COMPRESSION_RATIO = 200
_MB = 1024 * 1024


def resolve_within(path: Path, root: Path) -> Path:
    """Resolve ``path`` and ensure it is inside ``root`` (defeats ``..`` and symlink escapes)."""
    resolved = path.expanduser().resolve(strict=False)
    root_resolved = root.expanduser().resolve(strict=False)
    if not resolved.is_relative_to(root_resolved):
        raise SecurityError("Path escapes the permitted directory")
    return resolved


def validate_input_file(cfg: InputConfig) -> Path:
    """Validate the input file before any parser touches it."""
    raw = cfg.path.expanduser()
    if raw.is_symlink():
        raise SecurityError("Symbolic links are not accepted as input")
    root = cfg.allowed_root if cfg.allowed_root is not None else raw.parent
    path = resolve_within(raw, root)
    if not path.is_file():
        raise SecurityError("Input is not an existing regular file")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise SecurityError(f"Unsupported file type (allowed: {sorted(ALLOWED_EXTENSIONS)})")
    if path.stat().st_size > cfg.max_file_mb * _MB:
        raise SecurityError(f"File exceeds size limit of {cfg.max_file_mb} MB")
    if path.suffix.lower() == ".xlsx":
        _inspect_xlsx(path, cfg.max_uncompressed_mb)
    return path


def _inspect_xlsx(path: Path, max_uncompressed_mb: int) -> None:
    """Reject macro-bearing files, zip bombs and malformed containers."""
    if not zipfile.is_zipfile(path):
        raise SecurityError("File is not a valid XLSX container")
    with zipfile.ZipFile(path) as zf:
        infos = zf.infolist()
        if len(infos) > _MAX_ZIP_ENTRIES:
            raise SecurityError("Workbook container has too many entries")
        total = 0
        for info in infos:
            name = info.filename.lower()
            if name.endswith("vbaproject.bin") or "/activex/" in name or "/embeddings/" in name:
                raise SecurityError("Workbook contains macros or embedded objects")
            if ".." in Path(info.filename).parts or info.filename.startswith("/"):
                raise SecurityError("Workbook contains unsafe member paths")
            total += info.file_size
            if info.compress_size and info.file_size / info.compress_size > _MAX_COMPRESSION_RATIO:
                raise SecurityError("Suspicious compression ratio (possible zip bomb)")
        if total > max_uncompressed_mb * _MB:
            raise SecurityError("Workbook uncompressed size exceeds limit")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return (slug or "report")[:max_len]


@contextlib.contextmanager
def atomic_target(final_path: Path) -> Iterator[Path]:
    """Yield a temp path in the same directory; atomically move into place on success.

    Output files are never left half-written, and are created with restrictive
    permissions on POSIX (0o640).
    """
    final_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=final_path.parent, prefix=".tmp_", suffix=final_path.suffix
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        yield tmp
        if os.name == "posix":
            tmp.chmod(0o640)
        os.replace(tmp, final_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
