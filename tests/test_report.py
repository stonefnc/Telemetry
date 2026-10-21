import pytest

from telemetry.__main__ import main

HEADER = "ticket_id,category,priority,created_at,first_response_at,resolved_at,status,sla_met\n"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    # a developer's own TELEMETRY_PG_DSN or .env must not flip these tests to the PostgreSQL path
    monkeypatch.delenv("TELEMETRY_PG_DSN", raising=False)
    monkeypatch.chdir(tmp_path)


def _all(tmp_path, *extra):
    main(["all", "--db", str(tmp_path / "t.db"), "--out", str(tmp_path / "r.html"), "--count", "400", *extra])


def test_all_writes_report_and_can_run_twice(tmp_path, capsys):
    _all(tmp_path)
    _all(tmp_path)
    html = (tmp_path / "r.html").read_text(encoding="utf-8")
    assert "<svg" in html and html.count("<table>") == 4
    assert "Telemetry weekly SLA report" in html
    assert "loaded 400 tickets, rejected 0 rows" in capsys.readouterr().out


def test_all_refuses_a_user_csv_and_leaves_it_alone(tmp_path):
    mine = tmp_path / "mine.csv"
    mine.write_text("keep me")
    with pytest.raises(SystemExit, match="all always writes"):
        _all(tmp_path, "--csv", str(mine))
    assert mine.read_text() == "keep me"


def test_generate_refuses_existing_file_without_force(tmp_path):
    mine = tmp_path / "mine.csv"
    mine.write_text("keep me")
    with pytest.raises(SystemExit, match="--force"):
        main(["generate", "--csv", str(mine)])
    assert mine.read_text() == "keep me"
    main(["generate", "--csv", str(mine), "--force", "--count", "5"])
    assert mine.read_text().startswith("ticket_id")


def test_load_refuses_extra_column(tmp_path):
    csv = tmp_path / "t.csv"
    csv.write_text(HEADER.rstrip() + ",email\n")
    with pytest.raises(SystemExit, match="email"):
        main(["load", "--csv", str(csv), "--db", str(tmp_path / "t.db")])


def test_load_missing_file_is_a_clean_message(tmp_path):
    with pytest.raises(SystemExit, match="run generate first"):
        main(["load", "--db", str(tmp_path / "t.db")])


def test_zero_tickets_gives_a_clean_message(tmp_path):
    with pytest.raises(SystemExit, match="no tickets loaded"):
        _all(tmp_path, "--count", "0")
    assert not (tmp_path / "r.html").exists()


def test_report_before_load_is_a_clean_message(tmp_path):
    with pytest.raises(SystemExit, match="run load first"):
        main(["report", "--db", str(tmp_path / "empty.db"), "--out", str(tmp_path / "r.html")])


def test_unreachable_postgres_stops_report_with_a_message(tmp_path, monkeypatch):
    pytest.importorskip("psycopg")
    monkeypatch.setenv("TELEMETRY_PG_DSN", "postgresql://fake.invalid/db?connect_timeout=2")
    with pytest.raises(SystemExit, match="cannot connect"):
        main(["report", "--db", str(tmp_path / "t.db")])