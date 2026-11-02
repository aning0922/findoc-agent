"""Additive v10 only. Existing migration statements/checksums stay untouched."""

CONVERSATION_MIGRATION = (
    10,
    "conversations_v1",
    (
        """CREATE TABLE conversations (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL UNIQUE, workspace_id TEXT NOT NULL,
            title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 120),
            source_scope_sha TEXT NOT NULL CHECK(length(source_scope_sha)=64),
            source_payload TEXT NOT NULL CHECK(json_valid(source_payload)),
            source_payload_sha TEXT NOT NULL CHECK(length(source_payload_sha)=64),
            status TEXT NOT NULL CHECK(status='active'), created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, next_seq INTEGER NOT NULL DEFAULT 1 CHECK(next_seq>=1),
            UNIQUE(workspace_id,conversation_id))""",
        """CREATE TABLE conversation_sources (
            workspace_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
            document_id TEXT NOT NULL, company_id TEXT NOT NULL,
            source_revision TEXT NOT NULL REFERENCES document_sources(source_revision),
            content_sha256 TEXT NOT NULL, report_year INTEGER NOT NULL,
            report_type TEXT NOT NULL CHECK(report_type='annual'),
            period_start TEXT NOT NULL, period_end TEXT NOT NULL, basis TEXT NOT NULL,
            attempt INTEGER NOT NULL CHECK(attempt>=1), parser_version TEXT NOT NULL,
            PRIMARY KEY(workspace_id,conversation_id,document_id),
            FOREIGN KEY(workspace_id,conversation_id)
                REFERENCES conversations(workspace_id,conversation_id) ON DELETE CASCADE,
            FOREIGN KEY(workspace_id,document_id) REFERENCES documents(workspace_id,document_id))""",
        """CREATE TABLE conversation_operations (
            workspace_id TEXT NOT NULL, operation_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('create_conversation','send_turn','delete_conversation')),
            request_sha TEXT NOT NULL CHECK(length(request_sha)=64),
            conversation_id TEXT NOT NULL, turn_id TEXT,
            status TEXT NOT NULL CHECK(status IN ('running','completed','refused','failed','interrupted')),
            resource_deleted INTEGER NOT NULL CHECK(resource_deleted IN (0,1)),
            created_at TEXT NOT NULL, ended_at TEXT, error_code TEXT,
            payload TEXT NOT NULL CHECK(json_valid(payload)), payload_sha TEXT NOT NULL,
            PRIMARY KEY(workspace_id,operation_id),
            CHECK((status='running' AND ended_at IS NULL) OR
                  (status!='running' AND ended_at IS NOT NULL)))""",
        """CREATE TABLE conversation_turns (
            workspace_id TEXT NOT NULL, conversation_id TEXT NOT NULL,
            turn_id TEXT NOT NULL UNIQUE, seq INTEGER NOT NULL CHECK(seq>=1),
            operation_id TEXT NOT NULL, request_sha TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('running','completed','refused','failed','interrupted')),
            created_at TEXT NOT NULL, ended_at TEXT,
            payload TEXT NOT NULL CHECK(json_valid(payload)), payload_sha TEXT NOT NULL,
            execution_json TEXT NOT NULL CHECK(json_valid(execution_json)), execution_sha TEXT NOT NULL,
            claim TEXT,
            PRIMARY KEY(workspace_id,conversation_id,turn_id),
            UNIQUE(workspace_id,conversation_id,seq), UNIQUE(workspace_id,operation_id),
            FOREIGN KEY(workspace_id,conversation_id)
                REFERENCES conversations(workspace_id,conversation_id) ON DELETE CASCADE,
            FOREIGN KEY(workspace_id,operation_id)
                REFERENCES conversation_operations(workspace_id,operation_id),
            CHECK((status='running' AND ended_at IS NULL AND claim IS NOT NULL) OR
                  (status!='running' AND ended_at IS NOT NULL AND claim IS NULL)))""",
        """CREATE TABLE conversation_tool_events (
            workspace_id TEXT NOT NULL, conversation_id TEXT NOT NULL, turn_id TEXT NOT NULL,
            event_seq INTEGER NOT NULL CHECK(event_seq>=1),
            payload TEXT NOT NULL CHECK(json_valid(payload)), payload_sha TEXT NOT NULL,
            PRIMARY KEY(workspace_id,conversation_id,turn_id,event_seq),
            FOREIGN KEY(workspace_id,conversation_id,turn_id)
                REFERENCES conversation_turns(workspace_id,conversation_id,turn_id) ON DELETE CASCADE)""",
        "CREATE INDEX conversation_history ON conversations(workspace_id,sequence DESC)",
        """CREATE INDEX conversation_turn_history
            ON conversation_turns(workspace_id,conversation_id,seq)""",
        """CREATE UNIQUE INDEX conversation_one_running
            ON conversation_turns(workspace_id,conversation_id) WHERE status='running'""",
        """CREATE TRIGGER conversation_scope_immutable BEFORE UPDATE ON conversations
            WHEN NEW.sequence!=OLD.sequence OR NEW.conversation_id!=OLD.conversation_id
            OR NEW.workspace_id!=OLD.workspace_id OR NEW.created_at!=OLD.created_at
            OR NEW.source_scope_sha!=OLD.source_scope_sha OR NEW.source_payload!=OLD.source_payload
            OR NEW.source_payload_sha!=OLD.source_payload_sha OR NEW.status!=OLD.status
            BEGIN SELECT RAISE(ABORT,'conversation scope is immutable'); END""",
        """CREATE TRIGGER conversation_sources_immutable BEFORE UPDATE ON conversation_sources
            BEGIN SELECT RAISE(ABORT,'conversation sources are immutable'); END""",
        """CREATE TRIGGER conversation_turn_terminal BEFORE UPDATE ON conversation_turns
            WHEN OLD.status!='running'
            BEGIN SELECT RAISE(ABORT,'conversation terminal is immutable'); END""",
        """CREATE TRIGGER conversation_turn_identity BEFORE UPDATE ON conversation_turns
            WHEN NEW.workspace_id!=OLD.workspace_id OR NEW.conversation_id!=OLD.conversation_id
            OR NEW.turn_id!=OLD.turn_id OR NEW.seq!=OLD.seq OR NEW.operation_id!=OLD.operation_id
            OR NEW.request_sha!=OLD.request_sha OR NEW.created_at!=OLD.created_at
            OR (NEW.status='running' AND NEW.claim IS NOT OLD.claim)
            BEGIN SELECT RAISE(ABORT,'conversation turn identity is immutable'); END""",
        """CREATE TRIGGER conversation_event_immutable BEFORE UPDATE ON conversation_tool_events
            BEGIN SELECT RAISE(ABORT,'conversation event is immutable'); END""",
        """CREATE TRIGGER conversation_event_terminal BEFORE INSERT ON conversation_tool_events
            WHEN NOT EXISTS(SELECT 1 FROM conversation_turns WHERE workspace_id=NEW.workspace_id
            AND conversation_id=NEW.conversation_id AND turn_id=NEW.turn_id AND status='running')
            BEGIN SELECT RAISE(ABORT,'conversation event requires running turn'); END""",
        """CREATE TRIGGER conversation_operation_identity BEFORE UPDATE ON conversation_operations
            WHEN NEW.workspace_id!=OLD.workspace_id OR NEW.operation_id!=OLD.operation_id
            OR NEW.kind!=OLD.kind OR NEW.request_sha!=OLD.request_sha
            OR NEW.conversation_id!=OLD.conversation_id OR NEW.turn_id IS NOT OLD.turn_id
            OR NEW.created_at!=OLD.created_at
            OR (OLD.status!='running' AND (NEW.status!=OLD.status
                OR NEW.ended_at IS NOT OLD.ended_at OR NEW.error_code IS NOT OLD.error_code))
            OR NEW.resource_deleted<OLD.resource_deleted
            BEGIN SELECT RAISE(ABORT,'conversation operation identity is immutable'); END""",
    ),
)
