"""Constants shared by the generator, loader and report."""
COLUMNS = ["ticket_id", "category", "priority", "created_at", "first_response_at",
           "resolved_at", "status", "sla_met"]
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
# priority: (response target hours, resolution target hours). sql/views.sql and sql/views.postgres.sql repeat these, tests keep them equal.
SLA_TARGETS = {"urgent": (1, 8), "high": (4, 24), "medium": (8, 72), "low": (24, 120)}