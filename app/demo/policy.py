"""Explicit mutation inventory from the actual V1.2 routes. Unknown writes fail closed.

New modules must be registered here by the integration owner after review. A route
being allowlisted grants no business/fact authority; runtime admission still runs.
"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Mutation:
    method: str
    pattern: str
    owner: bool = False
    native_operation: bool = False

    def matches(self, method, path):
        return self.method == method and re.fullmatch(self.pattern, path) is not None


SEG = r"[^/]+"
MUTATIONS = (
    Mutation("POST", r"/cplus/exports", native_operation=True),
    Mutation("POST", r"/cplus/checkup-explanations", native_operation=True),
    Mutation("POST", r"/cplus/peer-comparisons", native_operation=True),
    Mutation("POST", r"/cplus/batch-plans", native_operation=True),
    Mutation("POST", r"/cplus/batches", native_operation=True),
    Mutation("POST", rf"/cplus/batches/{SEG}/cancel", native_operation=True),
    Mutation("POST", r"/cplus/segments", native_operation=True),
    Mutation("POST", r"/cplus/annual-diffs", native_operation=True),
    Mutation("POST", r"/cplus/retrieval/builds", native_operation=True),
    Mutation("POST", r"/cplus/retrieval/searches", native_operation=True),
    Mutation("POST", r"/cplus/research/enrollments", native_operation=True),
    Mutation("POST", r"/cplus/research/contexts", native_operation=True),
    Mutation("POST", r"/cplus/research/answers", native_operation=True),
    Mutation("POST", r"/cplus/financial/collections", native_operation=True),
    Mutation("POST", r"/cplus/financial/reviews", native_operation=True),
    Mutation("POST", r"/cplus/financial/confirmations", owner=True, native_operation=True),
    Mutation("POST", rf"/cplus/financial/confirmations/{SEG}/revoke", owner=True, native_operation=True),
    Mutation("POST", r"/cplus/financial/trend-projections", native_operation=True),
    Mutation("POST", r"/cplus/checkups", native_operation=True),
    Mutation("POST", r"/research/intent", native_operation=True),
    Mutation("POST", r"/research/handoffs", native_operation=True),
    Mutation("POST", r"/synthesis/plans", native_operation=True),
    Mutation("POST", r"/synthesis/jobs", native_operation=True),
    Mutation("POST", r"/deep-research/jobs", native_operation=True),
    Mutation("POST", r"/showcase-reports/drafts", native_operation=True),
    Mutation("POST", r"/showcase-reports", native_operation=True),
    Mutation("POST", rf"/showcase-reports/{SEG}/revisions", native_operation=True),
    Mutation("POST", r"/research-memories", native_operation=True),
    Mutation("PATCH", rf"/research-memories/{SEG}", native_operation=True),
    Mutation("DELETE", rf"/research-memories/{SEG}", native_operation=True),
    Mutation("POST", r"/financial/extended-metrics/collect", native_operation=True),
    Mutation("POST", r"/financial/extended-reviews", native_operation=True),
    Mutation("POST", r"/financial/extended-confirmations", owner=True, native_operation=True),
    Mutation("POST", rf"/financial/extended-confirmations/{SEG}/revoke", owner=True, native_operation=True),
    Mutation("POST", r"/financial/extended-analyses", native_operation=True),
    Mutation("POST", rf"/documents/{SEG}/parse-retry", native_operation=True),
    Mutation("POST", r"/disclosures/import", native_operation=True),
    Mutation("POST", r"/companies"),
    Mutation("PATCH", rf"/companies/{SEG}"),
    Mutation("PUT", rf"/documents/{SEG}/metadata"),
    Mutation("POST", r"/documents"),
    Mutation("POST", r"/report-documents"),
    Mutation("POST", rf"/documents/{SEG}/retry"),
    Mutation("POST", rf"/documents/{SEG}/reindex"),
    Mutation("POST", rf"/documents/{SEG}/binding-corrections"),
    Mutation("POST", r"/chat"),
    Mutation("POST", r"/agent/runs"),
    Mutation("POST", r"/financial-facts/reviews"),
    Mutation("POST", r"/financial-facts/confirmations", owner=True),
    Mutation("POST", r"/financial-facts/persisted", owner=True),
    Mutation("POST", rf"/financial-facts/acceptances/{SEG}/revoke", owner=True),
    Mutation("POST", r"/revenue-research/reviews"),
    Mutation("POST", r"/revenue-research/confirmations", owner=True),
    Mutation("POST", r"/analyses"),
    Mutation("POST", r"/analyses/company-comparison"),
    Mutation("POST", r"/research/selections/prepare"),
    Mutation("POST", r"/research/questions"),
    Mutation("POST", r"/research/templates/prepare"),
    Mutation("POST", r"/research/templates/execute-readonly"),
    Mutation("POST", r"/research/runs", native_operation=True),
    Mutation("POST", r"/research/tasks", native_operation=True),
    Mutation("POST", rf"/research/tasks/{SEG}/resume", owner=True, native_operation=True),
    Mutation("POST", r"/conversations", native_operation=True),
    Mutation("POST", rf"/conversations/{SEG}/turns", native_operation=True),
    Mutation("DELETE", rf"/conversations/{SEG}", native_operation=True),
    Mutation("POST", r"/memories", native_operation=True),
    Mutation("PATCH", rf"/memories/{SEG}", native_operation=True),
    Mutation("DELETE", rf"/memories/{SEG}", native_operation=True),
    Mutation("POST", r"/reports/drafts"),
    Mutation("POST", r"/reports", native_operation=True),
    Mutation("POST", rf"/reports/{SEG}/revisions", native_operation=True),
)


def mutation_for(method, path):
    return next((rule for rule in MUTATIONS if rule.matches(method, path)), None)
