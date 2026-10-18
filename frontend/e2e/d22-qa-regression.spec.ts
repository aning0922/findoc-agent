import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { createHash, randomUUID } from "node:crypto";
const root = readFileSync("../data/30d-foundation/d22-qa-runtime-path.txt", "utf8").trim();
const manifest = JSON.parse(readFileSync(`${root}/manifest.json`, "utf8"));
const report = manifest.reports.find((r: any) => r.report_id === "midea-2025");
const company = report.source.company_id;
const other = manifest.reports.find((r: any) => r.report_id === "gree-2025").source.company_id;
// D22 regression of D16 behaviors through the D17 persisted-run HTTP contract.
// Responses are controlled protocol substitutes; original PDFs remain real.
test.beforeEach(async ({page})=>{
  await page.route("**/api/research/runs?**",r=>r.fulfill({json:{schema_version:"research-history-v1",items:[],next_cursor:null}}));
});
async function fulfillRun(route:any, result:any) {
  const request=route.request().postDataJSON();
  return route.fulfill({json:{schema_version:"research-run-v1",run_id:randomUUID(),operation_id:request.operation_id,query:request.query,document_ids:request.document_ids,documents:result.documents,status:result.outcome,created_at:"2026-10-10T00:00:00Z",ended_at:"2026-10-10T00:00:01Z",result,historical_snapshot:true,integrity_sha256:"e".repeat(64),source_states:result.documents.map((d:any)=>({document_id:d.document_id,source_revision:d.source_revision,status:"current_at_read"}))}});
}
async function select(page: any) {
  await page.goto(`/research?company=${company}&mode=qa`);
  const panel = page.getByRole("region", { name: "研究资料选择" });
  await expect(panel.getByLabel(/美的集团股份有限公司 · 2025/)).toBeEnabled({ timeout: 60_000 });
  await panel.getByLabel(/美的集团股份有限公司 · 2025/).check();
  await panel.getByLabel("研究问题").fill("请摘录公司主营业务原文");
  return panel;
}
function response() {
  const s = report.source;
  return { schema_version: "research-answer-v1", selection_id: "a".repeat(64), outcome: "answered",
    content: `${s.report_year}年报《midea-2025.pdf》原文：\n浏览器受控协议测试原文\n[1]`, answer_mode:"verified_excerpts", human_review:"pending", documents: [s],
    citations: [{ number: 1, ...s, chunk_id: "ui-controlled", physical_page: 1,
      source_file: "midea-2025.pdf", text: "浏览器受控协议测试原文", kind: "paragraph" }] };
}
test("explicit research, verified result and pinned real PDF; selection clears result", async ({ page }) => {
  const posts: string[] = [];
  page.on("request", r => { if (r.url().endsWith("/research/runs")) posts.push(r.method()); });
  await page.route("**/api/research/runs", route => fulfillRun(route, response()));
  const panel = await select(page);
  expect(posts).toEqual([]);
  await panel.getByRole("button", { name: "开始研究", exact: true }).click();
  await expect(panel.getByRole("region", { name: "有证据的回答" })).toBeVisible();
  expect(posts).toEqual(["POST"]);
  const href = await panel.getByRole("link", { name: /打开原 PDF/ }).getAttribute("href");
  expect(href).toContain(`source_revision=${report.source.source_revision}`);
  expect(href).toContain("#page=1");
  const pdf = await page.request.get(href!.split("#")[0]);
  expect(pdf.ok()).toBe(true);
  expect(createHash("sha256").update(await pdf.body()).digest("hex")).toBe(report.source.content_sha256);
  for (const width of [1440,1280,1024]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `../data/30d-foundation/d22-browser/d22-qa-screenshots/qa-${width}.png` });
  }
  await panel.getByLabel(/美的集团股份有限公司 · 2025/).uncheck();
  await expect(panel.getByRole("region", { name: "有证据的回答" })).toHaveCount(0);
});

test("normal refusal and system failure have distinct empty results", async ({ page }) => {
  await page.route("**/api/research/runs", route => fulfillRun(route, { ...response(), outcome: "refused", reason: "insufficient_evidence", content: "", citations: [] }));
  const panel = await select(page);
  await panel.getByRole("button", { name: "开始研究", exact: true }).click();
  await expect(panel.getByText(/正常拒答/)).toBeVisible();
  await page.unroute("**/api/research/runs");
  await page.route("**/api/research/runs", route => route.fulfill({ status: 503,
    json: { ...response(), outcome: "system_error", error_code: "llm_error", content: "", citations: [] } }));
  await panel.getByRole("button", { name: "开始研究", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("服务未能确认研究结果");
  await expect(panel.getByRole("link", { name: /打开原 PDF/ })).toHaveCount(0);
});

test("network outcome unknown never retries POST automatically", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/research/runs", route => { requests++; return route.abort("failed"); });
  const panel = await select(page);
  await panel.getByRole("button", { name: "开始研究", exact: true }).click();
  await expect(panel.getByRole("alert")).toContainText("执行状态未知");
  await expect(panel.getByRole("button", { name: "开始研究", exact: true })).toBeDisabled();
  await panel.getByRole("button", { name: "刷新资料状态" }).focus();
  expect(requests).toBe(1);
});

test("late answer cannot appear after company or document selection changes", async ({ page }) => {
  let release!: () => void;
  const waiting = new Promise<void>(r => { release = r; });
  await page.route("**/api/research/runs", async route => {
    await waiting; await fulfillRun(route,response()).catch(() => {});
  });
  const panel = await select(page);
  await panel.getByRole("button", { name: "开始研究", exact: true }).click();
  await expect(panel.getByRole("button", { name: "正在读取或研究…" })).toBeDisabled();
  await page.getByRole("combobox", { name: "当前企业" }).selectOption(other);
  release();
  await expect(panel.getByText("已选择 0 / 4 份")).toBeVisible({ timeout: 60_000 });
  await expect(panel.getByRole("region", { name: "有证据的回答" })).toHaveCount(0);
  await page.unrouteAll({ behavior: "ignoreErrors" });
});
