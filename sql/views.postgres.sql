-- Reporting views, PostgreSQL variant of views.sql. Same columns and the same rules, using date_trunc and EXTRACT.
-- Weeks start on Monday (date_trunc('week')) and are bucketed by created_at. A test keeps the SLA targets equal to constants.py.
-- Hours and ages are cast to numeric so ROUND(x, n) works. CASCADE drops dependent views so the file can be re-run.

DROP VIEW IF EXISTS sla_targets CASCADE;
CREATE VIEW sla_targets AS
    SELECT 'urgent'::text AS priority, 1.0::numeric AS response_hours, 8.0::numeric AS resolution_hours
    UNION ALL SELECT 'high', 4.0, 24.0
    UNION ALL SELECT 'medium', 8.0, 72.0
    UNION ALL SELECT 'low', 24.0, 120.0;

DROP VIEW IF EXISTS as_of CASCADE;
CREATE VIEW as_of AS
    SELECT GREATEST(MAX(created_at), MAX(first_response_at), MAX(resolved_at)) AS ts
    FROM tickets;

-- A target counts as met or missed once the event happened. If the event has not happened yet, it is a miss
-- when the target time has already passed at the as_of moment, otherwise it is unknown (NULL, not counted).
DROP VIEW IF EXISTS ticket_facts CASCADE;
CREATE VIEW ticket_facts AS
    SELECT t.ticket_id, t.category, t.priority, t.status,
           to_char(date_trunc('week', t.created_at), 'YYYY-MM-DD') AS week,
           (EXTRACT(EPOCH FROM (t.first_response_at - t.created_at)) / 3600.0)::numeric AS response_hours,
           (EXTRACT(EPOCH FROM (t.resolved_at - t.created_at)) / 3600.0)::numeric AS resolution_hours,
           CASE WHEN t.first_response_at IS NOT NULL THEN
                    (CASE WHEN EXTRACT(EPOCH FROM (t.first_response_at - t.created_at)) / 3600.0 <= s.response_hours THEN 1 ELSE 0 END)
                WHEN EXTRACT(EPOCH FROM (a.ts - t.created_at)) / 3600.0 > s.response_hours THEN 0
                ELSE NULL END AS response_met,
           CASE WHEN t.resolved_at IS NOT NULL THEN
                    (CASE WHEN EXTRACT(EPOCH FROM (t.resolved_at - t.created_at)) / 3600.0 <= s.resolution_hours THEN 1 ELSE 0 END)
                WHEN EXTRACT(EPOCH FROM (a.ts - t.created_at)) / 3600.0 > s.resolution_hours THEN 0
                ELSE NULL END AS resolution_met
    FROM tickets t JOIN sla_targets s ON s.priority = t.priority CROSS JOIN as_of a;

DROP VIEW IF EXISTS weekly_summary CASCADE;
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

DROP VIEW IF EXISTS weekly_category_summary CASCADE;
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

DROP VIEW IF EXISTS backlog_age CASCADE;
CREATE VIEW backlog_age AS
    SELECT t.ticket_id, t.category, t.priority,
           ROUND((EXTRACT(EPOCH FROM (a.ts - t.created_at)) / 86400.0)::numeric, 2) AS age_days
    FROM tickets t, as_of a WHERE t.status = 'open';

DROP VIEW IF EXISTS backlog_age_buckets CASCADE;
CREATE VIEW backlog_age_buckets AS
    SELECT CASE WHEN age_days < 1 THEN '0-1 days'
                WHEN age_days < 3 THEN '1-3 days'
                WHEN age_days < 7 THEN '3-7 days'
                ELSE '7+ days' END AS bucket,
           COUNT(*) AS tickets
    FROM backlog_age GROUP BY bucket;
