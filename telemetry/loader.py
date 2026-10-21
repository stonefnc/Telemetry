"""Load a ticket CSV into SQL. Only the 8 schema columns are accepted, anything else is refused.

Error and rejection messages name fields and line numbers, never cell values, so a real file
pointed at the loader by mistake does not leak its content into the output.
"""
import csv
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from telemetry.constants import COLUMNS, SLA_TARGETS, TIME_FORMAT

SCHEMA = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
VIEWS = SCHEMA.with_name("views.sql")
VIEWS_POSTGRES = SCHEMA.with_name("views.postgres.sql")

TS_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}")
ID_RE = re.compile(r"[A-Za-z0-9-]{1,20}")
CATEGORY_MAX = 40
MIN_TS = datetime(2000, 1, 1)
# header names that are safe to echo back, anything else is only counted
KNOWN_UNWANTED = {"name", "requester", "requester_name", "email", "description", "subject", "body", "phone",
                  "user", "username", "notes", "comment", "comments", "assignee", "location", "asset_tag"}


class LoadError(ValueError):
    """The file cannot be loaded. The message never contains cell values."""


class ColumnError(LoadError):
    """The CSV header is not exactly the allowed columns."""


class TableError(LoadError):
    """The tickets table already exists with different columns."""


@dataclass
class LoadResult:
    loaded: int = 0
    rejected: list = field(default_factory=list)  # (csv line number, reason without values)


def pg_dsn():
    """PostgreSQL connection string from the environment, or from a .env file in the working folder."""
    dsn = os.environ.get("TELEMETRY_PG_DSN")
    env = Path(".env")
    if not dsn and env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "TELEMETRY_PG_DSN":
                dsn = value.strip().strip("\"'")
    return dsn or None


def connect(db_path="data/telemetry.db"):
    """SQLite by default. Set TELEMETRY_PG_DSN (environment or .env) to use PostgreSQL instead.

    Returns (connection, placeholder). The PostgreSQL option needs psycopg (version 3) and a server.
    """
    dsn = pg_dsn()
    if dsn:
        import psycopg  # optional dependency, only for the PostgreSQL option
        return psycopg.connect(dsn), "%s"
    import sqlite3
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path), "?"


def _ts(value, name, required=False):
    if value == "":
        if required:
            raise ValueError(f"{name} is required")
        return None
    if not TS_RE.fullmatch(value):
        raise ValueError(f"{name} is not YYYY-MM-DD HH:MM:SS")
    try:
        dt = datetime.strptime(value, TIME_FORMAT)
    except ValueError:
        raise ValueError(f"{name} is not a real date") from None
    if dt < MIN_TS or dt > datetime.now() + timedelta(days=1):
        raise ValueError(f"{name} is out of range")
    return dt


def _clean(row):
    """Return the row as a tuple of typed values, or raise ValueError saying which field is wrong."""
    if not ID_RE.fullmatch(row["ticket_id"]):
        raise ValueError("ticket_id has an invalid format")
    if not row["category"] or len(row["category"]) > CATEGORY_MAX:
        raise ValueError("category is empty or too long")
    if row["priority"] not in SLA_TARGETS:
        raise ValueError("priority is not a known value")
    if row["status"] not in ("open", "resolved"):
        raise ValueError("status is not a known value")
    created = _ts(row["created_at"], "created_at", required=True)
    first = _ts(row["first_response_at"], "first_response_at")
    resolved = _ts(row["resolved_at"], "resolved_at")
    if (first and first < created) or (resolved and resolved < created):
        raise ValueError("a timestamp is before created_at")
    if (row["status"] == "resolved") != (resolved is not None):
        raise ValueError("status does not match resolved_at")
    if row["sla_met"] not in ("", "0", "1"):
        raise ValueError("sla_met is not 0, 1 or empty")
    sla = int(row["sla_met"]) if row["sla_met"] else None
    fmt = lambda dt: dt.strftime(TIME_FORMAT) if dt else None
    return (row["ticket_id"], row["category"], row["priority"], fmt(created), fmt(first), fmt(resolved),
            row["status"], sla)


def _check_header(header):
    header = [h.strip() for h in header]
    counts = Counter(header)
    if sorted(counts.elements()) == sorted(COLUMNS):
        return header
    unwanted = [h for h in counts if h not in COLUMNS]
    shown = [h for h in unwanted if h in KNOWN_UNWANTED]
    parts = []
    if unwanted:
        parts.append(f"{len(unwanted)} unexpected column(s)" + (f" {shown}" if shown else ""))
    if [c for c in COLUMNS if c not in counts]:
        parts.append(f"missing {[c for c in COLUMNS if c not in counts]}")
    if [c for c in COLUMNS if counts[c] > 1]:
        parts.append(f"duplicated {[c for c in COLUMNS if counts[c] > 1]}")
    raise ColumnError("rejected columns: " + ", ".join(parts))


def _read(path):
    """Validate the whole file first, so the database is untouched if the header or file is bad."""
    result, rows, seen = LoadResult(), [], set()
    try:
        # utf-8-sig drops the byte order mark that Excel adds
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            # shortcut: the whole file is held in memory, fine for tens of thousands of tickets
            header = _check_header(next(reader, []))
            index = {name: i for i, name in enumerate(header)}
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
                rows.append(values)
    except UnicodeDecodeError:
        raise LoadError("file is not valid UTF-8") from None
    except csv.Error:
        raise LoadError("file is not valid CSV") from None
    return result, rows


def load_csv(path, conn, placeholder="?"):
    """Replace the tickets table with the CSV contents. Bad rows are reported in the result, not raised."""
    result, rows = _read(path)
    cur = conn.cursor()
    try:
        for stmt in SCHEMA.read_text().split(";"):
            if stmt.strip():
                cur.execute(stmt)
        cur.execute("SELECT * FROM tickets LIMIT 0")
        if [c[0] for c in cur.description] != COLUMNS:
            raise TableError("the tickets table already exists with different columns, drop it first")
        cur.execute("DELETE FROM tickets")
        names = ", ".join(COLUMNS)
        marks = ", ".join([placeholder] * len(COLUMNS))
        cur.executemany(f"INSERT INTO tickets ({names}) VALUES ({marks})", rows)
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    result.loaded = len(rows)
    return result


def is_postgres(conn):
    return type(conn).__module__.split(".")[0] == "psycopg"


def apply_views(conn):
    """Create or refresh the reporting views, using the PostgreSQL variant on a PostgreSQL connection."""
    cur = conn.cursor()
    for stmt in (VIEWS_POSTGRES if is_postgres(conn) else VIEWS).read_text().split(";"):
        if stmt.strip():
            cur.execute(stmt)
    conn.commit()