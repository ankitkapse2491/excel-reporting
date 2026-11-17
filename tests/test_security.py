from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from excel_reporting.config import InputConfig
from excel_reporting.errors import SecurityError
from excel_reporting.security import atomic_target, resolve_within, validate_input_file


def test_path_traversal_rejected(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(SecurityError):
        resolve_within(root / ".." / "secret.csv", root)


def test_input_outside_allowed_root_rejected(tmp_path: Path):
    (tmp_path / "a").mkdir()
    f = tmp_path / "a" / "x.csv"
    f.write_text("a,b\n1,2\n")
    cfg = InputConfig(path=f, allowed_root=tmp_path / "other")
    with pytest.raises(SecurityError):
        validate_input_file(cfg)


def test_bad_extension_rejected(tmp_path: Path):
    f = tmp_path / "x.xlsm"
    f.write_bytes(b"x")
    with pytest.raises(SecurityError):
        validate_input_file(InputConfig(path=f))


def test_size_limit(tmp_path: Path):
    f = tmp_path / "big.csv"
    f.write_bytes(b"a\n" * (1024 * 1024 + 10))  # ~2 MB
    cfg = InputConfig.model_construct(
        path=f, allowed_root=None, max_file_mb=1, max_uncompressed_mb=10,
        sheet=0, encoding="utf-8", delimiter=",", max_rows=10,
    )
    with pytest.raises(SecurityError):
        validate_input_file(cfg)


def test_macro_workbook_rejected(tmp_path: Path):
    f = tmp_path / "evil.xlsx"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("[Content_Types].xml", "<x/>")
        z.writestr("xl/vbaProject.bin", b"macro")
    with pytest.raises(SecurityError, match="macros"):
        validate_input_file(InputConfig(path=f))


def test_zip_bomb_rejected(tmp_path: Path):
    f = tmp_path / "bomb.xlsx"
    with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/sheet.xml", b"0" * 50_000_000)
    with pytest.raises(SecurityError):
        validate_input_file(InputConfig(path=f))


def test_non_zip_xlsx_rejected(tmp_path: Path):
    f = tmp_path / "fake.xlsx"
    f.write_text("not a zip")
    with pytest.raises(SecurityError):
        validate_input_file(InputConfig(path=f))


def test_atomic_target_cleans_up_on_failure(tmp_path: Path):
    final = tmp_path / "out.txt"
    with pytest.raises(RuntimeError), atomic_target(final) as tmp:
        tmp.write_text("partial")
        raise RuntimeError("boom")
    assert not final.exists()
    assert list(tmp_path.iterdir()) == []
