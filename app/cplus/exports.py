"""Root-owned domain resolution: saved snapshots, current display permission, no models."""
from contextlib import closing,contextmanager
import json
import os
import sqlite3
from fastapi import APIRouter,Request
from fastapi.responses import HTMLResponse,JSONResponse
from app.exports_v2 import ExportService,create_export_router
from app.exports_v2.projection import digest,project
from app.retrieval_v2 import SourceRef
from app.retrieval_v2.models import RetrievalError
from app.showcase_research.models import RuntimeIdentity


def rows(path,sql,params=()):
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        return [dict(r) for r in db.execute(sql,params)]


def register_exports(app,root,*,hybrid,annual,peer,statements,identity_provider,validate,guard,conversations):
    def owned(path,table,identifier,owner):
        # table is chosen only from the fixed domains below, never a browser string.
        value=rows(path,f'SELECT payload FROM {table} WHERE id=? AND owner=?',(identifier,owner))
        if len(value)!=1:
            raise RetrievalError('export_snapshot_not_found',404)
        return json.loads(value[0]['payload'])

    def fast_source(value,workspace):
        return SourceRef(kind='fast',identity_status='fast_source_verified',workspace_id=workspace,
                         **{k:value[k] for k in ('company_id','document_id','source_revision','content_sha256',
                                                'parser_version','report_year','attempt','report_type',
                                                'basis','period_start','period_end')}).model_dump()

    async def resolve(domain,identifier,revision,expected_sha,identity):
        validate(identity)
        owner=await hybrid.authorize(identity)
        fence={}
        contexts=None
        receipts=None
        status='current'
        if domain=='annual_diff_v1':
            if revision!=1:
                raise RetrievalError('export_revision_mismatch')
            snapshot=owned(annual.path,'results',identifier,owner)
            fence={'selected_sources':[snapshot['left_source'],snapshot['right_source']],
                   'memory_generation':snapshot.get('memory_generation')}
        elif domain=='peer_comparison_v1':
            if revision!=1:
                raise RetrievalError('export_revision_mismatch')
            snapshot=owned(peer.store.path,'snapshots',identifier,owner)
            collections=[statements.read(r['collection_id'] if isinstance(r,dict) else r,'collection') for r in snapshot['collection_refs']]
            fence={'selected_sources':[fast_source(c['source'],identity.workspace_id) for c in collections],
                   'memory_generation':snapshot.get('memory_generation')}
        elif domain=='checkup_v1':
            if revision!=1:
                raise RetrievalError('export_revision_mismatch')
            snapshot=statements.read(identifier,'checkup')
            collections=[statements.read(r['collection_id'] if isinstance(r,dict) else r,'collection') for r in snapshot['collection_refs']]
            fence={'selected_sources':[fast_source(c['source'],identity.workspace_id) for c in collections]}
        elif domain in ('template_run_v1','chart_report_v1'):
            if revision!=1:
                raise RetrievalError('export_revision_mismatch')
            name='cplus_template_service' if domain=='template_run_v1' else 'cplus_chart_report_service'
            leaf=getattr(app.state,name,None)
            if leaf is None:
                raise RetrievalError('export_snapshot_not_found',404)
            snapshot=owned(leaf.store.path,'snapshots',identifier,owner)
            collections=[statements.read(r['collection_id'],'collection') for r in snapshot['collection_refs']]
            fence={'selected_sources':snapshot['selected_sources'],
                   'memory_generation':snapshot.get('memory_generation')}
        elif domain=='research_answer_v1':
            if revision!=1:
                raise RetrievalError('export_revision_mismatch')
            snapshot=hybrid.read('answer',identifier,owner)
            context=hybrid.read('context',snapshot['context_id'],owner)
            if context.get('parent_conversation_id'):
                conversations.selection(context['parent_conversation_id'],'只读核验报告展示权限')
            fence=context
        elif domain=='showcase_report_v2':
            reports=app.state.showcase_report_service
            found=rows(reports.path,'SELECT v.payload FROM revisions v JOIN reports r ON r.id=v.report_id WHERE r.workspace=? AND r.id=? AND v.revision=?',(identity.workspace_id,identifier,revision))
            if len(found)!=1:
                raise RetrievalError('export_snapshot_not_found',404)
            snapshot=json.loads(found[0]['payload'])
            original=RuntimeIdentity(identity.instance_id,identity.generation,identity.expires_at,identity.workspace_id,identity.principal_id)
            research=app.state.showcase_research_service
            job=research.job(snapshot['snapshot']['job_id'],original)  # Permission before any stale fallback.
            scope=json.loads(rows(research.store.path,'SELECT scope FROM sr_jobs WHERE id=?',(job['job_id'],))[0]['scope'])
            fence={'selected_sources':[fast_source(s,identity.workspace_id) for s in scope['sources']],
                   'memory_generation':scope['memory_generation'],'preference_generation':scope.get('preference_generation'),
                   'parent_conversation_id':job['conversation_id'],'parent_sources':scope['sources']}
            try:
                await research.verified_job(job['job_id'],original)
            except Exception:
                status='stale'
        else:
            raise RetrievalError('unsupported_export_domain',422)
        if digest(snapshot)!=expected_sha:
            raise RetrievalError('export_snapshot_hash_mismatch')
        if domain in ('peer_comparison_v1','checkup_v1','template_run_v1','chart_report_v1'):
            try:
                current_collections,contexts=await statements.selected(snapshot['collection_refs'])
                with statements.tx(source=True) as db:
                    statements.guard(db,contexts)
                    receipts={c['cell_id']:statements.admitted(db,c) for collection in current_collections for c in collection['cells']}
                if domain=='peer_comparison_v1':
                    for comparison in snapshot['comparisons']:
                        if any(receipts.get(p['cell_id'])!=p['receipt_ref'] for p in comparison['points']):
                            status='stale'
                elif domain in ('template_run_v1','chart_report_v1'):
                    from app.research_templates_v1.shared import validate_point_snapshot
                    points=[{**c,'source_status':'current','receipt_ref':receipts[c['cell_id']],
                             'financial_review':'local_operator_confirmed' if receipts[c['cell_id']] else 'unconfirmed'}
                            for collection in current_collections for c in collection['cells']]
                    validate_point_snapshot(snapshot['financial_points'],points)
                elif not snapshot['candidate_view'] and any(r is None for r in receipts.values()):
                    status='stale'
            except Exception:
                status='stale'
        try:
            with guard(identity,fence):
                pass
        except Exception:
            validate(identity)  # Lease/instance failures are never historical-read permission.
            status='stale'
        validate(identity)
        display_companies={}
        for source in fence.get('selected_sources',[]):
            cid=source.get('company_id')
            if cid and cid not in display_companies:
                try:
                    company=statements.companies.get(cid)
                    display_companies[cid]={'name':company.name,'security_code':company.security_code,
                                            'exchange':company.exchange}
                except Exception:
                    display_companies[cid]={'name':None,'security_code':None,'exchange':None}
        return {'snapshot':snapshot,**fence,'display_status':status,
                'display_companies':display_companies,
                'statement_contexts':contexts,'statement_receipts':receipts}

    @contextmanager
    def export_guard(identity,resolved):
        validate(identity)
        if resolved['display_status']=='current':
            with guard(identity,resolved):
                if resolved.get('statement_contexts') is not None:
                    with statements.tx(source=True) as db:
                        statements.guard(db,resolved['statement_contexts'])
                        cells=[c for _,values in resolved['statement_contexts'] for c in values]
                        actual={c['cell_id']:statements.admitted(db,c) for c in cells if c['cell_id'] in resolved['statement_receipts']}
                        if actual!=resolved['statement_receipts']:
                            raise RetrievalError('export_receipts_changed')
                        yield
                else:
                    yield
        else:
            # Immutable, owner-checked historical data; no current authority is granted.
            yield
        validate(identity)

    async def reader(identity,manifest):
        # Revalidate the exact saved domain version's display permission. A
        # stale source can remain historical; a revoked parent cannot.
        validate(identity)
        ref=manifest['report_ref']
        try:
            await resolve(ref['domain'],ref['id'],ref['revision'],ref['payload_sha256'],identity)
        except Exception as exc:
            from app.exports_v2.service import ExportError
            raise ExportError('display_permission_denied',403) from exc
        validate(identity)
        return True

    service=ExportService(root,resolver=resolve,identity_validator=validate,publication_guard=export_guard,
                           before_commit_sync=validate,authorize_read=reader,
                           renderer_python=os.environ.get('FINDOC_EXPORT_PYTHON'))
    app.include_router(create_export_router(service,identity_provider))
    app.state.cplus_export_service=service
    router=APIRouter(prefix='/cplus/export-snapshots')

    def fail(exc):
        from .diagnostics import safe_failure
        safe_failure('export-snapshot',exc)
        return JSONResponse({'detail':{'code':getattr(exc,'code','export_snapshot_unavailable')}},
                            status_code=getattr(exc,'status',409),headers={'Cache-Control':'no-store'})

    @router.get('')
    async def listing(request:Request):
        try:
            identity=identity_provider(request)
            owner=await hybrid.authorize(identity)
            candidates=[]
            domains=[]
            for domain,name in [('template_run_v1','cplus_template_service'),('chart_report_v1','cplus_chart_report_service')]:
                leaf=getattr(app.state,name,None)
                if leaf is not None:
                    domains.append((domain,leaf.store.path,'SELECT rowid AS persistence_order,payload FROM snapshots WHERE owner=? ORDER BY rowid DESC',(owner,)))
            for domain,path,sql,params in domains+[

                ('annual_diff_v1',annual.path,'SELECT rowid AS persistence_order,payload FROM results WHERE owner=? ORDER BY rowid DESC',(owner,)),
                ('peer_comparison_v1',peer.store.path,'SELECT rowid AS persistence_order,payload FROM snapshots WHERE owner=? ORDER BY rowid DESC',(owner,)),
                ('research_answer_v1',hybrid.path,"SELECT rowid AS persistence_order,payload FROM objects WHERE owner=? AND kind='answer' ORDER BY rowid DESC",(owner,)),
                ('checkup_v1',statements.path,"SELECT rowid AS persistence_order,payload FROM records WHERE kind='checkup' ORDER BY rowid DESC",()),
                ('showcase_report_v2',app.state.showcase_report_service.path,'SELECT v.rowid AS persistence_order,v.payload FROM revisions v JOIN reports r ON r.id=v.report_id WHERE r.workspace=? ORDER BY v.rowid DESC',(identity.workspace_id,))]:
                for row in rows(path,sql,params):
                    snapshot=json.loads(row['payload'])
                    identifier=next(snapshot[k] for k in ('answer_id','result_id','report_id','run_id','id') if k in snapshot)
                    revision=snapshot.get('revision',1)
                    ref={'domain':domain,'id':identifier,'revision':revision,'payload_sha256':digest(snapshot)}
                    try:
                        resolved=await resolve(domain,identifier,revision,ref['payload_sha256'],identity)
                    except Exception as exc:
                        if getattr(exc,'status',None) in (401,403):
                            raise
                        continue
                    labels={'template_run_v1':'结构化研究模板','chart_report_v1':'图表报告草稿','annual_diff_v1':'双年经营原文','peer_comparison_v1':'同行候选对照','checkup_v1':'财报体检规则','research_answer_v1':'原文研究结果','showcase_report_v2':'综合研究报告'}
                    candidates.append({'report_ref':ref,'label':snapshot.get('title') or snapshot.get('question') or labels[domain],
                                       'display_status':resolved['display_status'],
                                       'company_ids':sorted(resolved.get('display_companies',{})),
                                       'saved_at':snapshot.get('created_at'),
                                       'persistence_order':row['persistence_order']})
            return {'schema_version':'export-snapshot-list-v1','items':candidates}
        except Exception as exc:
            return fail(exc)

    @router.get('/{domain}/{identifier}/revisions/{revision}/print')
    async def printing(domain:str,identifier:str,revision:int,snapshot_sha256:str,request:Request):
        try:
            identity=identity_provider(request)
            resolved=await resolve(domain,identifier,revision,snapshot_sha256,identity)
            ref={'domain':domain,'id':identifier,'revision':revision,'payload_sha256':snapshot_sha256}
            projection=project(ref,resolved)
            from .printing import render_projection
            def company_name(identifier):
                try:
                    return statements.companies.get(identifier).name
                except Exception:
                    return '保存时企业 '+str(identifier or '')[:8]
            body=render_projection(ref,resolved,projection,company_name)
            validate(identity)
            return HTMLResponse(body,headers={'Cache-Control':'no-store','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'self'"})
        except Exception as exc:
            return fail(exc)
    app.include_router(router)
    workflow_router=APIRouter(prefix='/cplus/companies')

    @workflow_router.get('/{company_id}/workflow')
    async def workflow(company_id:str,request:Request):
        try:
            statements.companies.get(company_id)
            payload=await listing(request)
            if isinstance(payload,JSONResponse):
                return payload
            # Membership comes from resolver-validated saved sources, never a title.
            return {'schema_version':'company-workflow-v1','company_id':company_id,
                    'items':[item for item in payload['items'] if company_id in item['company_ids']],
                    'limitations':['Dates are saved server timestamps when present; persistence_order is per domain only.',
                                   'Historical items are read-only and grant no financial authority.']}
        except Exception as exc:
            return fail(exc)
    app.include_router(workflow_router)
