import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
export const root = process.env.FINDOC_D20_RUNTIME_ROOT!,
  out = process.env.D20_ARTIFACT_DIR!;
export const reports: {
  report_id: string;
  source: any;
  original_sha256: string;
}[] = JSON.parse(readFileSync(`${root}/manifest.json`, "utf8")).reports;
export const metrics = ["revenue", "net_profit_parent", "operating_cash_flow"];
export function report(key: string, year = 2025) {
  return reports.find((r) => r.report_id === `${key}-${year}`)!;
}
export function record(name: string, v: unknown) {
  writeFileSync(`${out}/${name}.json`, JSON.stringify(v, null, 2));
}
export async function harness(page: Page) {
  // D20 regression explicitly creates v1 tasks against the frozen legacy harness.
  // D21 real browser tests use their own harness and send v2 unchanged.
  await page.route("**/api/research/tasks", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON();
    delete body.run_version;
    delete body.parent_task_id;
    return route.continue({postData: JSON.stringify(body)});
  });
  await page.route("**/src/main.tsx*", (route) =>
    route.fulfill({
      contentType: "text/javascript",
      body: 'import "/tests/support/d20-entry.tsx";',
    }),
  );
}
export async function open(page: Page, key = "midea") {
  await page.goto(
    `/research?company=${report(key).source.company_id}&mode=operating`,
  );
  await expect(
    page.getByRole("button", { name: /单企业两期间变化/ }),
  ).toBeVisible();
}
export async function configure(
  page: Page,
  template = "company_period_change",
  key = "midea",
  year = 2025,
) {
  await page
    .getByLabel("first 企业", { exact: true })
    .selectOption(report(key).source.company_id);
  await page
    .getByRole("button", {
      name:
        template === "company_period_change"
          ? /单企业两期间变化/
          : /两企业同期间比较/,
    })
    .click();
  if (template !== "company_period_change")
    await page
      .getByLabel("second 企业", { exact: true })
      .selectOption(report("gree").source.company_id);
  await expect(page.getByLabel("first 期间")).toContainText(String(year));
  await page.getByLabel("first 期间").selectOption(String(year));
  if (template === "company_period_change")
    await page.getByLabel("second 期间").selectOption(String(year - 1));
  await page
    .getByLabel("first 年报")
    .selectOption(report(key, year).source.document_id);
  await page
    .getByLabel("second 年报")
    .selectOption(
      report(
        template === "company_period_change" ? key : "gree",
        template === "company_period_change" ? year - 1 : year,
      ).source.document_id,
    );
  for (const side of ["first", "second"]) {
    const label = page
      .getByText("来源与逐指标披露选择", { exact: true })
      .nth(side === "first" ? 0 : 1);
    await expect(label).toBeVisible();
    await label.click();
    for (const metric of metrics) {
      const select = page.getByLabel(`${side} ${metric} 披露`, { exact: true });
      await expect(select.locator("option")).toHaveCount(2);
      await select.selectOption({ index: 1 });
    }
    await label.click();
  }
  await expect(
    page.getByRole("button", { name: "创建服务端研究任务", exact: true }),
  ).toBeEnabled();
}
export async function create(page: Page) {
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/research/tasks") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "创建服务端研究任务", exact: true })
    .dblclick();
  const r = await response;
  expect(r.status()).toBe(200);
  const t = await r.json();
  await expect(
    page.getByRole("region", { name: "当前经营研究任务" }),
  ).toContainText("等待人工确认", { timeout: 60000 });
  return t;
}
export async function current(page: Page, t: any, expectView = true) {
  if (page.url() === "about:blank") await page.goto("/research");
  await page.evaluate(
    ({ company, t }) =>
      localStorage.setItem(
        `findoc:operating-identity:${company}`,
        JSON.stringify({
          operation_id: t.operation_id,
          task_id: t.task_id,
          revision: t.revision,
          unknown: false,
        }),
      ),
    { company: t.input.first.company_id, t },
  );
  await open(
    page,
    reports
      .find((r) => r.source.company_id === t.input.first.company_id)!
      .report_id.split("-")[0],
  );
  if (expectView)
    await expect(
      page.getByRole("region", { name: "当前经营研究任务" }),
    ).toContainText(`revision ${t.revision}`);
}
export async function accept(page: Page, r: (typeof reports)[number]) {
  const s = r.source;
  await page.goto(
    `/evidence?company=${s.company_id}&document=${s.document_id}&revision=${s.source_revision}`,
  );
  await expect(page.locator(".pdf-location")).toContainText("金额区域已核验", {
    timeout: 60000,
  });
  await page.getByRole("button", { name: "生成审阅快照" }).click();
  await page.getByRole("button", { name: "人工核对并确认" }).click();
  const modal = page.getByRole("dialog", { name: "人工核对确认" });
  await modal.getByLabel("我已逐项核对原 PDF，并明确接受本次审阅内容").check();
  await modal.getByRole("button", { name: "我已核对并接受" }).click();
  await expect(page.getByTestId("acceptance-result")).toContainText(
    "自动化模拟接受凭证",
    { timeout: 60000 },
  );
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/financial-facts/persisted") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "保存已接受财务事实" }).click();
  const saved = await response;
  expect(saved.status()).toBe(200);
  const group = await saved.json();
  expect(group.confirmation_kind).toBe("simulated_test");
  expect(group.production_calculable).toBe(false);
  await expect(page.getByTestId("fact-result")).toContainText("已确认财务事实");
  return group;
}
export function tasks(): any[] {
  return JSON.parse(readFileSync(`${out}/waiting-tasks.json`, "utf8"));
}
