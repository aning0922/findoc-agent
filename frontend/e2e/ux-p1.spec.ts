import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { verifyIntegratedQA } from "../tests/support/s6-qa-journey.ts";
import { verifyReportJourney } from "../tests/support/d24-ux-report-journey.ts";
const sources = JSON.parse(readFileSync(process.env.UX_SOURCE_FILE!, "utf8"));
const out = process.env.UX_ARTIFACT_DIR!;
const live = process.env.FINDOC_UX_LIVE === "1";
const metrics = ["revenue", "net_profit_parent", "operating_cash_flow"];
const names = ["营业收入", "归母净利润", "经营活动现金流量净额"];
function dbFingerprint() {
  return ["documents.db", "documents.db-wal"].map((file) => {
    const path = `${process.env.FINDOC_UX_RUNTIME_ROOT}/${file}`;
    return existsSync(path)
      ? createHash("sha256").update(readFileSync(path)).digest("hex")
      : null;
  });
}
let companies: any[], documents: any[];
test.describe.configure({ mode: "serial" });
async function catalog(page: Page) {
  companies = await (await page.request.get("/api/companies")).json();
  const rows = await (await page.request.get("/api/research/sources")).json();
  documents = rows.documents;
}
function company(code: string) {
  return companies.find(
    (c) =>
      c.security_code === code ||
      c.security_code === (code === "000333" ? "MIDEA" : "GREE"),
  ).company_id;
}
function docId(code: string, year: number) {
  return documents.find(
    (d) => d.company_id === company(code) && d.report_year === year,
  ).document_id;
}
async function harness(page: Page) {
  await page.route("**/src/main.tsx*", (route) =>
    route.fulfill({
      contentType: "text/javascript",
      body: 'import "/tests/support/d20-entry.tsx";',
    }),
  );
}
async function waitPdf(page: Page) {
  const reader = page.locator(".pdf-scroll").first();
  if (await reader.isVisible()) {
    await expect(page.locator(".pdf-sheet canvas").first()).toBeVisible({
      timeout: 30000,
    });
    await expect(page.locator(".pdf-location").first()).not.toContainText(
      "正在渲染",
      { timeout: 30000 },
    );
    await expect(page.locator(".evidence-excerpt")).not.toContainText("读取中", { timeout: 30000 });
    await expect(page.locator(".evidence-excerpt")).not.toContainText("正在核验", { timeout: 30000 });
  }
}
async function screenshots(page: Page, name: string) {
  await expect(page.locator("main")).toBeVisible();
  const audits: any[] = [];
  for (const width of [1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    await waitPdf(page);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    const audit = await page.evaluate(() => {
      const rgb = (s: string) => {
        const n = s.match(/[\d.]+/g)?.map(Number) || [];
        return [n[0] || 0, n[1] || 0, n[2] || 0, n.length > 3 ? n[3] : 1];
      };
      const blend = (a: number[], b: number[]) =>
        [0, 1, 2].map((i) => a[i] * a[3] + b[i] * (1 - a[3]));
      const lum = (c: number[]) =>
        c
          .slice(0, 3)
          .map((x) => x / 255)
          .map((x) => (x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4))
          .reduce((a, x, i) => a + x * [0.2126, 0.7152, 0.0722][i], 0);
      const root = window.document.querySelector("main")!;
      const walker = window.document.createTreeWalker(
          root,
          NodeFilter.SHOW_TEXT,
        ),
        rows: any[] = [];
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const text = node.textContent?.trim(),
          el = node.parentElement;
        if (
          !text ||
          !el ||
          el.closest(
            "script, style, option, button:disabled, input:disabled, select:disabled",
          )
        )
          continue;
        const rect = el.getBoundingClientRect(),
          style = getComputedStyle(el);
        if (
          !rect.width ||
          !rect.height ||
          rect.bottom <= 0 ||
          rect.top >= innerHeight ||
          rect.right <= 0 ||
          rect.left >= innerWidth ||
          style.visibility !== "visible"
        )
          continue;
        let opacity = 1,
          bg = [255, 255, 255],
          chain: HTMLElement[] = [];
        for (let p: HTMLElement | null = el; p; p = p.parentElement)
          chain.unshift(p);
        for (const p of chain) {
          const s = getComputedStyle(p);
          opacity *= Number(s.opacity);
          bg = blend(rgb(s.backgroundColor), bg);
        }
        const fg = rgb(style.color);
        fg[3] *= opacity;
        const a = lum(blend(fg, bg)),
          b = lum(bg),
          contrast = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        rows.push({
          text: text.slice(0, 90),
          color: style.color,
          background: bg,
          font: style.fontSize,
          line_height: style.lineHeight,
          contrast,
        });
      }
      return {
        nodes: rows.length,
        minimum: rows.length ? Math.min(...rows.map((r) => r.contrast)) : null,
        failures: rows.filter((r) => r.contrast < 4.5),
        rows,
      };
    });
    audits.push({ name, width, ...audit });
    await page.screenshot({ path: `${out}/${name}-${width}.png` });
  }
  writeFileSync(
    `${out}/${name}-readability.json`,
    JSON.stringify(audits, null, 2),
  );
  expect(audits.flatMap((a) => a.failures)).toEqual([]);
  const cdp = await page.context().newCDPSession(page);
  const zoomProof: any[] = [];
  for (const physicalWidth of [1440, 1280, 1024]) {
    await cdp.send("Emulation.setDeviceMetricsOverride", {
      width: physicalWidth / 2,
      height: 450,
      deviceScaleFactor: 2,
      mobile: false,
    });
    await waitPdf(page);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    ).toBe(true);
    const metrics = await page.evaluate(() => ({
      width: innerWidth,
      height: innerHeight,
      dpr: devicePixelRatio,
    }));
    expect(metrics).toEqual({ width: physicalWidth / 2, height: 450, dpr: 2 });
    const capture = await cdp.send("Page.captureScreenshot", {
      format: "png",
      captureBeyondViewport: false,
    });
    const bytes = Buffer.from(capture.data, "base64");
    expect(bytes.readUInt32BE(16)).toBe(physicalWidth);
    expect(bytes.readUInt32BE(20)).toBe(900);
    writeFileSync(`${out}/${name}-${physicalWidth}-200pct.png`, bytes);
    zoomProof.push({
      physical_width: physicalWidth,
      ...metrics,
      png_width: bytes.readUInt32BE(16),
      png_height: bytes.readUInt32BE(20),
    });
  }
  writeFileSync(
    `${out}/${name}-zoom-proof.json`,
    JSON.stringify(zoomProof, null, 2),
  );
  await cdp.send("Emulation.clearDeviceMetricsOverride");
  await cdp.detach();
  await page.setViewportSize({ width: 1440, height: 900 });
}
async function configure(page: Page, comparison = false) {
  await page.goto(
    `/research?company=${company("000333")}&mode=operating&new=1`,
  );
  await page
    .getByRole("button", {
      name: comparison ? /两企业同期间比较/ : /单企业两期间变化/,
    })
    .click();
  if (comparison)
    await page
      .getByLabel("second 企业", { exact: true })
      .selectOption(company("000651"));
  await page.getByLabel("first 期间", { exact: true }).selectOption("2025");
  if (!comparison)
    await page.getByLabel("second 期间", { exact: true }).selectOption("2024");
  await page
    .getByRole("button", { name: "下一步：准备财报", exact: true })
    .click();
  await page
    .getByLabel("first 年报", { exact: true })
    .selectOption(docId("000333", 2025));
  // Deliberately choose the prior-year column of the SAME 2025 PDF.
  await page
    .getByLabel("second 年报", { exact: true })
    .selectOption(docId(comparison ? "000651" : "000333", 2025));
  await page
    .getByRole("button", { name: "下一步：确认来源", exact: true })
    .click();
  for (const side of ['first', 'second']) {
    const group = page.locator('.operating-side').nth(side === 'first' ? 0 : 1);
    await group.getByRole('button', { name: '采用这组三项来源', exact: true }).click();
    await expect(group.locator('select[aria-label$="披露"]')).toHaveCount(0);
  }
  await expect(
    page.getByRole("button", { name: "创建研究，开始核对数据" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "开始经营研究", exact: true }),
  ).toHaveCount(0);
}
async function start(page: Page) {
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/research/tasks") &&
      r.request().method() === "POST",
    { timeout: 180000 },
  );
  await page.getByRole("button", { name: "创建研究，开始核对数据" }).dblclick();
  const task = await (await response).json();
  expect(task.status).toBe("awaiting_human_confirmation");
  for (const side of ["first", "second"])
    expect(
      task.input[side].choices.every(
        (c: any) => c.fact_id === null && c.fact_set_id === null,
      ),
    ).toBe(true);
  await expect(
    page.getByRole("region", { name: "六项事实准备状态" }),
  ).toBeVisible();
  return task;
}
async function review(page: Page, side: string, year: number) {
  await page
    .locator(`.fact-group[data-side="${side}"] .fact-group-actions`)
    .getByRole("link", { name: /核对/ })
    .click();
  await expect(
    page.getByRole("heading", { name: `核对 ${year} 年财务 · 共 3 项`, exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("review-candidate")).toHaveCount(3);
  await expect(page.getByTestId("review-candidate").first()).toContainText(
    `${year} 年`,
  );
  await expect(page.locator("canvas").first()).toBeVisible();
  await page.getByRole("button", { name: "开始本组核对", exact: true }).click();
  await expect(
    page.getByText("已核对 0 / 3 项。逐项查看 PDF 并勾选后，才能明确接受。", {
      exact: true,
    }),
  ).toBeVisible();
  for (const name of names) {
    const check = page.getByLabel(`已核对 ${year} ${name}`, { exact: true });
    if (!(await check.isVisible()))
      await page
        .locator(".candidate-item > summary")
        .filter({ hasText: name })
        .click();
    await check.check();
  }
  await expect(page.locator('.review-scope')).toContainText('经营活动现金流量净额');
  await page.locator('.candidate-item > summary').filter({ hasText: '营业收入' }).click();
  await expect(page.getByLabel(`已核对 ${year} 营业收入`, { exact: true })).toBeChecked();
  await expect(page.locator('.review-scope')).toContainText('当前阅读：营业收入');
  await expect(page.locator('.evidence-header')).toContainText(`财务 ${year} 年 · 披露于 2025 年报`);
  await expect(page.locator('.evidence-header strong')).toHaveText('营业收入');
  await screenshots(page, `review-active-${year}`);
  await page
    .getByRole("button", { name: "确认本组数据", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "人工核对确认",
    exact: true,
  });
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('li')).toHaveCount(3);
  await expect(dialog).toContainText('本次确认全部 3 项');
  await page.screenshot({ path: `${out}/confirm-group-${year}.png` });
  return dialog;
}
test("正式首页、缺少资料、真实四 PDF 上传绑定与三种桌面布局", async ({
  page,
}) => {
  await catalog(page);
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST") posts++;
  });
  await page.goto("/");
  await expect(
    page.getByRole("link", { name: "新建企业经营研究 →" }),
  ).toBeVisible();
  await screenshots(page, "home");
  await page.getByRole("link", { name: "新建企业经营研究 →" }).click();
  await page
    .getByLabel("first 企业", { exact: true })
    .selectOption(company("000333"));
  expect(posts).toBe(0);
  if (!live) {
    await expect(page.getByLabel("first 年报", { exact: true })).toHaveCount(0);
    await page.getByLabel("first 期间", { exact: true }).selectOption("2025");
    await page.getByLabel("second 期间", { exact: true }).selectOption("2024");
    await screenshots(page, "create-range");
    await page
      .getByRole("button", { name: "下一步：准备财报", exact: true })
      .click();
    await expect(page.getByLabel("first 企业", { exact: true })).toHaveCount(0);
    await expect(page.getByText(/所选期间暂无可用财报/).first()).toBeVisible();
    await screenshots(page, "create-missing");
    await page
      .getByRole("button", { name: "上传财报" })
      .first()
      .click();
    await expect(page.getByRole("form", { name: "上传年报表单" })).toBeVisible();
    await page.getByRole("button", { name: "取消上传", exact: true }).click();
    expect(posts).toBe(0);
  }
  const receipts: any[] = [];
  for (const source of sources) {
    const [code, year] = [
      source.id.startsWith("midea") ? "000333" : "000651",
      Number(source.id.slice(-4)),
    ];
    await page.goto(`/companies/${company(code)}/documents`);
    await page
      .getByRole("button", { name: "上传并绑定年报", exact: true })
      .click();
    await page.getByLabel("报告年度", { exact: true }).fill(String(year));
    await page
      .getByLabel("PDF 文件", { exact: true })
      .setInputFiles(source.absolute_path);
    if (live) {
      await page.getByText("来源网址（可选）", { exact: true }).click();
      await page.getByLabel("来源网址", { exact: true }).fill(source.url);
    }
    await page.getByLabel("核对上传绑定", { exact: true }).check();
    const response = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/report-documents") &&
        r.request().method() === "POST",
      { timeout: 180000 },
    );
    await page
      .getByRole("button", { name: "提交 PDF 并绑定", exact: true })
      .dblclick();
    const upload = await (await response).json();
    await expect(
      page.getByRole("status").filter({ hasText: "上传与绑定已读回" }),
    ).toBeVisible({ timeout: 120000 });
    const meta = await (
      await page.request.get(`/api/documents/${upload.document_id}/metadata`)
    ).json();
    const src = await (
      await page.request.get(
        `/api/documents/${upload.document_id}/source?company_id=${company(code)}`,
      )
    ).json();
    expect(meta.company_id).toBe(company(code));
    expect(meta.report_year).toBe(year);
    expect(meta.period_start).toBe(`${year}-01-01`);
    expect(src.content_sha256).toBe(source.sha256);
    receipts.push({
      original: source.id,
      sha: src.content_sha256,
      upload,
      meta,
      source: src,
    });
  }
  expect(posts).toBe(4);
  await screenshots(page, "upload-ready");
  writeFileSync(
    `${out}/upload-proof.json`,
    JSON.stringify(
      { receipts, posts, actual_api: true, facts_confirmed: false },
      null,
      2,
    ),
  );
});
test('P1 creation removes duplicate scope fields, shares one PDF and explains invalidation', async ({ page }) => {
  await catalog(page); await harness(page);
  const writes: string[] = [];
  page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); });
  await page.goto(`/research?company=${company('000333')}&mode=operating&new=1`);
  await expect(page.getByLabel('first 企业', { exact: true })).toBeVisible();
  await expect(page.getByLabel('second 企业', { exact: true })).toHaveCount(0);
  await page.getByLabel('first 期间', { exact: true }).selectOption('2025');
  await page.getByLabel('second 期间', { exact: true }).selectOption('2024');
  await page.getByRole('button', { name: '下一步：准备财报', exact: true }).click();
  await expect(page.getByRole('button', { name: '下一步：确认来源', exact: true })).toBeDisabled();
  await expect(page.getByRole('status').filter({ hasText: '尚未选择可用年报' })).toBeVisible();
  await page.getByLabel('first 年报', { exact: true }).selectOption(docId('000333', 2025));
  await page.getByRole('button', { name: '也用本期年报核对 2024 年', exact: true }).click();
  await expect(page.getByLabel('second 年报', { exact: true })).toHaveValue(docId('000333', 2025));
  await screenshots(page, 'shared-pdf');
  await page.getByRole('button', { name: '下一步：确认来源', exact: true }).click();
  await expect(page.getByRole('button', { name: '创建研究，开始核对数据', exact: true })).toBeDisabled();
  await expect(page.locator('select[aria-label$="披露"]')).toHaveCount(0);
  for (const group of [0, 1]) await page.locator('.operating-side').nth(group).getByRole('button', { name: '采用这组三项来源', exact: true }).click();
  await expect(page.getByRole('button', { name: '创建研究，开始核对数据', exact: true })).toBeEnabled();
  await screenshots(page, 'single-disclosure');
  await page.getByRole('button', { name: '修改研究范围', exact: true }).click();
  await expect(page.locator('.scope-change')).toHaveCount(0);
  await page.getByLabel('second 期间', { exact: true }).selectOption('2023');
  await expect(page.locator('.scope-change')).toContainText('2024 年');
  await expect(page.locator('.scope-change')).toContainText('已保留上传文件');
  await page.getByRole('button', { name: /两企业同期间比较/ }).click();
  await expect(page.getByLabel('second 企业', { exact: true })).toBeVisible();
  await expect(page.getByLabel('second 期间', { exact: true })).toHaveCount(0);
  await page.getByLabel('second 企业', { exact: true }).selectOption(company('000651'));
  await page.getByLabel('first 期间', { exact: true }).selectOption('2025');
  await screenshots(page, 'comparison-range');
  expect(writes).toEqual([]);
  writeFileSync(`${out}/p1-creation-proof.json`, JSON.stringify({ writes, single_company_field: true, common_year: true, shared_pdf_explicit: true, scope_message: true }));
});
test('P1 multiple disclosures remain explicit without automatically selecting a version', async ({ page }) => {
  await catalog(page); await harness(page);
  const writes: string[] = [];
  page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); });
  await page.route('**/api/research/disclosures/**', async route => {
    const r = await route.fetch(), body = await r.json();
    body.disclosure_versions.push(`disclosure-v1:${'a'.repeat(64)}`);
    await route.fulfill({ response: r, json: body });
  });
  await page.goto(`/research?company=${company('000333')}&mode=operating&new=1`);
  await page.getByLabel('first 期间', { exact: true }).selectOption('2025');
  await page.getByLabel('second 期间', { exact: true }).selectOption('2024');
  await page.getByRole('button', { name: '下一步：准备财报', exact: true }).click();
  await page.getByLabel('first 年报', { exact: true }).selectOption(docId('000333', 2025));
  await page.getByRole('button', { name: '也用本期年报核对 2024 年', exact: true }).click();
  await page.getByRole('button', { name: '下一步：确认来源', exact: true }).click();
  await expect(page.getByRole('button', { name: '采用这组三项来源', exact: true })).toHaveCount(0);
  await expect(page.locator('select[aria-label$="披露"]')).toHaveCount(6);
  for (const side of ['first', 'second']) for (const metric of metrics) await expect(page.getByLabel(`${side} ${metric} 披露`, { exact: true })).toHaveValue('');
  await page.getByLabel('first revenue 披露', { exact: true }).selectOption({index: 2});
  await expect(page.getByRole('button', { name: '创建研究，开始核对数据', exact: true })).toBeDisabled();
  await screenshots(page, 'multiple-disclosure');
  expect(writes).toEqual([]);
  writeFileSync(`${out}/p1-multiple-disclosure-proof.json`, JSON.stringify({ response_injection: 'second disclosure candidate in GET only; no task submitted', independent_fields: 6, writes }));
});
test('P1 focused upload unknown result preserves scope and only offers read-only recovery', async ({ page }) => {
  await catalog(page); await harness(page);
  const writes: string[] = [];
  page.on('request', r => { if (r.method() !== 'GET') writes.push(r.url()); });
  await page.route('**/api/report-documents', route => route.fulfill({ status: 503, json: { detail: { code: 'test_upload_unavailable' } } }));
  await page.goto(`/research?company=${company('000333')}&mode=operating&new=1`);
  await page.getByLabel('first 期间', { exact: true }).selectOption('2025');
  await page.getByLabel('second 期间', { exact: true }).selectOption('2024');
  await page.getByRole('button', { name: '下一步：准备财报', exact: true }).click();
  await page.getByRole('button', { name: '上传另一份财报', exact: true }).click();
  await page.getByLabel('报告年度', { exact: true }).fill('2025');
  await page.getByLabel('PDF 文件', { exact: true }).setInputFiles(sources.find((s: any) => s.id === 'midea-2025').absolute_path);
  await page.getByLabel('核对上传绑定', { exact: true }).check();
  await page.getByRole('button', { name: '提交 PDF 并绑定', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: '上传响应未知' })).toBeVisible();
  await expect(page.getByRole('button', { name: '提交 PDF 并绑定', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '下一步：确认来源', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '刷新资料与绑定（只读）', exact: true }).click();
  await expect(page.getByLabel('报告年度', { exact: true })).toHaveValue('2025');
  await expect(page.getByRole('button', { name: '结束查证，重新选择文件', exact: true })).toBeVisible();
  expect(writes).toHaveLength(1); expect(writes[0]).toContain('/report-documents');
  await page.screenshot({ path: `${out}/focused-upload-unknown.png` });
  writeFileSync(`${out}/p1-upload-unknown-proof.json`, JSON.stringify({ injected_status: 503, upload_requests: 1, financial_or_task_writes: 0, scope_preserved: true }));
});
test("任务缺项、逐项核对取消零写入、接受未入库、入库只读返回和显式恢复", async ({
  page,
}) => {
  await catalog(page);
  await harness(page);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const writes: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST") writes.push(r.url());
  });
  await configure(page);
  await screenshots(page, "configure");
  const task = await start(page);
  await expect(
    page.getByRole("button", { name: "复核并继续研究", exact: true }),
  ).toHaveCount(0);
  const beforeContinue = writes.length;
  await page.goto("/");
  await expect(page.getByLabel("当前研究", { exact: true })).toContainText(
    "已入库 0 / 6 项",
  );
  await screenshots(page, "home-current");
  await page
    .getByLabel("当前研究", { exact: true })
    .locator(`a[href*="task=${task.task_id}"]`)
    .click();
  await expect(
    page.getByRole("region", { name: "六项事实准备状态" }),
  ).toBeVisible();
  expect(page.url()).toContain(task.task_id);
  expect(writes.length).toBe(beforeContinue);
  await screenshots(page, "waiting");
  let dialog = await review(page, "second", 2024);
  const beforeCancel = writes.length,
    cancelDbBefore = dbFingerprint();
  await dialog.getByRole("button", { name: "取消审阅", exact: true }).click();
  expect(writes.length).toBe(beforeCancel);
  expect(dbFingerprint()).toEqual(cancelDbBefore);
  await page
    .getByRole("button", { name: "确认本组数据", exact: true })
    .click();
  dialog = page.getByRole("dialog", { name: "人工核对确认", exact: true });
  await dialog.getByRole("checkbox").check();
  await dialog
    .getByRole("button", { name: "我已核对并接受", exact: true })
    .click();
  await expect(page.getByTestId("acceptance-result")).toContainText(
    "财务事实入库待完成",
  );
  const beforeReturn = writes.length;
  await page.getByRole("link", { name: "返回原研究任务（只读） →" }).click();
  await expect(page.getByTestId("slot-second:revenue")).toContainText(
    "已接受待入库",
  );
  expect(writes.length).toBe(beforeReturn);
  await screenshots(page, "accepted-awaiting-persist");
  await page
    .locator('.fact-group[data-side="second"] .fact-group-actions')
    .getByRole("link", { name: /保存已接受数据/ })
    .click();
  expect(writes.length).toBe(beforeReturn);
  await expect(page.getByRole('button', { name: '开始本组核对', exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "保存已接受数据", exact: true }),
  ).toBeEnabled();
  await screenshots(page, 'resumed-save');
  expect(writes.length).toBe(beforeReturn);
  await page
    .getByRole("button", { name: "保存已接受数据", exact: true })
    .click();
  await expect(page.getByTestId("fact-result")).toContainText(
    "保存成功并已重新查询",
  );
  await screenshots(page, "review-2024");
  const beforeNextGroup = writes.length;
  await page.getByRole('link', { name: '查看 2025 年另一组数据 →', exact: true }).click();
  await expect(page.getByRole('heading', { name: '核对 2025 年财务 · 共 3 项', exact: true })).toBeVisible();
  expect(writes.length).toBe(beforeNextGroup);
  let before = writes.length;
  await page.getByRole("link", { name: "返回原研究任务（只读） →" }).click();
  await expect(page.getByTestId("slot-second:revenue")).toContainText("已入库");
  expect(writes.length).toBe(before);
  dialog = await review(page, "first", 2025);
  await dialog.getByRole("checkbox").check();
  await dialog
    .getByRole("button", { name: "我已核对并接受", exact: true })
    .click();
  await page
    .getByRole("button", { name: "保存已接受数据", exact: true })
    .click();
  await expect(page.getByTestId("fact-result")).toContainText(
    "保存成功并已重新查询",
  );
  before = writes.length;
  await page.getByRole("link", { name: "返回原研究任务（只读） →" }).click();
  const resume = page.getByRole("button", {
    name: "复核并继续研究",
    exact: true,
  });
  await expect(resume).toBeEnabled();
  expect(writes.length).toBe(before);
  const readyFacts = await (
    await page.request.get(
      `/api/financial-facts?company_id=${company("000333")}&include_invalid=true`,
    )
  ).json();
  for (const side of ["first", "second"])
    for (const metric of metrics) {
      const fact = readyFacts.facts.find(
        (f: any) =>
          f.current_valid &&
          f.period === task.active_input[side].period.year &&
          f.metric_key === metric &&
          f.document_id ===
            task.active_input[side].choices.find(
              (c: any) => c.metric_key === metric,
            ).document_id,
      );
      await expect(page.getByTestId(`slot-${side}:${metric}`)).toContainText(
        `${fact.raw_value} ${fact.raw_unit}`,
      );
    }
  await screenshots(page, "six-ready");
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith(`/api/research/tasks/${task.task_id}/resume`) &&
      r.request().method() === "POST",
    { timeout: 180000 },
  );
  await resume.dblclick();
  const result = await (await response).json();
  expect(result.status).toBe("completed");
  await expect(
    page.getByRole("region", { name: "有限经营研究结果" }),
  ).toBeVisible();
  await expect(page.locator('.result-change')).toHaveCount(3);
  await expect(page.locator('.result-summary')).toContainText('2025 年较 2024 年');
  await expect(page.locator('.result-summary')).toContainText('减少');
  const citationsBefore = writes.length;
  const interpretations = page.getByRole('region', { name: '有限经营研究结果' });
  await interpretations.getByRole('button', { name: /^原文 \[/ }).first().click();
  await expect(page.locator('[id*="-cite-"]:focus')).toHaveCount(1);
  await expect(interpretations).toContainText('待人工语义复核');
  await page.screenshot({ path: `${out}/interpretation-source.png` });
  await interpretations.getByRole('button', { name: '返回待审解释', exact: true }).first().click();
  await expect(page.locator('[id*="-interpretation-"]:focus')).toHaveCount(1);
  expect(writes.length).toBe(citationsBefore);
  await page.locator('#research-results').evaluate(el => el.scrollIntoView({ block: 'start' }));
  await screenshots(page, "result");
  expect(
    writes.filter((x) => x.endsWith(`/tasks/${task.task_id}/resume`)),
  ).toHaveLength(1);
  before = writes.length;
  await page.reload();
  await expect(
    page.getByRole("region", { name: "有限经营研究结果" }),
  ).toBeVisible();
  expect(writes.length).toBe(before);
  await page.getByRole('navigation', { name: '产品导航' }).getByRole('link', { name: '企业与资料', exact: true }).click();
  await page.getByRole('region', { name: '企业目录' }).locator(`li[data-company-id="${company('000333')}"]`).getByRole('link', { name: '企业概览', exact: true }).click();
  await page.getByRole('navigation', { name: '产品导航' }).getByRole('link', { name: '我的研究', exact: true }).click();
  await page.getByRole('region', { name: '最近完成的研究' }).locator(`a[href*="task=${task.task_id}"]`).click();
  await expect(page.getByRole('region', { name: '有限经营研究结果' })).toBeVisible();
  expect(writes.length).toBe(before);
  // The independent financial analysis path still validates frozen source intent.
  await page.goto(`/companies/${company('000333')}/analysis?task=${task.task_id}`);
  for (const year of [2025, 2024])
    for (const name of names)
      await expect(
        page.getByLabel(`${year} ${name}披露版本`, { exact: true }),
      ).not.toHaveValue("");
  await expect(
    page.getByRole("status").filter({
      hasText:
        process.env.ASTRA_P0_BEFORE === "1"
          ? "已恢复此前研究"
          : "本次所需来源已全部核验",
    }),
  ).toBeVisible();
  await expect(page.getByTestId("row-revenue")).toContainText("已分析");
  await screenshots(page, "analysis-restored");
  await page.reload();
  for (const year of [2025, 2024])
    for (const name of names)
      await expect(
        page.getByLabel(`${year} ${name}披露版本`, { exact: true }),
      ).not.toHaveValue("");
  await page.goto(
    `/research?company=${company("000333")}&mode=operating&task=${task.task_id}`,
  );
  await expect(
    page.getByRole("region", { name: "有限经营研究结果" }),
  ).toBeVisible();
  before = writes.length;
  await page.getByRole("link", { name: "整理报告 →" }).click();
  await expect(page.getByLabel("选择已完成研究")).toHaveValue(
    task.task_id,
  );
  expect(writes.length).toBe(before);
  if (process.env.FINDOC_UX_INTEGRATION === "1") {
    await verifyIntegratedQA(page, result, out);
    await verifyReportJourney(page, result, out);
  }
  expect(writes.filter(x => x.endsWith('/financial-facts/confirmations'))).toHaveLength(2);
  expect(writes.filter(x => x.endsWith('/financial-facts/persisted'))).toHaveLength(2);
  writeFileSync(
    `${out}/journey-proof.json`,
    JSON.stringify(
      {
        task,
        result,
        writes,
        trigger_counts: {
          accept: writes.filter(x => x.endsWith('/financial-facts/confirmations')).length,
          persist: writes.filter(x => x.endsWith('/financial-facts/persisted')).length,
          resume: writes.filter(x => x.endsWith(`/tasks/${task.task_id}/resume`)).length,
        },
        cancel_zero_writes: true,
        cancel_db_sha_unchanged: true,
        cancel_db_sha: cancelDbBefore,
        return_zero_writes: true,
        reload_zero_writes: true,
        errors,
        live,
      },
      null,
      2,
    ),
  );
  expect(errors).toHaveLength(0);
});
test("原文问答以多文档问答为主，旧工作台通过明确兼容入口访问", async ({
  page,
}) => {
  await page.goto("/research?mode=qa");
  await expect(
    page.getByRole("region", { name: "研究资料选择" }),
  ).toBeVisible();
  await expect(page.locator(".legacy-workbench")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "查找原文", exact: true }),
  ).toHaveCount(1);
  await page.getByText("兼容工具：原有单文档工作台", { exact: true }).click();
  await page
    .getByRole("link", { name: "打开原有单文档 RAG / Agent / 上传工作台" })
    .click();
  expect(new URL(page.url()).pathname).toBe("/legacy");
  await expect(
    page.getByRole("button", { name: "Agent 有限任务", exact: true }),
  ).toBeVisible();
});
test("双企业研究、resume 响应丢失、按操作只读恢复和历史刷新", async ({
  page,
}) => {
  await catalog(page);
  await harness(page);
  await configure(page, true);
  const task = await start(page);
  const dialog = await review(page, "second", 2025);
  await dialog.getByRole("checkbox").check();
  await dialog
    .getByRole("button", { name: "我已核对并接受", exact: true })
    .click();
  await page
    .getByRole("button", { name: "保存已接受数据", exact: true })
    .click();
  await expect(page.getByTestId("fact-result")).toContainText(
    "保存成功并已重新查询",
  );
  await page.getByRole("link", { name: "返回原研究任务（只读） →" }).click();
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST") posts++;
  });
  await page.route(
    `**/api/research/tasks/${task.task_id}/resume`,
    async (route) => {
      const r = await route.fetch({ timeout: 120000 });
      expect(r.status()).toBe(200);
      await route.abort("failed");
    },
  );
  await page
    .getByRole("button", { name: "复核并继续研究", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "网络响应未知" }),
  ).toBeVisible({ timeout: 120000 });
  expect(posts).toBe(1);
  await page.reload();
  await page
    .getByRole("button", { name: "查证刚才的结果（只读）", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "有限经营研究结果" }),
  ).toBeVisible();
  expect(posts).toBe(1);
  await screenshots(page, "comparison-recovered");
  writeFileSync(
    `${out}/unknown-proof.json`,
    JSON.stringify({
      task_id: task.task_id,
      resume_posts: posts,
      no_automatic_retry: true,
    }),
  );
});
test("上下文篡改、企业切换和迟到 GET 不展示另一任务 PDF", async ({ page }) => {
  await catalog(page);
  await harness(page);
  const proof = JSON.parse(readFileSync(`${out}/journey-proof.json`, "utf8"));
  await page.goto(
    `/research?company=${company("000333")}&mode=operating&task=${proof.task.task_id}`,
  );
  await page.getByText("六项事实与原 PDF 证据", { exact: true }).click();
  await page.getByRole("button", { name: "查看全部六项", exact: true }).click();
  await page
    .getByTestId("slot-second:revenue")
    .getByText("已入库事实与证据", { exact: true })
    .click();
  const link = page
    .getByTestId("slot-second:revenue")
    .getByRole("link", { name: /重新查看核对记录/ });
  await expect(link).toBeVisible();
  const href = await link.getAttribute("href");
  let files = 0;
  page.on("request", (r) => {
    if (r.url().includes("/file?")) files++;
  });
  await page.goto(href!.replace("period=2024", "period=2025"));
  await expect(page.getByRole("alert")).toContainText("不一致");
  expect(files).toBe(0);
  expect(await page.locator("canvas").count()).toBe(0);
  await page.goto(
    `/research?company=${company("000333")}&mode=operating&task=${proof.task.task_id}`,
  );
  await expect(
    page.getByRole("region", { name: "有限经营研究结果" }),
  ).toBeVisible();
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  await page.route(
    `**/api/research/tasks/${proof.task.task_id}`,
    async (route) => {
      const r = await route.fetch();
      await gate;
      await route.fulfill({ response: r }).catch(() => {});
    },
  );
  await page
    .getByRole("button", { name: "刷新状态（只读）", exact: true })
    .click();
  // Frozen tasks expose a directory route instead of mutating their company scope.
  await expect(page.getByLabel('当前企业', { exact: true })).toHaveCount(0);
  await page.getByRole('navigation', { name: '产品导航' }).getByRole('link', { name: '企业与资料', exact: true }).click();
  await page.getByRole('region', { name: '企业目录' }).locator(`li[data-company-id="${company('000651')}"]`).getByRole('link', { name: '企业概览', exact: true }).click();
  await expect(page.getByLabel('当前企业', { exact: true })).toHaveValue(company('000651'));
  release();
  await expect(
    page.getByRole("region", { name: "有限经营研究结果" }),
  ).toHaveCount(0);
  await page.unrouteAll({ behavior: "wait" });
  await page.goto("/");
  await expect(
    page.getByRole("region", { name: "最近完成的研究" }),
  ).toContainText("美的");
});
test("接受与事实入库丢包后刷新只读恢复，1024 PDF 抽屉可退出核对", async ({
  page,
}) => {
  await catalog(page);
  await harness(page);
  await page.goto(
    `/evidence?company=${company("000651")}&document=${docId("000651", 2024)}`,
  );
  await expect(page.getByTestId("review-candidate")).toHaveCount(3);
  await page.getByRole("button", { name: "开始本组核对", exact: true }).click();
  await expect(
    page.getByText("已核对 0 / 3 项。逐项查看 PDF 并勾选后，才能明确接受。", {
      exact: true,
    }),
  ).toBeVisible();
  for (const name of names) {
    const check = page.getByLabel(`已核对 2024 ${name}`, { exact: true });
    if (!(await check.isVisible()))
      await page
        .locator(".candidate-item > summary")
        .filter({ hasText: name })
        .click();
    await check.check();
  }
  await page
    .getByRole("button", { name: "确认本组数据", exact: true })
    .click();
  let acceptancePosts = 0,
    persistencePosts = 0;
  page.on("request", (r) => {
    if (
      r.method() === "POST" &&
      r.url().endsWith("/financial-facts/confirmations")
    )
      acceptancePosts++;
    if (r.method() === "POST" && r.url().endsWith("/financial-facts/persisted"))
      persistencePosts++;
  });
  await page.route("**/api/financial-facts/confirmations", async (route) => {
    const r = await route.fetch({ timeout: 120000 });
    expect(r.status()).toBe(200);
    await route.abort("failed");
  });
  await page.getByRole("dialog").getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "我已核对并接受", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "接受结果未知" }).first(),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "保存已接受数据", exact: true }),
  ).toBeEnabled();
  expect(acceptancePosts).toBe(1);
  await page.route("**/api/financial-facts/persisted", async (route) => {
    const r = await route.fetch({ timeout: 120000 });
    expect(r.status()).toBe(200);
    await route.abort("failed");
  });
  await page
    .getByRole("button", { name: "保存已接受数据", exact: true })
    .click();
  await expect(page.getByTestId("fact-result")).toContainText(
    "事实操作结果未知",
  );
  await page.reload();

  await expect(page.getByTestId("fact-result")).toContainText(
    "保存成功并已重新查询",
  );
  expect(persistencePosts).toBe(1);
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.reload();
  await expect(
    page.getByRole("complementary", { name: "PDF 原文证据", exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: `${out}/pdf-split-1024.png` });
  await page.setViewportSize({ width: 720, height: 450 });
  await page.reload();
  await expect(
    page.getByRole("button", { name: "查看原PDF", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "查看原PDF", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "PDF 原文证据", exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: `${out}/pdf-drawer-narrow-720.png` });
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("dialog", { name: "PDF 原文证据", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "查证数据保存结果（只读）", exact: true }),
  ).toBeEnabled();
  writeFileSync(
    `${out}/acceptance-unknown-proof.json`,
    JSON.stringify({
      acceptance_posts: acceptancePosts,
      persistence_posts: persistencePosts,
      recovered_by_get: true,
      drawer_escape: true,
    }),
  );
});
test("服务端真实失败、拒答与预算耗尽显示不同下一动作", async ({ page }) => {
  test.skip(
    live,
    "provider fault injection exists only in controlled server assembly",
  );
  await catalog(page);
  await harness(page);
  const cases: any[] = [];
  for (const kind of ["failed", "refused", "budget"]) {
    expect(
      (await page.request.post(`/api/__test__/ux-state/${kind}`)).ok(),
    ).toBe(true);
    await configure(page);
    for (const side of ["first", "second"])
      for (const metric of metrics)
        await page
          .getByLabel(`${side} ${metric} 事实`, { exact: true })
          .selectOption({ index: 1 });
    const waiting = await start(page);
    const response = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/api/research/tasks/${waiting.task_id}/resume`) &&
        r.request().method() === "POST",
      { timeout: 180000 },
    );
    await page
      .getByRole("button", { name: "复核并继续研究", exact: true })
      .click();
    const task = await (await response).json();
    expect(task.status).toBe(kind === "refused" ? "refused" : "failed");
    const stage = page.getByRole("region", { name: "研究阶段与下一步" });
    await expect(stage).toContainText(
      kind === "budget"
        ? "预算已耗尽"
        : kind === "refused"
          ? "证据不足"
          : "研究未完成",
    );
    await expect(
      page.getByRole("region", { name: "有限经营研究结果" }),
    ).toHaveCount(0);
    let posts = 0;
    page.on("request", (r) => {
      if (r.method() === "POST") posts++;
    });
    await page.reload();
    await expect(stage).toContainText(
      kind === "budget"
        ? "预算已耗尽"
        : kind === "refused"
          ? "证据不足"
          : "研究未完成",
    );
    expect(posts).toBe(0);
    await page.screenshot({ path: `${out}/task-${kind}-1440.png` });
    cases.push({ kind, task });
    page.removeAllListeners("request");
  }
  await page.request.post("/api/__test__/ux-state/normal");
  writeFileSync(`${out}/terminal-proof.json`, JSON.stringify(cases, null, 2));
});
test("返回修改范围撤销下游资格，两个可用年报仍必须明确选择", async ({
  page,
}) => {
  await catalog(page);
  await harness(page);
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST") posts++;
  });
  await configure(page);
  await page.getByRole("button", { name: "修改研究范围", exact: true }).click();
  await page.getByLabel("first 期间", { exact: true }).selectOption("2024");
  await page.getByLabel("second 期间", { exact: true }).selectOption("2023");
  await page
    .getByRole("button", { name: "下一步：准备财报", exact: true })
    .click();
  await expect(page.getByLabel("first 年报", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("second 年报", { exact: true })).toHaveValue("");
  await expect(
    page.getByRole("button", { name: "下一步：确认来源", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByLabel("first revenue 披露", { exact: true }),
  ).toHaveCount(0);
  expect(posts).toBe(0);
  await page.getByRole("button", { name: "修改研究范围", exact: true }).click();
  await page.getByLabel("first 期间", { exact: true }).selectOption("2025");
  await page.getByLabel("second 期间", { exact: true }).selectOption("2024");
  await page
    .getByRole("button", { name: "下一步：准备财报", exact: true })
    .click();
  await expect(
    page.getByLabel("second 年报", { exact: true }).locator("option"),
  ).toHaveCount(3);
  await expect(page.getByLabel("second 年报", { exact: true })).toHaveValue("");
  expect(posts).toBe(0);
  await screenshots(page, "source-choice-required");
  writeFileSync(
    `${out}/range-invalidation-proof.json`,
    JSON.stringify(
      {
        changed_range_clears_documents_and_disclosures: true,
        multiple_reports_not_auto_selected: true,
        posts,
      },
      null,
      2,
    ),
  );
});
test("没有来源意图时不自动选已入库事实，明确选择后刷新复用完整身份", async ({
  page,
}) => {
  await catalog(page);
  await harness(page);
  const id = company("000333");
  const mutations: string[] = [];
  page.on("request", (r) => {
    if (
      r.method() !== "GET" &&
      /confirmations|persisted|research\/tasks/.test(r.url())
    )
      mutations.push(r.url());
  });
  await page.goto(`/companies/${id}/analysis`);
  for (const year of [2025, 2024])
    for (const name of names)
      await expect(
        page.getByLabel(`${year} ${name}披露版本`, { exact: true }),
      ).toHaveValue("");
  await expect(page.getByTestId("row-revenue")).toContainText("待选版本");
  const choice = page.getByLabel("2025 营业收入披露版本", { exact: true });
  await choice.selectOption({ index: 1 });
  const chosen = await choice.inputValue();
  await page.reload();
  await expect(choice).toHaveValue(chosen);
  await expect(
    page.getByLabel("2024 营业收入披露版本", { exact: true }),
  ).toHaveValue("");
  await page.evaluate((companyId) => {
    localStorage.removeItem(`findoc:source-intent:${companyId}`);
    localStorage.removeItem(`findoc:operating-identity:${companyId}`);
  }, id);
  await page.reload();
  await page
    .getByText(
      process.env.ASTRA_P0_BEFORE === "1"
        ? "沿用已完成研究中明确选定的来源"
        : "更换研究来源",
      { exact: true },
    )
    .click();
  const original = JSON.parse(
    readFileSync(`${out}/journey-proof.json`, "utf8"),
  ).task;
  await page.locator(`a[href*="analysis?task=${original.task_id}"]`).click();
  for (const year of [2025, 2024])
    for (const name of names)
      await expect(
        page.getByLabel(`${year} ${name}披露版本`, { exact: true }),
      ).not.toHaveValue("");
  expect(mutations).toEqual([]);
  writeFileSync(
    `${out}/explicit-analysis-intent-proof.json`,
    JSON.stringify(
      {
        no_year_based_auto_selection: true,
        explicit_choice_revalidated_after_reload: true,
        explicit_research_choice_restores_sources_without_local_hint: true,
        chosen,
        mutations,
      },
      null,
      2,
    ),
  );
});
test("两个已核准披露版本并存时保留冻结选择，分析页不自动挑选最新来源", async ({
  page,
}) => {
  await catalog(page);
  await harness(page);
  await page.goto(
    `/evidence?company=${company("000333")}&document=${docId("000333", 2024)}`,
  );
  await page.getByRole("button", { name: "开始本组核对", exact: true }).click();
  await expect(
    page.getByText("已核对 0 / 3 项。逐项查看 PDF 并勾选后，才能明确接受。", {
      exact: true,
    }),
  ).toBeVisible();
  for (const name of names) {
    const check = page.getByLabel(`已核对 2024 ${name}`, { exact: true });
    if (!(await check.isVisible()))
      await page
        .locator(".candidate-item > summary")
        .filter({ hasText: name })
        .click();
    await check.check();
  }
  await page
    .getByRole("button", { name: "确认本组数据", exact: true })
    .click();
  await page.getByRole("dialog").getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "我已核对并接受", exact: true })
    .click();
  await page
    .getByRole("button", { name: "保存已接受数据", exact: true })
    .click();
  await expect(page.getByTestId("fact-result")).toContainText(
    "保存成功并已重新查询",
  );
  const query = await (
    await page.request.get(
      `/api/financial-facts?company_id=${company("000333")}&include_invalid=true`,
    )
  ).json();
  expect(query.requires_version_selection).toBe(true);
  const valid = query.facts.filter(
    (f: any) =>
      f.period === 2024 && f.metric_key === "revenue" && f.current_valid,
  );
  expect(new Set(valid.map((f: any) => f.disclosure_version)).size).toBe(2);
  await page.goto(`/companies/${company("000333")}/analysis`);
  const select = page.getByLabel("2024 营业收入披露版本", { exact: true });
  await expect(select.locator("option")).toHaveCount(3);
  await expect(select).toHaveValue("");
  await select.selectOption(
    valid.find((f: any) => f.document_id === docId("000333", 2024)).fact_id,
  );
  const proof = JSON.parse(readFileSync(`${out}/journey-proof.json`, "utf8"));
  await page.goto(
    `/research?company=${company("000333")}&mode=operating&task=${proof.task.task_id}`,
  );
  await expect(
    page.getByRole("region", { name: "有限经营研究结果" }),
  ).toBeVisible();
  let resumes = 0;
  page.on("request", (r) => {
    if (r.url().endsWith("/resume") && r.method() === "POST") resumes++;
  });
  await page.reload();
  await expect(
    page.getByRole("region", { name: "有限经营研究结果" }),
  ).toBeVisible();
  expect(resumes).toBe(0);
  writeFileSync(
    `${out}/disclosure-conflict-proof.json`,
    JSON.stringify(
      {
        two_original_disclosures: true,
        disclosure_versions: valid.map((f: any) => f.disclosure_version),
        ambiguous_periods: query.ambiguous_periods,
        conflicting_periods: query.conflicting_periods,
        frozen_task_kept: true,
        auto_resume_posts: resumes,
        simulated_test: true,
      },
      null,
      2,
    ),
  );
});
test("P0-A actual shell widths, container PDF and keyboard navigation", async ({
  page,
}) => {
  await catalog(page);
  await harness(page);
  const before = process.env.ASTRA_P0_BEFORE === "1";
  const measurements: any[] = [];
  const writes: string[] = [];
  page.on("request", (r) => {
    if (
      r.method() !== "GET" &&
      /confirmations|persisted|research\/tasks/.test(r.url())
    )
      writes.push(r.url());
  });
  for (const width of [1440, 1280, 1024, 720, 640, 512]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(
      `/evidence?company=${company("000651")}&document=${docId("000651", 2024)}`,
    );
    await expect(page.locator(".candidate-panel")).toBeVisible();
    const toggle = page.getByRole("button", { name: /展开证据|查看原PDF/ });
    if (await toggle.isVisible()) await toggle.click();
    await expect(page.locator(".evidence-viewer")).toBeVisible();
    await expect(page.locator(".pdf-sheet canvas")).toBeVisible({
      timeout: 30000,
    });
    await expect(page.locator(".pdf-location")).not.toContainText("正在渲染", {
      timeout: 30000,
    });
    const m = await page.evaluate(() => {
      const sidebar = document.querySelector(".sidebar")!,
        body = document.querySelector(".app-body")!,
        layout = document.querySelector(".evidence-layout")!;
      return {
        width: innerWidth,
        sidebar: getComputedStyle(sidebar).width,
        sidebarVisible: sidebar.getClientRects().length > 0,
        margin: getComputedStyle(body).marginLeft,
        bodyLeft: body.getBoundingClientRect().left,
        workspace: layout.getBoundingClientRect().width,
        overflow: document.documentElement.scrollWidth - innerWidth,
        readerRole: document
          .querySelector(".evidence-viewer")
          ?.getAttribute("role"),
        canvas: document.querySelector("canvas")?.getBoundingClientRect().width,
      };
    });
    measurements.push(m);
    if (!before) {
      expect(m.sidebar).toBe(
        `${width >= 1100 ? 224 : 0}px`,
      );
      expect(m.margin).toBe(
        `${width >= 1100 ? 224 : 0}px`,
      );
      expect(m.overflow).toBeLessThanOrEqual(1);
      expect(m.readerRole).toBe(
        m.workspace >= 900 ? "complementary" : "dialog",
      );
    }
    await page.screenshot({ path: `${out}/p0-review-${width}.png` });
    if (m.readerRole === "dialog") await page.keyboard.press("Escape");
    if (!before && width < 1100) {
      const menu = page.getByRole("button", { name: "打开导航" });
      await menu.click();
      await expect(
        page.getByRole("navigation", { name: "产品导航" }).getByRole("link"),
      ).toHaveCount(3);
      expect(await page.evaluate(() => document.body.style.overflow)).toBe(
        "hidden",
      );
      await page.keyboard.press("Shift+Tab");
      await page.keyboard.press("Tab");
      await page.keyboard.press("Escape");
      await expect(menu).toBeFocused();
      expect(await page.evaluate(() => document.body.style.overflow)).not.toBe(
        "hidden",
      );
      await expect(
        page.getByRole("navigation", { name: "产品导航" }),
      ).toBeHidden();
    }
  }
  if (!before) {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(
      `/evidence?company=${company("000651")}&document=${docId("000651", 2024)}`,
    );
    await page
      .getByRole("button", { name: "开始本组核对", exact: true })
      .click();
    const check = page.getByLabel("已核对 2024 营业收入", { exact: true });
    await check.check();
    await page.getByLabel("缩放", { exact: true }).selectOption("1.5");
    await page
      .locator(".evidence-header")
      .getByRole("button", { name: "返回核对", exact: true })
      .click();
    await page.getByRole("button", { name: "查看原PDF", exact: true }).click();
    await expect(page.getByLabel("缩放", { exact: true })).toHaveValue("1.5");
    await expect(check).toBeChecked();
    await page.locator(".product-body").evaluate((el) => {
      (el as HTMLElement).style.width = "800px";
    });
    await expect(
      page.getByRole("dialog", { name: "PDF 原文证据", exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel("缩放", { exact: true })).toHaveValue("1.5");
    await page.keyboard.press("Escape");
    await expect(check).toBeChecked();
    await expect(
      page.getByRole("button", { name: "查看原PDF", exact: true }),
    ).toBeFocused();
  }
  expect(writes).toEqual([]);
  writeFileSync(
    `${out}/p0-layout.json`,
    JSON.stringify({ before, measurements, writes }, null, 2),
  );
});
test("P0-B explicit task B owns the scope despite stored same-slot A", async ({
  page,
}) => {
  await catalog(page);
  await harness(page);
  const before = process.env.ASTRA_P0_BEFORE === "1";
  const id = company("000333");
  const task = JSON.parse(
    readFileSync(`${out}/journey-proof.json`, "utf8"),
  ).task;
  const query = await (
    await page.request.get(
      `/api/financial-facts?company_id=${id}&include_invalid=true`,
    )
  ).json();
  const a = query.facts.find(
    (f: any) =>
      f.period === 2024 &&
      f.metric_key === "revenue" &&
      f.document_id === docId("000333", 2024) &&
      f.current_valid,
  );
  const b = query.facts.find(
    (f: any) =>
      f.period === 2024 &&
      f.metric_key === "revenue" &&
      f.document_id === docId("000333", 2025) &&
      f.current_valid,
  );
  expect(a.fact_id).not.toBe(b.fact_id);
  await page.goto(`/companies/${id}/analysis`);
  await page.evaluate(
    ({ id, a }) =>
      localStorage.setItem(`findoc:source-intent:${id}`, JSON.stringify([a])),
    { id, a },
  );
  await page.goto(`/companies/${id}/analysis?task=${task.task_id}`);
  await expect(
    page
      .locator(".disclosure-panel .status")
      .filter({ hasText: before ? "已恢复来源意图" : "已核验 6 / 6" }),
  ).toBeVisible();
  const details = page.locator(".disclosure-panel > details").last();
  if (
    !(await details.getAttribute("open")) &&
    !(await details.evaluate((el) => (el as HTMLDetailsElement).open))
  )
    await details.locator("summary").first().click();
  const actual = await page
    .getByLabel("2024 营业收入披露版本", { exact: true })
    .inputValue();
  expect(actual).toBe(before ? a.fact_id : b.fact_id);
  await page.screenshot({ path: `${out}/p0-explicit-task-b.png` });
  writeFileSync(
    `${out}/p0-source-ab.json`,
    JSON.stringify(
      {
        before,
        task: task.task_id,
        a: a.fact_id,
        b: b.fact_id,
        actual,
        sameAmount: a.value_cny_yuan === b.value_cny_yuan,
      },
      null,
      2,
    ),
  );
});

test("P0-B partial task, historical coverage, late response, empty storage and company comparison", async ({
  page,
}) => {
  test.skip(
    process.env.ASTRA_P0_BEFORE === "1",
    "Additional fixes are verified against the implementation only",
  );
  await catalog(page);
  await harness(page);
  const id = company("000333");
  const task = JSON.parse(
    readFileSync(`${out}/journey-proof.json`, "utf8"),
  ).task;
  const query = await (
    await page.request.get(
      `/api/financial-facts?company_id=${id}&include_invalid=true`,
    )
  ).json();
  const a = query.facts.find(
    (f: any) =>
      f.period === 2024 &&
      f.metric_key === "revenue" &&
      f.document_id === docId("000333", 2024) &&
      f.current_valid,
  );
  const b = query.facts.find(
    (f: any) =>
      f.period === 2024 &&
      f.metric_key === "revenue" &&
      f.document_id === docId("000333", 2025) &&
      f.current_valid,
  );
  const writes: string[] = [];
  page.on("request", (r) => {
    if (
      r.method() !== "GET" &&
      /confirmations|persisted|research\/tasks|reports\/.*revisions/.test(
        r.url(),
      )
    )
      writes.push(r.url());
  });
  await page.goto(`/companies/${id}/analysis`);
  await page.evaluate(
    ({ id, a }) =>
      localStorage.setItem(`findoc:source-intent:${id}`, JSON.stringify([a])),
    { id, a },
  );
  const queryUrl = "**/api/financial-facts?**";
  await page.route(queryUrl, async (route) => {
    const response = await route.fetch();
    const value = await response.json();
    value.facts = value.facts.map((f: any) =>
      f.fact_id === b.fact_id
        ? { ...f, current_valid: false, calculable: false }
        : f,
    );
    await route.fulfill({ response, json: value });
  });
  await page.goto(`/companies/${id}/analysis?task=${task.task_id}`);
  await expect(
    page.locator(".disclosure-panel > .section-title .status"),
  ).toHaveText("已核验 5 / 6 项");
  await expect(
    page.getByLabel("2024 营业收入披露版本", { exact: true }),
  ).toHaveValue("");
  await expect(page.getByLabel("当前范围缺项")).toContainText(
    "2024 年 · 营业收入",
  );
  await expect(page.getByText("更换研究来源", { exact: true })).toBeVisible();
  await page.screenshot({ path: `${out}/p0-partial-task.png` });
  await page.unroute(queryUrl);
  // Read-only catalog fixture adds a newer available year; the chosen task still owns its periods.
  await page.route(queryUrl, async (route) => {
    const response = await route.fetch();
    const value = await response.json();
    value.facts.push({ ...a, period: 2026, fact_id: "available-newer-year" });
    await route.fulfill({ response, json: value });
  });
  await page.goto(`/companies/${id}/analysis?task=${task.task_id}`);
  await expect(page.getByLabel("本期年度", { exact: true })).toHaveValue(
    "2025",
  );
  await expect(page.getByLabel("上期年度", { exact: true })).toHaveValue(
    "2024",
  );
  await expect(
    page.locator(".disclosure-panel > .section-title .status"),
  ).toHaveText("已核验 6 / 6 项");
  await page.unroute(queryUrl);
  // Plenty of valid historical identities cannot fill current-period slots.
  const historical = Array.from({ length: 8 }, (_, i) => ({
    ...a,
    period: 2000 + i,
    fact_id: `history-${i}`,
  }));
  await page.route(queryUrl, async (route) => {
    const response = await route.fetch();
    const value = await response.json();
    value.facts.push(...historical);
    await route.fulfill({ response, json: value });
  });
  await page.evaluate(
    ({ id, a, historical }) => {
      localStorage.removeItem(`findoc:operating-identity:${id}`);
      localStorage.setItem(
        `findoc:source-intent:${id}`,
        JSON.stringify([a, ...historical]),
      );
    },
    { id, a, historical },
  );
  await page.goto(`/companies/${id}/analysis`);
  await expect(
    page.locator(".disclosure-panel > .section-title .status"),
  ).toHaveText("已核验 1 / 6 项");
  await expect(page.getByLabel("当前范围缺项").locator("li")).toHaveCount(5);
  await page.screenshot({ path: `${out}/p0-history-is-not-coverage.png` });
  await page.unroute(queryUrl);
  // User scope/source edits own the page even after a successful or failed old GET.
  for (const fail of [false, true]) {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => (release = resolve));
    let started!: () => void;
    const pending = new Promise<void>((resolve) => (started = resolve));
    const taskUrl = `**/api/research/tasks/${task.task_id}`;
    await page.route(taskUrl, async (route) => {
      const response = await route.fetch();
      started();
      await gate;
      await route.fulfill(
        fail
          ? { status: 503, json: { detail: { message: "迟到核验失败" } } }
          : { response },
      );
    });
    await page.goto(`/companies/${id}/analysis?task=${task.task_id}`);
    await pending;
    await page.getByLabel("本期年度", { exact: true }).selectOption("2024");
    await page
      .getByLabel("2024 营业收入披露版本", { exact: true })
      .selectOption(a.fact_id);
    const returned = page.waitForResponse((r) =>
      r.url().endsWith(`/research/tasks/${task.task_id}`),
    );
    release();
    await returned;
    await page.evaluate(
      () =>
        new Promise<void>((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
        ),
    );
    await expect(page.getByLabel("本期年度", { exact: true })).toHaveValue(
      "2024",
    );
    await expect(page.getByLabel("上期年度", { exact: true })).toHaveValue("0");
    await expect(
      page.getByLabel("2024 营业收入披露版本", { exact: true }),
    ).toHaveValue(a.fact_id);
    await expect(page.locator(".disclosure-panel")).toContainText(
      "本次手动选择",
    );
    await expect(page.locator(".disclosure-panel")).not.toContainText(
      "迟到核验失败",
    );
    await page.unroute(taskUrl);
    // A fresh query must not remount the view and revive the old task owner.
    await page.route(queryUrl, async (route) => {
      const response = await route.fetch();
      const value = await response.json();
      const unrelated = { ...a, period: 2001, fact_id: `refresh-${fail}` };
      value.facts.push(unrelated);
      await route.fulfill({ response, json: value });
    });
    const refreshed = page.waitForResponse((r) =>
      r.url().includes("/api/financial-facts?"),
    );
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await refreshed;
    await expect(page.getByLabel("本期年度", { exact: true })).toHaveValue(
      "2024",
    );
    await expect(page.getByLabel("上期年度", { exact: true })).toHaveValue("0");
    await expect(page.locator(".disclosure-panel")).toContainText(
      "本次手动选择",
    );
    await page.unroute(queryUrl);
  }
  // Cleared hints + two equal-amount sources still require explicit selection.
  await page.evaluate(() => localStorage.clear());
  await page.goto(`/companies/${id}/analysis`);
  await expect(
    page.locator(".disclosure-panel > .section-title .status"),
  ).toHaveText("已核验 0 / 6 项");
  await expect(
    page.getByLabel("2024 营业收入披露版本", { exact: true }),
  ).toHaveValue("");
  await expect(
    page.getByLabel("2024 营业收入披露版本", { exact: true }).locator("option"),
  ).toHaveCount(3);
  await page
    .getByRole("button", { name: "双企业同期间比较", exact: true })
    .click();
  await page
    .getByLabel("企业 B", { exact: true })
    .selectOption(company("000651"));
  await page.getByLabel("对比财务年度", { exact: true }).selectOption("2024");
  await page.getByLabel("比较展示单位", { exact: true }).selectOption("yuan");
  for (const side of ["A", "B"])
    await page
      .locator("details.comparison-source")
      .filter({
        has: page.getByLabel(`${side} 营业收入披露版本`, { exact: true }),
      })
      .locator("summary")
      .click();
  await page
    .getByLabel("A 营业收入披露版本", { exact: true })
    .selectOption(a.fact_id);
  await page
    .getByLabel("B 营业收入披露版本", { exact: true })
    .selectOption({ index: 1 });
  await expect(page.locator(".financial-table")).toContainText(
    "189,163,654,064.64",
  );
  expect(writes).toEqual([]);
  writeFileSync(
    `${out}/p0-source-regressions.json`,
    JSON.stringify(
      {
        partial_task_no_local_fill: true,
        task_scope_preserved_with_newer_available_year: true,
        historical_keys: 9,
        current_coverage: "1/6",
        late_success_and_failure_revoked: true,
        cleared_storage_no_auto_selection: true,
        multiple_candidates: 2,
        company_comparison: true,
        business_writes: writes,
      },
      null,
      2,
    ),
  );
});
test("创建响应丢失时优先只读查证，刷新不重建也不继续任务", async ({ page }) => {
  await catalog(page);
  await harness(page);
  await configure(page);
  let creates = 0,
    resumes = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith("/api/research/tasks"))
      creates++;
    if (r.method() === "POST" && r.url().endsWith("/resume")) resumes++;
  });
  await page.route("**/api/research/tasks", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const response = await route.fetch({ timeout: 180000 });
    expect(response.status()).toBe(200);
    await route.abort("failed");
  });
  await page
    .getByRole("button", { name: "创建研究，开始核对数据", exact: true })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "网络响应未知" }),
  ).toBeVisible({ timeout: 180000 });
  await expect(
    page.getByRole("region", { name: "企业与期间配置" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "查证刚才的结果（只读）", exact: true }),
  ).toBeVisible();
  await screenshots(page, "creation-unknown");
  await page.reload();
  await expect(
    page.getByRole("region", { name: "六项事实准备状态" }),
  ).toBeVisible();
  expect(creates).toBe(1);
  expect(resumes).toBe(0);
  writeFileSync(
    `${out}/creation-unknown-proof.json`,
    JSON.stringify(
      {
        creates,
        resumes,
        creation_form_withdrawn: true,
        restored_by_get_only: true,
      },
      null,
      2,
    ),
  );
});
test("正式入口保留生产门禁，来源重建撤下旧研究金额与 PDF", async ({ page }) => {
  await catalog(page);
  const proof = JSON.parse(readFileSync(`${out}/journey-proof.json`, "utf8"));
  const path = `/research?company=${company("000333")}&mode=operating&task=${proof.task.task_id}`;
  // Formal main.tsx, no harness: simulated facts can never become production facts.
  await page.goto(path);
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: /资格失效/ })
      .first(),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "有限经营研究结果" }),
  ).toHaveCount(0);
  await harness(page);
  await page.reload();
  await expect(
    page.getByRole("region", { name: "有限经营研究结果" }),
  ).toBeVisible();
  const id = docId("000333", 2025),
    source = await (
      await page.request.get(
        `/api/documents/${id}/source?company_id=${company("000333")}`,
      )
    ).json();
  expect(
    (
      await page.request.post(`/api/documents/${id}/reindex`, {
        data: { expected_attempt: source.attempt },
      })
    ).status(),
  ).toBe(202);
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST") posts++;
  });
  await page.reload();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: /资格失效/ })
      .first(),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "有限经营研究结果" }),
  ).toHaveCount(0);
  await expect(page.locator(".result-change")).toHaveCount(0);
  expect(posts).toBe(0);
  await page.screenshot({ path: `${out}/source-invalidated-1440.png` });
});
