import sqlite3

import pytest

from generator.generate import COLUMNS, generate, write_csv
from telemetry.loader import ColumnError, load_csv


@pytest.fixture
def conn():
    return sqlite3.connect(":memory:")


def test_loads_generated_data(tmp_path, conn):
    p = tmp_path / "t.csv"
    write_csv(p, generate(500))
    res = load_csv(p, conn)
    assert res.loaded == 500 and res.rejected == []
    assert conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 500
    assert conn.execute("SELECT COUNT(*) FROM tickets WHERE status='open' AND sla_met IS NOT NULL").fetchone()[0] == 0


@pytest.mark.parametrize("extra", ["requester_name", "email", "description"])
def test_extra_column_is_rejected_and_nothing_loaded(tmp_path, conn, extra):
    p = tmp_path / "t.csv"
    p.write_text(",".join(COLUMNS + [extra]) + "\n" + ",".join(["x"] * 9) + "\n")
    with pytest.raises(ColumnError, match=extra):
        load_csv(p, conn)
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='tickets'").fetchone() is None


def test_missing_column_is_rejected(tmp_path, conn):
    p = tmp_path / "t.csv"
    p.write_text(",".join(COLUMNS[:-1]) + "\n")
    with pytest.raises(ColumnError, match="sla_met"):
        load_csv(p, conn)


def test_bad_rows_are_reported_not_fatal(tmp_path, conn):
    good = generate(3)
    p = tmp_path / "t.csv"
    write_csv(p, good)
    lines = p.read_text().splitlines()
    lines += [
        "T-90001,Wi-Fi,low,not a date,,,open,",          # bad timestamp
        "T-90002,Wi-Fi,huge,2024-01-01 09:00:00,,,open,",  # bad priority
        "T-90003,Wi-Fi",                                   # short row
        lines[1],                                          # duplicate id
        "T-90004,Wi-Fi,low,2024-01-01 09:00:00,,,resolved,1",  # resolved without resolved_at
    ]
    p.write_text("\n".join(lines) + "\n")
    res = load_csv(p, conn)
    assert res.loaded == 3
    assert [line for line, _ in res.rejected] == [5, 6, 7, 8, 9]
    assert "duplicate" in res.rejected[3][1]


def test_reload_replaces_rows(tmp_path, conn):
    p = tmp_path / "t.csv"
    write_csv(p, generate(20))
    load_csv(p, conn)
    load_csv(p, conn)
    assert conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 20