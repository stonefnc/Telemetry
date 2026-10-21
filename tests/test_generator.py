from collections import Counter

import csv

import pytest

from generator.generate import CATEGORIES, END, START, generate, write_csv
from telemetry.constants import COLUMNS, SLA_TARGETS, TIME_FORMAT


def test_count_columns_and_ids():
    rows = generate()
    assert len(rows) == 2500
    assert all(list(r) == COLUMNS for r in rows)
    assert len({r["ticket_id"] for r in rows}) == 2500


def test_same_seed_same_data():
    assert generate(300, seed=1) == generate(300, seed=1)
    assert generate(300, seed=1) != generate(300, seed=2)


def test_categories_priorities_and_dates():
    rows = generate()
    assert {r["category"] for r in rows} == set(CATEGORIES)
    assert {r["priority"] for r in rows} <= set(SLA_TARGETS)
    assert all(START.strftime(TIME_FORMAT) <= r["created_at"] < END.strftime(TIME_FORMAT) for r in rows)


def test_back_to_school_is_busy():
    rows = generate()
    by_month = Counter(r["created_at"][5:7] for r in rows)
    assert by_month["08"] > 2 * by_month["10"]
    assert by_month["09"] > by_month["10"]


def test_sla_misses_exist_and_open_tickets_are_blank():
    rows = generate()
    misses = sum(1 for r in rows if r["sla_met"] == 0)
    met = sum(1 for r in rows if r["sla_met"] == 1)
    assert 0.03 < misses / (misses + met) < 0.5
    for r in rows:
        if r["status"] == "open":
            assert r["resolved_at"] == "" and r["sla_met"] == ""
        else:
            assert r["first_response_at"] <= r["resolved_at"]


def test_write_csv_roundtrip(tmp_path):
    p = tmp_path / "t.csv"
    write_csv(p, generate(50))
    with open(p, newline="", encoding="utf-8") as f:
        got = list(csv.DictReader(f))
    assert len(got) == 50 and list(got[0]) == COLUMNS

def test_write_csv_refuses_to_overwrite_and_makes_folders(tmp_path):
    p = tmp_path / "new" / "dir" / "t.csv"
    write_csv(p, generate(5))
    p.write_text("keep me")
    with pytest.raises(FileExistsError):
        write_csv(p, generate(5))
    assert p.read_text() == "keep me"
    write_csv(p, generate(5), overwrite=True)
    assert p.read_text().startswith("ticket_id")