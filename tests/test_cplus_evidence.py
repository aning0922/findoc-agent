"""Generated PDF + controlled references; no real provider or human admission."""
from contextlib import contextmanager
import hashlib
from types import SimpleNamespace
import pytest
import pymupdf
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cplus.evidence import create_evidence_router
from app.retrieval_v2 import EvidenceRef, SourceRef
from app.retrieval_v2.models import RetrievalError


@pytest.mark.parametrize('kind,text,expected',[('fast','Exact research excerpt','exact_excerpt_quads'),
                                              ('fast','Missing quote','page_only'),
                                              ('ocr','Exact research excerpt','verified_ocr_line_bbox')])
def test_exact_location_fallback_and_ocr_coordinates_preserve_original(kind,text,expected):
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=400,height=300)
        page.insert_text((30,60),'Exact research excerpt')
        raw=pdf.tobytes()
    original_sha=hashlib.sha256(raw).hexdigest()
    source=SourceRef(kind=kind,workspace_id='demo',company_id='company',document_id='document',
                     source_revision='a'*64,content_sha256=original_sha,parser_version='test',
                     report_year=2025,identity_status='fast_source_verified' if kind=='fast' else 'file_transcription_only',
                     artifact_id='artifact' if kind=='ocr' else None)
    evidence=EvidenceRef(source_ref=source,evidence_id='evidence',physical_page=1,text=text,
                         bbox=[.1,.2,.4,.3] if kind=='ocr' else None)
    locked=[]
    @contextmanager
    def guard(identity,context):
        locked.append(True)
        try:
            yield
        finally:
            locked.pop()
    class Hybrid:
        async def authorize(self,identity):
            if identity=='revoked':
                raise RetrievalError('lease_expired',401)
            return 'owner'
        def read(self,kind,identifier,owner):
            return {'context_id':'context','findings':[{'evidence_ref':evidence.model_dump()}]}
        async def validate_context(self,*args):
            pass
        async def verify(self,ref):
            assert ref==evidence
    class Sources:
        async def file(self,*args,**kwargs):
            return raw
    hybrid=Hybrid()
    hybrid.parse=Sources()
    app=FastAPI()
    app.include_router(create_evidence_router(hybrid=hybrid,preparer=None,sources=Sources(),
                                                           identity_provider=lambda request:'revoked' if request.headers.get('X-Test-Revoked') else SimpleNamespace(),
                                                           publication_guard=guard))
    with TestClient(app) as client:
        base='/cplus/research/answers/answer/evidence/evidence'
        result=client.get(base+'/location')
        assert result.status_code==200 and result.json()['location_mode']==expected
        if kind=='ocr':
            assert result.json()['rects']==[[40.,60.,160.,90.]]
        image=client.get(base+'/image')
        assert image.status_code==200 and image.content.startswith(b'\x89PNG\r\n\x1a\n')
        assert image.headers['X-Findoc-Location-Mode']==expected
        assert client.get(base+'/image',headers={'X-Test-Revoked':'1'}).status_code==401
    assert not locked and hashlib.sha256(raw).hexdigest()==original_sha
