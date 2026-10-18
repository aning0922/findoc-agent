import { test,expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
const proof=JSON.parse(readFileSync(process.env.D23_REPORT_PROOF!,'utf8'));
for(const c of proof.cases) {
  test(`D23 ${process.env.D23_PHASE} readonly ${c.title}`,async({page})=>{
    const saved=JSON.parse(readFileSync(`${process.env.D23_ARTIFACT_DIR}/${c.task_id}-saved.json`,'utf8'));
    await page.route('**/src/main.tsx*',r=>r.fulfill({contentType:'text/javascript',body:'import "/tests/support/d20-entry.tsx";'}));
    const writes:string[]=[];page.on('request',r=>{if(['POST','PATCH','PUT','DELETE'].includes(r.method()))writes.push(r.url());});
    await page.goto(`/reports?report=${saved.report.report_id}&revision=1`);
    const report=page.getByRole('article',{name:'已保存报告版本'});await expect(report).toBeVisible();
    await expect(report).toContainText('simulated_test');
    for(const f of c.facts)await expect(report).toContainText(f.value_cny_yuan);
    if(process.env.D23_PHASE==='invalidated') {
      await expect(report).toContainText('已失效，仅供历史审计');
      await expect(page.getByLabel('报告标题')).toHaveCount(0);
      await expect(page.getByRole('button',{name:'编辑为新版本'})).toHaveCount(0);
      await expect(page.getByRole('button',{name:'下载 v1 · Markdown'})).toBeDisabled();
    }
    await page.getByLabel('报告版本', { exact: true }).selectOption('2');
    await expect(report.getByRole('heading',{name:'用户修订 · '+c.title,exact:true})).toBeVisible();
    await expect(report).toContainText('原系统标题');
    await page.reload();await expect(report).toBeVisible();expect(writes).toHaveLength(0);
    await page.screenshot({path:`${process.env.D23_ARTIFACT_DIR}/${c.task_id}-${process.env.D23_PHASE}.png`,fullPage:true});
  });
}
