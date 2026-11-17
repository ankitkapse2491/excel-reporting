# Compliance mapping

> This software provides **technical controls that support** GDPR, HIPAA, PCI DSS and SOC 2 / ISO 27001 programmes. It is not certified, and compliance is an organisational property. Legal basis, DPAs, access control, retention schedules, risk assessments and incident response must be provided by your organisation. Have your compliance team review this before processing regulated data.

## GDPR

| Requirement | Support in this project | Your responsibility |
|---|---|---|
| Data minimisation (Art. 5(1)(c), 25) | PII masked/hashed/dropped before analysis; row-level data excluded unless `include_data_sheet: true` | Set `include_data_sheet` deliberately; drop unneeded columns |
| Pseudonymisation (Art. 4(5), 32) | `hash` action: keyed HMAC-SHA256; key held outside the data in an env var | Manage and rotate the key in a secrets manager |
| Integrity / confidentiality (Art. 32) | Input validation, atomic writes, restrictive file modes, container hardening | Encryption at rest, access control on input/output folders |
| Accountability (Art. 5(2), 30) | Audit log of who/when/which file hash/which PII columns | Retain per policy; record processing activities |
| Storage limitation (Art. 5(1)(e)) | Reports carry generation time and classification | Delete reports and inputs per retention schedule |
| Erasure / access requests | Inputs are never modified; outputs are regenerable | Delete or regenerate outputs after source changes |

## HIPAA (if processing PHI)

- Set `pii.action: drop` or `hash`; add health identifiers to `pii.columns` (MRN, diagnosis codes where applicable); set `report.min_group_size` to at least 5 for small-cell suppression.
- No PHI in logs or the audit log (metadata only).
- Required outside this tool: BAA, access controls, encryption at rest and in transit, workforce training, breach procedures. Use the Docker `--network none` mode.

## PCI DSS (if cardholder data is present)

- Card-like columns are detected by name and Luhn-validated content. `mask` keeps only the last four digits (PCI DSS 3.4 allows truncation); `hash` is keyed; `drop` removes the column.
- **Best practice: do not feed full PANs into this tool.** Scope reduction upstream is far safer than relying on detection.
- Outputs and audit logs never contain full PANs when a PII action is enabled. Keep it enabled.

## SOC 2 / ISO 27001

| Control area | Evidence |
|---|---|
| Change management | CI gates: ruff, mypy (strict), pytest + coverage, PR-based workflow |
| Vulnerability management | bandit, pip-audit, Dependabot, SBOM artifact per build |
| Secrets management | No secrets in repo/config; gitleaks (CI + pre-commit) |
| Logging and monitoring | Structured JSON logs to stderr; tamper-evident audit log with verification command |
| Secure development | Strict typing, input validation, tests for security controls (`tests/test_security.py`) |
| Availability / integrity | Atomic output writes; deterministic exit codes for scheduler alerting |
| Access control | Run under a least-privilege service account; restrict input/output/audit directories |

## Recommended deployment checklist

- [ ] Dedicated low-privilege service account; folders ACL-restricted
- [ ] Volume/disk encryption enabled
- [ ] `REPORT_PII_SALT` stored in a secrets manager, rotated, >= 32 random characters
- [ ] Audit log shipped to immutable storage / SIEM; `verify-audit` scheduled
- [ ] Retention/deletion job for `data/output` and inputs
- [ ] Hash-pinned dependency install; SBOM archived per release
- [ ] Branch protection and required CI checks on `main`
