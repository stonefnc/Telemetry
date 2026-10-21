"""Command line: python -m telemetry [generate|load|report|all]"""
import argparse
import os
import sys
from pathlib import Path

from generator.generate import generate, write_csv
from telemetry.loader import ColumnError, apply_views, connect, load_csv
from telemetry.report import build_report


def _load(args):
    conn, ph = connect(args.db)
    try:
        res = load_csv(args.csv, conn, ph)
    except ColumnError as e:
        sys.exit(f"load failed: {e}")
    print(f"loaded {res.loaded} tickets, rejected {len(res.rejected)} rows")
    for line, reason in res.rejected[:10]:
        print(f"  line {line}: {reason}")
    return conn


def _report(args, conn=None):
    if os.environ.get("TELEMETRY_PG_DSN"):
        sys.exit("report needs the SQLite views, the PostgreSQL view variant is planned")
    if conn is None:
        conn, _ = connect(args.db)
    apply_views(conn)
    Path(args.out).write_text(build_report(conn), encoding="utf-8")
    print(f"wrote {args.out}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="telemetry")
    p.add_argument("command", choices=["generate", "load", "report", "all"])
    p.add_argument("--csv", default="data/tickets.csv")
    p.add_argument("--db", default="data/telemetry.db")
    p.add_argument("--out", default="report.html")
    p.add_argument("--count", type=int, default=2500)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)
    if args.command in ("generate", "all"):
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        write_csv(args.csv, generate(args.count, args.seed))
        print(f"wrote {args.csv}")
    conn = _load(args) if args.command in ("load", "all") else None
    if args.command in ("report", "all"):
        _report(args, conn)


if __name__ == "__main__":
    main()