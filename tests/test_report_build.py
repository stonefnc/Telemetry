import sqlite3

import pytest

from telemetry.loader import apply_views, load_csv
from telemetry.report import build_report

HEADER = "ticket_id,category,priority,created_at,first_response_at,resolved_at,status,sla_met\n"


def _conn(tmp_path, *lines):
    p = tmp_path / "s.csv"
    p.write_text(HEADER + "\n".join(lines) + "\n")
    conn = sqlite3.connect(":memory:")
    load_csv(p, conn)
    apply_views(conn)
    return conn


def test_hostile_category_is_escaped(tmp_path):
    conn = _conn(tmp_path, "A,<script>alert(1)</script>,low,2024-01-08 09:00:00,2024-01-08 10:00:00,2024-01-08 12:00:00,resolved,1")
    html = build_report(conn)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_weeks_without_tickets_are_filled_in(tmp_path):
    conn = _conn(tmp_path,
                 "A,Wi-Fi,low,2024-01-01 09:00:00,2024-01-01 10:00:00,2024-01-01 12:00:00,resolved,1",
                 "B,Wi-Fi,low,2024-02-12 09:00:00,2024-02-12 10:00:00,2024-02-12 12:00:00,resolved,1")
    html = build_report(conn)
    # 7 calendar weeks from 2024-01-01 to 2024-02-12, the quiet ones show with 0 tickets
    assert "<td>2024-01-15</td><td>0</td>" in html
    assert "<td>2024-01-08</td><td>0</td>" in html


def test_category_without_sla_data_is_listed_last(tmp_path):
    conn = _conn(tmp_path,
                 "A,Wi-Fi,low,2024-01-08 09:00:00,2024-01-08 10:00:00,2024-01-08 12:00:00,resolved,1",
                 "B,printing,low,2024-01-08 09:00:00,2024-01-08 10:00:00,2024-01-08 12:00:00,resolved,1",
                 "C,Zeta,low,2024-01-08 11:00:00,,,open,")
    cats = build_report(conn).split("By category")[1].split("Open backlog")[0]
    assert cats.rindex("Zeta") > cats.rindex("printing")


def test_empty_database_fails_cleanly(tmp_path):
    conn = _conn(tmp_path)
    with pytest.raises(ValueError, match="no tickets"):
        build_report(conn)