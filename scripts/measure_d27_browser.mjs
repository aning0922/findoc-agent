// Built formal frontend against the real D27 production-gate server. No mocks.
import { chromium } from '../frontend/node_modules/playwright-core/index.mjs';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
import assert from 'node:assert/strict';
const out=process.argv[2];
assert(out);mkdirSync(out,{recursive:true});
const original=JSON.parse(readFileSync(new URL('../data/d27/a-final/results.json',import.meta.url),'utf8'));
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:900}});
const page=await context.newPage();
const proof={actual_server:true,actual_built_frontend:true,actual_bge:true,actual_milvus:true,
  human_review:'pending',qa_dom:[],pdf:[],browser_errors:[],writes:[]};
page.on('pageerror',e=>proof.browser_errors.push(e.message));
page.on('request',r=>{if(['POST','PUT','DELETE'].includes(r.method()))proof.writes.push({method:r.method(),url:r.url()});});
await page.addInitScript(()=>{
  window.__d27={longTasks:[],gaps:[]};
  new PerformanceObserver(list=>window.__d27.longTasks.push(...list.getEntries().map(x=>({start:x.startTime,duration:x.duration})))).observe({type:'longtask',buffered:true});
  let last=performance.now();function tick(t){window.__d27.gaps.push(t-last);last=t;requestAnimationFrame(tick);}requestAnimationFrame(tick);
});
try{
  for(const q of original.questions.filter(q=>q.gold)){
    const source=q.sources[0].source;
    const t=performance.now();
    await page.goto(`http://127.0.0.1:14227/research?company=${source.company_id}&mode=qa`);
    for(let n=0;n<10 && await page.getByRole('button',{name:q.query,exact:true}).count()===0;n++){
      const more=page.getByRole('button',{name:'加载更多研究',exact:true});
      await more.waitFor({state:'visible',timeout:15000});await more.click();
      await page.waitForTimeout(80);
    }
    await page.getByRole('button',{name:q.query,exact:true}).first().click();
    const owner=page.locator(`[data-document-id="${source.document_id}"][data-source-revision="${source.source_revision}"]`).first();
    await owner.waitFor({state:'visible',timeout:20000});
    const table=owner.getByRole('table').filter({hasText:q.gold.raw_value}).first();
    const headers=await table.locator('th').allTextContents();
    const row=table.locator('tr').filter({hasText:q.gold.raw_value}).first();
    const cells=await row.locator('td').allTextContents();
    assert.equal(headers.indexOf(`${q.gold.period}年`),cells.indexOf(q.gold.raw_value));
    assert(headers.includes(`${q.gold.period}年`));
    assert((await row.innerText()).includes(q.gold.raw_unit));
    proof.qa_dom.push({id:q.id,headers,cells,source,aligned:true,history_open_seconds:(performance.now()-t)/1000});
  }
  await page.screenshot({path:`${out}/real-answer-table.png`,fullPage:true});
  for(const report of original.reports){
    const s=report.source,t=performance.now();
    await page.goto(`http://127.0.0.1:14227/evidence?${new URLSearchParams({company:s.company_id,document:s.document_id,revision:s.source_revision,period:String(s.report_year),metric:'revenue'})}`);
    const open=page.getByRole('button',{name:'查看原PDF',exact:true}).first();
    // Desktop opens the reader by default; narrow screens expose the open button.
    const click=performance.now();
    if(await open.isVisible())await open.click();
    await page.locator('.pdf-sheet canvas').first().waitFor({state:'visible',timeout:30000});
    await page.waitForFunction(()=>![...document.querySelectorAll('.pdf-location')].some(x=>x.textContent.includes('正在渲染')));
    const entry={report:report.report_id,physical_pages:s.physical_pages,first_open_seconds:(performance.now()-t)/1000,
      click_to_canvas_seconds:(performance.now()-click)/1000,pdf_network:await page.evaluate(()=>performance.getEntriesByType('resource').filter(x=>x.name.includes('/file?')).map(x=>({name:x.name,duration:x.duration,transferSize:x.transferSize,decodedBodySize:x.decodedBodySize}))),zooms:[]};
    const zoom=page.getByLabel('缩放',{exact:true});
    for(const value of ['1.5','1','fit']){
      const oldWidth=await page.locator('.pdf-sheet canvas').first().evaluate(x=>x.style.width);
      const z=performance.now();await zoom.selectOption(value);
      await page.waitForFunction(old=>document.querySelector('.pdf-sheet canvas')?.style.width!==old,oldWidth);
      await page.waitForFunction(()=>![...document.querySelectorAll('.pdf-location')].some(x=>x.textContent.includes('正在渲染')));
      entry.zooms.push({value,seconds:(performance.now()-z)/1000,canvasWidth:await page.locator('.pdf-sheet canvas').first().evaluate(x=>x.style.width)});
    }
    const references=page.getByLabel('切换引用',{exact:true});
    const options=await references.locator('option').evaluateAll(xs=>xs.map(x=>({value:x.value,text:x.textContent})));
    const current=await references.inputValue();
    const currentPage=await page.getByLabel('物理页码',{exact:true}).inputValue();
    const other=options.find(x=>x.value && x.value!==current && !x.text.includes(`物理第 ${currentPage} 页`));
    if(other){const z=performance.now();await references.selectOption(other.value);
      const expectedPage=/物理第\s+(\d+)\s+页/.exec(other.text)?.[1];assert(expectedPage);
      await page.locator(`canvas[aria-label="PDF 物理第 ${expectedPage} 页"]`).waitFor({state:'visible'});
      await page.waitForFunction(()=>![...document.querySelectorAll('.pdf-location')].some(x=>x.textContent.includes('正在渲染')));
      entry.switch_reference_seconds=(performance.now()-z)/1000;entry.reference=other;entry.expected_physical_page=expectedPage;}
    entry.browser=await page.evaluate(()=>window.__d27);
    proof.pdf.push(entry);
    await page.screenshot({path:`${out}/${report.report_id}-pdf.png`,fullPage:true});
    writeFileSync(`${out}/results.json`,JSON.stringify(proof,null,2));
  }
  assert.equal(proof.browser_errors.length,0);
}finally{writeFileSync(`${out}/results.json`,JSON.stringify(proof,null,2));await browser.close();}
