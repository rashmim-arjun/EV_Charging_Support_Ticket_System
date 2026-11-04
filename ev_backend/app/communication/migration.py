SQL = """
CREATE TABLE communication_runs (
 run_id TEXT PRIMARY KEY, simulator_version TEXT NOT NULL, config_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE communication_sessions (
 session_id TEXT PRIMARY KEY REFERENCES charging_sessions(session_id),
 run_id TEXT NOT NULL REFERENCES communication_runs(run_id), trace_id TEXT NOT NULL UNIQUE,
 app_id TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT NOT NULL,
 status TEXT NOT NULL, components_json TEXT NOT NULL
);
CREATE TABLE communication_events (
 event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES communication_sessions(session_id) ON DELETE CASCADE,
 trace_id TEXT NOT NULL, correlation_id TEXT NOT NULL, message_id TEXT, parent_event_id TEXT,
 component_id TEXT NOT NULL, component_type TEXT NOT NULL,
 timestamp TEXT NOT NULL, sequence INTEGER NOT NULL, event_type TEXT NOT NULL,
 severity TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, payload_json TEXT NOT NULL,
 UNIQUE(session_id, sequence)
);
CREATE INDEX idx_comm_events_session ON communication_events(session_id,timestamp,sequence);
CREATE INDEX idx_comm_events_correlation ON communication_events(correlation_id,message_id);
CREATE TABLE communication_truth (
 session_id TEXT PRIMARY KEY REFERENCES communication_sessions(session_id) ON DELETE CASCADE,
 template_id TEXT NOT NULL, split TEXT NOT NULL, annotations_json TEXT NOT NULL
);
CREATE TABLE communication_diagnoses (
 id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL REFERENCES communication_sessions(session_id) ON DELETE CASCADE,
 result_json TEXT NOT NULL, case_id TEXT REFERENCES cases(case_id) ON DELETE SET NULL,
 created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""
