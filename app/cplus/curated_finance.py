"""Manifest-pinned, unconfirmed display observations. No extraction or writes on GET."""
import hashlib
import json
import os
from pathlib import Path
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse


def create_curated_finance_router(root,sources,identity_provider,validate):
    root=Path(root)
    router=APIRouter(prefix='/cplus/dashboard')
    @router.get('/financial-observations')
    async def read(request:Request):
        try:
            identity=identity_provider(request)
            validate(identity)
            manifest_file=root/'.demo-manifest.json'
            manifest_raw=manifest_file.read_bytes()
            if hashlib.sha256(manifest_raw).hexdigest()!=os.environ.get('DEMO_INTERNAL_MANIFEST_SHA'):
                raise ValueError('manifest_changed')
            manifest=json.loads(manifest_raw)
            entry=next((e for e in manifest['files'] if e['path']=='cplus-financial-candidates.json'),None)
            if entry is None:
                return {'schema_version':'cplus-curated-financial-series-v1','series':[],
                        'data_origin':'preset_candidate','financial_authority':False,'human_approvals':0,
                        'limitations':['当前种子尚无财务展示候选，请在企业三表中明确提取。']}
            file=root/'cplus-financial-candidates.json'
            if file.is_symlink() or file.stat().st_nlink!=1:
                raise ValueError('candidate_file_changed')
            raw=file.read_bytes()
            if len(raw)>1_000_000 or hashlib.sha256(raw).hexdigest()!=entry['sha256']:
                raise ValueError('candidate_file_changed')
            data=json.loads(raw)
            if (data['schema_version']!='cplus-curated-financial-series-v1'
                    or data['data_origin']!='preset_candidate' or data['financial_authority'] is not False
                    or data['human_approvals']!=0 or not 0<len(data['series'])<=5):
                raise ValueError('candidate_contract_invalid')
            current={}
            for series in data['series']:
                status='current'
                if not 0<len(series['points'])<=2:
                    raise ValueError('candidate_point_budget')
                for point in series['points']:
                    try:
                        identifier=point['document_id']
                        if identifier not in current:
                            current[identifier]=await sources.source(identifier)
                        actual=current[identifier]
                        if (any(actual[k]!=point[k] for k in ('source_revision','content_sha256','parser_version'))
                                or actual['company_id']!=series['company_id'] or actual['basis']!=series['basis']
                                or not 1<=point['physical_page']<=actual['physical_pages']
                                or point['financial_review']!='unconfirmed'):
                            raise ValueError('candidate_source_changed')
                    except Exception:
                        status='stale_or_unavailable'
                series['current_source_status']=status
                if status!='current':
                    series['points']=[]
            validate(identity)
            return {**data,'seed_version':manifest['seed_version'],
                    'limitations':['预置候选来自明确选择的真实PDF与期间，尚未人工核准；不写入已确认财务事实。']}
        except Exception as exc:
            from .diagnostics import safe_failure
            safe_failure('curated-finance',exc)
            return JSONResponse({'detail':{'code':getattr(exc,'code','curated_finance_unavailable')}},
                                status_code=getattr(exc,'status',409),headers={'Cache-Control':'no-store'})
    return router
