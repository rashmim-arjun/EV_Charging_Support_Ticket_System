SQL = """
ALTER TABLE communication_events ADD COLUMN attempt_id TEXT;
ALTER TABLE case_checks ADD COLUMN diagnosis_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE case_evidence ADD COLUMN diagnosis_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE resolutions ADD COLUMN diagnosis_version INTEGER NOT NULL DEFAULT 1;
DROP INDEX idx_resolution_case;
CREATE UNIQUE INDEX idx_resolution_case_version ON resolutions(case_id,diagnosis_version);
CREATE TABLE support_tickets (
 case_id TEXT PRIMARY KEY REFERENCES cases(case_id) ON DELETE CASCADE,
 state TEXT NOT NULL DEFAULT 'new' CHECK(state IN ('new','investigating','awaiting_evidence','assigned','escalated','resolved','closed')),
 priority TEXT NOT NULL DEFAULT 'P2' CHECK(priority IN ('P0','P1','P2','P3')),
 assigned_team TEXT NOT NULL DEFAULT 'triage',
 supporting_teams_json TEXT NOT NULL DEFAULT '[]',
 decision_json TEXT NOT NULL DEFAULT '{}',
 manual_assignment INTEGER NOT NULL DEFAULT 0,
 manual_priority INTEGER NOT NULL DEFAULT 0,
 version INTEGER NOT NULL DEFAULT 1,
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 resolved_at TEXT, closed_at TEXT
);
CREATE TABLE ticket_history (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
 action TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL,
 before_json TEXT NOT NULL DEFAULT '{}', after_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX idx_ticket_history_case ON ticket_history(case_id,id);
CREATE INDEX idx_ticket_queue ON support_tickets(state,assigned_team,priority);
INSERT INTO support_tickets(case_id,state,resolved_at)
 SELECT case_id,CASE WHEN status='resolved' THEN 'resolved' ELSE 'new' END,
 CASE WHEN status='resolved' THEN created_at ELSE NULL END FROM cases;
INSERT INTO ticket_history(case_id,action,actor,reason,after_json)
 SELECT case_id,'migrated','system','Existing case retained as the same support ticket; no inferred historical routing.',
 json_object('state',state,'assigned_team',assigned_team,'priority',priority) FROM support_tickets;
CREATE TRIGGER create_support_ticket AFTER INSERT ON cases BEGIN
 INSERT INTO support_tickets(case_id) VALUES (NEW.case_id);
 INSERT INTO ticket_history(case_id,action,actor,reason,after_json)
 VALUES (NEW.case_id,'created','system','Customer complaint recorded as support ticket.', '{"state":"new"}');
END;
"""
