"""Fake help desk ticket generator. Synthetic data only, no names, emails or descriptions."""
import csv
import random
from datetime import datetime, timedelta

COLUMNS = ["ticket_id", "category", "priority", "created_at", "first_response_at",
           "resolved_at", "status", "sla_met"]

# category: (share of tickets, resolution time multiplier)
CATEGORIES = {
    "device repair": (0.18, 2.0),
    "iPad setup": (0.14, 0.8),
    "Chromebook loss": (0.06, 2.5),
    "password reset": (0.25, 0.3),
    "Wi-Fi": (0.15, 1.2),
    "printing": (0.12, 0.7),
    "account changes": (0.10, 0.9),
}
PRIORITY_SHARE = {"low": 0.30, "medium": 0.50, "high": 0.16, "urgent": 0.04}
# priority: (response target hours, resolution target hours)
SLA_TARGETS = {"urgent": (1, 8), "high": (4, 24), "medium": (8, 72), "low": (24, 120)}

START = datetime(2023, 8, 7)  # a Monday, start of school year one
END = datetime(2025, 6, 27)  # tickets are as of this date, later ones stay open
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def week_weight(week_start):
    """Relative ticket volume for a week: back-to-school rush, summer lull, holiday dip."""
    m = week_start.month
    if m == 8:
        return 3.0
    if m == 9:
        return 2.0
    if m in (6, 7) and not (m == 6 and week_start.day < 14):
        return 0.3
    if m == 12 and week_start.day > 18 or m == 1 and week_start.day < 4:
        return 0.4
    return 1.0


def _weeks():
    weeks, w = [], START
    while w < END:
        weeks.append(w)
        w += timedelta(days=7)
    return weeks


def generate(n=2500, seed=42):
    rng = random.Random(seed)
    weeks = _weeks()
    weights = [week_weight(w) for w in weeks]
    cats, cat_w = zip(*[(c, v[0]) for c, v in CATEGORIES.items()])
    pris, pri_w = zip(*PRIORITY_SHARE.items())
    created = []
    for _ in range(n):
        week = rng.choices(weeks, weights)[0]
        created.append(week + timedelta(days=rng.randrange(5), hours=7, minutes=rng.randrange(0, 540)))
    created.sort()
    rows = []
    for i, c in enumerate(created, 1):
        cat = rng.choices(cats, cat_w)[0]
        pri = rng.choices(pris, pri_w)[0]
        resp_t, res_t = SLA_TARGETS[pri]
        # busy weeks are slower, which produces more SLA misses in August and September
        load = 1.5 if c.month in (8, 9) else 1.0
        resp_h = resp_t * load * rng.lognormvariate(-1.0, 0.9)
        res_h = res_t * CATEGORIES[cat][1] * load * rng.lognormvariate(-1.2, 0.9)
        res_h = max(res_h, resp_h)
        first = c + timedelta(hours=resp_h)
        done = c + timedelta(hours=res_h)
        if done > END:
            status, resolved, sla = "open", "", ""
            first_s = first.strftime(TIME_FORMAT) if first <= END else ""
        else:
            status, resolved = "resolved", done.strftime(TIME_FORMAT)
            first_s = first.strftime(TIME_FORMAT)
            sla = int(resp_h <= resp_t and res_h <= res_t)
        rows.append({"ticket_id": f"T-{i:05d}", "category": cat, "priority": pri,
                     "created_at": c.strftime(TIME_FORMAT), "first_response_at": first_s,
                     "resolved_at": resolved, "status": status, "sla_met": sla})
    return rows


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "data/tickets.csv"
    write_csv(out, generate())
    print(f"wrote {out}")