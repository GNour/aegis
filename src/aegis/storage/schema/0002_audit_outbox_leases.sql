ALTER TABLE audit_outbox ADD COLUMN claim_token TEXT;
ALTER TABLE audit_outbox ADD COLUMN claim_expires_at TEXT;
ALTER TABLE audit_outbox ADD COLUMN flushed_at TEXT;
