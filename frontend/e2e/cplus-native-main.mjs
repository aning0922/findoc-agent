// Real independent Chromium processes, local gateway, real PDF/BGE/Vision; no provider.
import {chromium} from 'playwright';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
const origin='http://127.0.0.1:14540';
const config=Object.fromEntries((await readFile(new URL('../../data/showcase-local.env',import.meta.url),'utf8')).split('\n').filter(x=>x&&!x.startsWith('#')).map(x=>{const i=x.indexOf('=');return[x.slice(0,i),x.slice(i+1)];}));
const out=new URL('../../data/cplus-native-proof/',import.meta.url);await mkdir(out,{recursive:true});
const result={tier:'REAL_CHROMIUM_HTTP_PDF_BGE_MILVUS_VISION',provider_calls:0,human_financial_approvals:0,steps:[],screenshots:[]};
const save=()=>writeFile(new URL('result.json',out),JSON.stringify(result,null,2));
function assert(value,message){if(!value)throw Error(message);result.steps.push({name:message,status:'PASS'});console.log('PASS',message);}
const browsers=await Promise.all([chromium.launch({channel:'chrome',headless:true}),chromium.launch({channel:'chrome',headless:true})]);
const [a,b]=await Promise.all(browsers.map(browser=>browser.newPage({viewport:{width:1440,height:1000}})));
a.setDefaultTimeout(90000);b.setDefaultTimeout(90000);
async function api(page,method,path,body){const response=await page.request.fetch(origin+'/api'+path,{method,data:body,headers:{Origin:origin},timeout:180000});const value=await response.json();if(!response.ok())throw Error(`${method} ${path} ${response.status()} ${JSON.stringify(value)}`);return value;}
async function login(page){await page.goto(origin);for(let n=0;n<180;n++){const s=await page.request.get(origin+'/api/demo/status');if((await s.json()).service_state==='ready')break;await page.waitForTimeout(500)}await page.reload();await page.getByLabel('账号',{exact:true}).fill(config.DEMO_USERNAME);await page.getByLabel('密码',{exact:true}).fill(config.DEMO_PASSWORD);await page.getByRole('button',{name:'进入演示',exact:true}).click();}
try{
 await login(a);await a.getByRole('heading',{name:'研究概览',exact:true}).waitFor();await a.locator('.sd-kpis').waitFor();assert(true,'browser A real login and workspace warm');
 const initial=await api(a,'GET','/demo/session');result.generation_before=initial.lease_generation;
 for(const width of [1440,1280,390]){await a.setViewportSize({width,height:1000});await a.screenshot({path:new URL(`home-${width}.png`,out).pathname,fullPage:width===390});assert(await a.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`home no horizontal overflow ${width}`);result.screenshots.push(`home-${width}.png`)}
 await a.setViewportSize({width:1440,height:1000});
 const companies=await api(a,'GET','/companies'),gree=companies.find(c=>c.security_code==='000651');assert(!!gree,'real seeded Gree company exists');
 await a.goto(origin+`/companies/${gree.company_id}/overview`);await a.getByRole('button',{name:'三大报表',exact:true}).click();
 const docs=await api(a,'GET','/documents');const identities=[];
 for(const d of docs.filter(d=>d.status==='ready')){const meta=await api(a,'GET',`/documents/${d.document_id}/metadata`);if(meta.company_id===gree.company_id)identities.push({document_id:d.document_id,...meta})}
 for(const d of identities){await a.getByLabel('选择资料',{exact:false}).selectOption(d.document_id);await a.getByRole('button',{name:'提取三表候选',exact:true}).click();await a.getByRole('heading',{name:`${d.report_year} 年报 · 来源当前有效`,exact:true}).waitFor();}
 assert(identities.length===2,'two real annual reports extracted by UI');
 for(const button of await a.getByRole('button',{name:'选本报告全年/年末列',exact:true}).all())await button.click();
 await a.getByLabel('显示待核对候选观察',{exact:false}).check();await a.getByRole('button',{name:'生成趋势',exact:true}).click();await a.getByRole('button',{name:'生成趋势',exact:true}).waitFor({state:'visible'});await a.waitForFunction(()=>!document.querySelector('.cplus360 button[disabled]')||!document.body.textContent.includes('有待核对操作'));
 await a.getByRole('button',{name:'企业概览',exact:true}).click();await a.getByLabel('所选真实数据趋势',{exact:true}).waitFor();
 for(const width of [1440,1280,390]){await a.setViewportSize({width,height:1000});await a.screenshot({path:new URL(`company360-${width}.png`,out).pathname,fullPage:width===390});assert(await a.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`company360 no horizontal overflow ${width}`);result.screenshots.push(`company360-${width}.png`)}
 await a.setViewportSize({width:1440,height:1000});
 const collections=await api(a,'GET',`/cplus/companies/${gree.company_id}/statements`);result.collection_cells=collections.collections.map(c=>({year:c.source.report_year,cells:c.cells.length}));assert(collections.collections.every(c=>c.cells.some(v=>v.extraction_status==='candidate')),'real statement cells remain candidate');
 // Actual Vision retry, not a mock or re-labelled legacy READY.
 const scan=docs.find(d=>d.status==='failed');assert(!!scan,'scan keeps legacy failed state');
 const parseIdentity=await api(a,'GET',`/documents/${scan.document_id}/parse-identity`);
 const parsed=await api(a,'POST',`/documents/${scan.document_id}/parse-retry`,{operation_id:randomUUID(),expected_source_revision:parseIdentity.source_revision});assert(parsed.state==='completed','real OCR engine completed in this generation');
 const quality=await api(a,'GET',`/documents/${scan.document_id}/parse-quality`);result.ocr={artifact_id:quality.artifact_id,method:quality.pages.map(p=>p.method),lines:quality.pages.reduce((n,p)=>n+(p.lines?.length||0),0)};
 assert((await api(a,'GET',`/documents/${scan.document_id}`)).status==='failed','OCR does not grant legacy READY');
 await a.goto(origin+'/conversations');const panel=a.getByLabel('原文与OCR研究',{exact:true});await panel.getByLabel('资料',{exact:true}).selectOption(scan.document_id);await panel.getByLabel('研究方式',{exact:true}).selectOption('ocr');await panel.getByRole('button',{name:'读取资料身份',exact:true}).click();await panel.getByRole('button',{name:'明确加入转录研究',exact:true}).click();await panel.getByRole('button',{name:'建立混合检索索引',exact:true}).waitFor();await panel.getByRole('button',{name:'建立混合检索索引',exact:true}).click();await panel.getByRole('button',{name:'固定范围，开始研究',exact:true}).waitFor({state:'visible'});await a.waitForTimeout(400);await panel.getByRole('button',{name:'固定范围，开始研究',exact:true}).click();
 await panel.getByLabel('研究问题',{exact:true}).fill('主要会计数据');await panel.getByRole('button',{name:'提交研究问题',exact:true}).click();await panel.getByRole('button',{name:'定位原文',exact:true}).first().waitFor();assert(true,'typed OCR enrollment build context answer completed through UI');
 await panel.getByRole('button',{name:'定位原文',exact:true}).first().click();await panel.getByLabel('原文高亮预览',{exact:true}).waitFor();await panel.getByText('已按核验 OCR 行坐标高亮 · 转录待审',{exact:true}).waitFor();assert(true,'real OCR line bbox preview verified');await a.screenshot({path:new URL('ocr-highlight-1440.png',out).pathname,fullPage:true});result.screenshots.push('ocr-highlight-1440.png');
 await panel.getByRole('button',{name:'收藏这条证据',exact:true}).first().click();await panel.getByText('证据已收藏；可在下方记忆中查询与删除。',{exact:true}).waitFor();assert(true,'real OCR evidence saved to research memory without financial approval');
 // A separate Chromium process has its own cookie jar; owner action is explicit twice.
 await login(b);await b.getByRole('heading',{name:'演示空间正在使用',exact:true}).waitFor();assert(true,'browser B conflict displays remaining lease');await b.getByLabel('共享演示密码',{exact:true}).fill(config.DEMO_PASSWORD);await b.getByLabel('所有者口令',{exact:true}).fill(config.DEMO_OWNER_PASSWORD);assert(await b.getByRole('button',{name:'确认接管',exact:true}).isDisabled(),'takeover blocked before explicit confirmation');await b.getByLabel('我确认结束当前体验并重置演示环境',{exact:false}).check();await b.getByRole('button',{name:'确认接管',exact:true}).click();await b.getByRole('heading',{name:'研究概览',exact:true}).waitFor();
 const after=await api(b,'GET','/demo/session');assert(after.lease_generation>initial.lease_generation,'owner takeover created new generation');result.generation_after=after.lease_generation;assert((await a.request.get(origin+'/api/companies')).status()===401,'old browser loses actual HTTP access');
 const reset=await api(b,'GET',`/cplus/companies/${gree.company_id}/statements`);assert(reset.collections.length===0,'new generation has no previous financial candidate writes');
 await b.getByRole('button',{name:'退出演示',exact:true}).click();await b.getByRole('button',{name:'进入演示',exact:true}).waitFor();result.result='PASS';await save();console.log(JSON.stringify(result));
}catch(error){result.result='FAIL';result.error=String(error);result.visible_page_text=(await a.locator('body').innerText()).slice(0,3000);await a.screenshot({path:new URL('failure.png',out).pathname,fullPage:true});await save();console.error(String(error));process.exitCode=1}finally{for(const page of [a,b]){try{const s=await page.request.get(origin+'/api/demo/session');if(s.ok())await api(page,'POST','/demo/logout',{operation_id:randomUUID()})}catch{/* Cleanup never claims success on a revoked token. */}}await Promise.all(browsers.map(browser=>browser.close()));}
