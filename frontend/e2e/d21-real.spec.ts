import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
const root=process.env.FINDOC_D21_RUNTIME_ROOT!, out=process.env.D21_ARTIFACT_DIR!;
const reports=JSON.parse(readFileSync(`${root}/manifest.json`,"utf8")).reports;
function report(key:string,year:number) {return reports.find((r:any) => r.report_id===`${key}-${year}`);}
async function harness(page:any) {
  await page.route("**/src/main.tsx*", (route:any) => route.fulfill({contentType:"text/javascript",body:'import "/tests/support/d20-entry.tsx";'}));
}
for (const template of ["company_period_change","company_same_period_comparison"]) {
  test(`真实模型 ${template}：创建等待、恢复、来源、持久结果与刷新零POST`, async ({page}) => {
    await harness(page);
    await page.goto(`/research?company=${report("midea",2025).source.company_id}&mode=operating`);
    await page.getByRole("button",{name:template==="company_period_change"?/单企业两期间变化/:/两企业同期间比较/}).click();
    await page.getByLabel("first 企业",{exact:true}).selectOption(report("midea",2025).source.company_id);
    if(template!=="company_period_change") await page.getByLabel("second 企业",{exact:true}).selectOption(report("gree",2025).source.company_id);
    await page.getByLabel("first 期间").selectOption("2025");
    if(template==="company_period_change") await page.getByLabel("second 期间").selectOption("2024");
    await page.getByLabel("first 年报").selectOption(report("midea",2025).source.document_id);
    await page.getByLabel("second 年报").selectOption(report(template==="company_period_change"?"midea":"gree",template==="company_period_change"?2024:2025).source.document_id);
    for(const side of ["first","second"]) {
      const details=page.getByText("来源与逐指标披露选择",{exact:true}).nth(side==="first"?0:1);
      await details.click();
      for(const metric of ["revenue","net_profit_parent","operating_cash_flow"]) {
        const select=page.getByLabel(`${side} ${metric} 披露`,{exact:true});
        await expect(select.locator("option")).toHaveCount(2);await select.selectOption({index:1});
      }
      await details.click();
    }
    const waitResponse=page.waitForResponse((r) => r.url().endsWith("/research/tasks")&&r.request().method()==="POST");
    await page.getByRole("button",{name:"创建服务端研究任务",exact:true}).dblclick();
    const wait=await (await waitResponse).json();
    expect(wait.graph_version).toBe("d21-operating-graph-v2");expect(wait.status).toBe("awaiting_human_confirmation");
    const resumeButton=page.getByRole("button",{name:"刷新 revision 并恢复研究"});
    await expect(resumeButton).toBeEnabled({timeout:60000});
    const response=page.waitForResponse((r) => r.url().endsWith(`/research/tasks/${wait.task_id}/resume`)&&r.request().method()==="POST");
    await resumeButton.dblclick();
    const r=await response, result=await r.json();
    expect(r.status()).toBe(200);expect(result.status).toBe("completed");
    expect(result.budget.used.model_calls).toBeGreaterThanOrEqual(1);
    expect(result.final_research_content.test_mode).toBe("simulated_test");
    await expect(page.getByRole("region",{name:"有限经营研究结果"})).toBeVisible({timeout:60000});
    await expect(page.locator(".operating-result-values")).toHaveCount(3);
    const resultRegion=page.getByRole("region",{name:"有限经营研究结果"});
    await expect(resultRegion).toContainText("待人工语义复核");
    await resultRegion.scrollIntoViewIfNeeded();
    await page.screenshot({path:`${out}/${template}-result-1440.png`});
    const original=resultRegion.getByText("展开保存的完整原文与来源",{exact:true}).first();
    await original.click();
    const link=resultRegion.getByRole("link",{name:/打开经营原文 PDF/}).first();
    const href=await link.getAttribute("href");expect(href).toContain("#page=");
    const pdf=await page.request.get(href!.split("#")[0]);expect(pdf.status()).toBe(200);
    const popup=page.waitForEvent("popup");await link.click();const tab=await popup;await tab.waitForLoadState("domcontentloaded");await tab.close();
    let posts=0;page.on("request",(r) => {if(r.method()==="POST")posts++;});
    await page.reload();
    await expect(page.getByRole("region",{name:"有限经营研究结果"})).toBeVisible({timeout:60000});expect(posts).toBe(0);
    for(const width of [1280,1024]) {
      await page.setViewportSize({width,height:900});
      expect(await page.evaluate(() => document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
      await page.screenshot({path:`${out}/${template}-workbench-${width}.png`});
    }
    writeFileSync(`${out}/${template}-proof.json`,JSON.stringify({result,pdf_status:pdf.status(),refresh_post_count:posts,actual_bge:true,actual_milvus:true,actual_llm:true,simulated_test:true,human_acceptance:0},null,2));
  });
}
