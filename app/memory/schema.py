"""Export only: the owning backend registers v11 after integrating v10."""

MEMORY_MIGRATION = (
    11,
    "research_preferences_v1",
    (
        """CREATE TABLE memory_items (
            workspace_id TEXT NOT NULL, principal_id TEXT NOT NULL,
            memory_id TEXT NOT NULL UNIQUE, type TEXT NOT NULL CHECK(type='research_preference'),
            key TEXT NOT NULL, value TEXT NOT NULL CHECK(length(value) BETWEEN 1 AND 200),
            source_turn_id TEXT, revision INTEGER NOT NULL CHECK(revision>=1),
            confirmed_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(workspace_id,principal_id,memory_id),
            UNIQUE(workspace_id,principal_id,type,key),
            CHECK((key='analysis_focus' AND value IN ('cash_flow','revenue','profitability','balanced'))
                OR (key='display_unit' AND value IN
                    ('CNY_YUAN','CNY_TEN_THOUSAND','CNY_HUNDRED_MILLION'))
                OR (key='research_habit' AND value IN ('evidence_first','compare_periods_first'))))""",
        """CREATE TABLE memory_operations (
            workspace_id TEXT NOT NULL, principal_id TEXT NOT NULL, operation_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('create_memory','update_memory','delete_memory')),
            request_sha TEXT NOT NULL CHECK(length(request_sha)=64
                AND request_sha NOT GLOB '*[^0-9a-f]*'), memory_id TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK(revision>=1),
            resource_deleted INTEGER NOT NULL CHECK(resource_deleted IN (0,1)),
            created_at TEXT NOT NULL, PRIMARY KEY(workspace_id,principal_id,operation_id))""",
        """CREATE TABLE memory_events (
            workspace_id TEXT NOT NULL, principal_id TEXT NOT NULL, event_id TEXT NOT NULL UNIQUE,
            memory_id TEXT NOT NULL, action TEXT NOT NULL
                CHECK(action IN ('create_memory','update_memory','delete_memory')),
            revision INTEGER NOT NULL CHECK(revision>=1), operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL, PRIMARY KEY(workspace_id,principal_id,event_id),
            FOREIGN KEY(workspace_id,principal_id,operation_id)
                REFERENCES memory_operations(workspace_id,principal_id,operation_id))""",
        """CREATE TABLE memory_context_generation (
            workspace_id TEXT NOT NULL, principal_id TEXT NOT NULL,
            generation INTEGER NOT NULL CHECK(generation>=0),
            PRIMARY KEY(workspace_id,principal_id))""",
        """CREATE TABLE memory_context_exclusions (
            workspace_id TEXT NOT NULL, principal_id TEXT NOT NULL, turn_id TEXT NOT NULL,
            reason TEXT NOT NULL CHECK(reason='memory_source'),
            PRIMARY KEY(workspace_id,principal_id,turn_id))""",
        """CREATE TRIGGER memory_event_immutable BEFORE UPDATE ON memory_events
            BEGIN SELECT RAISE(ABORT,'memory events are immutable'); END""",
        """CREATE TRIGGER memory_operation_immutable BEFORE UPDATE ON memory_operations
            WHEN NEW.workspace_id!=OLD.workspace_id OR NEW.principal_id!=OLD.principal_id
                OR NEW.operation_id!=OLD.operation_id OR NEW.kind!=OLD.kind
                OR NEW.request_sha!=OLD.request_sha OR NEW.memory_id!=OLD.memory_id
                OR NEW.revision!=OLD.revision OR NEW.created_at!=OLD.created_at
                OR NEW.resource_deleted<OLD.resource_deleted
            BEGIN SELECT RAISE(ABORT,'memory operation identity is immutable'); END""",
    ),
)
