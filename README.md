# Excel Reporting

Secure, auditable automated reporting from Excel and CSV files.

**Pipeline:** read (CSV/XLSX) -> clean -> detect and protect PII -> summarise -> charts -> reports (XLSX with native charts, PDF, self-contained HTML).

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"

python scripts/make_sample_data.py          # synthetic data with fake PII -> data/input/sales.csv
cp config/pipeline.example.yaml config/pipeline.yaml
excel-reporting validate-config -c config/pipeline.yaml
excel-reporting run -c config/pipeline.yaml
excel-reporting verify-audit data/audit/audit.jsonl
```

Reports land in `data/output/`. Use `--dry-run` to process without writing reports.
Exit codes: `0` ok, `1` error, `2` config, `3` security, `4` data.

### Scheduling

Any scheduler can call the CLI: Windows Task Scheduler, cron, or CI.

```bash
excel-reporting run -c /etc/excel-reporting/pipeline.yaml
```

### Docker

```bash
docker build -t excel-reporting .
docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges --network none \
  -v "$PWD/config:/app/config:ro" -v "$PWD/data/input:/app/data/input:ro" \
  -v "$PWD/data/output:/app/data/output" -v "$PWD/data/audit:/app/data/audit" \
  -e REPORT_PII_SALT excel-reporting run -c /app/config/pipeline.yaml
```

## Layout

| Path | Purpose |
|---|---|
| `src/excel_reporting/config.py` | Strict pydantic config; YAML via `safe_load`; error text never echoes values |
| `security.py` | Path confinement, extension/size/zip-bomb/macro checks, atomic writes |
| `ingest.py`, `clean.py` | Safe parsing with row caps; deterministic cleaning with statistics |
| `pii.py` | Name- and content-based PII detection; mask / HMAC-hash / drop |
| `analyze.py`, `charts.py` | Group/trend summaries (small-cell suppression), matplotlib charts |
| `reports/` | XLSX (native charts), PDF, HTML writers |
| `audit.py` | Hash-chained, tamper-evident JSONL audit log |

## Development

```bash
pytest --cov          # tests
ruff check . && mypy src && bandit -r src -ll
```

CI (`.github/workflows/ci.yml`) runs lint, types, tests on Python 3.10/3.12/3.13, SAST, `pip-audit`, SBOM generation and secret scanning.

See [SECURITY.md](SECURITY.md) and [docs/COMPLIANCE.md](docs/COMPLIANCE.md).
