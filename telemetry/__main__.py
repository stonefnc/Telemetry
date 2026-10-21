"""Command line: python -m telemetry [generate|load|report|all]"""
import argparse
import sqlite3
import sys
from pathlib import Path

from generator.generate import generate, write_csv
from telemetry.loader import LoadError, apply_views, connect, load_csv
from telemetry.report import build_report

# the tool's own scratch file, git-ignored. `all` rewrites it on every run, so it never takes a user file.
DEFAULT_CSV = "data/generated/tickets.csv"
try:
    from psycopg import Error as _PgError
    DB_ERRORS = _PgError
except ImportError:  # psycopg is optional, SQLite needs nothing else
    DB_ERRORS = sqlite3.Error


def _generate(args):
    path = DEFAULT_CSV if args.command == "all" else (args.csv or DEFAULT_CSV)
    try:
        write_csv(path, generate(args.count, args.seed), overwrite=args.command == "all" or args.force)
    except FileExistsError:
        sys.exit(f"{path} already exists, use --force to overwrite it")
    print(f"wrote {path}")
    return path


def _connect(db):
    try:
        return connect(db)
    except DB_ERRORS:
        sys.exit("cannot connect to the database, check TELEMETRY_PG_DSN")


def _load(args, path):
    conn, ph = _connect(args.db)
    try:
        res = load_csv(path, conn, ph)
    except FileNotFoundError:
        sys.exit(f"{path} not found, run generate first")
    except LoadError as e:
        sys.exit(f"load failed: {e}")
    finally:
        conn.close()
    print(f"loaded {res.loaded} tickets, rejected {len(res.rejected)} rows")
    for line, reason in res.rejected[:10]:
        print(f"  line {line}: {reason}")


def _report(args):
    conn, _ = _connect(args.db)
    try:
        apply_views(conn)
        html = build_report(conn)
    except (sqlite3.Error, DB_ERRORS):
        sys.exit("the database has no loaded tickets, run load first")
    except ValueError as e:
        sys.exit(f"report failed: {e}")
    finally:
        conn.close()
    Path(args.out).write_text(html, encoding="utf-8")
    print(f"wrote {args.out}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="telemetry")
    p.add_argument("command", choices=["generate", "load", "report", "all"])
    p.add_argument("--csv", help=f"CSV path for generate and load (default {DEFAULT_CSV}), not accepted by all")
    p.add_argument("--force", action="store_true", help="let generate overwrite an existing file")
    p.add_argument("--db", default="data/telemetry.db")
    p.add_argument("--out", default="report.html")
    p.add_argument("--count", type=int, default=2500)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)
    if args.command == "all" and args.csv:
        sys.exit(f"all always writes its own {DEFAULT_CSV}, use generate, load and report to work with another file")
    path = args.csv or DEFAULT_CSV
    if args.command in ("generate", "all"):
        path = _generate(args)
    if args.command in ("load", "all"):
        _load(args, path)
    if args.command in ("report", "all"):
        _report(args)


if __name__ == "__main__":
    main()