"""Append-only v12; never revise the applied v10/v11 migration text."""

CONVERSATION_CONTEXT_MIGRATION = (12, "conversation_summary_v1", (
    """CREATE TABLE conversation_summaries (
        workspace_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
        version INTEGER NOT NULL CHECK(version>=1),
        covered_from_seq INTEGER NOT NULL CHECK(covered_from_seq>=1),
        covered_through_seq INTEGER NOT NULL CHECK(covered_through_seq>=covered_from_seq),
        source_scope_sha TEXT NOT NULL, memory_generation INTEGER NOT NULL,
        payload TEXT NOT NULL CHECK(json_valid(payload)), payload_sha TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(workspace_id,conversation_id,version),
        FOREIGN KEY(workspace_id,conversation_id)
            REFERENCES conversations(workspace_id,conversation_id) ON DELETE CASCADE)""",
    """CREATE TRIGGER conversation_summary_immutable BEFORE UPDATE ON conversation_summaries
        BEGIN SELECT RAISE(ABORT,'conversation summary is immutable'); END""",
))
