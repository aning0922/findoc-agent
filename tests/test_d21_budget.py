"""Version governance, measured legal paths, and physical attempt reservations."""
import copy
import json
from contextlib import closing
from dataclasses import asdict
from unittest.mock import AsyncMock
import uuid

import pytest
from pydantic import ValidationError

from app.agent.execution_budget import ExecutionBudget, TEMPLATE_LIMITS, BudgetExceeded
from app.agent.tool_loop import run_tool_loop, ToolExecutionContext
from app.rag.retriever import TrustedContext
from app.rag.openai_compatible_llm import ProviderCallError
from app.research.task_contracts import StartTaskV2
from app.research.repository import HistoryError
from tests.test_d11_financial_analysis import saved as saved
from tests.test_d13_company_comparison import paired as paired
from tests.test_d18_templates import body, run, Scripted, final
from tests.test_d19_tasks import setup, start, resume


@pytest.mark.parametrize('missing', [0, 3, 6])
@pytest.mark.parametrize('template', ['A', 'B'])
def test_measured_capacity(saved, paired, tmp_path, missing, template, monkeypatch):
    h, a, _ = saved
    b = None
    if template == 'B':
        h, a, b, _ = paired
    svc, repo, graph = setup(h)
    from app.research.templates import TemplateSession
    monkeypatch.setattr(TemplateSession, "execute_limited_model", AsyncMock())
    raw = body(a, b)
    slots = [c for side in ('first', 'second') for c in raw[side]['choices']]
    for choice in slots[:missing]:
        choice.update(fact_set_id=None, fact_id=None)
    req = StartTaskV2.model_validate(dict(operation_id=str(uuid.uuid4()), input=raw,
                                         run_version='d21-operating-graph-v2'))
    record = run(graph.start(req))
    if missing:
        selected = body(a, b)
        from app.research.task_contracts import ResumeTask
        approved = ResumeTask.model_validate(dict(operation_id=str(uuid.uuid4()),
            expected_revision=record['revision'], facts=[dict(side=side, **{k: c[k] for k in
                ('metric_key', 'fact_set_id', 'fact_id')}) for side in ('first', 'second')
                for c in selected[side]['choices']]))
        record = run(graph.resume(record['task_id'], approved))
    assert record['status'] == 'collecting_explanation', record
    baseline = copy.deepcopy(record['budget'])
    measured = []
    budget = ExecutionBudget.restore(baseline, checkpoint=lambda v: measured.append(copy.deepcopy(v)))
    # Freeze D21 extra schedule: first response rejected, one protocol repair response,
    # validation and final eligibility. This measures budget costs, not model semantics.
    for name in ('model_attempt_1', 'validate_protocol_1', 'model_attempt_2',
                 'validate_protocol_2', 'joint_final_admission', 'persist_result'):
        budget.consume('steps')
        if name.startswith('model_attempt'):
            budget.consume('model_calls')
    assert budget.steps <= 36 and budget.tool_calls <= 25 and budget.model_calls == 2
    proof = dict(template=template, missing=missing, baseline=baseline,
                 worst_with_protocol_repair=budget.durable(), reservations=len(measured),
                 controlled_capacity_schedule=True, actual_llm=False)
    (tmp_path / 'd21-capacity-case.json').write_text(json.dumps(proof))


def test_v1_unchanged_and_explicit_child_audit(saved):
    h, g, _ = saved
    _, repo, graph = setup(h)
    parent = run(graph.start(start(g)))
    req = StartTaskV2.model_validate(dict(operation_id=str(uuid.uuid4()), input=body(g, confirmed=False),
        run_version='d21-operating-graph-v2', parent_task_id=parent['task_id']))
    child = run(graph.start(req))
    assert repo.get(parent['task_id']) == parent
    assert parent['budget']['limits'] == asdict(TEMPLATE_LIMITS)
    assert child['parent_budget_audit'] == parent['budget']
    assert child['parent_task_id'] == parent['task_id']
    assert child['budget']['schema_version'] == 'template-budget-v2'
    assert [r['task_id'] for r in repo.page(20, None)['items']] == [child['task_id'], parent['task_id']]
    # Original checkpoint still resumes with frozen v1 accumulated counters.
    old = run(graph.resume(parent['task_id'], resume(g, parent)))
    assert old['budget']['schema_version'] == 'template-budget-v1'
    assert old['budget']['used']['tool_calls'] == 24
    with closing(repo.registry._connect()) as conn, conn:
        claim_record, claim = repo.start(StartTaskV2.model_validate({**req.model_dump(mode='json'),
            'operation_id': str(uuid.uuid4())}))
        assert claim
        wrong = copy.deepcopy(claim_record['budget'])
        wrong['schema_version'] = 'template-budget-v1'
        with pytest.raises(HistoryError, match='budget_version_change_forbidden'):
            repo.reserve(claim_record['task_id'], claim, wrong)


@pytest.mark.parametrize('version', ['template-budget-v1', 'template-budget-v2'])
def test_budget_exact_boundaries_and_restore(version):
    for counter in ('steps', 'tool_calls', 'model_calls'):
        values = []
        b = ExecutionBudget(version=version, checkpoint=lambda v: values.append(v))
        for _ in range(getattr(b.limits, counter)):
            b.consume(counter)
        frozen = b.durable()
        restored = ExecutionBudget.restore(frozen, checkpoint=lambda _: None)
        with pytest.raises(BudgetExceeded, match=f'budget_{counter}_exhausted'):
            restored.consume(counter)
        assert restored.payload()['used'] == frozen['used']
        assert len(values) == getattr(b.limits, counter)
    b = ExecutionBudget(version=version)
    b.retrieval(12)
    b.retrieval(12)
    with pytest.raises(BudgetExceeded):
        b.retrieval(1)
    with pytest.raises(BudgetExceeded):
        ExecutionBudget(version=version).context(16001)
    frozen = ExecutionBudget(version=version).durable()
    frozen['limits']['steps'] += 1
    with pytest.raises(ValueError, match='unsupported_budget_version'):
        ExecutionBudget.restore(frozen, checkpoint=lambda _: None)


def test_v2_unknown_provider_no_retry_and_durable_first():
    states = []
    b = ExecutionBudget(version='template-budget-v2', checkpoint=lambda v: states.append(v))
    model = Scripted(ProviderCallError(retryable=True), final())
    run_tool_loop(model=model, messages=[], registry={},
                  execution_context=ToolExecutionContext(TrustedContext('demo'), None), budget=b)
    assert model.calls == b.model_calls == 1
    assert any(s['used']['model_calls'] == 1 for s in states)
    with pytest.raises(ValidationError):
        StartTaskV2.model_validate(dict(operation_id=str(uuid.uuid4()), input={},
                                       run_version='unknown', budget={}))


def test_failed_reservation_zero_io(saved, monkeypatch):
    h, g, _ = saved
    svc, repo, graph = setup(h)
    monkeypatch.setattr(repo, 'reserve', lambda *a: (_ for _ in ()).throw(HistoryError('injected')))
    svc.preparer.prepare_many = AsyncMock(side_effect=AssertionError('unreserved IO'))
    with pytest.raises(HistoryError):
        run(graph.start(StartTaskV2.model_validate(dict(operation_id=str(uuid.uuid4()), input=body(g),
            run_version='d21-operating-graph-v2'))))
    svc.preparer.prepare_many.assert_not_called()


def test_task_and_budget_versions_cannot_be_crossed(saved):
    from app.research.task_contracts import TASK_RECORD
    h, g, _ = saved
    _, _, graph = setup(h)
    value = run(graph.start(start(g)))
    value["budget"] = ExecutionBudget(version="template-budget-v2").durable()
    with pytest.raises(ValidationError, match="task_budget_version_mismatch"):
        TASK_RECORD.validate_python(value)
