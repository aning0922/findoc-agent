import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
const proof = JSON.parse(readFileSync(process.env.D23_REPORT_PROOF!, "utf8"));
for (const [index, c] of proof.cases.entries()) {
  test(`D23 save version history ${c.title} ${c.task_id}`, async ({ page }) => {
    await page.setViewportSize({ width: [1024,1280,1440,1280][index], height:900 });
    await page.route("**/src/main.tsx*", r => r.fulfill({ contentType:"text/javascript", body:'import "/tests/support/d20-entry.tsx";' }));
    const posts: string[] = [];
    page.on("request", r => { if (r.method()==="POST") posts.push(r.url()); });
    await page.goto('/reports'); await page.getByText('从已完成研究整理报告草稿', { exact: true }).click();
    await page.getByLabel('选择已完成研究').selectOption(c.task_id);
    expect(posts).toHaveLength(0);
    await page.getByRole('button',{name:'生成草稿',exact:true}).click();
    await expect(page.getByRole('article',{name:'报告草稿预览'})).toBeVisible();
    const controls=page.getByRole('region',{name:'编辑报告'});
    await controls.getByLabel('用户结论 1（待人工语义审阅）').fill('用户初版结论，未验证经营归因。');
    const responsePromise=page.waitForResponse(r=>r.request().method()==='POST' && r.url().endsWith('/api/reports'));
    await controls.getByRole('button',{name:'保存第 1 版',exact:true}).dblclick();
    const saved=await (await responsePromise).json();
    await expect(page).toHaveURL(new RegExp(`report=${saved.report.report_id}&revision=1`));
    expect(posts.filter(url=>url.endsWith('/api/reports'))).toHaveLength(1);

    const report=page.getByRole('article',{name:'已保存报告版本'});
    await expect(report).toBeVisible();
    await expect(report).toContainText('simulated_test');
    await expect(report).toContainText('用户结论 · 待人工语义审阅');
    for (const f of c.facts) { await expect(report.locator(`[data-fact-id="${f.fact_id}"] data`)).toHaveAttribute('value', f.value_cny_yuan); await expect(report.locator(`[data-fact-id="${f.fact_id}"] data`)).toHaveText(f.value_cny_yuan.replace(/\B(?=(\d{3})+(?!\d))/g, ',')); }
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.getByRole('button',{name:'编辑为新版本',exact:true}).click();
    await page.getByLabel('报告标题').fill('用户修订 · '+c.title);
    await page.getByLabel('用户结论 1（待人工语义审阅）').fill('修订结论仍为待审断言。');
    await page.getByRole('button',{name:'保存为 v2',exact:true}).click();
    await expect(report.getByRole('heading',{name:'用户修订 · '+c.title,exact:true})).toBeVisible();
    await expect(report).toContainText('父版本 1');
    await page.getByLabel('报告版本', { exact: true }).selectOption('1');
    await expect(report.getByRole('heading',{name:c.title,exact:true})).toBeVisible();
    await expect(report).toContainText('用户初版结论，未验证经营归因。');
    await expect(page.getByLabel('报告标题')).toHaveCount(0);
    await expect(page.getByRole('button',{name:'打开最新版本后编辑',exact:true})).toBeVisible();
    await page.screenshot({path:`${process.env.D23_ARTIFACT_DIR}/${c.task_id}-saved-v1.png`,fullPage:true});
    const before=posts.length;
    await page.reload(); await expect(report).toBeVisible(); expect(posts).toHaveLength(before);
    writeFileSync(`${process.env.D23_ARTIFACT_DIR}/${c.task_id}-saved.json`,JSON.stringify(saved));
  });
}

test('D23 lost response locks POST and operation GET recovers across refresh',async({page})=>{
  const c=proof.cases[0];
  await page.route("**/src/main.tsx*",r=>r.fulfill({contentType:'text/javascript',body:'import "/tests/support/d20-entry.tsx";'}));
  await page.goto('/reports'); await page.getByText('从已完成研究整理报告草稿', { exact: true }).click(); await page.getByLabel('选择已完成研究').selectOption(c.task_id);
  await page.getByRole('button',{name:'生成草稿',exact:true}).click();
  let body: { operation_id:string } | undefined;
  await page.route('**/api/reports',async route=>{
    if(route.request().method()!=='POST') return route.continue();
    body=route.request().postDataJSON();const response=await route.fetch();expect(response.status()).toBe(200);await route.abort('failed');
  });
  let posts=0;page.on('request',r=>{if(r.method()==='POST' && r.url().endsWith('/api/reports'))posts++;});
  await page.getByRole('button',{name:'保存第 1 版',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('保存结果未知');
  await expect(page.getByRole('button',{name:'保存第 1 版',exact:true})).toBeDisabled();
  await page.reload();
  await expect(page.getByLabel('按 operation 查询')).toHaveValue(body!.operation_id);
  await page.getByRole('button',{name:'查询历史操作（GET）',exact:true}).click();
  await expect(page.getByRole('article',{name:'已保存报告版本'})).toBeVisible();
  expect(posts).toBe(1);
});

test('D23 production UI rejects simulated persisted history',async({page})=>{
  const c=proof.cases[0];const saved=JSON.parse(readFileSync(`${process.env.D23_ARTIFACT_DIR}/${c.task_id}-saved.json`,'utf8'));
  await page.goto(`/reports?report=${saved.report.report_id}&revision=1`);
  await expect(page.getByRole('alert')).toContainText('报告结构或研究身份不一致');
  await expect(page.getByRole('article',{name:'已保存报告版本'})).toHaveCount(0);
});
