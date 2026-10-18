// Actual HTTP multipart of a fixed-SHA long PDF into a new production-gate root.
import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import { readFileSync,mkdirSync,writeFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
import assert from 'node:assert/strict';
const out=process.argv[2];mkdirSync(out,{recursive:true});
const source=JSON.parse(readFileSync(new URL('../product/validation/sources.json',import.meta.url),'utf8')).find(s=>s.id==='gree-2025');
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:900}});
const page=await context.newPage();
const proof={actual_http_pdf_bge_milvus:true,source,frontend_writes:[],catalog:[],human_acceptances:0,human_review:'pending',errors:[]};
page.on('request',r=>{if(r.method()!=='GET')proof.frontend_writes.push({method:r.method(),url:r.url()});});
page.on('pageerror',e=>proof.errors.push(e.message));
page.on('response',async r=>{if(r.url().endsWith('/api/documents')&&r.status()===200){proof.catalog.push({at:performance.now(),documents:await r.json()});}});
try{
  const companyResponse=await context.request.post('http://127.0.0.1:14228/api/companies',{data:{name:'珠海格力电器股份有限公司',security_code:'000651',exchange:'SZSE'}});
  assert.equal(companyResponse.status(),201);const company=await companyResponse.json();proof.company=company;
  const url=`http://127.0.0.1:14228/companies/${company.company_id}/documents`;
  await page.goto(url);await page.getByRole('heading',{name:'准备财报资料',exact:true}).waitFor();
  const t=performance.now();
  const upload=await context.request.post('http://127.0.0.1:14228/api/report-documents',{multipart:{
    file:{name:'gree-2025.pdf',mimeType:'application/pdf',buffer:readFileSync(new URL('../'+source.path,import.meta.url))},
    metadata:JSON.stringify({company_id:company.company_id,report_year:2025,report_type:'annual',basis:'PRC_GAAP',period_start:'2025-01-01',period_end:'2025-12-31',source_url:source.url})}});
  proof.http_upload_seconds=(performance.now()-t)/1000;proof.receipt=await upload.json();assert.equal(upload.status(),202);
  await page.reload();
  const row=page.locator('article').filter({has:page.getByRole('heading',{name:'gree-2025.pdf',exact:true})});
  await row.waitFor({state:'visible'});proof.initial_status_text=await row.innerText();
  await page.screenshot({path:`${out}/processing.png`,fullPage:true});
  await page.waitForFunction(()=>[...document.querySelectorAll('article')].some(a=>a.textContent.includes('gree-2025.pdf')&&a.textContent.includes('PDF 处理就绪')),null,{timeout:180000});
  proof.upload_to_visible_ready_seconds=(performance.now()-t)/1000;
  proof.final_status_text=await row.innerText();
  const response=await context.request.get(`http://127.0.0.1:14228/api/documents/${proof.receipt.document_id}/source`);
  proof.final_source=await response.json();assert.equal(proof.final_source.content_sha256,source.sha256);
  assert(proof.final_source.parser_version.startsWith('fast-pdf-v4;table-geometry-v2;'));
  assert(proof.catalog.length>=3);assert(proof.frontend_writes.length===0);assert.equal(proof.errors.length,0);
  proof.automatic_upload_replays=0;proof.reopened_page_without_upload_intent=true;
  await page.screenshot({path:`${out}/ready.png`,fullPage:true});
}finally{writeFileSync(`${out}/results.json`,JSON.stringify(proof,null,2));await browser.close();}
