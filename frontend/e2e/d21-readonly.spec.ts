import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const records = JSON.parse(readFileSync(process.env.D21_READONLY_RESULTS!,"utf8"));
for (const record of records) {
  test(`新进程只读 ${record.input.template} 完整经营结果`, async ({page}) => {
    await page.route("**/src/main.tsx*",(route) => route.fulfill({contentType:"text/javascript",body:'import "/tests/support/d20-entry.tsx";'}));
    let posts=0;page.on("request",(r) => {if(r.method()==="POST")posts++;});
    await page.goto("/research");
    await page.evaluate((t) => localStorage.setItem(`findoc:operating-identity:${t.input.first.company_id}`,JSON.stringify({operation_id:t.operation_id,task_id:t.task_id,revision:t.revision,unknown:false})),record);
    await page.goto(`/research?company=${record.input.first.company_id}&mode=operating`);
    await expect(page.getByRole("region",{name:"当前经营研究任务"})).toContainText("研究执行已完成");
    await expect(page.getByRole("region",{name:"有限经营研究结果"})).toContainText("待人工语义复核",{timeout:60000});
    await expect(page.locator(".operating-result-values")).toHaveCount(3);
    expect(posts).toBe(0);
    await page.screenshot({path:`${process.env.D21_ARTIFACT_DIR}/${record.input.template}-readonly-current.png`});
  });
}
