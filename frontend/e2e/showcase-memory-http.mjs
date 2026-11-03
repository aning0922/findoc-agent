// Real browser + HTTP + local BGE semantic index. No LLM or financial signing.
import { chromium } from 'playwright';
import { writeFile } from 'node:fs/promises';
const base=process.env.DEMO_CHECK_ORIGIN, out=process.env.DEMO_CHECK_OUTPUT;
const assert=(v,m)=>{if(!v)throw Error(m);};
const browser=await chromium.launch({headless:true});
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(45000);
 const errors=[];let llmWrites=0,financial=0;
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{const p=new URL(r.url()).pathname;if(r.method()==='POST'&&/\/turns$|\/research\/intent|\/synthesis\/|\/deep-research\//.test(p))llmWrites++;if(r.method()==='POST'&&/confirmations|persisted|\/resume$/.test(p))financial++;});
 await page.goto(base);await page.getByLabel('账号',{exact:true}).fill(process.env.DEMO_CHECK_USERNAME);await page.getByLabel('密码',{exact:true}).fill(process.env.DEMO_CHECK_PASSWORD);await page.getByRole('button',{name:'进入演示',exact:true}).click();await page.getByRole('heading',{name:'研究概览',exact:true}).waitFor();
 await page.goto(`${base}/conversations`);await page.getByRole('button',{name:'选择年报',exact:true}).click();
 const dialog=page.getByRole('dialog');await dialog.locator('section').filter({hasText:'000651-2025.pdf'}).getByRole('checkbox').check();
 await dialog.getByRole('button',{name:'创建会话',exact:true}).click();await page.waitForURL(/conversation=/);
 const cid1=new URL(page.url()).searchParams.get('conversation');
 const memory=page.locator('.research-memory');await memory.locator('summary').click();
 const text='继续研究经营活动现金流与回款质量，比较现金流和利润是否匹配。';
 await memory.getByLabel('内容',{exact:true}).fill(text);await memory.getByRole('checkbox',{name:'我确认保存这条研究记忆',exact:true}).check();
 await memory.getByRole('button',{name:'保存记忆',exact:true}).click();await memory.locator('article').filter({hasText:text}).waitFor();
 const prefs=memory.locator('div').filter({has:page.getByText('仅保存你明确确认的研究偏好',{exact:false})}).last();
 // Controls belong to the nested, existing preferences component.
 await memory.getByLabel('偏好类型',{exact:true}).selectOption('analysis_focus');await memory.getByLabel('偏好内容',{exact:true}).selectOption('cash_flow');await memory.getByRole('button',{name:'保存偏好',exact:true}).click();await memory.getByText('分析侧重：现金流',{exact:true}).waitFor();
 await memory.getByLabel('偏好类型',{exact:true}).selectOption('display_unit');await memory.getByLabel('偏好内容',{exact:true}).selectOption('CNY_TEN_THOUSAND');await memory.getByRole('button',{name:'保存偏好',exact:true}).click();await memory.getByText('展示单位：万元',{exact:true}).waitFor();
 await memory.getByLabel('偏好类型',{exact:true}).selectOption('research_habit');await memory.getByLabel('偏好内容',{exact:true}).selectOption('compare_periods_first');await memory.getByRole('button',{name:'保存偏好',exact:true}).click();await memory.getByText('研究习惯：先比较期间',{exact:true}).waitFor();
 // New conversation uses the same frozen source, never a new provider turn.
 const cid2=await page.evaluate(async()=>{const source=await(await fetch('/api/research/sources')).json();const r=await fetch('/api/conversations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operation_id:crypto.randomUUID(),document_ids:[source.documents.find(d=>d.selectable).document_id]})});if(!r.ok)throw Error('create second');return(await r.json()).conversation_id;});
 assert(cid1!==cid2,'independent conversations');await page.goto(`${base}/conversations?conversation=${cid2}`);
 await page.locator('.research-memory summary').click();await page.locator('.research-memory').getByLabel('搜索研究记忆',{exact:true}).fill('现金回收和盈利质量');await page.locator('.research-memory').getByRole('button',{name:'搜索',exact:true}).click();await page.locator('.research-memory article').filter({hasText:text}).waitFor();
 for(const width of [1440,1280,390]){await page.setViewportSize({width,height:1000});await page.screenshot({path:`${out}/memory-${width}.png`,fullPage:true});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow ${width}`);}
 await page.locator('.research-memory article').filter({hasText:text}).getByRole('button',{name:'删除',exact:true}).click();await page.locator('.research-memory').getByRole('button',{name:'确认删除',exact:true}).click();await page.locator('.research-memory').getByText('没有找到研究记忆。',{exact:true}).waitFor();
 await page.locator('.research-memory').getByRole('button',{name:'搜索',exact:true}).click();await page.locator('.research-memory').getByText('没有找到研究记忆。',{exact:true}).waitFor();
 await page.goto(base);await page.getByLabel('财务指标',{exact:true}).waitFor();assert(await page.getByLabel('财务指标',{exact:true}).inputValue()==='operating_cash_flow','focus changes metric');
 const overview=await page.evaluate(async()=>await(await fetch('/api/dashboard/overview')).json());assert(overview.suggested_questions[0].id==='operating_cash_flow','focus question order');
 assert((await page.locator('.sd-grid > section').evaluateAll(nodes=>nodes.slice().sort((a,b)=>Number(getComputedStyle(a).order)-Number(getComputedStyle(b).order))[0].textContent)).includes('各期财务对比'),'habit changes visual order');
 assert((await page.locator('.sd-grid').textContent()).includes('坐标以万元显示'),'display unit preference');
 const result={evidence:'REAL_CHROMIUM_HTTP_REAL_LOCAL_BGE',conversation_ids:[cid1,cid2],semantic_query:'现金回收和盈利质量',semantic_result:text,deleted_future_recall:true,preferences:overview.display_preferences,llm_calls:llmWrites,human_financial_approvals:financial,browser_errors:errors};assert(llmWrites===0&&financial===0&&errors.length===0,'no model/signing/errors');await writeFile(`${out}/browser-result.json`,JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
