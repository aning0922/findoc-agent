"""Server-owned shared counters for the existing loop and bounded research adapters."""

from typing import Any

from dataclasses import asdict, dataclass
import time
from collections.abc import Callable


class BudgetExceeded(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TemplateLimits:
    steps: int = 32
    model_calls: int = 4  # Physical attempts, including the existing provider retry.
    tool_calls: int = 24
    retrieval_per_call: int = 12
    retrieval_total: int = 24
    documents: int = 4
    context_chars: int = 16000
    elapsed_seconds: int = 120


TEMPLATE_LIMITS = TemplateLimits()  # Immutable v1 history.
# D21 capacity proof: 30-step/24-tool all-missing resume plus bounded model,
# validation and failure headroom. No provider/network automatic retries.
TEMPLATE_LIMITS_V2 = TemplateLimits(steps=40, tool_calls=28, retrieval_total=24,
                                   model_calls=2, elapsed_seconds=240)
BUDGET_VERSIONS = {"template-budget-v1": TEMPLATE_LIMITS,
                   "template-budget-v2": TEMPLATE_LIMITS_V2}


class ExecutionBudget:
    """One task instance; never reset on tool/loop reentry. Elapsed limit is soft.

    Synchronous provider/vector/PDF IO cannot be forcibly cancelled. Check before
    starting and after returning; an overdue result is withheld, not interrupted.
    Character limits count JSON messages/tools too, not just retrieved prose.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 checkpoint: Callable[[dict[str, Any]], None] | None = None,
                 version: str = "template-budget-v1") -> None:
        self.limits = BUDGET_VERSIONS[version]
        self.version = version
        self._clock = clock
        self._started = clock()
        self.steps = 0
        self.model_calls = 0
        self.tool_calls = 0
        self.retrieval_total = 0
        self.processed_call_ids: set[str] = set()
        self._operations: set[tuple[str, str]] = set()
        self.error_code: str | None = None
        self._checkpoint = checkpoint
        self._elapsed = 0.0
        self.phase = "initial"

    def durable(self) -> dict[str, Any]:
        return dict(**self.payload(), operations=sorted(self._operations),
                    processed_call_ids=sorted(self.processed_call_ids), phase=self.phase)

    @classmethod
    def restore(cls, value: dict[str, Any], *, checkpoint: Callable[[dict[str, Any]], None]) -> "ExecutionBudget":
        version = value["schema_version"]
        if version not in BUDGET_VERSIONS or value["limits"] != asdict(BUDGET_VERSIONS[version]):
            raise ValueError("unsupported_budget_version")
        budget = cls(checkpoint=checkpoint, version=version)
        for name in ("steps", "model_calls", "tool_calls", "retrieval_total"):
            used = value["used"][name]
            if type(used) is not int or not 0 <= used <= getattr(budget.limits, name):
                raise ValueError("invalid_budget")
            setattr(budget, name, used)
        budget._elapsed = float(value["elapsed_seconds"])
        if not 0 <= budget._elapsed:
            raise ValueError("invalid_elapsed")
        budget._operations = {tuple(item) for item in value["operations"]}
        budget.processed_call_ids = set(value["processed_call_ids"])
        budget.error_code = value["error_code"]
        budget.phase = value["phase"]
        return budget

    def checkpoint(self) -> None:
        if self._checkpoint is not None:
            self._checkpoint(self.durable())

    def fail(self, code: str) -> None:
        self.error_code = code
        self.checkpoint()
        raise BudgetExceeded(code)

    def check(self) -> None:
        if self.error_code:
            raise BudgetExceeded(self.error_code)
        if self._elapsed + self._clock() - self._started >= self.limits.elapsed_seconds:
            self.fail("budget_elapsed_exhausted")

    def consume(self, counter: str) -> None:
        self.check()
        if counter not in ("steps", "model_calls", "tool_calls"):
            raise ValueError("unknown budget counter")
        value = getattr(self, counter)
        if value >= getattr(self.limits, counter):
            self.fail(f"budget_{counter}_exhausted")
        setattr(self, counter, value + 1)
        self.checkpoint()  # Commit reservation before any provider/tool side effect.

    def operation(self, name: str, arguments: str) -> None:
        self.consume("tool_calls")
        key = (self.phase + ":" + name, arguments)
        if key in self._operations:
            self.fail("repeated_operation")
        self._operations.add(key)
        self.checkpoint()

    def retrieval(self, count: int) -> None:
        self.check()
        if type(count) is not int or not 1 <= count <= self.limits.retrieval_per_call:
            self.fail("budget_retrieval_per_call_exhausted")
        if self.retrieval_total + count > self.limits.retrieval_total:
            self.fail("budget_retrieval_total_exhausted")
        self.retrieval_total += count  # Reserve requested slots, even on empty/failed retrieval.
        self.checkpoint()

    def context(self, chars: int) -> None:
        self.check()
        if chars > self.limits.context_chars:
            self.fail("budget_context_exhausted")

    def payload(self) -> dict[str, object]:
        return dict(
            schema_version=self.version, limits=asdict(self.limits),
            used=dict(steps=self.steps, model_calls=self.model_calls,
                      tool_calls=self.tool_calls, retrieval_total=self.retrieval_total),
            elapsed_seconds=round(self._elapsed + self._clock() - self._started, 6),
            time_boundary="soft_before_and_after_io_no_hard_cancellation",
            error_code=self.error_code,
        )
