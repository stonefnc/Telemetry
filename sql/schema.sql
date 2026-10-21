CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    priority TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    first_response_at TIMESTAMP,
    resolved_at TIMESTAMP,
    status TEXT NOT NULL,
    sla_met INTEGER
);