const crypto=require('node:crypto');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const root=process.argv[2] || '/Users/aipuli/.codex/worktrees/findoc-showcase-cplus-integration/findoc-agent';
const {chromium}=require(root+'/frontend/node_modules/playwright');
const {createServer}=require(require.resolve('vite',{paths:[root+'/frontend']}));
const react=require(require.resolve('@vitejs/plugin-react',{paths:[root+'/frontend']})).default;
(async()=>{
 const tmp=await fs.mkdtemp(path.join(os.tmpdir(),'batch-ui-review-'));
 let browser,server;
 try{
 const entry=path.join(tmp,'entry.jsx');
 await fs.writeFile(entry,`import React from 'react';import{createRoot}from'react-dom/client';import{BatchResearchPanel}from ${JSON.stringify(root+'/frontend/src/product/cplus/batch/BatchResearchPanel.tsx')};createRoot(document.getElementById('root')).render(<BatchResearchPanel companies={[]} sources={[]}/>);`);
 const portServer=http.createServer();await new Promise(r=>portServer.listen(0,'127.0.0.1',r));const port=portServer.address().port;await new Promise(r=>portServer.close(r));
 server=await createServer({configFile:false,envDir:false,root:root+'/frontend',cacheDir:path.join(tmp,'cache'),plugins:[react()],resolve:{alias:{'react-dom':path.dirname(require.resolve('react-dom/package.json',{paths:[root+'/frontend']})),'react':path.dirname(require.resolve('react/package.json',{paths:[root+'/frontend']}))},dedupe:['react','react-dom']},server:{host:'127.0.0.1',port,strictPort:true,fs:{allow:[root+'/frontend',tmp,await fs.realpath(root+'/frontend/node_modules')]}}});await server.listen();const base='http://127.0.0.1:'+port;
 assert(![14540,14542].includes(port));
 browser=await chromium.launch({headless:true});const outcomes=[];
 const sourcePath=root+'/frontend/src/product/cplus/batch/BatchResearchPanel.tsx';const sourceSha=crypto.createHash('sha256').update(await fs.readFile(sourcePath)).digest('hex');
 const operation='11111111-1111-4111-8111-111111111111';const plan={batch_plan_id:'fixture-ai-plan',revision:1,batch_plan_sha256:'a'.repeat(64),limits:{execution_mode:'ai_review',max_provider_attempts:4},cells:Array.from({length:4},(_,i)=>({cell_key:'cell-'+i,company_id:'company',template:'risk_excerpt',question:'fixture question',prepared:{generate_explanation:true,selected_sources:[{document_id:'doc'}]}}))};
 const variants=[['saved_ai',structuredClone(plan),true,true],['missing_ai_limits',structuredClone(plan),false,false],['conflicting_mode',structuredClone(plan),false,false],['legacy_pure',structuredClone(plan),true,false]];
 delete variants[1][1].limits;variants[2][1].limits.execution_mode='pure_tools';variants[3][1].limits={max_cells:12,parallel_cells:1,templates:['risk_excerpt','annual_changes'],provider_calls_by_service:0};for(const c of variants[3][1].cells)delete c.prepared.generate_explanation;
 for(const [name,saved,allow,checked] of variants){const page=await browser.newPage();page.setDefaultTimeout(10000);
 let posted=null;const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.addInitScript(op=>sessionStorage.setItem('findoc:cplus-batch-operation',JSON.stringify({id:op,action:'plan'})),operation);
 await page.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
 await page.route('**/api/**',route=>{
 const request=route.request();
 if(request.method()==='GET'&&request.url().endsWith('/batch-operations/'+operation))return route.fulfill({json:{operation_id:operation,state:'completed',result:saved}});
 if(request.method()==='POST'&&request.url().endsWith('/batches')){posted=request.postDataJSON();return route.fulfill({json:{operation_id:posted.operation_id,state:'completed',result:{batch_id:'batch-fixture',revision:1,state:'completed',cells:[]}}});}
 return route.abort();
 });
 await page.route('**/review',route=>route.fulfill({contentType:'text/html',body:`<div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>t=>t;window.__vite_plugin_react_preamble_installed__=true;</script><script type="module" src="/@fs${entry}"></script>`}));
 await page.goto(base+'/review');await page.getByRole('button',{name:'查询原操作',exact:true}).click();
 const confirmation=await page.locator('article').filter({hasText:'确认计划'}).innerText();
 const checkbox=page.getByRole('checkbox').first();
 const actualChecked=await checkbox.isChecked(), disabled=await page.getByRole('button',{name:'批准并开始',exact:true}).isDisabled();
 const matches=actualChecked===checked&&disabled===!allow&&(name==='saved_ai'?confirmation.includes('最多 4 次 AI 解释')&&!confirmation.includes('模型调用为零'):name==='legacy_pure'?confirmation.includes('模型调用为零'):confirmation.includes('禁止批准'));
 if(allow&&!disabled){await page.getByRole('button',{name:'批准并开始',exact:true}).click();assert.equal(posted.batch_plan_id,saved.batch_plan_id);assert.equal(posted.confirmed,true)}
 else assert.equal(posted,null);
 assert.deepEqual(errors,[]);
 outcomes.push({name,result:matches?'PASS':'FAIL',actual_checked:actualChecked,approval_disabled:disabled,expected_approval_enabled:allow,confirmation_text:confirmation,approval_sent:posted!==null});
 await page.close();}
 const output={tier:'UI_MOCK_ACTUAL_REACT_ISOLATED_BROWSER',source_sha256:sourceSha,cases:outcomes,real_provider_calls:0,real_backend_requests:0,original_reproduction_preserved:true};
 assert.equal(crypto.createHash('sha256').update(await fs.readFile(sourcePath)).digest('hex'),sourceSha,'source changed during fixture');
 await fs.writeFile(__dirname+'/M5-batch-ui-recovery-FIXED-proof.json',JSON.stringify(output,null,2)+'\n');console.log(JSON.stringify(output));
 if(outcomes.some(c=>c.result!=='PASS'))process.exitCode=1;

 }finally{if(browser)await browser.close();if(server)await server.close();await fs.rm(tmp,{recursive:true,force:true});}
})().catch(e=>{console.error(e);process.exitCode=1});
