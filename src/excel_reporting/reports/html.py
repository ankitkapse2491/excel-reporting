"""Self-contained HTML report. Autoescaped templates + strict CSP; no scripts, no remote assets."""

from __future__ import annotations

import base64
from pathlib import Path

from jinja2 import Environment, select_autoescape

from ..security import atomic_target
from .context import ReportContext, table_rows

_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
 content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>{{ title }}</title>
<style>
:root{--fg:#1d2733;--bg:#fff;--muted:#5c6b7a;--acc:#2a6f97;--row:#f2f6f9;--line:#d9e1e8}
@media (prefers-color-scheme:dark){:root{--fg:#e6edf3;--bg:#10161c;--muted:#9aa8b5;--acc:#6bb0d6;--row:#18212a;--line:#2b3744}}
body{font:15px/1.5 system-ui,sans-serif;color:var(--fg);background:var(--bg);margin:0 auto;max-width:980px;padding:24px 16px}
h1{margin:0 0 4px}h2{margin-top:32px;border-bottom:2px solid var(--acc);padding-bottom:4px}
.meta{color:var(--muted);font-size:13px;word-break:break-all}
.badge{display:inline-block;background:var(--acc);color:#fff;border-radius:4px;padding:1px 8px;font-size:12px}
table{border-collapse:collapse;width:100%;font-size:13px;display:block;overflow-x:auto}
th{background:var(--acc);color:#fff;text-align:left}
th,td{padding:5px 9px;border:1px solid var(--line)}tbody tr:nth-child(even){background:var(--row)}
td.n{text-align:right;font-variant-numeric:tabular-nums}
img{max-width:100%;height:auto}figure{margin:16px 0}
</style></head><body>
<h1>{{ title }}</h1>
<p class="meta"><span class="badge">{{ classification }}</span> Generated {{ generated }}<br>
Source: {{ source_name }}<br>SHA-256: {{ sha }}</p>
<h2>Overview</h2>
<table><tbody>{% for k, v in overview %}<tr><th>{{ k }}</th><td>{{ v }}</td></tr>{% endfor %}</tbody></table>
<p class="meta">Privacy: <b>{{ pii_action }}</b> applied to {{ pii_cols or 'no detected PII columns' }}.</p>
{% if charts %}<h2>Charts</h2>{% for t, b64 in charts %}
<figure><img alt="{{ t }}" src="data:image/png;base64,{{ b64 }}"><figcaption class="meta">{{ t }}</figcaption></figure>
{% endfor %}{% endif %}
{% for key, header, rows in groups %}<h2>Summary by {{ key }}</h2>
<table><thead><tr>{% for h in header %}<th>{{ h }}</th>{% endfor %}</tr></thead><tbody>
{% for r in rows %}<tr>{% for c in r %}<td{% if not loop.first %} class="n"{% endif %}>{{ c }}</td>{% endfor %}</tr>{% endfor %}
</tbody></table>{% endfor %}
</body></html>
"""

_env = Environment(autoescape=select_autoescape(default=True, default_for_string=True))
_tpl = _env.from_string(_TEMPLATE)


def write_html(ctx: ReportContext, out_path: Path) -> None:
    groups = []
    for key, table in ctx.analysis.group_tables.items():
        rounded = table.round(2)
        groups.append((key, [str(c) for c in rounded.columns], table_rows(rounded)))
    html = _tpl.render(
        title=ctx.title,
        classification=ctx.classification,
        generated=ctx.generated_str,
        source_name=ctx.source_name,
        sha=ctx.source_sha256,
        overview=[(k, str(v)) for k, v in ctx.analysis.overview.items()],
        pii_action=ctx.pii_action,
        pii_cols=", ".join(ctx.pii_columns),
        charts=[(t, base64.b64encode(b).decode("ascii")) for t, b in ctx.charts.items()],
        groups=groups,
    )
    with atomic_target(out_path) as tmp:
        tmp.write_text(html, encoding="utf-8")
