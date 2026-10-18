import { expect, test } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { createHash, randomUUID } from "node:crypto";
const seed = JSON.parse(readFileSync("../product/validation/d17-real-save.json", "utf8"));
const saved = seed.runs[0].result;
const company = seed.reports.find((r: any) => r.report_id === "midea-2025").source.company_id;
const other = seed.reports.find((r: any) => r.report_id === "gree-2025").source.company_id;
const out = process.env.D17_ARTIFACT_DIR!;
async function panel(page: any) {
  await page.goto(`/research?company=${company}`);
  const p = page.getByRole("region", { name: "研究资料选择" });
  await expect(p.getByLabel(/美的集团股份有限公司 · 2025/)).toBeEnabled();
  return p;
}
async function allHistory(page: any) {
  const list = page.getByRole("region", { name: "研究历史列表" });
  await expect(list.getByRole("listitem").first()).toBeVisible();
  while (await list.getByRole("button", { name: "加载更多研究" }).count()) {
    const before = await list.getByRole("listitem").count();
    await list.getByRole("button", { name: "加载更多研究" }).click();
    await expect.poll(() => list.getByRole("listitem").count()).toBeGreaterThan(before);
  }
  return list;
}
async function begin(page: any) {
  const p = await panel(page);
  await p.getByLabel(/美的集团股份有限公司 · 2025/).check();
  await p.getByLabel("研究问题").fill("明确的受控浏览器问题");
  return p;
}
test("restart history restores all persisted states, original content and real PDF without POST", async ({ page }) => {
  let posts = 0; page.on("request", r => { if (r.method() === "POST") posts++; });
  const p = await panel(page);
  const list = await allHistory(page);
  await expect(list.getByRole("listitem").first()).toBeVisible();
  await list.screenshot({ path: `${out}/history-list.png` });
  const records: any[] = [];
  for (const entry of seed.runs) {
    const record = entry.result;
    // Distinguish duplicate question summaries using status text in the same list row.
    const label = { answered: "已保存回答", refused: "已保存拒答", system_error: "已保存系统错误" }[record.status as "answered"];
    const row = list.getByRole("listitem").filter({ hasText: label }).filter({ hasText: record.query.slice(0, 80) });
    await row.first().getByRole("button").click();
    const detail = p.getByRole("region", { name: "研究历史详情" });
    await expect(detail).toContainText(record.run_id);
    if (record.status === "answered") {
      await expect(detail.locator("details").first()).toContainText(record.result.content);
      const links = detail.getByRole("link", { name: /打开原 PDF/ });
      expect(await links.count()).toBe(record.result.citations.length);
      const href = await links.first().getAttribute("href");
      const pdf = await page.request.get(href!.split("#")[0]); expect(pdf.ok()).toBe(true);
      expect(createHash("sha256").update(await pdf.body()).digest("hex")).toBe(record.result.citations[0].content_sha256);
      const popupEvent = page.waitForEvent("popup"); await links.first().click(); const popup = await popupEvent;
      await popup.waitForURL(/\/file\?/, { waitUntil: "commit" });
      await popup.screenshot({ path: `${out}/history-pdf.png` }); await popup.close();
      for (const width of [1440, 1280, 1024]) {
        await page.setViewportSize({ width, height: 960 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await detail.scrollIntoViewIfNeeded(); await page.screenshot({ path: `${out}/history-answered-${width}.png` });
      }
    } else {
      await expect(detail.getByRole("link", { name: /打开原 PDF/ })).toHaveCount(0);
      await detail.scrollIntoViewIfNeeded(); await page.screenshot({ path: `${out}/history-${record.status}.png` });
    }
    records.push({ run_id: record.run_id, state: record.status });
  }
  await page.reload();
  await expect(page.getByRole("region", { name: "研究历史列表" })).toContainText("已保存回答");
  expect(posts).toBe(0);
  writeFileSync(`${out}/restart-browser-proof.json`, JSON.stringify({ records, post_calls: posts, pdf_sha_verified: true }, null, 2));
});

test("unknown POST response uses known operation GET, including page refresh, with no replay", async ({ page }) => {
  let posts = 0; let operation = ""; let reads = 0;
  await page.route("**/api/research/runs", async route => { posts++; operation = route.request().postDataJSON().operation_id; await route.abort("failed"); });
  await page.route("**/api/research/runs/by-operation/*", route => { reads++; return route.fulfill({ json: { ...saved, operation_id: operation } }); });
  let p = await begin(page); await p.getByRole("button", { name: "开始研究", exact: true }).click();
  await expect(p.getByRole("alert")).toContainText("执行状态未知");
  await page.reload(); p = page.getByRole("region", { name: "研究资料选择" });
  await p.getByRole("button", { name: "按操作身份恢复" }).click();
  await expect(p.getByRole("region", { name: "研究历史详情" })).toContainText(saved.run_id);
  expect(posts).toBe(1); expect(reads).toBe(1);
});

test("save failure, history read failure and source expiration are explicit", async ({ page }) => {
  await page.route("**/api/research/runs", route => route.fulfill({ status: 503, json: { detail: "research_save_failed" } }));
  const p = await begin(page); await p.getByRole("button", { name: "开始研究", exact: true }).click();
  await expect(p.getByRole("alert")).toContainText("保存失败");
  await expect(p.getByRole("region", { name: "有证据的回答" })).toHaveCount(0);
  await page.route("**/api/research/runs?*", route => route.fulfill({ status: 503, json: { detail: "history_read_failed" } }));
  await p.getByRole("button", { name: "刷新研究历史" }).click();
  await expect(p.getByRole("region", { name: "研究历史列表" })).toContainText("历史读取失败");
  await page.route("**/api/research/runs/by-operation/*", route => route.fulfill({ json: { ...saved,
    operation_id: route.request().url().split("/").pop(), source_states: saved.source_states.map((s: any) => ({ ...s, status: "expired" })) } }));
  await p.getByRole("button", { name: "按操作身份恢复" }).click();
  await expect(p.getByRole("region", { name: "研究历史详情" })).toContainText("来源已过期");
  await expect(p.getByRole("link", { name: /打开原 PDF/ })).toHaveCount(0);
  await page.screenshot({ path: `${out}/history-expired-controlled.png`, fullPage: true });
});

test("late POST and detail responses cannot cross company, history or selection changes", async ({ page }) => {
  let release!: () => void; const gate = new Promise<void>(r => { release = r; });
  await page.route("**/api/research/runs", async route => {
    const op = route.request().postDataJSON().operation_id; await gate;
    await route.fulfill({ json: { ...saved, operation_id: op } }).catch(() => {});
  });
  const p = await begin(page); await p.getByRole("button", { name: "开始研究", exact: true }).click();
  await expect(p.getByRole("button", { name: "正在读取或研究…" })).toBeDisabled();
  await p.getByLabel(/美的集团股份有限公司 · 2025/).uncheck();
  await page.getByRole("combobox", { name: "当前企业" }).selectOption(other);
  release();
  await expect(p.getByRole("region", { name: "研究历史详情" })).toHaveCount(0);
  await page.unrouteAll({ behavior: "ignoreErrors" });
  // A slow historical detail is also revoked when another history entry is opened.
  await page.goto(`/research?company=${company}`);
  let releaseDetail!: () => void; const delay = new Promise<void>(r => { releaseDetail = r; });
  await page.route(`**/api/research/runs/${saved.run_id}`, async route => { await delay; await route.fulfill({ json: saved }).catch(() => {}); });
  const list = await allHistory(page);
  await list.getByRole("listitem").filter({ hasText: "已保存回答" }).filter({ hasText: saved.query }).first().getByRole("button").click();
  await list.getByRole("listitem").filter({ hasText: "已保存拒答" }).first().getByRole("button").click();
  await expect(page.getByRole("region", { name: "研究历史详情" })).toContainText("正常拒答");
  releaseDetail();
  await expect(page.getByRole("region", { name: "有证据的回答" })).toHaveCount(0);
  await page.unrouteAll({ behavior: "ignoreErrors" });
});

test("bounded pagination loads more and malformed detail never becomes answer", async ({ page }) => {
  const one = { ...saved, run_id: randomUUID() }; const two = { ...saved, run_id: randomUUID(), query: "第二页研究" };
  const calls: string[] = [];
  await page.route("**/api/research/runs?*", route => {
    calls.push(route.request().url()); const next = new URL(route.request().url()).searchParams.has("cursor");
    return route.fulfill({ json: { schema_version: "research-history-v1", items: [next ? two : one], next_cursor: next ? null : "opaque-controlled" } });
  });
  const p = await panel(page); await p.getByRole("button", { name: "加载更多研究" }).click();
  await expect(p.getByRole("region", { name: "研究历史列表" }).getByRole("listitem")).toHaveCount(2);
  expect(calls[1]).toContain("cursor=opaque-controlled");
  await page.route(`**/api/research/runs/${two.run_id}`, route => route.fulfill({ json: { ...two, result: { ...two.result, outcome: "refused" } } }));
  await p.getByRole("button", { name: "第二页研究", exact: true }).click();
  await expect(p.getByRole("alert")).toContainText("读取失败或结果损坏");
  await expect(p.getByRole("region", { name: "有证据的回答" })).toHaveCount(0);
});
