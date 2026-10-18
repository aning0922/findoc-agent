"""Read-only public archive transport for the complete production React route.

Frozen fact views come from the original Task analysis, never native acceptance
rows. This validates reading/navigation, not renewed financial qualification.
The C2 guard supplies real freshly parsed PDFs, isolated SQLite and no sockets.
"""
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote


def create_d29_d_app():
    from tests.support.d29_c2_app import create_d29_c2_app
    from fastapi import APIRouter, HTTPException
    from fastapi.responses import JSONResponse, Response
    from app.reports.markdown import render

    app = create_d29_c2_app()
    root = Path(os.environ['D29_ALLOWED_WORKTREE'])
    evidence = root / 'product/d28/evidence/human-followup'
    tasks = [json.loads((evidence / f'{name}-user-resume-completed.json').read_text())['task']
             for name in ('midea', 'gree', 'comparison')]
    reports = {r: json.loads((evidence / f'midea-report-v{r}-user-saved.json').read_text())['detail']
               for r in (1, 2)}
    archive = next(r.endpoint for r in app.routes if getattr(r, 'path', '') == '/__test__/archive/tasks/{task_id}')
    router = APIRouter()

    def response(value):
        return JSONResponse(value, headers={'Cache-Control': 'no-store', 'X-Test-Archive': 'public-readonly'})

    @router.get('/research/tasks')
    async def task_history():
        for t in tasks:
            await archive(t['task_id'])
        return response(dict(schema_version='template-task-history-v1', items=tasks, next_before=None))

    @router.get('/research/tasks/{task_id}')
    async def task_detail(task_id: str):
        return await archive(task_id)

    @router.get('/financial-facts')
    async def frozen_facts(company_id: str):
        facts = {}
        for t in tasks:
            if t['input']['template'] != 'company_period_change' or t['input']['first']['company_id'] != company_id:
                continue
            await archive(t['task_id'])
            for a in t['snapshot']['analysis_results']:
                for key in ('current', 'previous'):
                    f = a[key]
                    facts[f['fact_id']] = f
        return response(dict(schema='financial-fact-query-v1', facts=list(facts.values()),
                             requires_version_selection=False, ambiguous_periods=[], conflicting_periods=[], automatic_selection=False))

    @router.get('/financial-facts/acceptances')
    def no_native_acceptance_import():
        return response(dict(schema='financial-acceptance-discovery-v1', automatic_selection=False, items=[]))

    @router.get('/reports')
    def report_history():
        d = reports[2]
        return response(dict(schema_version='report-history-v1', next_before=None, items=[dict(
            report_id=d['report']['report_id'], current_revision=2,
            title=d['report']['editor_revision']['title'] or d['report']['trusted_snapshot']['title'],
            watermark=None, current_eligibility=d['current_eligibility'])]))

    async def detail(report_id, revision):
        d = reports.get(revision)
        if not d or d['report']['report_id'] != report_id:
            raise HTTPException(404, 'archive_not_found')
        await archive(d['report']['trusted_snapshot']['task_id'])
        return d

    @router.get('/reports/{report_id}/revisions/{revision}')
    async def report_detail(report_id: str, revision: int):
        return response({**await detail(report_id, revision), "current_revision": 2})

    @router.get('/reports/{report_id}/revisions/{revision}/markdown')
    async def markdown(report_id: str, revision: int):
        d = await detail(report_id, revision)
        raw = render(d['report'])
        filename = f'FinDoc-历史研究-{report_id}-v{revision}.md'
        return Response(raw, media_type='text/markdown', headers={
            'X-Test-Archive': 'public-readonly', 'X-Report-Id': report_id,
            'X-Report-Revision': str(revision), 'X-Report-Payload-SHA256': d['payload_sha256'],
            'X-Markdown-Renderer': 'trusted-markdown-v1', 'X-Markdown-SHA256': hashlib.sha256(raw).hexdigest(),
            'X-Report-Eligibility': 'qualified_at_export',
            'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename),
        })

    # Deliberately test-only transport. Production app/ has no archive injection.
    app.router.routes[0:0] = router.routes
    return app
