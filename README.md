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

Options: `--weeks`, `--export`, `--export-format` (report, see below), `--csv` (generate and load only, default data/generated/tickets.csv), `--force` (lets generate overwrite an existing file), `--db` (default data/telemetry.db), `--out` (default report.html), `--count` (default 2500) and `--seed` (default 42). The same seed always produces the same tickets.

`all` always rewrites its own scratch file data/generated/tickets.csv and refuses `--csv`, so it can never overwrite a file of yours. `generate` refuses to overwrite an existing file unless `--force` is given. To load your own CSV, run `load --csv <file>` then `report`.

## Report options and exports

`report --weeks N` limits the report to the most recent N calendar weeks, counted back from the last week that has tickets. If N is larger than the number of weeks with data, all weeks are used and no empty weeks are added before the first ticket. It applies to the overall table, the weekly tables and charts, the by-category table and the exports. Without it all weeks are used. The open backlog is a snapshot of tickets open at the end of the data, so it is never limited.

`report --export DIR` also writes the report tables to DIR, as CSV and JSON by default (`--export-format csv`, `json` or `csv,json`). Without `--export` only the HTML is written. The HTML and the exports are built from one set of query results. Four tables are exported, one file per table and format:

| File | Columns |
|---|---|
| overall | tickets, resolved, avg_first_response_hours, avg_resolution_hours, response_sla_pct, resolution_sla_pct |
| weekly_summary | week, created, resolved, close_rate, avg_first_response_hours, avg_resolution_hours, response_sla_pct, resolution_sla_pct |
| weekly_category_summary | week, category, then the same columns as weekly_summary after week |
| backlog_age_buckets | bucket, tickets |

weekly_summary includes weeks with no tickets, with 0 for created and resolved and empty cells (null in JSON) for the rest. weekly_category_summary has only the weeks and categories that have tickets. The by-category table shown in the HTML is an overall roll-up per category and is not exported. JSON files are a list of objects keyed by column name. Percentages are 0 to 100, close_rate is 0 to 1 and hours are decimal hours.

In the CSV files, a text cell that starts with =, +, - or @, or with a tab or carriage return, gets a leading apostrophe so a spreadsheet shows it as text instead of running it as a formula. Numeric cells are not changed, so a negative number stays a number, and the JSON files are not changed.

## What it does

1. Generator: about 2,500 tickets over two school years (2023-08-07 to 2025-06-27). Categories are device repair, iPad setup, Chromebook loss, password reset, Wi-Fi, printing and account changes. August and September are busier and slower, summer and the holidays are quiet, and some tickets miss their SLA. Tickets still unresolved at the end date stay open.
2. Schema and loader: the table has ticket_id, category, priority, created_at, first_response_at, resolved_at, status and sla_met. The loader checks the CSV header before reading any row and refuses the whole file if the columns are not exactly these eight, so a names, emails or descriptions column is never read. A byte order mark, spaces around names and a different column order are accepted. Ids must look like T-00001, categories are capped at 40 characters and timestamps must be YYYY-MM-DD HH:MM:SS, between 2000 and tomorrow. Messages name fields and line numbers and never print cell values. Bad rows (bad dates, unknown priority or status, short rows, duplicate ids, mismatched status) are listed with their line number and the rest still load.
3. SQL views in `sql/views.sql` (SQLite) and `sql/views.postgres.sql` (PostgreSQL, same columns and rules): weekly close rate, average first response, average resolution, response and resolution SLA percentage by week and by category, and backlog age with age buckets. SLA is computed from the timestamps against per-priority targets (urgent 1h and 8h, high 4h and 24h, medium 8h and 72h, low 24h and 120h for response and resolution), not read from the sla_met column. Weeks start on Monday. A ticket that is still open and already past a target counts as a miss for that target. A ticket still within its target is not counted yet. An event exactly on its target counts as met.
4. Report: one self-contained HTML page with an overall table, tickets created per week, SLA percentage per week, the latest 8 weeks, a by-category table and open backlog by age. Charts are inline SVG.

## Report preview

Screenshot placeholder. To be added after the layout is checked in a browser.

## Status

- Tests: 87 pytest tests. Without a PostgreSQL server 72 pass and 15 PostgreSQL tests are skipped, and they show as skips, not passes. Run with `python -m pytest -rs` to see the skips. The 15 were last run against a real server on 2026-10-21 and passed, but that was before the SLA boundary fix in `sql/views.sql`, the `--weeks` start fix and the category ordering change, so they have not been run on the current code.
- Python: the current suite was run without a server on Python 3.14.7. The earlier run on Python 3.11.9 was before those fixes and has not been repeated. Other versions have not been run.
- SQLite: tested on every run.
- PostgreSQL: tested against a real PostgreSQL 16.4 server (Windows x64 binaries) on 2026-10-21, with psycopg 3.3.6. No other PostgreSQL version has been tried. The tests cover loading, each view matching SQLite on the same 2,500 generated tickets, hand-checked numbers, the report HTML matching the SQLite report, the `--weeks` limit and the exports matching SQLite, and the command line end to end. The weekly average hours can differ by 0.01 from SQLite where a value sits exactly on a rounding tie, because SQLite rounds a floating point value while PostgreSQL rounds an exact numeric. Nothing here is run in CI, so PostgreSQL is only checked when someone runs the tests against a server.
- To use PostgreSQL, set `TELEMETRY_PG_DSN` in the environment or in a git-ignored `.env` file in the folder you run from (copy .env.example). `load` then replaces all rows of the `tickets` table in that database (the table is created if missing, and `load` refuses an existing `tickets` table with different columns) and `report` builds its views there.
- To run the PostgreSQL tests, start any PostgreSQL server, install psycopg and set `TELEMETRY_PG_TEST_DSN` to a scratch database, for example `postgresql://user:password@localhost:5432/scratch`, then run `python -m pytest tests/test_postgres.py -rs`. Each test creates and drops its own schema. Leave the variable unset and those tests skip.
- The report layout and charts are not yet checked visually in a browser. The tests only check the HTML structure.

## Time zones

All timestamps are treated as one local time zone. There is no time zone or daylight saving handling, so durations that cross a clock change are off by an hour. The generated data has this property too.

## Data safety

Anything under data/private/ and the .env file are git-ignored, as is every `*.csv` anywhere in the repo (small made-up fixtures can go in tests/fixtures/), plus databases, data/generated/ and report.html. Use fake data only.