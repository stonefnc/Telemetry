"""PostgreSQL path tests.

The tests marked with the `pg` fixture need a real server and are skipped when TELEMETRY_PG_TEST_DSN is unset
or psycopg is not installed. Each test works in its own throwaway schema that is dropped afterwards, so the
server's other data is never touched. Use a scratch database for the DSN anyway.
"""
import os
import re
import sqlite3
import uuid

import pytest

from generator.generate import generate, write_csv
from telemetry.__main__ import main
from telemetry.constants import SLA_TARGETS
from telemetry.loader import VIEWS_POSTGRES, apply_views, is_postgres, load_csv
from telemetry.report import build_report

HEADER = "ticket_id,category,priority,created_at,first_response_at,resolved_at,status,sla_met\n"
SMALL = HEADER + "\n".join([
    "A,Wi-Fi,medium,2024-01-08 09:00:00,2024-01-08 11:00:00,2024-01-09 09:00:00,resolved,1",
    "B,Wi-Fi,medium,2024-01-08 09:00:00,2024-01-08 21:00:00,2024-01-10 09:00:00,resolved,0",
    "C,printing,high,2024-01-08 09:00:00,2024-01-08 10:00:00,2024-01-12 09:00:00,resolved,0",
    "D,printing,low,2024-01-10 09:00:00,,,open,",
    "S,Wi-Fi,low,2024-01-14 10:00:00,,,open,",
]) + "\n"
VIEW_QUERIES = {
    "weekly_summary": "SELECT * FROM weekly_summary ORDER BY week",
    "weekly_category_summary": "SELECT * FROM weekly_category_summary ORDER BY week, category",
    "backlog_age_buckets": "SELECT * FROM backlog_age_buckets ORDER BY bucket",
    "ticket_facts": "SELECT ticket_id, week, response_met, resolution_met FROM ticket_facts ORDER BY ticket_id",
}


@pytest.fixture
def pg_dsn_scoped():
    """A DSN whose search_path is a fresh schema, dropped after the test."""
    base = os.environ.get("TELEMETRY_PG_TEST_DSN")
    if not base:
        pytest.skip("TELEMETRY_PG_TEST_DSN is not set, no PostgreSQL server to test against")
    psycopg = pytest.importorskip("psycopg")
    from psycopg.conninfo import make_conninfo
    schema = "telemetry_test_" + uuid.uuid4().hex[:12]
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA {schema}")
        try:
            yield make_conninfo(base, options=f"-c search_path={schema}")
        finally:
            admin.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.fixture
def pg(pg_dsn_scoped):
    import psycopg
    with psycopg.connect(pg_dsn_scoped) as conn:
        yield conn


def _csv(tmp_path, text):
    p = tmp_path / "s.csv"
    p.write_text(text)
    return p


def _sqlite(path):
    conn = sqlite3.connect(":memory:")
    load_csv(path, conn)
    apply_views(conn)
    return conn


def _num(v):
    return round(float(v), 2) if v is not None and not isinstance(v, str) else v


def _rows(conn, sql):
    # sorted in Python because PostgreSQL and SQLite order text differently (locale against binary)
    return sorted(tuple(_num(v) for v in r) for r in conn.execute(sql).fetchall())


# These two need no server.

def test_postgres_views_file_targets_match_constants():
    sql = VIEWS_POSTGRES.read_text()
    first = re.search(r"'(\w+)'::text AS priority, ([\d.]+)::numeric AS response_hours, ([\d.]+)::numeric", sql)
    rest = re.findall(r"UNION ALL SELECT '(\w+)', ([\d.]+), ([\d.]+)", sql)
    got = {p: (float(r), float(s)) for p, r, s in [first.groups(), *rest]}
    assert got == {p: (float(r), float(s)) for p, (r, s) in SLA_TARGETS.items()}


def test_sqlite_is_not_detected_as_postgres():
    assert not is_postgres(sqlite3.connect(":memory:"))


# The rest run against a real server.

def test_loads_into_postgres_with_real_timestamps(tmp_path, pg):
    p = tmp_path / "t.csv"
    write_csv(p, generate(500))
    res = load_csv(p, pg, "%s")
    assert res.loaded == 500 and res.rejected == []
    assert pg.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 500
    assert pg.execute("SELECT data_type FROM information_schema.columns WHERE table_name = 'tickets' "
                      "AND column_name = 'created_at' AND table_schema = current_schema()").fetchone()[0] \
        == "timestamp without time zone"
    assert pg.execute("SELECT COUNT(*) FROM tickets WHERE status='open' AND sla_met IS NOT NULL").fetchone()[0] == 0


def test_reload_replaces_rows_and_bad_rows_are_rejected(tmp_path, pg):
    load_csv(_csv(tmp_path, SMALL), pg, "%s")
    res = load_csv(_csv(tmp_path, HEADER + "T-1,Wi-Fi,low,2024-02-30 09:00:00,,,open,\nT-2,Wi-Fi,low,2024-01-08 09:00:00,,,open,\n"),
                   pg, "%s")
    assert res.loaded == 1 and len(res.rejected) == 1
    assert pg.execute("SELECT ticket_id FROM tickets").fetchall() == [("T-2",)]


def test_views_on_postgres_match_hand_checked_numbers(tmp_path, pg):
    load_csv(_csv(tmp_path, SMALL), pg, "%s")
    apply_views(pg)
    r = pg.execute("SELECT * FROM weekly_summary ORDER BY week").fetchall()
    # week 2024-01-08 holds A to D and also S, created on the Sunday that ends that week
    assert [(w, c, rs, float(cr), float(a), float(b), float(x), float(y)) for w, c, rs, cr, a, b, x, y in r][0] \
        == ("2024-01-08", 5, 3, 0.6, 5.0, 56.0, 50.0, 66.67)
    assert pg.execute("SELECT week FROM ticket_facts WHERE ticket_id = 'S'").fetchone()[0] == "2024-01-08"
    assert sorted((p, float(r), float(s)) for p, r, s in pg.execute("SELECT * FROM sla_targets")) \
        == sorted((p, float(r), float(s)) for p, (r, s) in SLA_TARGETS.items())


def test_open_overdue_and_within_target_tickets_on_postgres(tmp_path, pg):
    text = HEADER + "\n".join([
        "U,Wi-Fi,urgent,2024-01-01 09:00:00,,,open,",
        "W,Wi-Fi,low,2024-02-01 11:00:00,,,open,",
        "V,Wi-Fi,low,2024-02-01 09:00:00,2024-02-01 10:00:00,2024-02-01 12:00:00,resolved,1"]) + "\n"
    load_csv(_csv(tmp_path, text), pg, "%s")
    apply_views(pg)
    q = lambda t: pg.execute(f"SELECT response_met, resolution_met FROM ticket_facts WHERE ticket_id='{t}'").fetchone()
    assert q("U") == (0, 0) and q("W") == (None, None)


def test_apply_views_can_run_twice(tmp_path, pg):
    load_csv(_csv(tmp_path, SMALL), pg, "%s")
    apply_views(pg)
    apply_views(pg)
    assert pg.execute("SELECT COUNT(*) FROM weekly_summary").fetchone()[0] == 1


@pytest.mark.parametrize("view", VIEW_QUERIES)
def test_each_view_matches_sqlite_on_the_same_generated_data(tmp_path, pg, view):
    p = tmp_path / "g.csv"
    write_csv(p, generate(2500))
    load_csv(p, pg, "%s")
    apply_views(pg)
    got, want = _rows(pg, VIEW_QUERIES[view]), _rows(_sqlite(p), VIEW_QUERIES[view])
    assert len(got) == len(want)
    # SQLite computes hours from floating point julian days, so a value that sits exactly on a rounding tie
    # (0.555 hours) can land one hundredth lower than PostgreSQL's exact numeric result. Everything else is equal.
    assert got == [pytest.approx(w, abs=0.0101) if any(isinstance(v, float) for v in w) else w for w in want]


def test_report_html_on_postgres_equals_sqlite_report(tmp_path, pg):
    p = tmp_path / "g.csv"
    write_csv(p, generate(2500))
    load_csv(p, pg, "%s")
    apply_views(pg)
    assert build_report(pg) == build_report(_sqlite(p))


def test_command_line_runs_end_to_end_on_postgres(tmp_path, monkeypatch, pg_dsn_scoped):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELEMETRY_PG_DSN", pg_dsn_scoped)
    main(["all", "--count", "300"])
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "Telemetry weekly SLA report" in html and "Open backlog by age" in html
