"""Command line interface. Exit codes: 0 ok, 1 error, 2 config, 3 security, 4 data."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .audit import verify
from .config import load_config
from .errors import ReportingError
from .logging_setup import setup_logging
from .pipeline import run


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="excel-reporting", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="Run the reporting pipeline")
    r.add_argument("-c", "--config", required=True, type=Path)
    r.add_argument("--dry-run", action="store_true", help="Process and analyse but write no reports")

    v = sub.add_parser("validate-config", help="Validate a configuration file")
    v.add_argument("-c", "--config", required=True, type=Path)

    a = sub.add_parser("verify-audit", help="Verify the audit log hash chain")
    a.add_argument("path", type=Path)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    log = logging.getLogger("excel_reporting")
    try:
        if args.command == "verify-audit":
            ok, n, msg = verify(args.path)
            print(f"{'OK' if ok else 'FAIL'}: {n} entries checked - {msg}")
            return 0 if ok else 1

        cfg = load_config(args.config)
        setup_logging(cfg.log_level)
        if args.command == "validate-config":
            print("Configuration is valid.")
            return 0

        result = run(cfg, dry_run=args.dry_run)
        print(f"Run {result.run_id}: {result.rows_in} rows read, {result.rows_out} after cleaning; "
              f"PII columns protected: {', '.join(result.pii_columns) or 'none'}")
        for out in result.outputs:
            print(f"  wrote {out}")
        return 0
    except ReportingError as exc:
        log.error(str(exc))
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code
    except Exception as exc:  # noqa: BLE001
        # Never print tracebacks: they may contain data values.
        print(f"unexpected error: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
