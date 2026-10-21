import sqlite3

import pytest

from generator.generate import generate, write_csv
from telemetry.loader import apply_views, load_csv

HEADER = "ticket_id,category,priority,created_at,first_response_at,resolved_at,status,sla_met\n"
# One week (Monday 2024-01-08), hand-checked numbers: see test_weekly_summary
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
                 "response_sla_pct": 66.67, "resolution_sla_pct": 66.67}


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
    assert abs(both - met) <= 5
    assert conn.execute("SELECT COUNT(*) FROM weekly_summary").fetchone()[0] > 90