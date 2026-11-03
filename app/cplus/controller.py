"""Root-owned controller discovery boundary and fixed-child import adapter."""
from contextlib import closing, contextmanager
from datetime import datetime, UTC
import json
import sqlite3

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

from app.company_discovery import CNInfoProvider, DiscoveryService, TrustedImportIdentity, create_discovery_router
from app.company_discovery.contracts import DiscoveryError
from app.demo.controller import token_hash
from app.demo.gateway import FencedResponse
from app.public_pdf_cache import PublicPdfCacheBroker


def register_cplus_controller(app, controller):
    def check(identity, connection=None):
        handle = controller.manager.handle
        if (handle is None or handle.generation != identity.generation
                or handle.instance_id != identity.instance_id):
            raise DiscoveryError("runtime_changed", 401)

        def read(db):
            row = db.execute("SELECT s.expires,s.revoked,s.generation,t.state,t.session_hash,t.generation AS slot_generation "
                             "FROM sessions s CROSS JOIN slot t WHERE s.hash=?", (identity.principal,)).fetchone()
            if (row is None or row["revoked"] is not None or row["state"] != "active"
                    or row["session_hash"] != identity.principal or row["generation"] != identity.generation
                    or row["slot_generation"] != identity.generation or controller.clock() >= row["expires"]
                    or identity.expires_at > row["expires"] + .001):
                raise DiscoveryError("lease_expired_or_replaced", 401)
        if connection is not None:
            read(connection)
        else:
            with closing(sqlite3.connect(controller.store.path.as_uri()+"?mode=ro",uri=True)) as db:
                db.row_factory=sqlite3.Row
                read(db)

    @contextmanager
    def guard(identity):
        # Held only across short synchronous publication/ledger writes, never network await.
        with closing(sqlite3.connect(controller.store.path.as_uri()+"?mode=ro",uri=True,timeout=5,isolation_level=None)) as db:
            db.row_factory=sqlite3.Row
            db.execute("BEGIN")
            check(identity, db)
            if db.execute("PRAGMA journal_mode").fetchone()[0].lower() not in ("delete","truncate","persist"):
                raise DiscoveryError("controller_fence_unsupported",503)
            yield
            check(identity, db)
            db.execute("ROLLBACK")

    def identity_provider(request):
        token=request.cookies.get(controller.cookie_name)
        handle=controller.capture(token)
        session=controller.session(token)
        identity=TrustedImportIdentity(generation=handle.generation,instance_id=handle.instance_id,
                                      principal=token_hash(token),
                                      expires_at=datetime.fromisoformat(session['expires_at']).timestamp(),
                                      fence=lambda:guard(identity))
        check(identity)
        return identity

    async def binder(identity, content, resolved, announcement, *, on_phase):
        check(identity)
        handle=controller.manager.handle  # Capture once; never switch handles after awaiting.
        headers={"X-Findoc-Internal-Secret":handle.secret,"X-Findoc-Generation":str(handle.generation),
                 "X-Findoc-Instance":handle.instance_id,
                 "X-Findoc-Lease-Expires-At":datetime.fromtimestamp(identity.expires_at,UTC).isoformat()}

        async def request(method,path,**kwargs):
            check(identity)
            result=await handle.client.request(method,path,headers=headers,**kwargs)
            check(identity)
            if result.status_code>=400:
                raise DiscoveryError("child_binding_failed",result.status_code if result.status_code<500 else 503)
            return result.json()

        companies=await request("GET","/companies")
        matches=[c for c in companies if c['security_code']==resolved['security_code'] and c['exchange']==resolved['exchange']]
        if len(matches)>1:
            raise DiscoveryError("needs_manual_review")
        selected=matches[0] if matches else None
        requested=resolved.get('company_id')
        if requested and (selected is None or selected['company_id']!=requested):
            raise DiscoveryError("company_binding_conflict")
        if selected and (selected['name']!=resolved['official_name'] or selected.get('country')!='CN'):
            raise DiscoveryError("needs_manual_review")
        if selected is None:
            if not resolved.get('create_company'):
                raise DiscoveryError("explicit_company_creation_required")
            selected=await request('POST','/companies',json={
                'name':resolved['official_name'],'security_code':resolved['security_code'],
                'exchange':resolved['exchange'],'country':'CN'})
            await on_phase('company_created',created_company_id=selected['company_id'])
        await on_phase('uploading')
        year=announcement['report_year']
        metadata=dict(company_id=selected['company_id'],report_year=year,report_type='annual',
                      basis='unknown',period_start=f'{year}-01-01',period_end=f'{year}-12-31',
                      source_url=announcement['pdf_url'])
        value=await request('POST','/report-documents',files={
            'file':(f"{resolved['security_code']}-{year}.pdf",content,'application/pdf')},
            data={'metadata':json.dumps(metadata)})
        return dict(company_id=selected['company_id'],document_id=value['document_id'],status=value['document_status'])

    cache=PublicPdfCacheBroker(controller.config.control_root,max_disk_bytes=256*1024*1024)
    service=DiscoveryService(controller.config.control_root,CNInfoProvider(),cache,binder,check)
    router=create_discovery_router(service,identity_provider)

    class DiscoveryBoundary:
        def __init__(self,app):
            self.inner=app
        async def __call__(self,scope,receive,send):
            if scope['type'] != 'http' or not scope['path'].startswith('/cplus/discovery/'):
                await self.inner(scope,receive,send)
                return
            request=Request(scope)
            token=request.cookies.get(controller.cookie_name)
            try:
                handle=controller.capture(token)
            except HTTPException as exc:
                await JSONResponse({'detail':exc.detail},exc.status_code,
                                   headers={'Cache-Control':'no-store'})(scope,receive,send)
                return
            await FencedResponse(self.inner,controller,token,handle.generation)(scope,receive,send)

    app.include_router(router)
    # Fence the final ASGI emission, including FastAPI's lazy included-router forms.
    app.add_middleware(DiscoveryBoundary)
    app.state.cplus_discovery_service=service
    app.state.cplus_public_cache=cache
