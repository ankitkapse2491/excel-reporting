# Security

## Reporting a vulnerability

Email your security contact (set one before go-live) with details and reproduction steps. Do not open public issues for vulnerabilities.

## Threat model and controls

| Threat | Control | Where |
|---|---|---|
| Path traversal / symlink escape | Input must resolve inside `allowed_root`; symlinks rejected; output names are slugged and re-confined | `security.py`, `pipeline.py` |
| Malicious workbooks (macros, zip bombs, XML attacks) | `.xlsm`/`.xls` rejected; `vbaProject.bin`, ActiveX and embeddings rejected; compression-ratio and uncompressed-size caps; `defusedxml`; values-only, read-only parsing so formulas never run | `security.py`, `ingest.py` |
| Resource exhaustion | File size, row count and entry-count limits; chunked CSV | `config.py`, `ingest.py` |
| Formula injection in output | Strings written with explicit string cell type | `reports/excel.py` |
| XSS in HTML report | Jinja2 autoescape; CSP `default-src 'none'`; no scripts or remote assets | `reports/html.py` |
| PII leakage | Detection plus mask/hash/drop *before* analysis; row-level data excluded by default; small-cell suppression | `pii.py`, `analyze.py` |
| Secrets in code/config | HMAC key read from an environment variable only; `.gitignore`, gitleaks in CI and pre-commit | `pii.py` |
| Log leakage | Logs and errors carry metadata only; no tracebacks to stdout | `logging_setup.py`, `cli.py` |
| Tampered audit trail | Hash-chained append-only log with `verify-audit` | `audit.py` |
| Partial/corrupt outputs | Atomic temp-file write and replace; 0o640 on POSIX | `security.py` |
| Supply chain | Bounded dependency ranges, Dependabot, `pip-audit`, CycloneDX SBOM | CI |
| Container escape | Non-root user, read-only rootfs, dropped caps, no network | `Dockerfile` |

## Known limitations

- The audit log is tamper-*evident*, not tamper-*proof*. An attacker with write access can truncate it or rewrite the entire chain. Forward it to immutable/WORM storage or a SIEM.
- Concurrent runs writing the same audit file are not locked. Use one writer per audit file or a separate file per job.
- PII detection is heuristic. Review `pii.columns` for each new dataset; PII in free-text columns is not detected.
- Reports and the audit log are not encrypted at rest by the application. Use disk/volume encryption (BitLocker, LUKS) or an encrypted share.
- Pin hashes for production installs: `pip-compile --generate-hashes` and `pip install --require-hashes`.
