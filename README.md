# Telemetry

Load a help desk ticket CSV into SQL and produce a weekly SLA report. All data is generated and fake. No real names, emails, tickets or descriptions are ever used.

Status: scaffold only. Everything below is planned unless marked built.

## Planned usage

    python -m telemetry all

Generates the fake tickets, loads them into SQLite and writes the weekly HTML report. The steps can also run on their own:

    python -m telemetry generate
    python -m telemetry load
    python -m telemetry report

## Planned pieces

1. Generator (planned): about 2,500 tickets over two school years. Categories include device repair, iPad setup, Chromebook loss, password reset, Wi-Fi, printing and account changes. Busy weeks in August and September, realistic response and resolution times, some SLA misses.
2. Schema (planned): ticket_id, category, priority, created_at, first_response_at, resolved_at, status, sla_met. The loader rejects any other column, so names, emails and descriptions are never read. Bad rows are reported, not fatal.
3. Storage (planned): SQLite by default, PostgreSQL as an option through a connection string in .env.
4. SQL views in sql/ (planned): weekly close rate, average first response, average resolution, response and resolution SLA percentage by week and by category, and backlog age.
5. Report (planned): a one page HTML file with a small table and one or two simple charts.
6. Tests (planned): pytest against generated data, including the column rejection rule.

## Report preview

Screenshot placeholder. To be added once the report command exists.

## Data safety

Anything under data/private/ and the .env file are git-ignored. Generated CSVs and databases are ignored too.

## Tests

Not written yet.