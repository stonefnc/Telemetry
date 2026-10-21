import sqlite3

import pytest

from generator.generate import generate, write_csv
from telemetry.constants import SLA_TARGETS
from telemetry.loader import apply_views, load_csv

HEADER = "ticket_id,category,priority,created_at,first_response_at,resolved_at,status,sla_met\n"
# One week (Monday 2024-01-08), hand-checked numbers: see test_weekly_summary.
# D is open with no response 48h after creation and its 24h response target has passed, so it counts as a miss.
SMALL = HEADER + "\n".join([
    "A,Wi-Fi,medium,2024-01-08 09:00:00,2024-01-08 11:00:00,2024-01-09 09:00:00,resolved,1",
    "B,Wi-Fi,medium,2024-01-08 09:00:00,2024-01-08 21:00:00,2024-01-10 09:00:00,resolved,0",
    "C,printing,high,2024-01-08 09:00:00,2024-01-08 10:00:00,2024-01-12 09:00:00,resolved,0",
    "D,printing,low,2024-01-10 09:00:00,,,open,",
]) + "\n"


@pytest.fixture
def small(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text(SMALL)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    assert load_csv(p, conn).loaded == 4
    apply_views(conn)
    return conn


def test_weekly_summary(small):
    r = dict(small.execute("SELECT * FROM weekly_summary").fetchone())
    assert r == {"week": "2024-01-08", "created": 4, "resolved": 3, "close_rate": 0.75,
                 "avg_first_response_hours": 5.0, "avg_resolution_hours": 56.0,
                 "response_sla_pct": 50.0, "resolution_sla_pct": 66.67}


def test_weekly_category_summary(small):
    rows = {r["category"]: dict(r) for r in small.execute("SELECT * FROM weekly_category_summary")}
    assert rows["Wi-Fi"]["response_sla_pct"] == 50.0 and rows["Wi-Fi"]["resolution_sla_pct"] == 100.0
    assert rows["printing"]["close_rate"] == 0.5 and rows["printing"]["resolution_sla_pct"] == 0.0


def test_sunday_belongs_to_the_week_before(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text(HEADER + "S,Wi-Fi,low,2024-01-14 10:00:00,,,open,\n")
    conn = sqlite3.connect(":memory:")
    load_csv(p, conn)
    apply_views(conn)
    assert conn.execute("SELECT week FROM ticket_facts").fetchone()[0] == "2024-01-08"


def test_backlog_age(small):
    r = small.execute("SELECT ticket_id, age_days FROM backlog_age").fetchall()
    assert [tuple(x) for x in r] == [("D", 2.0)]
    assert [tuple(x) for x in small.execute("SELECT * FROM backlog_age_buckets")] == [("1-3 days", 1)]


def test_views_agree_with_generated_sla_met(tmp_path):
    p = tmp_path / "g.csv"
    write_csv(p, generate(2500))
    conn = sqlite3.connect(":memory:")
    load_csv(p, conn)
    apply_views(conn)
    both = conn.execute("SELECT COUNT(*) FROM ticket_facts WHERE response_met = 1 AND resolution_met = 1").fetchone()[0]
    met = conn.execute("SELECT COUNT(*) FROM tickets WHERE sla_met = 1").fetchone()[0]
    assert both == met
    assert conn.execute("SELECT COUNT(*) FROM weekly_summary").fetchone()[0] > 90

def _db(tmp_path, *lines):
    p = tmp_path / "s.csv"
    p.write_text(HEADER + "\n".join(lines) + "\n")
    conn = sqlite3.connect(":memory:")
    assert load_csv(p, conn).rejected == []
    apply_views(conn)
    return conn


def test_open_overdue_ticket_counts_as_a_miss(tmp_path):
    conn = _db(tmp_path,
               "U,Wi-Fi,urgent,2024-01-01 09:00:00,,,open,",
               "V,Wi-Fi,low,2024-02-01 09:00:00,2024-02-01 10:00:00,2024-02-01 12:00:00,resolved,1")
    assert conn.execute("SELECT response_met, resolution_met FROM ticket_facts WHERE ticket_id='U'").fetchone() == (0, 0)
    assert conn.execute("SELECT response_sla_pct, resolution_sla_pct FROM weekly_summary WHERE week='2024-01-01'").fetchone() == (0.0, 0.0)


def test_open_ticket_within_target_is_not_counted(tmp_path):
    conn = _db(tmp_path,
               "W,Wi-Fi,low,2024-02-01 11:00:00,,,open,",
               "V,Wi-Fi,low,2024-02-01 09:00:00,2024-02-01 10:00:00,2024-02-01 12:00:00,resolved,1")
    assert conn.execute("SELECT response_met, resolution_met FROM ticket_facts WHERE ticket_id='W'").fetchone() == (None, None)
    assert conn.execute("SELECT response_sla_pct FROM weekly_summary").fetchone()[0] == 100.0


def test_sla_targets_view_matches_constants():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tickets (ticket_id TEXT, category TEXT, priority TEXT, created_at TIMESTAMP, "
                 "first_response_at TIMESTAMP, resolved_at TIMESTAMP, status TEXT, sla_met INTEGER)")
    apply_views(conn)
    got = {p: (r, s) for p, r, s in conn.execute("SELECT priority, response_hours, resolution_hours FROM sla_targets")}
    assert got == {p: (float(r), float(s)) for p, (r, s) in SLA_TARGETS.items()}