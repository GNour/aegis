CREATE TABLE IF NOT EXISTS stage_execution_packets (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    flow_run_id TEXT NOT NULL REFERENCES flow_runs(id),
    stage_run_id TEXT NOT NULL UNIQUE REFERENCES stage_runs(id),
    schema_version INTEGER NOT NULL,
    packet_json TEXT NOT NULL,
    packet_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stage_execution_packets_task_id
    ON stage_execution_packets(task_id);
CREATE INDEX IF NOT EXISTS idx_stage_execution_packets_flow_run_id
    ON stage_execution_packets(flow_run_id);
