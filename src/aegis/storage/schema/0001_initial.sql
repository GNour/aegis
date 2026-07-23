CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    state TEXT NOT NULL,
    version INTEGER NOT NULL,
    schema_version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_records (
    key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    principal_type TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    causation_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_outbox (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    event_version INTEGER NOT NULL,
    actor_id TEXT NOT NULL,
    principal_type TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    causation_id TEXT,
    idempotency_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    task_id TEXT REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS flow_runs (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), flow_id TEXT NOT NULL,
    flow_version INTEGER NOT NULL, flow_hash TEXT NOT NULL, routing_reason TEXT NOT NULL,
    state TEXT NOT NULL, current_stage_id TEXT NOT NULL, schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS stage_runs (
    id TEXT PRIMARY KEY, flow_run_id TEXT NOT NULL REFERENCES flow_runs(id), stage_id TEXT NOT NULL,
    stage_snapshot_json TEXT NOT NULL, role_id TEXT NOT NULL, model_alias TEXT NOT NULL,
    skills_json TEXT NOT NULL, capability_profile TEXT NOT NULL, state TEXT NOT NULL,
    ordinal INTEGER NOT NULL, budgets_json TEXT NOT NULL, schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY, stage_run_id TEXT NOT NULL REFERENCES stage_runs(id), runtime TEXT NOT NULL,
    started_at TEXT NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
    tool_tokens INTEGER NOT NULL, cost_usd REAL NOT NULL, native_session_id TEXT,
    herdr_session_id TEXT, finished_at TEXT, failure_class TEXT, exit_result TEXT,
    schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS decision_requests (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), question TEXT NOT NULL,
    options_json TEXT NOT NULL, evidence_json TEXT NOT NULL, impact TEXT NOT NULL,
    requested_by TEXT NOT NULL, resolution TEXT, schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS approval_requests (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), action_payload_hash TEXT NOT NULL,
    scope TEXT NOT NULL, risk TEXT NOT NULL, reason TEXT NOT NULL, expires_at TEXT NOT NULL,
    nonce TEXT NOT NULL, signer_id TEXT, used_at TEXT, use_event_id TEXT, schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS session_links (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
    stage_run_id TEXT NOT NULL REFERENCES stage_runs(id), attempt_id TEXT NOT NULL REFERENCES attempts(id),
    runtime TEXT NOT NULL, native_session_id TEXT, herdr_session_id TEXT,
    sanitized_export_artifact_id TEXT, schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS handoff_packets (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), outcome TEXT NOT NULL,
    changed_files_json TEXT NOT NULL, tests_json TEXT NOT NULL, decisions_json TEXT NOT NULL,
    risks_json TEXT NOT NULL, unresolved_questions_json TEXT NOT NULL, next_action TEXT NOT NULL,
    commit_id TEXT, commit_ids_json TEXT NOT NULL, schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), kind TEXT NOT NULL, uri TEXT NOT NULL,
    digest TEXT NOT NULL, byte_size INTEGER NOT NULL, redaction_class TEXT NOT NULL,
    retention TEXT NOT NULL, producer TEXT NOT NULL, schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_syncs (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), canonical_commit TEXT NOT NULL,
    state TEXT NOT NULL, ready_for_cleanup INTEGER NOT NULL, qmd_receipt TEXT, qmd_collection TEXT,
    qmd_source_commit TEXT, openviking_receipt TEXT, openviking_uri TEXT, openviking_source_commit TEXT,
    schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cleanup_records (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), target_labels_json TEXT NOT NULL,
    preconditions_json TEXT NOT NULL, actions_json TEXT NOT NULL, verified INTEGER NOT NULL,
    state TEXT NOT NULL, failure_reason TEXT, schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY, sequence INTEGER NOT NULL UNIQUE, event_type TEXT NOT NULL,
    event_version INTEGER NOT NULL, actor_id TEXT NOT NULL, correlation_id TEXT NOT NULL,
    payload_json TEXT NOT NULL, prior_hash TEXT NOT NULL, event_hash TEXT NOT NULL,
    occurred_at TEXT NOT NULL, task_id TEXT REFERENCES tasks(id), causation_id TEXT,
    schema_version INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state);
CREATE INDEX IF NOT EXISTS idx_outbox_sequence ON audit_outbox(sequence);
CREATE INDEX IF NOT EXISTS idx_outbox_task_sequence ON audit_outbox(task_id, sequence);
CREATE INDEX IF NOT EXISTS idx_flow_runs_task ON flow_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_stage_runs_flow ON stage_runs(flow_run_id);
CREATE INDEX IF NOT EXISTS idx_attempts_stage ON attempts(stage_run_id);
