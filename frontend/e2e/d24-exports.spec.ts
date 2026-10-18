import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
const proof = JSON.parse(readFileSync(process.env.D24_REPORT_PROOF!, "utf8"));
const dir = process.env.D24_ARTIFACT_DIR!;
const phase = process.env.D24_PHASE!;
for (const [index, c] of proof.cases.entries()) {
  test(`D24 actual download ${phase} ${c.title} ${c.task_id}`, async ({ page }) => {
    await page.setViewportSize({ width:[1024,1280,1440,1280][index],height:900 });
    await page.route("**/src/main.tsx*", r => r.fulfill({contentType:"text/javascript",body:'import "/tests/support/d20-entry.tsx";'}));
    const posts:string[]=[];
    page.on('request',r=>{if(r.method()==='POST')posts.push(r.url());});
    await page.goto(`/reports?report=${c.report_id}&revision=1`);
    const controls=page.getByRole('region',{name:'报告 Markdown 导出'});
    await expect(page.getByRole('article',{name:'已保存报告版本'})).toBeVisible();
    if(phase==='revoked') {
      await expect(controls).toContainText('已失效');
      await expect(controls.getByRole('button',{name:'下载 v1 · Markdown',exact:true})).toBeDisabled();
      const response=await page.request.get(`/api/reports/${c.report_id}/revisions/1/markdown`);
      expect(response.status()).toBe(409);
      writeFileSync(`${dir}/${phase}-${index}.json`,JSON.stringify({phase,case:c.title,blocked:true,status:response.status(),noPost:posts.length===0}));
      return;
    }
    const records=[];
    for(const revision of [1,2]) {
      await page.getByLabel('报告版本', { exact: true }).selectOption(String(revision));
      await expect(controls.getByRole('button')).toContainText(`下载 v${revision} · Markdown`);
      const responsePromise=page.waitForResponse(r=>r.url().endsWith(`/revisions/${revision}/markdown`));
      const downloadPromise=page.waitForEvent('download');
      await controls.getByRole('button',{name:`下载 v${revision} · Markdown`,exact:true}).dblclick();
      const response=await responsePromise;
      expect(response.status()).toBe(200);
      const download=await downloadPromise;
      expect(await download.failure()).toBeNull();
      expect(download.suggestedFilename()).toContain(`-${c.report_id}-v${revision}.md`);
      const target=`${dir}/${phase}-${index}-v${revision}.md`;
      await download.saveAs(target);
      const bytes=readFileSync(target),md=bytes.toString('utf8');
      const hash=createHash('sha256').update(bytes).digest('hex');
      expect(hash).toBe(response.headers()['x-markdown-sha256']);
      expect(response.headers()['x-report-payload-sha256']).toBe(c.versions[revision-1].payload_sha256);
      for(const f of c.facts) for(const k of ['raw_value','raw_unit','value_cny_yuan','disclosure_version','receipt_id']) expect(md).toContain(f[k]);
      for(const a of c.analysis) for(const k of ['absolute_formula_id','percentage_formula_id','absolute_expression','percentage_expression']) expect(md).toContain(a[k]);
      for(const heading of ['研究问题与范围','六项财务事实','三项确定性分析','经营年报原文与完整引用','模型解释','未解决问题','风险与限制','用户自行编辑的结论','证据与审计附录'])expect(md).toContain(heading);
      expect(md).toContain('simulated_test');expect(md).toContain('pending_semantic_review');
      if(revision===1)expect(md).not.toContain('用户结论仅作为待审断言');
      else expect(md).toContain('用户结论仅作为待审断言');
      if(phase==='restart')expect(bytes.equals(readFileSync(`${dir}/live-${index}-v${revision}.md`))).toBe(true);
      // Downloaded Markdown's generated source link opens the original PDF with fixed identities.
      const link=md.match(/\]\((\/api\/documents\/[^\n]+?)\)/)![1];
      const pdf=await page.request.get(link.split('#')[0]);
      expect(pdf.status()).toBe(200);expect((await pdf.body()).subarray(0,5).toString()).toBe('%PDF-');
      await expect(controls.getByRole('status')).toContainText('已交给浏览器下载');
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      records.push({revision,filename:download.suggestedFilename(),bytes:bytes.length,markdown_sha256:hash,payload_sha256:c.versions[revision-1].payload_sha256,pdfLinkOpened:true,restartEqual:phase==='restart',fileChecked:true});
    }
    await page.screenshot({path:`${dir}/${phase}-${index}.png`,fullPage:true});
    expect(posts).toHaveLength(0);
    writeFileSync(`${dir}/${phase}-${index}.json`,JSON.stringify({phase,case:c.title,downloads:records,noPost:true},null,2));
  });
}
for(const failure of ['network','http','wrong-revision','bad-sha','truncated','download-dispatch']) {
  test(`D24 download failure ${failure}`,async({page})=>{
    if(phase!=='live')test.skip();
    const c=proof.cases[0];
    await page.route("**/src/main.tsx*",r=>r.fulfill({contentType:'text/javascript',body:'import "/tests/support/d20-entry.tsx";'}));
    await page.goto(`/reports?report=${c.report_id}&revision=1`);
    const controls=page.getByRole('region',{name:'报告 Markdown 导出'});
    await expect(controls).toBeVisible();
    let downloads=0;page.on('download',()=>downloads++);
    if(failure==='download-dispatch')await page.evaluate(()=>{HTMLAnchorElement.prototype.click=function(){throw new Error('download_dispatch_failed');};});
    else await page.route('**/revisions/1/markdown',async r=>{
      if(failure==='network')return r.abort('failed');
      if(failure==='http')return r.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error_code:'source_changed'})});
      const response=await r.fetch();
      const headers={...response.headers()};
      if(failure==='wrong-revision')headers['x-report-revision']='2';
      if(failure==='bad-sha')headers['x-markdown-sha256']='f'.repeat(64);
      await r.fulfill({response,headers,...(failure==='truncated'?{body:'截断内容'}:{})});
    });
    await controls.getByRole('button',{name:'下载 v1 · Markdown',exact:true}).click();
    await expect(controls.getByRole('alert')).toContainText('失败');
    await expect(controls.getByRole('status')).toHaveCount(0);
    expect(downloads).toBe(0);
    await expect(controls.getByRole('button',{name:'下载 v1 · Markdown',exact:true})).toBeEnabled();
  });
}
test('D24 unsaved draft has no export entry and production refuses simulation',async({page})=>{
  if(phase!=='live')test.skip();
  await page.route("**/src/main.tsx*",r=>r.fulfill({contentType:'text/javascript',body:'import "/tests/support/d20-entry.tsx";'}));
  await page.goto('/reports'); await page.getByText('从已完成研究整理报告草稿', { exact: true }).click();
  await page.getByLabel('选择已完成研究').selectOption(proof.cases[0].task_id);
  await page.getByRole('button',{name:'生成草稿',exact:true}).click();
  await expect(page.getByRole('article',{name:'报告草稿预览'})).toBeVisible();
  await expect(page.getByRole('button',{name:'下载 v1 · Markdown',exact:true})).toHaveCount(0);
  await page.unroute('**/src/main.tsx*');
  await page.goto(`/reports?report=${proof.cases[0].report_id}&revision=1`);
  await expect(page.getByRole('alert').first()).toContainText('报告结构或研究身份不一致');
  await expect(page.getByRole('button',{name:'下载 v1 · Markdown',exact:true})).toHaveCount(0);
});
