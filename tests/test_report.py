import pytest

from telemetry.__main__ import main


def test_all_writes_report(tmp_path, capsys):
    out = tmp_path / "r.html"
    main(["all", "--csv", str(tmp_path / "t.csv"), "--db", str(tmp_path / "t.db"), "--out", str(out), "--count", "400"])
    html = out.read_text(encoding="utf-8")
    assert "<svg" in html and html.count("<table>") == 4
    assert "Telemetry weekly SLA report" in html
    assert "loaded 400 tickets, rejected 0 rows" in capsys.readouterr().out


def test_load_refuses_extra_column(tmp_path):
    csv = tmp_path / "t.csv"
    csv.write_text("ticket_id,category,priority,created_at,first_response_at,resolved_at,status,sla_met,email\n")
    with pytest.raises(SystemExit, match="email"):
        main(["load", "--csv", str(csv), "--db", str(tmp_path / "t.db")])