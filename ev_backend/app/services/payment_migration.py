"""Add manual verification without rewriting diagnostic payment observations."""

SQL = """
CREATE TABLE payment_submissions (
 submission_id TEXT PRIMARY KEY,
 case_id TEXT NOT NULL REFERENCES cases(case_id),
 transaction_reference TEXT,
 submitted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 source TEXT NOT NULL CHECK(source IN ('customer','legacy_claim')),
 legacy_json TEXT,
 proof_name TEXT, proof_type TEXT, proof_size INTEGER, proof_sha256 TEXT,
 proof_content BLOB
);
CREATE INDEX idx_payment_submissions_case ON payment_submissions(case_id,submitted_at);
CREATE TABLE ticket_payments (
 case_id TEXT PRIMARY KEY REFERENCES cases(case_id),
 status TEXT NOT NULL DEFAULT 'not_submitted'
   CHECK(status IN ('not_submitted','submitted','under_review','verified','rejected')),
 version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
 submission_id TEXT REFERENCES payment_submissions(submission_id),
 reviewer_id TEXT REFERENCES reviewers(reviewer_id),
 reviewed_at TEXT, reason TEXT,
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
INSERT INTO ticket_payments(case_id) SELECT case_id FROM cases;
CREATE TRIGGER create_ticket_payment AFTER INSERT ON cases BEGIN
 INSERT INTO ticket_payments(case_id) VALUES (NEW.case_id);
END;
INSERT INTO reviewers(reviewer_id,name,role,active)
 SELECT 'rev-payment-001','Local payment reviewer','payment_reviewer',1
 WHERE NOT EXISTS(SELECT 1 FROM reviewers WHERE reviewer_id='rev-payment-001');

-- "Paid" was never evidence of a manual review in the v6 schema. Preserve the
-- original claim/reference and require review; never infer a successful review.
INSERT INTO payment_submissions(submission_id,case_id,transaction_reference,source,legacy_json)
 SELECT 'legacy-'||c.case_id,c.case_id,s.payment_ref,'legacy_claim',
 json_object('reported_payment_status',c.reported_payment_status,
   'session_reference',c.reported_session_ref,'payment_reference',s.payment_ref,
   'payment_record_ids',json((SELECT json_group_array(p.payment_id) FROM payment_records p
      WHERE p.session_id=c.reported_session_ref AND lower(trim(p.status)) IN ('paid','verified'))))
 FROM cases c LEFT JOIN charging_sessions s ON s.session_id=c.reported_session_ref
 WHERE lower(trim(c.reported_payment_status)) IN ('paid','verified','success')
    OR EXISTS(SELECT 1 FROM payment_records p WHERE p.session_id=c.reported_session_ref
              AND lower(trim(p.status)) IN ('paid','verified'));
UPDATE ticket_payments SET status='under_review',version=1,submission_id='legacy-'||case_id
 WHERE case_id IN (SELECT case_id FROM payment_submissions WHERE source='legacy_claim');
INSERT INTO ticket_history(case_id,action,actor,reason,before_json,after_json)
 SELECT t.case_id,'payment_legacy_review_required','system',
 'Historical payment claim retained; no independent or manual verification evidence exists.',
 json_object('legacy',json(s.legacy_json)),
 json_object('payment_status','under_review','payment_version',1,'submission_id',s.submission_id)
 FROM ticket_payments t JOIN payment_submissions s ON s.submission_id=t.submission_id
 WHERE s.source='legacy_claim';
"""

# The running development backend may already have applied v7. Use a new
# migration rather than changing its marker or discarding any proof/history.
RESET_COMPATIBILITY_SQL = """
CREATE TABLE payment_submissions_v8 (
 submission_id TEXT PRIMARY KEY,
 case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
 transaction_reference TEXT,
 submitted_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 source TEXT NOT NULL CHECK(source IN ('customer','legacy_claim')),
 legacy_json TEXT,
 proof_name TEXT, proof_type TEXT, proof_size INTEGER, proof_sha256 TEXT,
 proof_content BLOB
);
INSERT INTO payment_submissions_v8 SELECT * FROM payment_submissions;
CREATE TABLE ticket_payments_v8 (
 case_id TEXT PRIMARY KEY REFERENCES cases(case_id) ON DELETE CASCADE,
 status TEXT NOT NULL DEFAULT 'not_submitted'
   CHECK(status IN ('not_submitted','submitted','under_review','verified','rejected')),
 version INTEGER NOT NULL DEFAULT 0 CHECK(version>=0),
 submission_id TEXT REFERENCES payment_submissions_v8(submission_id),
 reviewer_id TEXT REFERENCES reviewers(reviewer_id),
 reviewed_at TEXT, reason TEXT,
 updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
INSERT INTO ticket_payments_v8 SELECT * FROM ticket_payments;
DROP TRIGGER create_ticket_payment;
DROP TABLE ticket_payments;
DROP TABLE payment_submissions;
ALTER TABLE payment_submissions_v8 RENAME TO payment_submissions;
ALTER TABLE ticket_payments_v8 RENAME TO ticket_payments;
CREATE INDEX idx_payment_submissions_case ON payment_submissions(case_id,submitted_at);
CREATE TRIGGER create_ticket_payment AFTER INSERT ON cases BEGIN
 INSERT INTO ticket_payments(case_id) VALUES (NEW.case_id);
END;
"""
