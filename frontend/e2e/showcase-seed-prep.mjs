// Build only public, explicitly labelled demonstration material in a disposable runtime.
import { readFile,writeFile } from 'node:fs/promises';
import { createHash,randomUUID } from 'node:crypto';
export async function preparePublicSeed(page,base,api,out){
 const assert=(v,m)=>{if(!v)throw Error(m);};const result={official_documents:[],notes:[],financial_approvals:0};
 const companies=await api('/companies');const gree=companies.find(c=>c.security_code==='000651');assert(gree,'Gree exists');
 const midea=companies.find(c=>c.security_code==='000333')||await api('/companies',{name:'美的集团股份有限公司',security_code:'000333',exchange:'SZSE'});
 for(const [code,year,company]of[['000651',2024,gree],['000333',2025,midea]]){
  const list=await api(`/disclosures/search?code=${code}&report_year=${year}`);const candidate=list.items[0];assert(candidate?.sha256,'verified public catalogue');
  const imported=await api('/disclosures/import',{operation_id:randomUUID(),candidate_id:candidate.candidate_id,company_id:company.company_id});assert(imported.state==='completed','official download/import');
  const id=imported.result.document_id;let document;
  for(let n=0;n<240;n++){document=await api(`/documents/${id}`);if(document.status==='ready'||document.status==='failed')break;await page.waitForTimeout(700);}
  assert(document.status==='ready',`${code}-${year} actual fast/BGE READY`);
  const source=await api(`/documents/${id}/source?company_id=${company.company_id}`);assert(source.content_sha256===candidate.sha256,'public SHA');result.official_documents.push({document_id:id,sha256:source.content_sha256,source_revision:source.source_revision,report_year:year,company_id:company.company_id});
  await writeFile(`${out}/seed-preparation.json`,JSON.stringify(result,null,2));
 }
 const scan=await readFile(process.env.DEMO_CHECK_SCAN_PATH);assert(createHash('sha256').update(scan).digest('hex')==='175235d1122aec489a6c943ec8c1f8f9fcb5ffdd0e75f938f5ce6080c8ed163a','known derived public scan');
 const uploaded=await page.request.post(`${base}/api/report-documents`,{headers:{'X-Operation-ID':randomUUID(),'Origin':base},multipart:{file:{name:'美的2025_公开原文第9页_派生扫描示例.pdf',mimeType:'application/pdf',buffer:scan},metadata:JSON.stringify({company_id:midea.company_id,report_year:2025,report_type:'annual',basis:'PRC_GAAP',period_start:'2025-01-01',period_end:'2025-12-31'})}});assert(uploaded.ok(),`derived scan binding only HTTP${uploaded.status()}: ${await uploaded.text()}`);const doc=await uploaded.json();
 const identity=await api(`/documents/${doc.document_id}/parse-identity`);const parsed=await api(`/documents/${doc.document_id}/parse-retry`,{operation_id:randomUUID(),expected_source_revision:identity.source_revision});assert(parsed.state==='completed','real Vision completed');const artifact=await api(`/documents/${doc.document_id}/parse-quality?artifact_id=${parsed.artifact_id}`);assert(artifact.ocr_pages===1&&artifact.pages[0].lines.length>20,'real OCR lines');
 result.ocr={document_id:doc.document_id,artifact_id:artifact.artifact_id,lines:artifact.pages[0].lines.length,cells:artifact.pages[0].tables[0].cells.length,sha256:artifact.content_sha256,legacy_source_verified:artifact.legacy_source_verified};
 for(const text of ['预置演示研究线索：后续关注经营现金流与回款质量；这不是财务确认或投资结论。','预置演示研究问题：原材料价格与海外汇率变化如何影响经营风险？请回到年报原文。']){const receipt=await api('/research-memories',{operation_id:randomUUID(),type:'note',text,company_id:gree.company_id,confirmed:true});assert(receipt.state==='completed','demo note with real BGE');result.notes.push(receipt.memory_id);}
 const docs=await api('/documents');assert(docs.filter(d=>d.status==='ready').length===3,'three actual official READY PDFs');result.documents=docs.map(d=>({document_id:d.document_id,status:d.status}));result.report_ids=(await api('/showcase-reports')).map(r=>r.report_id);assert(result.report_ids.length>=2,'two actually generated reports');
 await writeFile(`${out}/seed-preparation.json`,JSON.stringify(result,null,2));return result;
}
