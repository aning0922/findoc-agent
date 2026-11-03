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
