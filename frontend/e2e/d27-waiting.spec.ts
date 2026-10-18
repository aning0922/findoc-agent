import { test, expect } from '@playwright/test';
import { writeFileSync } from 'node:fs';
const out=process.env.UX_ARTIFACT_DIR!;

test('D27 operating wait stops browser only; committed original operation restores with zero replay',async({page})=>{
  const companies=await (await page.request.get('/api/companies')).json();
  const company=companies.find((c:any)=>c.security_code==='000333');
  const sourceList=await (await page.request.get('/api/research/sources')).json();
  const doc=sourceList.documents.find((d:any)=>d.company_id===company.company_id&&d.report_year===2025);
  await page.goto(`/research?company=${company.company_id}&mode=operating&new=1`);
  await page.getByLabel('first 期间',{exact:true}).selectOption('2025');
  await page.getByLabel('second 期间',{exact:true}).selectOption('2024');
  await page.getByRole('button',{name:'下一步：准备财报',exact:true}).click();
  for(const side of ['first','second'])await page.getByLabel(`${side} 年报`,{exact:true}).selectOption(doc.document_id);
  await page.getByRole('button',{name:'下一步：确认来源',exact:true}).click();
  for(const group of await page.locator('.operating-side').all())await group.getByRole('button',{name:'采用这组三项来源',exact:true}).click();
  let saved:any,posts=0;let release!:()=>void;const reads:string[]=[];
  page.on('request',r=>{if(r.method()==='GET'&&r.url().includes('/research/tasks/'))reads.push(r.url());});
  const delivery=new Promise<void>(resolve=>release=resolve);
  await page.route('**/api/research/tasks',async route=>{
    if(route.request().method()!=='POST')return route.continue();
    posts++;const response=await route.fetch();expect(response.status()).toBe(200);saved=await response.json();
    await delivery;await route.abort('failed').catch(()=>{});
  });
  await page.getByRole('button',{name:'创建研究，开始核对数据',exact:true}).evaluate(b=>{(b as HTMLElement).click();(b as HTMLElement).click();});
  await expect(page.getByLabel('本页等待状态',{exact:true})).toContainText('核验所选年报');
  await expect(page.getByLabel('本页等待状态',{exact:true})).toContainText(/已等待 [1-9]\d* 秒/,{timeout:5000});
  await expect.poll(()=>!!saved,{timeout:120000}).toBe(true);
  expect(saved.status).toBe('awaiting_human_confirmation');expect(posts).toBe(1);
  await page.getByRole('button',{name:'停止本页等待',exact:true}).click();release();
  await expect(page.getByRole('alert').filter({hasText:'已停止本页等待'})).toBeVisible();
  await expect(page.getByRole('alert').filter({hasText:'已停止本页等待'})).toContainText('可能仍在执行');
  await page.reload();
  // The existing restoration effect reads the original operation automatically.
  // This is a GET; clicking a recovery button during that GET is unnecessary.
  await expect(page.getByRole('region',{name:'六项事实准备状态'})).toBeVisible();
  expect(posts).toBe(1);
  expect(reads.some(url=>url.endsWith(`/research/tasks/by-operation/${saved.operation_id}`))).toBe(true);
  const recovered=await (await page.request.get(`/api/research/tasks/by-operation/${saved.operation_id}`)).json();
  expect(recovered.task_id).toBe(saved.task_id);expect(recovered.revision).toBe(saved.revision);
  await page.screenshot({path:`${out}/operating-wait-restored.png`,fullPage:true});
  writeFileSync(`${out}/operating-wait-proof.json`,JSON.stringify({saved,recovered,posts,reads,automatic_replays:0,
    actual_http_sqlite:true,actual_model:false,actual_retrieval:false,simulated_test:true},null,2));
});
