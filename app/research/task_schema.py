"""D19 additive task, operation and LangGraph checkpoint storage."""

TASK_MIGRATION = (
    8,
    "persistent_template_tasks_v1",
    (
        """CREATE TABLE template_tasks (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL UNIQUE,
    workspace_id TEXT NOT NULL, operation_id TEXT NOT NULL, request_sha TEXT NOT NULL,
    revision INTEGER NOT NULL, claim TEXT, payload TEXT NOT NULL, payload_sha TEXT NOT NULL,
    UNIQUE(workspace_id,operation_id))""",
        """CREATE TABLE template_operations (
    workspace_id TEXT NOT NULL, operation_id TEXT NOT NULL, task_id TEXT NOT NULL,
    request_sha TEXT NOT NULL, outcome TEXT NOT NULL,
    PRIMARY KEY(workspace_id,operation_id))""",
        """CREATE TABLE template_checkpoints (
    workspace_id TEXT NOT NULL, task_id TEXT NOT NULL, namespace TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL, parent_id TEXT, payload BLOB NOT NULL, payload_sha TEXT NOT NULL,
    PRIMARY KEY(workspace_id,task_id,namespace,checkpoint_id))""",
        """CREATE TABLE template_checkpoint_writes (
    workspace_id TEXT NOT NULL, task_id TEXT NOT NULL, namespace TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL, node_task_id TEXT NOT NULL, write_index INTEGER NOT NULL,
    payload BLOB NOT NULL, payload_sha TEXT NOT NULL,
    PRIMARY KEY(workspace_id,task_id,namespace,checkpoint_id,node_task_id,write_index))""",
        """CREATE TABLE financial_acceptance_revocations (
    workspace_id TEXT NOT NULL, receipt_id TEXT NOT NULL, confirmation_kind TEXT NOT NULL,
    revoked_at TEXT NOT NULL, reason TEXT NOT NULL,
    PRIMARY KEY(workspace_id,receipt_id,confirmation_kind))""",
        """CREATE TRIGGER receipt_revocation_immutable_update BEFORE UPDATE ON financial_acceptance_revocations
    BEGIN SELECT RAISE(ABORT,'receipt revocation is immutable'); END""",
        """CREATE TRIGGER receipt_revocation_immutable_delete BEFORE DELETE ON financial_acceptance_revocations
    BEGIN SELECT RAISE(ABORT,'receipt revocation is immutable'); END""",
        """CREATE TRIGGER template_identity_immutable BEFORE UPDATE ON template_tasks
    WHEN NEW.task_id != OLD.task_id OR NEW.workspace_id != OLD.workspace_id
    OR NEW.operation_id != OLD.operation_id OR NEW.request_sha != OLD.request_sha
    OR NEW.sequence != OLD.sequence
    BEGIN SELECT RAISE(ABORT,'template identity is immutable'); END""",
    ),
)
