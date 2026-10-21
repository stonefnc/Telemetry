"""One page HTML weekly SLA report built from the SQL views. No external assets, charts are inline SVG."""
from datetime import date, timedelta
from decimal import Decimal
from html import escape

W, H, PAD = 720, 180, 28


def _bars(values, label):
    top = max(values) or 1
    bw = (W - 2 * PAD) / len(values)
    bars = "".join(
        f'<rect x="{PAD + i * bw:.1f}" y="{H - PAD - v / top * (H - 2 * PAD):.1f}" '
        f'width="{max(bw - 1, 1):.1f}" height="{v / top * (H - 2 * PAD):.1f}" fill="#4a6fa5"/>'
        for i, v in enumerate(values))
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{escape(label)}">{bars}'
            f'<text x="{PAD}" y="12" font-size="11">max {top}</text></svg>')


def _lines(series, label):
    """series: {name: (colour, [values 0-100 or None])}"""
    n = max(len(v) for _, v in series.values())
    step = (W - 2 * PAD) / max(n - 1, 1)
    out = []
    for name, (colour, vals) in series.items():
        pts = " ".join(f"{PAD + i * step:.1f},{H - PAD - v / 100 * (H - 2 * PAD):.1f}"
                       for i, v in enumerate(vals) if v is not None)
        out.append(f'<polyline fill="none" stroke="{colour}" stroke-width="2" points="{pts}"/>')
    legend = "".join(f'<text x="{PAD + 110 * i}" y="12" font-size="11" fill="{c}">{escape(nm)}</text>'
                     for i, (nm, (c, _)) in enumerate(series.items()))
    axis = (f'<line x1="{PAD}" y1="{H - PAD}" x2="{W - PAD}" y2="{H - PAD}" stroke="#999"/>'
            f'<text x="2" y="{PAD}" font-size="10">100%</text><text x="2" y="{H - PAD}" font-size="10">0%</text>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{escape(label)}">{axis}{"".join(out)}{legend}</svg>'


def _table(headers, rows):
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{'' if c is None else escape(str(c))}</td>" for c in r) + "</tr>"
                   for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def build_report(conn):
    # PostgreSQL returns numeric as Decimal, show it the way SQLite shows a float
    q = lambda sql: [tuple(float(v) if isinstance(v, Decimal) else v for v in r) for r in conn.execute(sql).fetchall()]
    found = q("SELECT week, created, resolved, close_rate, avg_first_response_hours, avg_resolution_hours, "
              "response_sla_pct, resolution_sla_pct FROM weekly_summary ORDER BY week")
    if not found:
        raise ValueError("no tickets loaded, nothing to report")
    # fill weeks without tickets so the charts keep a true time axis and "latest 8 weeks" is 8 calendar weeks
    known, weeks, day = {w[0]: w for w in found}, [], date.fromisoformat(found[0][0])
    while day <= date.fromisoformat(found[-1][0]):
        weeks.append(known.get(day.isoformat(), (day.isoformat(), 0, 0, None, None, None, None, None)))
        day += timedelta(days=7)
    total = q("SELECT COUNT(*), COUNT(resolution_hours), ROUND(AVG(response_hours), 1), "
              "ROUND(AVG(resolution_hours), 1), ROUND(100.0 * AVG(response_met), 1), "
              "ROUND(100.0 * AVG(resolution_met), 1) FROM ticket_facts")[0]
    by_cat = q("SELECT category, COUNT(*), ROUND(AVG(response_hours), 1), ROUND(AVG(resolution_hours), 1), "
               "ROUND(100.0 * AVG(response_met), 1), ROUND(100.0 * AVG(resolution_met), 1) AS res_sla "
               "FROM ticket_facts GROUP BY category ORDER BY res_sla NULLS LAST")
    backlog = q("SELECT bucket, tickets FROM backlog_age_buckets ORDER BY bucket")
    as_of = q("SELECT substr(CAST(ts AS TEXT), 1, 10) FROM as_of")[0][0]
    kpi = _table(["Tickets", "Resolved", "Avg first response (h)", "Avg resolution (h)", "Response SLA %", "Resolution SLA %"],
                 [total])
    latest = _table(["Week", "Created", "Resolved", "Close rate", "Avg first response (h)", "Avg resolution (h)",
                     "Response SLA %", "Resolution SLA %"], list(reversed(weeks[-8:])))
    cats = _table(["Category", "Tickets", "Avg first response (h)", "Avg resolution (h)",
                   "Response SLA %", "Resolution SLA %"], by_cat)
    created = _bars([w[1] for w in weeks], "Tickets created per week")
    sla = _lines({"Response SLA": ("#2e7d32", [w[6] for w in weeks]),
                  "Resolution SLA": ("#c0392b", [w[7] for w in weeks])}, "SLA percentage per week")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Telemetry weekly SLA report</title>
<style>body{{font:14px system-ui,sans-serif;max-width:780px;margin:1.5rem auto;padding:0 16px;color:#222}}
table{{border-collapse:collapse;width:100%;margin:.5rem 0 1.5rem}}th,td{{border:1px solid #ccc;padding:3px 6px;text-align:right}}
th:first-child,td:first-child{{text-align:left}}svg{{width:100%;height:auto}}h2{{font-size:1.05rem;margin-top:1.5rem}}</style></head>
<body><h1>Telemetry weekly SLA report</h1>
<p>Synthetic data. Data runs to {escape(as_of)}. Weeks start on Monday.</p>
<h2>Overall</h2>{kpi}
<h2>Tickets created per week</h2>{created}
<h2>SLA percentage per week</h2>{sla}
<h2>Latest 8 weeks</h2>{latest}
<h2>By category (lowest resolution SLA first)</h2>{cats}
<h2>Open backlog by age</h2>{_table(["Age", "Open tickets"], backlog)}
</body></html>
"""