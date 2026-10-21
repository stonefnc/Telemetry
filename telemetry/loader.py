"""Load a ticket CSV into SQL. Only the 8 schema columns are accepted, anything else is refused."""
import csv
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from generator.generate import COLUMNS, SLA_TARGETS, TIME_FORMAT

SCHEMA = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
VIEWS = SCHEMA.with_name("views.sql")


class ColumnError(ValueError):
    """The CSV header is not exactly the allowed columns."""


@dataclass
class LoadResult:
    loaded: int = 0
    rejected: list = field(default_factory=list)  # (csv line number, reason)


def connect(db_path="data/telemetry.db"):
    """SQLite by default. Set TELEMETRY_PG_DSN (from .env) to use PostgreSQL instead.

    Returns (connection, placeholder). The PostgreSQL path is untested here, it needs psycopg and a server.
    """
    dsn = os.environ.get("TELEMETRY_PG_DSN")
    if dsn:
        import psycopg  # optional dependency, only for the PostgreSQL option
        return psycopg.connect(dsn), "%s"
    import sqlite3
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path), "?"


def _ts(value, required):
    if value == "":
        if required:
            raise ValueError("missing timestamp")
        return None
    datetime.strptime(value, TIME_FORMAT)
    return value


def _clean(row):
    """Return the row as a tuple of typed values, or raise ValueError saying what is wrong."""
    if not row["ticket_id"]:
        raise ValueError("missing ticket_id")
    if not row["category"]:
        raise ValueError("missing category")
    if row["priority"] not in SLA_TARGETS:
        raise ValueError(f"unknown priority {row['priority']!r}")
    if row["status"] not in ("open", "resolved"):
        raise ValueError(f"unknown status {row['status']!r}")
    created = _ts(row["created_at"], True)
    first = _ts(row["first_response_at"], False)
    resolved = _ts(row["resolved_at"], False)
    if first and first < created or resolved and resolved < created:
        raise ValueError("timestamp before created_at")
    if (row["status"] == "resolved") != (resolved is not None):
        raise ValueError("status does not match resolved_at")
    if row["sla_met"] not in ("", "0", "1"):
        raise ValueError(f"bad sla_met {row['sla_met']!r}")
    sla = int(row["sla_met"]) if row["sla_met"] else None
    return (row["ticket_id"], row["category"], row["priority"], created, first, resolved, row["status"], sla)


def load_csv(path, conn, placeholder="?"):
    """Replace the tickets table with the CSV contents. Bad rows are reported in the result, not raised."""
    result = LoadResult()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        # the header is checked before any data row is read, so extra columns are never parsed
        if sorted(header) != sorted(COLUMNS):
            extra = sorted(set(header) - set(COLUMNS))
            missing = sorted(set(COLUMNS) - set(header))
            raise ColumnError(f"rejected columns, unexpected {extra} missing {missing}")
        index = {name: i for i, name in enumerate(header)}
        cur = conn.cursor()
        for stmt in SCHEMA.read_text().split(";"):
            if stmt.strip():
                cur.execute(stmt)
        cur.execute("DELETE FROM tickets")
        seen = set()
        sql = f"INSERT INTO tickets VALUES ({', '.join([placeholder] * len(COLUMNS))})"
        for row in reader:
            line = reader.line_num
            try:
                if len(row) != len(header):
                    raise ValueError(f"expected {len(header)} fields, got {len(row)}")
                values = _clean({c: row[index[c]].strip() for c in COLUMNS})
                if values[0] in seen:
                    raise ValueError("duplicate ticket_id")
                seen.add(values[0])
            except ValueError as e:
                result.rejected.append((line, str(e)))
                continue
            cur.execute(sql, values)
            result.loaded += 1
    conn.commit()
    return result

def apply_views(conn):
    """Create or refresh the reporting views (SQLite syntax)."""
    cur = conn.cursor()
    for stmt in VIEWS.read_text().split(";"):
        if stmt.strip():
            cur.execute(stmt)
    conn.commit()
