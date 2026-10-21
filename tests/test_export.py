import csv
import json
import sqlite3

import pytest

from generator.generate import generate, write_csv
from telemetry.__main__ import main
from telemetry.loader import apply_views, load_csv
from telemetry.report import (BACKLOG_COLUMNS, OVERALL_COLUMNS, WEEKLY_CATEGORY_COLUMNS, WEEKLY_COLUMNS, build_report,
                              collect, write_exports)

HEADER = "ticket_id,category,priority,created_at,first_response_at,resolved_at,status,sla_met\n"
# weeks of 2024-01-01 and 2024-01-15 have tickets, the week of 2024-01-08 is empty
SMALL = HEADER + "\n".join([
    "A,Wi-Fi,medium,2024-01-01 09:00:00,2024-01-01 11:00:00,2024-01-02 09:00:00,resolved,1",
    "B,printing,high,2024-01-02 09:00:00,2024-01-02 10:00:00,2024-01-06 09:00:00,resolved,0",
    "C,Wi-Fi,low,2024-01-15 09:00:00,2024-01-15 10:00:00,2024-01-15 12:00:00,resolved,1",
    "D,printing,low,2024-01-15 10:00:00,,,open,",
]) + "\n"


def _db(path, text=None):
    conn = sqlite3.connect(":memory:")
    if text is not None:
        path.write_text(text)
    load_csv(path, conn)
    apply_views(conn)
    return conn


@pytest.fixture
def small(tmp_path):
    return _db(tmp_path / "s.csv", SMALL)


@pytest.fixture
def big(tmp_path):
    p = tmp_path / "g.csv"
    write_csv(p, generate(2500))
    return _db(p)


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def test_export_writes_exactly_four_tables_in_both_formats(small, tmp_path):
    written = write_exports(collect(small), tmp_path / "out")
    names = ["overall", "weekly_summary", "weekly_category_summary", "backlog_age_buckets"]
    assert sorted(written) == sorted(f"{n}.{e}" for n in names for e in ("csv", "json"))
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == sorted(written)


def test_export_columns_and_values(small, tmp_path):
    write_exports(collect(small), tmp_path)
    assert _read_csv(tmp_path / "overall.csv")[0] == OVERALL_COLUMNS
    assert _read_csv(tmp_path / "weekly_summary.csv")[0] == WEEKLY_COLUMNS
    assert _read_csv(tmp_path / "weekly_category_summary.csv")[0] == WEEKLY_CATEGORY_COLUMNS
    assert _read_csv(tmp_path / "backlog_age_buckets.csv")[0] == BACKLOG_COLUMNS
    overall = json.loads((tmp_path / "overall.json").read_text())
    # hand-checked: first responses 2h, 1h, 1h, resolutions 24h, 96h, 3h, resolution targets met for A and C only
    assert overall == [{"tickets": 4, "resolved": 3, "avg_first_response_hours": 1.3, "avg_resolution_hours": 41.0,
                        "response_sla_pct": 100.0, "resolution_sla_pct": 66.7}]
    assert json.loads((tmp_path / "backlog_age_buckets.json").read_text()) == [{"bucket": "0-1 days", "tickets": 1}]


def test_empty_week_is_exported_with_zero_tickets_and_empty_cells(small, tmp_path):
    write_exports(collect(small), tmp_path)
    rows = _read_csv(tmp_path / "weekly_summary.csv")[1:]
    assert [r[0] for r in rows] == ["2024-01-01", "2024-01-08", "2024-01-15"]
    assert rows[1] == ["2024-01-08", "0", "0", "", "", "", "", ""]
    assert json.loads((tmp_path / "weekly_summary.json").read_text())[1]["close_rate"] is None


def test_csv_and_json_hold_the_same_rows(big, tmp_path):
    write_exports(collect(big), tmp_path)
    for name in ("overall", "weekly_summary", "weekly_category_summary", "backlog_age_buckets"):
        csv_rows = _read_csv(tmp_path / f"{name}.csv")
        json_rows = json.loads((tmp_path / f"{name}.json").read_text())
        assert len(csv_rows) - 1 == len(json_rows)
        assert [r[0] for r in csv_rows[1:]] == [str(j[csv_rows[0][0]]) for j in json_rows]


def test_html_and_export_come_from_the_same_numbers(small, tmp_path):
    data = collect(small)
    html = build_report(small)
    for week in data["weeks"]:
        assert f"<td>{week[0]}</td><td>{week[1]}</td>" in html


def test_a_format_can_be_left_out(small, tmp_path):
    assert all(n.endswith(".json") for n in write_exports(collect(small), tmp_path, ("json",)))


def test_weeks_limits_weekly_tables_and_totals_but_not_the_backlog(big):
    full, last8 = collect(big), collect(big, weeks=8)
    assert len(last8["weeks"]) == 8 and last8["weeks"] == full["weeks"][-8:]
    cutoff = last8["weeks"][0][0]
    assert {r[0] for r in last8["weekly_category"]} <= {w[0] for w in last8["weeks"]}
    assert last8["total"][0] == sum(w[1] for w in last8["weeks"]) < full["total"][0]
    assert sum(r[1] for r in last8["by_cat"]) == last8["total"][0]
    assert last8["backlog"] == full["backlog"] and cutoff == full["weeks"][-8][0]


def test_weeks_larger_than_the_data_gives_everything(small):
    assert collect(small, weeks=500)["weeks"][-3:] == collect(small)["weeks"]
    assert collect(small, weeks=500)["total"] == collect(small)["total"]


def test_default_report_is_unchanged_and_says_nothing_about_a_limit(small):
    assert build_report(small) == build_report(small, None) and "Showing the last" not in build_report(small)
    assert "Showing the last 2 weeks" in build_report(small, 2)


def test_weeks_with_an_empty_window_still_has_the_requested_weeks(small):
    # the last 2 calendar weeks are 2024-01-08 (empty) and 2024-01-15
    assert [w[0] for w in collect(small, 2)["weeks"]] == ["2024-01-08", "2024-01-15"]


def test_command_line_export_and_weeks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TELEMETRY_PG_DSN", raising=False)
    main(["all", "--count", "400"])
    assert not (tmp_path / "out").exists()  # no export unless asked
    main(["report", "--weeks", "4", "--export", "out", "--export-format", "csv"])
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "backlog_age_buckets.csv", "overall.csv", "weekly_category_summary.csv", "weekly_summary.csv"]
    assert len(_read_csv(tmp_path / "out" / "weekly_summary.csv")) == 5
    assert "Showing the last 4 weeks" in (tmp_path / "report.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("args,message", [(["--weeks", "0"], "1 or more"), (["--export-format", "xml"], "csv, json")])
def test_command_line_rejects_bad_options(args, message):
    with pytest.raises(SystemExit, match=message):
        main(["report", *args])
