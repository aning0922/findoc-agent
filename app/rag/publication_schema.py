"""D16 publication ledger, in the authoritative documents database."""

INDEX_PUBLICATION_MIGRATION = (6, "versioned_index_publications", (
    """CREATE TABLE index_publications (
        generation TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        source_revision TEXT NOT NULL,
        manifest_json TEXT NOT NULL,
        manifest_sha256 TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('building','failed','complete','active','revoked')),
        FOREIGN KEY(source_revision) REFERENCES document_sources(source_revision)
    )""",
    """CREATE UNIQUE INDEX index_one_active ON index_publications(workspace_id, document_id)
        WHERE state='active'""",
))
