"""D6 additive source/audit DDL included in the one analyst migration plan."""

SOURCE_MIGRATION = (
    3,
    "report_sources_and_corrections",
    (
        """CREATE TABLE document_sources (
            source_revision TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL, document_id TEXT NOT NULL,
            content_sha256 TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt >= 1),
            parser_version TEXT NOT NULL, physical_pages INTEGER NOT NULL CHECK(physical_pages > 0),
            created_at TEXT NOT NULL, invalidated_at TEXT,
            FOREIGN KEY(workspace_id, document_id) REFERENCES documents(workspace_id, document_id)
        )""",
        """CREATE TABLE document_evidence (
            evidence_id TEXT PRIMARY KEY, source_revision TEXT NOT NULL,
            physical_page INTEGER NOT NULL CHECK(physical_page >= 1),
            text TEXT NOT NULL, kind TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
            FOREIGN KEY(source_revision) REFERENCES document_sources(source_revision)
        )""",
        "CREATE INDEX d6_evidence_source ON document_evidence(source_revision, physical_page)",
        """CREATE TABLE report_source_origins (
            document_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL,
            source_url TEXT, assessment_json TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(workspace_id, document_id) REFERENCES documents(workspace_id, document_id)
        )""",
        """CREATE TABLE report_binding_corrections (
            correction_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, document_id TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK(sequence >= 1),
            old_metadata_json TEXT NOT NULL, new_metadata_json TEXT NOT NULL,
            reason TEXT NOT NULL CHECK(length(trim(reason)) > 0),
            action_kind TEXT NOT NULL CHECK(action_kind = 'explicit_user_request'),
            old_attempt INTEGER NOT NULL, new_attempt INTEGER NOT NULL,
            created_at TEXT NOT NULL, UNIQUE(document_id, sequence),
            FOREIGN KEY(workspace_id, document_id) REFERENCES documents(workspace_id, document_id)
        )""",
        """CREATE TRIGGER d6_correction_immutable_update BEFORE UPDATE ON report_binding_corrections
            BEGIN SELECT RAISE(ABORT, 'correction audit is immutable'); END""",
        """CREATE TRIGGER d6_correction_immutable_delete BEFORE DELETE ON report_binding_corrections
            BEGIN SELECT RAISE(ABORT, 'correction audit is immutable'); END""",
        """CREATE TRIGGER d6_origin_immutable BEFORE UPDATE ON report_source_origins
            BEGIN SELECT RAISE(ABORT, 'source origin is immutable'); END""",
    ),
)

# Existing D6 evidence and migration checksums stay unchanged.
LAYOUT_MIGRATION = (
    4,
    "parsed_evidence_layout",
    (
        """CREATE TABLE document_evidence_layout (
            evidence_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            FOREIGN KEY(evidence_id) REFERENCES document_evidence(evidence_id)
        )""",
        """CREATE TRIGGER d7_layout_immutable_update BEFORE UPDATE ON document_evidence_layout
            BEGIN SELECT RAISE(ABORT, 'parsed layout is immutable'); END""",
        """CREATE TRIGGER d7_layout_immutable_delete BEFORE DELETE ON document_evidence_layout
            BEGIN SELECT RAISE(ABORT, 'parsed layout is immutable'); END""",
    ),
)
