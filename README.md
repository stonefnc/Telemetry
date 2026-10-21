# Telemetry

Load a help desk ticket CSV into SQL and produce a weekly SLA report. All data is generated and fake. No real names, emails, tickets or descriptions are ever used or read.

## Usage

Requires Python 3.11 or newer. The app uses only the standard library for SQLite. pytest is needed for the tests. The optional PostgreSQL path needs psycopg 3 (`pip install -r requirements-postgres.txt`).

    pip install -r requirements.txt
    python -m telemetry all

This generates the fake tickets, loads them into SQLite and writes `report.html`. The steps also run on their own:

    python -m telemetry generate
    python -m telemetry load
    python -m telemetry report

Options: `--csv` (generate and load only, default data/generated/tickets.csv), `--force` (lets generate overwrite an existing file), `--db` (default data/telemetry.db), `--out` (default report.html), `--count` (default 2500) and `--seed` (default 42). The same seed always produces the same tickets.

`all` always rewrites its own scratch file data/generated/tickets.csv and refuses `--csv`, so it can never overwrite a file of yours. `generate` refuses to overwrite an existing file unless `--force` is given. To load your own CSV, run `load --csv <file>` then `report`.

## What it does

1. Generator: about 2,500 tickets over two school years (2023-08-07 to 2025-06-27). Categories are device repair, iPad setup, Chromebook loss, password reset, Wi-Fi, printing and account changes. August and September are busier and slower, summer and the holidays are quiet, and some tickets miss their SLA. Tickets still unresolved at the end date stay open.
2. Schema and loader: the table has ticket_id, category, priority, created_at, first_response_at, resolved_at, status and sla_met. The loader checks the CSV header before reading any row and refuses the whole file if the columns are not exactly these eight, so a names, emails or descriptions column is never read. A byte order mark, spaces around names and a different column order are accepted. Ids must look like T-00001, categories are capped at 40 characters and timestamps must be YYYY-MM-DD HH:MM:SS, between 2000 and tomorrow. Messages name fields and line numbers and never print cell values. Bad rows (bad dates, unknown priority or status, short rows, duplicate ids, mismatched status) are listed with their line number and the rest still load.
3. SQL views in `sql/views.sql` (SQLite) and `sql/views.postgres.sql` (PostgreSQL, same columns and rules): weekly close rate, average first response, average resolution, response and resolution SLA percentage by week and by category, and backlog age with age buckets. SLA is computed from the timestamps against per-priority targets (urgent 1h and 8h, high 4h and 24h, medium 8h and 72h, low 24h and 120h for response and resolution), not read from the sla_met column. Weeks start on Monday. A ticket that is still open and already past a target counts as a miss for that target. A ticket still within its target is not counted yet.
4. Report: one self-contained HTML page with an overall table, tickets created per week, SLA percentage per week, the latest 8 weeks, a by-category table and open backlog by age. Charts are inline SVG.

## Report preview

Screenshot placeholder. To be added after the layout is checked in a browser.

## Status

- Tests: 66 pytest tests pass on Python 3.14.7 when a PostgreSQL server is available (`python -m pytest`). Without one, 55 pass and 11 PostgreSQL tests are skipped, and the skips are reported as skips, not passes. They are not yet run on Python 3.11, though the code avoids anything newer than 3.11.
- SQLite: tested on every run.
- PostgreSQL: tested against a real PostgreSQL 16.4 server (Windows x64 binaries) on 2026-10-21, with psycopg 3.3.6. No other PostgreSQL version has been tried. The tests cover loading, each view matching SQLite on the same 2,500 generated tickets, hand-checked numbers, the report HTML matching the SQLite report, and the command line end to end. The weekly average hours can differ by 0.01 from SQLite where a value sits exactly on a rounding tie, because SQLite works from floating point julian days. Nothing here is run in CI, so PostgreSQL is only checked when someone runs the tests against a server.
- To use PostgreSQL, set `TELEMETRY_PG_DSN` in the environment or in a git-ignored `.env` file in the folder you run from (copy .env.example). `load` then replaces the `tickets` table in that database and `report` builds its views there.
- To run the PostgreSQL tests, start any PostgreSQL server, install psycopg and set `TELEMETRY_PG_TEST_DSN` to a scratch database, for example `postgresql://user:password@localhost:5432/scratch`, then run `python -m pytest tests/test_postgres.py -rs`. Each test creates and drops its own schema. Leave the variable unset and those tests skip.
- The report layout and charts are not yet checked visually in a browser. The tests only check the HTML structure.

## Time zones

All timestamps are treated as one local time zone. There is no time zone or daylight saving handling, so durations that cross a clock change are off by an hour. The generated data has this property too.

## Data safety

Anything under data/private/ and the .env file are git-ignored, as is every `*.csv` anywhere in the repo (small made-up fixtures can go in tests/fixtures/), plus databases, data/generated/ and report.html. Use fake data only.