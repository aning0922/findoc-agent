"""D10 additive schema, in the existing checksummed analyst migration plan."""

FINANCIAL_FACT_MIGRATION = (
    5,
    "accepted_general_financial_facts",
    (
        """CREATE TABLE financial_fact_sets (
            fact_set_id TEXT PRIMARY KEY,
            receipt_id TEXT NOT NULL UNIQUE REFERENCES financial_acceptance_receipts(receipt_id),
            workspace_id TEXT NOT NULL,
            company_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            source_revision TEXT NOT NULL REFERENCES document_sources(source_revision),
            disclosure_version TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            confirmation_kind TEXT NOT NULL CHECK(confirmation_kind IN ('local_operator','simulated_test')),
            saved_at TEXT NOT NULL,
            fact_count INTEGER NOT NULL CHECK(fact_count > 0),
            payload_sha256 TEXT NOT NULL,
            FOREIGN KEY(workspace_id, company_id) REFERENCES companies(workspace_id, company_id),
            FOREIGN KEY(workspace_id, document_id) REFERENCES documents(workspace_id, document_id)
        )""",
        """CREATE TABLE confirmed_financial_facts (
            fact_id TEXT PRIMARY KEY,
            fact_set_id TEXT NOT NULL REFERENCES financial_fact_sets(fact_set_id),
            metric_key TEXT NOT NULL CHECK(metric_key IN ('revenue','net_profit_parent','operating_cash_flow')),
            period INTEGER NOT NULL CHECK(typeof(period)='integer' AND period BETWEEN 1 AND 9999),
            period_type TEXT NOT NULL CHECK(period_type IN ('annual','semiannual','quarterly')),
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL CHECK(period_end >= period_start),
            raw_value TEXT NOT NULL,
            raw_unit TEXT NOT NULL,
            value_text TEXT NOT NULL CHECK(typeof(value_text)='text'),
            unit TEXT NOT NULL CHECK(unit='CNY_YUAN'),
            currency TEXT NOT NULL CHECK(currency='CNY'),
            scope TEXT NOT NULL CHECK(scope='consolidated'),
            accounting_basis TEXT NOT NULL CHECK(accounting_basis='PRC_GAAP'),
            source_ref TEXT NOT NULL,
            candidate_json TEXT NOT NULL,
            UNIQUE(fact_set_id, metric_key, period_start, period_end),
            UNIQUE(fact_set_id, source_ref)
        )""",
        "CREATE INDEX d10_sets_company_source ON financial_fact_sets(workspace_id, company_id, document_id, disclosure_version)",
        "CREATE INDEX d10_facts_period_metric ON confirmed_financial_facts(period, period_start, period_end, metric_key, scope)",
        """CREATE TRIGGER d10_set_immutable_update BEFORE UPDATE ON financial_fact_sets
            BEGIN SELECT RAISE(ABORT, 'financial fact set is immutable'); END""",
        """CREATE TRIGGER d10_set_immutable_delete BEFORE DELETE ON financial_fact_sets
            BEGIN SELECT RAISE(ABORT, 'financial fact set is immutable'); END""",
        """CREATE TRIGGER d10_fact_immutable_update BEFORE UPDATE ON confirmed_financial_facts
            BEGIN SELECT RAISE(ABORT, 'financial fact is immutable'); END""",
        """CREATE TRIGGER d10_fact_immutable_delete BEFORE DELETE ON confirmed_financial_facts
            BEGIN SELECT RAISE(ABORT, 'financial fact is immutable'); END""",
    ),
)
