"""Read-only, exact-reference PDF location. Original objects are never edited."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
import pymupdf

from app.retrieval_v2 import EvidenceRef


def create_evidence_router(*, hybrid, preparer, sources, identity_provider, publication_guard):
    router = APIRouter(prefix='/cplus')

    async def locate(answer_id, evidence_id, request, *, image=False):
        identity = identity_provider(request)
        owner = await hybrid.authorize(identity)
        answer = hybrid.read('answer', answer_id, owner)
        context = hybrid.read('context', answer['context_id'], owner)
        await hybrid.validate_context(context, owner)
        matches = [f['evidence_ref'] for f in answer['findings']
                   if f['evidence_ref']['evidence_id'] == evidence_id]
        if len(matches) != 1:
            raise ValueError('ambiguous_or_missing_evidence')
        ref = EvidenceRef.model_validate(matches[0])
        await hybrid.verify(ref)
        source = ref.source_ref
        raw = (await sources.file(source.document_id, source_revision=source.source_revision,
                                  company_id=source.company_id) if source.kind == 'fast'
               else await hybrid.parse.file(source.document_id, source.artifact_id))
        with publication_guard(identity, context), pymupdf.open(stream=raw, filetype='pdf') as pdf:
            page = pdf[ref.physical_page-1]
            if source.kind == 'ocr':
                # Vision's stored bbox is normalized top-left, verified with exact line.
                boxes = [pymupdf.Rect(ref.bbox[0]*page.rect.width, ref.bbox[1]*page.rect.height,
                                     ref.bbox[2]*page.rect.width, ref.bbox[3]*page.rect.height)] if ref.bbox else []
                mode = 'verified_ocr_line_bbox' if boxes else 'page_only'
            else:
                boxes = [q.rect for q in page.search_for(ref.text, quads=True)]
                mode = 'exact_excerpt_quads' if boxes else 'page_only'
            if image:
                for box in boxes:
                    annotation = page.add_highlight_annot(box)
                    annotation.set_colors(stroke=(1, .75, .1))
                    annotation.set_opacity(.4)
                    annotation.update()
                return Response(page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5), alpha=False).tobytes('png'),
                                media_type='image/png', headers={'Cache-Control':'no-store',
                                    'X-Findoc-Location-Mode':mode,'X-Content-Type-Options':'nosniff'})
            return {'schema_version':'evidence-location-v1','evidence_ref':ref.model_dump(),
                    'location_mode':mode,'rects':[[b.x0,b.y0,b.x1,b.y1] for b in boxes],
                    'coordinate_system':'pdf_points_top_left','page_width':page.rect.width,
                    'page_height':page.rect.height,'financial_authority':False,
                    'fallback_reason':None if boxes else 'exact_quote_not_located_open_original_page'}

    def fail(exc):
        return JSONResponse({'detail':{'code':getattr(exc,'code','evidence_unavailable')}},
                            status_code=getattr(exc,'status',409),headers={'Cache-Control':'no-store'})

    @router.get('/documents/{document_id}/research-source')
    async def selected_source(document_id: str, request: Request):
        try:
            await hybrid.authorize(identity_provider(request))
            selection = await preparer.prepare_many(document_ids=[document_id],query='只读核验研究资料')
            from .runtime import fast_ref
            return fast_ref(selection.documents[0]).model_dump()
        except Exception as exc:
            return fail(exc)

    @router.get('/research/answers/{answer_id}/evidence/{evidence_id}/location')
    async def location(answer_id: str, evidence_id: str, request: Request):
        try:
            return await locate(answer_id,evidence_id,request)
        except Exception as exc:
            return fail(exc)

    @router.get('/research/answers/{answer_id}/evidence/{evidence_id}/image')
    async def image(answer_id: str, evidence_id: str, request: Request):
        try:
            return await locate(answer_id,evidence_id,request,image=True)
        except Exception as exc:
            return fail(exc)

    return router
