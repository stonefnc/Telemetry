# Telemetry

Load a help desk ticket CSV into SQL and produce a weekly SLA report. All data is generated and fake. No real names, emails, tickets or descriptions are ever used or read.

## Usage

Requires Python 3.11 or newer. The app uses only the standard library. pytest is needed for the tests.

    pip install -r requirements.txt
    python -m telemetry all

This generates the fake tickets, loads them into SQLite and writes `report.html`. The steps also run on their own:

    python -m telemetry generate
    python -m telemetry load
    python -m telemetry report

Options: `--csv` (default data/tickets.csv), `--db` (default data/telemetry.db), `--out` (default report.html), `--count` (default 2500) and `--seed` (default 42). The same seed always produces the same tickets.

## What it does

1. Generator: about 2,500 tickets over two school years (2023-08-07 to 2025-06-27). Categories are device repair, iPad setup, Chromebook loss, password reset, Wi-Fi, printing and account changes. August and September are busier and slower, summer and the holidays are quiet, and some tickets miss their SLA. Tickets still unresolved at the end date stay open.
2. Schema and loader: the table has ticket_id, category, priority, created_at, first_response_at, resolved_at, status and sla_met. The loader checks the CSV header before reading any row and refuses the whole file if the columns are not exactly these eight, so a names, emails or descriptions column is never read. Bad rows (bad dates, unknown priority or status, short rows, duplicate ids, mismatched status) are listed with their line number and the rest still load.
3. SQL views in `sql/views.sql`: weekly close rate, average first response, average resolution, response and resolution SLA percentage by week and by category, and backlog age with age buckets. SLA is computed from the timestamps against per-priority targets (urgent 1h and 8h, high 4h and 24h, medium 8h and 72h, low 24h and 120h for response and resolution), not read from the sla_met column. Weeks start on Monday.
4. Report: one self-contained HTML page with an overall table, tickets created per week, SLA percentage per week, the latest 8 weeks, a by-category table and open backlog by age. Charts are inline SVG.

## Report preview

Screenshot placeholder. To be added after the layout is checked in a browser.

## Status

- Tests: 20 pytest tests pass on Python 3.14.7 (`python -m pytest`). They are not yet run on 3.11, though the code avoids anything newer than 3.11.
- SQLite is the tested path.
- PostgreSQL: loading is supported in code. Set `TELEMETRY_PG_DSN` in a git-ignored `.env` file or the environment and install psycopg. This path is untested, with no server available during the build. The views use SQLite date functions, so a PostgreSQL view variant is planned and `report` stops with a message when PostgreSQL is selected.
- The report layout and charts are not yet checked visually in a browser. The tests only check the HTML structure.

## Data safety

Anything under data/private/ and the .env file are git-ignored, as are generated CSVs, databases and report.html. Use fake data only.