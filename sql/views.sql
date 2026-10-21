-- Reporting views. SQLite syntax (date and julianday). The PostgreSQL variant is views.postgres.sql, keep the two in step.
-- Weeks start on Monday and are bucketed by created_at. SLA targets mirror generator.generate.SLA_TARGETS.
-- Durations come from whole seconds (strftime '%s'), not julianday, so an event exactly on its target counts as met.

DROP VIEW IF EXISTS sla_targets;
CREATE VIEW sla_targets AS
    SELECT 'urgent' AS priority, 1.0 AS response_hours, 8.0 AS resolution_hours
    UNION ALL SELECT 'high', 4.0, 24.0
    UNION ALL SELECT 'medium', 8.0, 72.0
    UNION ALL SELECT 'low', 24.0, 120.0;

DROP VIEW IF EXISTS as_of;
CREATE VIEW as_of AS
    SELECT MAX(MAX(created_at), COALESCE(MAX(first_response_at), ''), COALESCE(MAX(resolved_at), '')) AS ts
    FROM tickets;
-- A target counts as met or missed once the event happened. If the event has not happened yet, it is a miss
-- when the target time has already passed at the as_of moment, otherwise it is unknown (NULL, not counted).
DROP VIEW IF EXISTS ticket_facts;
CREATE VIEW ticket_facts AS
    SELECT t.ticket_id, t.category, t.priority, t.status,
           date(t.created_at, 'weekday 0', '-6 days') AS week,
           (strftime('%s', t.first_response_at) - strftime('%s', t.created_at)) / 3600.0 AS response_hours,
           (strftime('%s', t.resolved_at) - strftime('%s', t.created_at)) / 3600.0 AS resolution_hours,
           CASE WHEN t.first_response_at IS NOT NULL THEN
                    (CASE WHEN (strftime('%s', t.first_response_at) - strftime('%s', t.created_at)) / 3600.0 <= s.response_hours THEN 1 ELSE 0 END)
                WHEN (strftime('%s', a.ts) - strftime('%s', t.created_at)) / 3600.0 > s.response_hours THEN 0
                ELSE NULL END AS response_met,
           CASE WHEN t.resolved_at IS NOT NULL THEN
                    (CASE WHEN (strftime('%s', t.resolved_at) - strftime('%s', t.created_at)) / 3600.0 <= s.resolution_hours THEN 1 ELSE 0 END)
                WHEN (strftime('%s', a.ts) - strftime('%s', t.created_at)) / 3600.0 > s.resolution_hours THEN 0
                ELSE NULL END AS resolution_met
    FROM tickets t JOIN sla_targets s ON s.priority = t.priority CROSS JOIN as_of a;

DROP VIEW IF EXISTS weekly_summary;
CREATE VIEW weekly_summary AS
    SELECT week,
           COUNT(*) AS created,
           COUNT(resolution_hours) AS resolved,
           ROUND(1.0 * COUNT(resolution_hours) / COUNT(*), 4) AS close_rate,
           ROUND(AVG(response_hours), 2) AS avg_first_response_hours,
           ROUND(AVG(resolution_hours), 2) AS avg_resolution_hours,
           ROUND(100.0 * AVG(response_met), 2) AS response_sla_pct,
           ROUND(100.0 * AVG(resolution_met), 2) AS resolution_sla_pct
    FROM ticket_facts GROUP BY week;

DROP VIEW IF EXISTS weekly_category_summary;
CREATE VIEW weekly_category_summary AS
    SELECT week, category,
           COUNT(*) AS created,
           COUNT(resolution_hours) AS resolved,
           ROUND(1.0 * COUNT(resolution_hours) / COUNT(*), 4) AS close_rate,
           ROUND(AVG(response_hours), 2) AS avg_first_response_hours,
           ROUND(AVG(resolution_hours), 2) AS avg_resolution_hours,
           ROUND(100.0 * AVG(response_met), 2) AS response_sla_pct,
           ROUND(100.0 * AVG(resolution_met), 2) AS resolution_sla_pct
    FROM ticket_facts GROUP BY week, category;


DROP VIEW IF EXISTS backlog_age;
CREATE VIEW backlog_age AS
    SELECT t.ticket_id, t.category, t.priority,
           ROUND(julianday(a.ts) - julianday(t.created_at), 2) AS age_days
    FROM tickets t, as_of a WHERE t.status = 'open';

DROP VIEW IF EXISTS backlog_age_buckets;
CREATE VIEW backlog_age_buckets AS
    SELECT CASE WHEN age_days < 1 THEN '0-1 days'
                WHEN age_days < 3 THEN '1-3 days'
                WHEN age_days < 7 THEN '3-7 days'
                ELSE '7+ days' END AS bucket,
           COUNT(*) AS tickets
    FROM backlog_age GROUP BY bucket;