CREATE TABLE IF NOT EXISTS request_idempotency (
    key TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS principal_nonces (
    nonce TEXT PRIMARY KEY,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS note_proposals (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    task_id TEXT REFERENCES tasks(id),
    markdown_text TEXT NOT NULL,
    source_metadata_json TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    message TEXT NOT NULL,
    schedule TEXT NOT NULL,
    timezone TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_note_proposals_task_id ON note_proposals(task_id);
