"""Run with repository on PYTHONPATH; offline cached BGE and temp seed copy only."""
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from app.demo.seed import materialize,verify_seed
from app.parsing import ParseV2Service
from app.rag.embed import embed
from app.rag.store import get_client,MilvusSearchStore
from app.rag.publications import IndexPublications
from app.rag.retriever import Retriever,SearchFilters,TrustedContext
from app.retrieval_v2 import HybridRetrievalService,SourceRef
from tests.test_document_sources import Harness
from tests.test_parse_v2 import Engine


async def main():
    seed=Path('/Users/aipuli/.codex/worktrees/findoc-showcase-cplus-integration/findoc-agent/data/showcase-seed-v1')
    _,digest=verify_seed(seed)
    baseline=json.loads(Path('docs/cplus/evidence/M0-retrieval-before.json').read_text())
    with TemporaryDirectory(prefix='findoc-cplus-hybrid-') as directory:
        root=Path(directory)/'runtime';materialize(seed,root,digest)
        h=Harness(root)  # Adds synthetic helper companies only to the disposable copy.
        parse=ParseV2Service(runtime_root=root,documents=h.documents,sources=h.service,engine=Engine())
        client=get_client(str(root/'milvus.db'))
        try:
            pubs=IndexPublications(h.registry,client)
            retriever=Retriever(embed,MilvusSearchStore(client,'findoc_runtime_documents_v1',include_scope_metadata=True,publications=pubs))
            def dense(q,refs,k):
                ids=tuple(sorted(r.document_id for r in refs));revisions=tuple(sorted((r.document_id,r.source_revision) for r in refs))
                return retriever.retrieve(q,context=TrustedContext('demo'),filters=SearchFilters(document_ids=ids,source_revisions=revisions),top_k=k)
            service=HybridRetrievalService(root,h.service,parse,dense)
            results=[]
            for case in baseline['results']:
                refs=[SourceRef(kind='fast',identity_status='fast_source_verified',**{k:v for k,v in r.items() if k in ('workspace_id','company_id','document_id','source_revision','content_sha256','parser_version','report_year','attempt','report_type','basis','period_start','period_end')}) for r in case['sources']]
                await service.build(refs);result=await service.search(refs,case['query'])
                results.append(dict(case_id=case['case_id'],query=case['query'],pages=[c['evidence_ref']['physical_page'] for c in result['items']],scores=[{k:c[k] for k in ('dense_cosine','fusion_score','rerank_score')} for c in result['items']]))
            with sqlite3.connect(parse.path) as db:
                artifact=json.loads(db.execute('SELECT payload FROM artifacts').fetchone()[0])
            ref=SourceRef(kind='ocr',identity_status='file_transcription_only',workspace_id='demo',**{k:artifact[k] for k in ('company_id','document_id','source_revision','content_sha256','parser_version','report_year','config_hash','metadata_sha256')},artifact_id=artifact['artifact_id'],artifact_sha256=artifact['output_sha256'],selected_pages=[1])
            built=await service.build([ref]);ocr=await service.search([ref],'营业收入')
            proof=dict(implementation_sha256=hashlib.sha256(Path('app/retrieval_v2/service.py').read_bytes()).hexdigest(),tier='REAL_PDF_BGE_MILVUS_AND_EXISTING_VISION_ARTIFACT',llm_calls=0,financial_approvals=0,seed_manifest_sha256=digest,results=results,ocr_indexed=built['indexed_passages'],ocr_hits=len(ocr['items']),ocr_legacy_ready=False,model_revision='unknown',limitations=['No model answer execution','Ranking/page diagnostics are not human semantic precision','Historical entrusted-finance failure is a separate run'])
            verify_seed(seed,digest)
            Path('docs/cplus/evidence/M1-retrieval-real.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2))
            print(json.dumps(proof,ensure_ascii=False))
        finally: client.close()


if __name__=='__main__': asyncio.run(main())
