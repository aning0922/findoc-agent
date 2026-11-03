"""Real root-wired HTTP/CSV export; synthetic parent permission, no model."""
from contextlib import contextmanager
from types import SimpleNamespace
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cplus.exports import register_exports
from app.exports_v2.projection import digest
from app.retrieval_v2 import TrustedIdentity
from app.retrieval_v2.models import RetrievalError


def test_saved_file_rechecks_parent_permission_without_rerender(tmp_path):
    allowed = [True]
    reads = []
    snapshot = dict(schema_version='cplus-research-answer-v1', answer_id='answer',
                    context_id='context', question='fixture', findings=[], financial_authority=False)
    scope = dict(parent_conversation_id='parent', selected_sources=[])

    async def authorize(identity):
        return 'fixture-owner'

    def selection(*args):
        reads.append(args)
        if not allowed[0]:
            raise RetrievalError('parent_display_revoked', 403)

    @contextmanager
    def guard(*args):
        yield

    identity = TrustedIdentity(workspace_id='demo', instance_id='fixture', generation=1,
                               principal_id='fixture', expires_at=time.time()+300)
    app = FastAPI()
    register_exports(app, tmp_path,
        hybrid=SimpleNamespace(authorize=authorize, read=lambda kind, ident, owner:
                               snapshot if kind == 'answer' else scope),
        annual=None, peer=None, statements=None,
        identity_provider=lambda request: identity, validate=lambda identity: None,
        guard=guard, conversations=SimpleNamespace(selection=selection))
    body = dict(operation_id=str(uuid4()), report_ref=dict(domain='research_answer_v1',
                id='answer', revision=1, payload_sha256=digest(snapshot)), formats=['csv'],
                export_profile_version='research-v1')
    with TestClient(app) as client:
        created = client.post('/cplus/exports', json=body)
        assert created.status_code == 200
        href = created.json()['result']['files'][0]['href']
        first = client.get(href)
        assert first.status_code == 200
        service = app.state.cplus_export_service
        with service.tx() as db:
            before = list(db.execute('SELECT id,state FROM ops'))
        allowed[0] = False
        denied = client.get(href)
        assert denied.status_code == 403
        assert denied.json()['detail']['code'] == 'display_permission_denied'
        assert first.content not in denied.content
        allowed[0] = True
        again = client.get(href)
        assert again.status_code == 200
        assert again.content == first.content
        assert again.headers['etag'] == first.headers['etag']
        with service.tx() as db:
            assert list(db.execute('SELECT id,state FROM ops')) == before
        assert len(reads) >= 5
