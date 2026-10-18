"""Reviewed D23 migration 9: immutable revisions/operations/refs, atomic head fence."""

REPORT_MIGRATION = (
    9,
    "immutable_report_revisions_v1",
    (
        """CREATE TABLE reports (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id TEXT NOT NULL, report_id TEXT NOT NULL,
            created_at TEXT NOT NULL, current_revision INTEGER NOT NULL CHECK(current_revision>=1),
            UNIQUE(workspace_id,report_id),
            FOREIGN KEY(workspace_id,report_id,current_revision)
                REFERENCES report_revisions(workspace_id,report_id,revision)
                DEFERRABLE INITIALLY DEFERRED)""",
        """CREATE TABLE report_revisions (
            workspace_id TEXT NOT NULL, report_id TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK(revision>=1), parent_revision INTEGER,
            operation_id TEXT NOT NULL, task_id TEXT NOT NULL REFERENCES template_tasks(task_id),
            task_revision INTEGER NOT NULL CHECK(task_revision>=1),
            schema_version TEXT NOT NULL CHECK(schema_version='report-revision-v1'),
            builder_version TEXT NOT NULL, source_content_sha256 TEXT NOT NULL CHECK(length(source_content_sha256)=64),
            canonical_payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256)=64),
            editor_json TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(workspace_id,report_id,revision), UNIQUE(workspace_id,operation_id),
            FOREIGN KEY(workspace_id,operation_id) REFERENCES report_operations(workspace_id,operation_id)
                DEFERRABLE INITIALLY DEFERRED,
            CHECK((revision=1 AND parent_revision IS NULL) OR (revision>1 AND parent_revision IS NOT NULL AND parent_revision=revision-1)),
            FOREIGN KEY(workspace_id,report_id) REFERENCES reports(workspace_id,report_id),
            FOREIGN KEY(workspace_id,report_id,parent_revision)
                REFERENCES report_revisions(workspace_id,report_id,revision))""",
        """CREATE TABLE report_operations (
            workspace_id TEXT NOT NULL, operation_id TEXT NOT NULL,
            request_sha TEXT NOT NULL CHECK(length(request_sha)=64),
            report_id TEXT NOT NULL, revision INTEGER NOT NULL,
            outcome TEXT NOT NULL CHECK(outcome='stored'),
            PRIMARY KEY(workspace_id,operation_id),
            FOREIGN KEY(workspace_id,report_id,revision)
                REFERENCES report_revisions(workspace_id,report_id,revision))""",
        """CREATE TABLE report_source_refs (
            workspace_id TEXT NOT NULL, report_id TEXT NOT NULL, revision INTEGER NOT NULL,
            document_id TEXT NOT NULL, source_revision TEXT NOT NULL REFERENCES document_sources(source_revision),
            content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
            PRIMARY KEY(workspace_id,report_id,revision,document_id),
            FOREIGN KEY(workspace_id,document_id) REFERENCES documents(workspace_id,document_id),
            FOREIGN KEY(workspace_id,report_id,revision)
                REFERENCES report_revisions(workspace_id,report_id,revision))""",
        """CREATE TABLE report_fact_refs (
            workspace_id TEXT NOT NULL, report_id TEXT NOT NULL, revision INTEGER NOT NULL,
            side TEXT NOT NULL CHECK(side IN ('first','second')), metric_key TEXT NOT NULL,
            fact_id TEXT NOT NULL REFERENCES confirmed_financial_facts(fact_id),
            fact_set_id TEXT NOT NULL REFERENCES financial_fact_sets(fact_set_id),
            receipt_id TEXT NOT NULL REFERENCES financial_acceptance_receipts(receipt_id),
            disclosure_version TEXT NOT NULL,
            PRIMARY KEY(workspace_id,report_id,revision,side,metric_key),
            FOREIGN KEY(workspace_id,report_id,revision)
                REFERENCES report_revisions(workspace_id,report_id,revision))""",
        "CREATE INDEX d23_reports_history ON reports(workspace_id,sequence DESC)",
        "CREATE INDEX d23_revisions_task ON report_revisions(workspace_id,task_id,task_revision)",
        "CREATE INDEX d23_sources_audit ON report_source_refs(workspace_id,source_revision)",
        "CREATE INDEX d23_facts_audit ON report_fact_refs(workspace_id,receipt_id)",
        """CREATE TRIGGER d23_report_head_update BEFORE UPDATE ON reports
            WHEN NEW.sequence!=OLD.sequence OR NEW.workspace_id!=OLD.workspace_id
            OR NEW.report_id!=OLD.report_id OR NEW.created_at!=OLD.created_at
            OR NEW.current_revision!=OLD.current_revision+1
            BEGIN SELECT RAISE(ABORT,'invalid report head update'); END""",
        """CREATE TRIGGER d23_report_head_delete BEFORE DELETE ON reports
            BEGIN SELECT RAISE(ABORT,'report history is immutable'); END""",
        *tuple(
            f"CREATE TRIGGER d23_{table}_{action.lower()} BEFORE {action} ON {table} "
            "BEGIN SELECT RAISE(ABORT,'report history is immutable'); END"
            for table in (
                "report_revisions",
                "report_operations",
                "report_source_refs",
                "report_fact_refs",
            )
            for action in ("UPDATE", "DELETE")
        ),
    ),
)
