import sqlite3

import pytest

from generator.generate import generate, write_csv
from telemetry.constants import COLUMNS
from telemetry.loader import ColumnError, LoadError, TableError, load_csv, pg_dsn


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

H = ",".join(COLUMNS)
GOOD = "T-1,Wi-Fi,low,2024-01-08 09:00:00,2024-01-08 10:00:00,2024-01-09 09:00:00,resolved,1"


def _file(tmp_path, text, encoding="utf-8"):
    p = tmp_path / "t.csv"
    p.write_bytes(text.encode(encoding))
    return p


def _count(conn):
    return conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]


def test_bom_header_is_accepted(tmp_path, conn):
    assert load_csv(_file(tmp_path, f"{H}\n{GOOD}\n", "utf-8-sig"), conn).loaded == 1


def test_whitespace_and_reordered_header_are_accepted(tmp_path, conn):
    cols = list(reversed(COLUMNS))
    vals = dict(zip(COLUMNS, GOOD.split(",")))
    p = _file(tmp_path, ",".join(f" {c} " for c in cols) + "\n" + ",".join(vals[c] for c in cols) + "\n")
    assert load_csv(p, conn).loaded == 1
    assert conn.execute("SELECT category, priority FROM tickets").fetchone() == ("Wi-Fi", "low")


def test_duplicate_header_is_named(tmp_path, conn):
    p = _file(tmp_path, ",".join(COLUMNS[:-1] + ["category"]) + "\n")
    with pytest.raises(ColumnError, match=r"duplicated \['category'\]") as e:
        load_csv(p, conn)
    assert "missing ['sla_met']" in str(e.value)


def test_headerless_file_leaves_table_untouched_and_leaks_nothing(tmp_path, conn):
    good = tmp_path / "good.csv"
    write_csv(good, generate(10))
    load_csv(good, conn)
    p = _file(tmp_path, "T-77,SECRETVALUE,low,2024-01-08 09:00:00,,,open,\n")
    with pytest.raises(ColumnError) as e:
        load_csv(p, conn)
    assert "SECRETVALUE" not in str(e.value) and "T-77" not in str(e.value)
    assert _count(conn) == 10


def test_unknown_extra_column_name_is_not_echoed(tmp_path, conn):
    with pytest.raises(ColumnError) as e:
        load_csv(_file(tmp_path, f"{H},jane.doe\n"), conn)
    assert "jane" not in str(e.value) and "1 unexpected" in str(e.value)


@pytest.mark.parametrize("line,reason", [
    ("T-1,Wi-Fi,low,2024-1-8 9:00:00,,,open,", "created_at is not YYYY"),
    ("T-1,Wi-Fi,low,2024-02-30 09:00:00,,,open,", "created_at is not a real date"),
    ("T-1,Wi-Fi,low,2099-01-01 09:00:00,,,open,", "created_at is out of range"),
    ("T-1,Wi-Fi,low,2024-01-08 09:00:00,,2024-01-07 09:00:00,resolved,1", "before created_at"),
    ("T-1,Wi-Fi,low,2024-01-08 09:00:00,2024-01-07 09:00:00,,open,", "before created_at"),
    ("T-1,Wi-Fi,low,2024-01-08 09:00:00,,,resolved,1", "status does not match"),
    ("a b,Wi-Fi,low,2024-01-08 09:00:00,,,open,", "ticket_id has an invalid format"),
    ("T-1," + "x" * 41 + ",low,2024-01-08 09:00:00,,,open,", "category is empty or too long"),
    ("T-1,Wi-Fi,low,2024-01-08 09:00:00,,,open,2", "sla_met"),
])
def test_row_rejections(tmp_path, conn, line, reason):
    res = load_csv(_file(tmp_path, f"{H}\n{line}\n"), conn)
    assert res.loaded == 0 and len(res.rejected) == 1
    assert reason in res.rejected[0][1]


def test_rejection_reasons_do_not_contain_cell_values(tmp_path, conn):
    res = load_csv(_file(tmp_path, f"{H}\nT-1,SECRETVALUE,SECRETPRIORITY,SECRETDATE,,,SECRETSTATUS,SECRETSLA\n"), conn)
    assert res.rejected and "SECRET" not in res.rejected[0][1]


def test_stored_timestamps_are_fixed_width(tmp_path, conn):
    load_csv(_file(tmp_path, f"{H}\n{GOOD}\n"), conn)
    assert conn.execute("SELECT created_at FROM tickets").fetchone()[0] == "2024-01-08 09:00:00"


def test_existing_table_with_other_columns_is_refused_before_delete(tmp_path, conn):
    conn.execute("CREATE TABLE tickets (ticket_id TEXT, note TEXT)")
    conn.execute("INSERT INTO tickets VALUES ('keep', 'me')")
    conn.commit()
    with pytest.raises(TableError):
        load_csv(_file(tmp_path, f"{H}\n{GOOD}\n"), conn)
    assert conn.execute("SELECT ticket_id FROM tickets").fetchall() == [("keep",)]


def test_invalid_utf8_is_a_clean_error(tmp_path, conn):
    with pytest.raises(LoadError, match="UTF-8"):
        load_csv(_file(tmp_path, f"{H}\nT-1,caf\xe9\n", "latin-1"), conn)


def test_pg_dsn_from_env_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TELEMETRY_PG_DSN", raising=False)
    assert pg_dsn() is None
    (tmp_path / ".env").write_text("OTHER=1\nTELEMETRY_PG_DSN=\"postgresql://fake/db\"\n")
    assert pg_dsn() == "postgresql://fake/db"
    monkeypatch.setenv("TELEMETRY_PG_DSN", "postgresql://env/db")
    assert pg_dsn() == "postgresql://env/db"