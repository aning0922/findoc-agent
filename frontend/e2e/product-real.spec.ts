import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { formatDecimal } from "../src/product/api.ts";
const stage = process.env.FINDOC_PRODUCT_STAGE || "d12";
const root = readFileSync(
  `../data/30d-foundation/${stage}-product-runtime-path.txt`,
  "utf8",
).trim();
const manifest = JSON.parse(readFileSync(`${root}/manifest.json`, "utf8"));
const gold = JSON.parse(
  readFileSync("../product/validation/manual-benchmark.json", "utf8"),
).facts;
const metrics: Record<string, string> = {
  revenue: "营业收入",
  net_profit_parent: "归母净利润",
  operating_cash_flow: "经营活动现金流量净额",
};
const expected: Record<string, Record<string, string>> = {
  midea: {
    revenue: "12.11",
    net_profit_parent: "14.03",
    operating_cash_flow: "-11.84",
  },
  gree: {
    revenue: "-9.89",
    net_profit_parent: "-9.89",
    operating_cash_flow: "57.93",
  },
};
const proof: any[] = [];
let version = "";
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: "ignoreErrors" });
});
test.beforeAll(({ browser }) => {
  version = browser.version();
});
test.afterAll(() =>
  writeFileSync(
    `../product/validation/${stage === "d12" ? "d12-product-measurements" : `${stage}-product-measurements`}.json`,
    JSON.stringify(
      {
        runtime: root,
        chromium: version,
        observations: proof,
        human_acceptance: "pending",
        confirmation_kind: "simulated_test",
        substitutions: manifest.substitutions,
        production_analysis_unchanged: true,
      },
      null,
      2,
    ),
  ),
);
async function legacyScreenshot(page: Page, options: Parameters<Page["screenshot"]>[0]) {
  if (stage === "d12") await page.screenshot(options);
}
function group(key: string, year: number) {
  const doc = manifest.reports.find(
    (r: any) => r.report_id === `${key}-${year}`,
  ).source.document_id;
  return manifest.groups.find((g: any) => g.document_id === doc);
}
async function preview(page: Page) {
  await page.route("**/src/main.tsx*", (route) =>
    route.fulfill({
      contentType: "application/javascript",
      body: "import '/tests/support/d12-entry.tsx'",
    }),
  );
}
async function open(page: Page, key = "midea", view = "analysis") {
  await preview(page);
  const current = group(key, 2025);
  await page.goto(`/companies/${current.company_id}/${view}`);
  await expect(page.getByText("披露版本与来源", { exact: true })).toBeVisible({
    timeout: 60_000,
  });
  await expect(
    page.getByText("隔离 UI Harness", { exact: false }),
  ).toBeVisible();
}
async function choose(page: Page, key = "midea", previousReport = 2024) {
  for (const [m, title] of Object.entries(metrics)) {
    for (const [year, g] of [
      [2025, group(key, 2025)],
      [2024, group(key, previousReport)],
    ] as const) {
      const fact = g.facts.find(
        (f: any) => f.metric_key === m && f.period === year,
      );
      await page
        .getByLabel(`${year} ${title}披露版本`, { exact: true })
        .selectOption(fact.fact_id);
    }
  }
  for (const [m, value] of Object.entries(expected[key]))
    await expect(
      page.getByTestId(`row-${m}`).getByText(`${value}%`, { exact: true }),
    ).toBeVisible({ timeout: 30_000 });
}
test("正式入口：模拟事实永不变成生产 KPI；正式 D11 拒绝模拟", async ({
  page,
  request,
}) => {
  const g = group("midea", 2025);
  let posts = 0;
  page.on("request", (r) => {
    if (r.url().endsWith("/analyses")) posts++;
  });
  await page.goto(`/companies/${g.company_id}/overview`);
  await expect(page.getByText("尚无可用于正式分析的已确认事实")).toBeVisible();
  await expect(
    page.getByText("查询含自动化模拟事实", { exact: false }),
  ).toBeVisible();
  await expect(page.locator(".money-link")).toHaveCount(0);
  expect(posts).toBe(0);
  const c = g.facts.find(
      (f: any) => f.metric_key === "revenue" && f.period === 2025,
    ),
    p = group("midea", 2024).facts.find((f: any) => f.metric_key === "revenue");
  const ref = (f: any, set: any) => ({
    fact_set_id: f.fact_set_id,
    fact_id: f.fact_id,
    period: f.period,
    source_revision: f.source_revision,
    disclosure_version: set.disclosure_version,
  });
  const response = await request.post("/api/analyses", {
    data: {
      schema_version: "financial-analysis-v1",
      company_id: g.company_id,
      metric_key: "revenue",
      current: ref(c, g),
      previous: ref(p, group("midea", 2024)),
    },
  });
  expect(response.status()).toBe(404);
  for (const width of [1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.evaluate(() => window.scrollTo(0, 0));
    await legacyScreenshot(page, {
      path: `../product/validation/d12-screenshots/production-empty-${width}.png`,
      fullPage: true,
    });
  }
  proof.push({
    production_simulation_denied: true,
    formal_analysis_status: 404,
    formal_posts_without_selection: posts,
  });
});
for (const key of ["midea", "gree"]) {
  test(`${key} 四真实原报：三指标/两种2024披露/Decimal单位/原PDF`, async ({
    page,
  }) => {
    const errors: string[] = [],
      responses: any[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("response", async (r) => {
      if (r.url().endsWith("/__test__/analyses") && r.status() === 200)
        responses.push(await r.json());
    });
    await open(page, key);
    expect(responses).toHaveLength(0);
    await expect(page.getByText("多披露版本", { exact: true })).toHaveCount(3);
    await choose(page, key);
    for (const g of [group(key, 2024), group(key, 2025)]) {
      for (const f of g.facts) {
        const benchmark = gold.find(
          (b: any) =>
            b.document_id === `${key}-${g.review.source.report_year}` &&
            b.metric === f.metric_key &&
            b.period === f.period,
        );
        expect(f.value_cny_yuan).toBe(benchmark.value_cny_yuan);
        await page
          .getByLabel(`${f.period} ${metrics[f.metric_key]}披露版本`, {
            exact: true,
          })
          .selectOption(f.fact_id);
        await expect(
          page.locator(`[data-fact-id="${f.fact_id}"]`),
        ).toContainText(formatDecimal(f.value_cny_yuan));
        await page.locator(`[data-fact-id="${f.fact_id}"]`).click();
        const ref = f.evidence[0];
        await expect(page.locator(".fact-evidence")).toHaveCSS(
          "width",
          "340px",
        );
        await page
          .getByRole("button", { name: "展开阅读", exact: true })
          .click();
        await expect(page.getByLabel("物理页码")).toHaveValue(
          String(ref.physical_page),
          { timeout: 30_000 },
        );
        await expect(page.locator("canvas")).toHaveAttribute(
          "aria-label",
          `PDF 物理第 ${ref.physical_page} 页`,
        );
        await expect(page.locator(".pdf-location")).toContainText(
          "金额区域已核验",
          { timeout: 30_000 },
        );
        if (f.metric_key === "revenue")
          await page.evaluate(() => window.scrollTo(0, 0));
        await legacyScreenshot(page, {
          path: `../product/validation/d12-screenshots/${key}-${g.review.source.report_year}-${f.period}-pdf.png`,
        });
        await page.getByRole("button", { name: "收起证据侧栏" }).click();
        proof.push({
          report: `${key}-${g.review.source.report_year}`,
          metric: f.metric_key,
          period: f.period,
          fact_id: f.fact_id,
          source_revision: f.source_revision,
          disclosure_version: g.disclosure_version,
          amount: f.value_cny_yuan,
          physical_page: ref.physical_page,
          evidence_id: ref.evidence_id,
          candidate_id: f.candidate_id,
        });
      }
    }
    await choose(page, key, 2025);
    const row = page.getByTestId("row-revenue");
    await row.getByText("2025 · 原值与单位").click();
    await expect(row).toContainText(
      group(key, 2025).facts.find(
        (f: any) => f.metric_key === "revenue" && f.period === 2025,
      ).raw_unit,
    );
    await page.getByLabel("展示单位").selectOption("yi");
    const fact = group(key, 2025).facts.find(
      (f: any) => f.metric_key === "revenue" && f.period === 2025,
    );
    await expect(
      page.locator(`[data-fact-id="${fact.fact_id}"]`),
    ).toContainText(formatDecimal(fact.value_cny_yuan, 8));
    for (const width of [1440, 1280, 1024]) {
      await page.setViewportSize({ width, height: 900 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.evaluate(() => window.scrollTo(0, 0));
      await legacyScreenshot(page, {
        path: `../product/validation/d12-screenshots/${key}-analysis-${width}.png`,
        fullPage: true,
      });
    }
    expect(errors).toEqual([]);
    expect(responses.length).toBeGreaterThanOrEqual(3);
    for (const a of responses) {
      expect(a.percentage_change).toBe(expected[key][a.metric_key]);
      expect(a.production_calculable).toBe(false);
    }
    proof.push({ company: key, analyses: responses, errors });
  });
}
test("企业切换与迟到查询隔离；概览选择与浏览器前进后退", async ({ page }) => {
  await open(page);
  await choose(page);
  await page.getByRole("link", { name: "企业概览", exact: true }).click();
  await expect(page.locator(".money-link")).toHaveCount(0);
  await page.getByText("检查与选择各指标披露版本", { exact:true }).click();
  for (const [m, title] of Object.entries(metrics)) {
    for (const year of [2024, 2025])
      await page
        .getByLabel(`${year} ${title}披露版本`, { exact: true })
        .selectOption(
          group("midea", year).facts.find(
            (f: any) => f.metric_key === m && f.period === year,
          ).fact_id,
        );
    await expect(page.getByTestId(`kpi-${m}`)).toContainText(
      `${expected.midea[m]}%`,
    );
  }
  await expect(page.getByTestId("kpi-revenue")).toContainText(
    "456,451,731,000",
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await legacyScreenshot(page, {
    path: "../product/validation/d12-screenshots/midea-overview.png",
    fullPage: true,
  });
  await page
    .getByLabel("当前企业")
    .selectOption(group("gree", 2025).company_id);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "珠海格力电器股份有限公司",
  );
  await expect(page.locator(".money-link")).toHaveCount(0);
  await page.goBack();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "美的集团股份有限公司",
  );
  let release!: () => void, seen!: () => void;
  const gate = new Promise<void>((r) => {
      release = r;
    }),
    started = new Promise<void>((r) => {
      seen = r;
    });
  await page.route("**/financial-facts?**", async (route) => {
    if (!route.request().url().includes(group("midea", 2025).company_id))
      return route.continue();
    const response = await route.fetch();
    seen();
    await gate;
    try {
      await route.fulfill({ response });
    } catch {}
  });
  await page.reload();
  await started;
  await page
    .getByLabel("当前企业")
    .selectOption(group("gree", 2025).company_id);
  release();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "珠海格力电器股份有限公司",
  );
  await expect(page.getByText("披露版本与来源", { exact: true })).toBeVisible();
  await expect(page.getByText("midea-2025.pdf", { exact: true })).toHaveCount(
    0,
  );
});
test("版本切换撤销旧分析与引用；迟到分析不恢复", async ({ page }) => {
  await open(page);
  await choose(page);
  const f = group("midea", 2025).facts.find(
    (f: any) => f.metric_key === "revenue" && f.period === 2025,
  );
  await page.locator(`[data-fact-id="${f.fact_id}"]`).click();
  await expect(page.locator("canvas")).toBeVisible({ timeout: 30_000 });
  let release!: () => void, seen!: () => void;
  const gate = new Promise<void>((r) => {
      release = r;
    }),
    started = new Promise<void>((r) => {
      seen = r;
    });
  await page.route("**/__test__/analyses", async (route) => {
    const response = await route.fetch();
    seen();
    await gate;
    try {
      await route.fulfill({ response });
    } catch {}
  });
  await page
    .getByLabel("2024 营业收入披露版本", { exact: true })
    .selectOption(
      group("midea", 2025).facts.find(
        (f: any) => f.metric_key === "revenue" && f.period === 2024,
      ).fact_id,
    );
  await started;
  await expect(page.locator("canvas")).toHaveCount(0);
  await expect(
    page.getByTestId("row-revenue").getByText("12.11%", { exact: true }),
  ).toHaveCount(0);
  await page
    .getByLabel("2025 营业收入披露版本", { exact: true })
    .selectOption("");
  release();
  await expect(page.getByTestId("row-revenue")).toContainText(
    "指标不完整 / 待选版本",
  );
  await expect(
    page.getByTestId("row-revenue").getByText("12.11%", { exact: true }),
  ).toHaveCount(0);
});
test("缺失、冲突、零基数和partial状态合同（明确的响应故障注入）", async ({
  page,
}) => {
  await preview(page);
  await page.route("**/financial-facts?**", async (route) => {
    const response = await route.fetch(),
      q = await response.json();
    q.facts = q.facts.filter(
      (f: any) =>
        !(f.metric_key === "operating_cash_flow" && f.period === 2024),
    );
    q.conflicting_periods = ["injected-conflict-contract"];
    await route.fulfill({ response, json: q });
  });
  await open(page);
  await expect(
    page.getByText("其中 1 个存在金额冲突。", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByLabel("2024 经营活动现金流量净额披露版本", { exact: true }),
  ).toBeDisabled();
  await page.route("**/__test__/analyses", async (route) => {
    const response = await route.fetch(),
      a = await response.json();
    a.status = "partial";
    a.percentage_change = null;
    a.percentage_reason =
      a.metric_key === "revenue" ? "zero_base" : "non_adjacent_annual_periods";
    a.reasons = [
      {
        code: a.percentage_reason,
        message:
          a.metric_key === "revenue"
            ? "上期为零，同比百分比无定义，仅提供绝对差额。"
            : "两期不是可比的相邻年度，仅提供绝对差额。",
      },
    ];
    a.limitations = [
      {
        code: "negative_base",
        message: "负基数限制：不能从百分比符号推断经营改善或恶化。",
      },
    ];
    await route.fulfill({ response, json: a });
  });
  for (const m of ["revenue", "net_profit_parent"])
    for (const year of [2024, 2025])
      await page
        .getByLabel(`${year} ${metrics[m]}披露版本`, { exact: true })
        .selectOption(
          group("midea", year).facts.find(
            (f: any) => f.metric_key === m && f.period === year,
          ).fact_id,
        );
  await expect(page.getByTestId("row-revenue")).toContainText("无法计算同比");
  await expect(page.getByTestId("row-net_profit_parent")).toContainText(
    "partial",
  );
  await expect(page.getByTestId("row-operating_cash_flow")).toContainText(
    "指标不完整",
  );
  await expect(
    page.getByTestId("row-revenue").getByText("0%", { exact: true }),
  ).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await legacyScreenshot(page, {
    path: "../product/validation/d12-screenshots/injected-partial-contract.png",
    fullPage: true,
  });
  proof.push({
    fault_injection_only: [
      "missing metric",
      "conflict banner",
      "zero base",
      "non-adjacent",
      "negative base",
    ],
    not_actual_report_arithmetic: true,
  });
});
test("网络错误撤销数字；恢复重新GET；年份/指标选择和键盘缩放", async ({
  page,
}) => {
  await open(page);
  await choose(page);
  await page.getByLabel("本期年度").selectOption("2024");
  await expect(page.getByText("分析不可比较", { exact: false })).toBeVisible();
  await expect(
    page.getByTestId("row-revenue").getByText("12.11%", { exact: true }),
  ).toHaveCount(0);
  await page.getByLabel("本期年度").selectOption("2025");
  await expect(page.getByTestId("row-revenue")).toContainText("12.11%");
  await page.getByLabel("归母净利润", { exact: true }).uncheck();
  await expect(page.getByTestId("row-net_profit_parent")).toHaveCount(0);
  await page.route("**/financial-facts?**", (route) => route.abort("failed"));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("alert")).toContainText("网络连接失败");
  await expect(page.locator(".money-link")).toHaveCount(0);
  await page.unroute("**/financial-facts?**");
  await page.getByRole("button", { name: "重试读取", exact: true }).click();
  await expect(page.getByText("披露版本与来源", { exact: true })).toBeVisible();
  await page.getByLabel("当前企业").focus();
  await page.keyboard.press("Tab");
  expect(await page.evaluate(() => document.activeElement?.tagName)).not.toBe(
    "BODY",
  );
  await page
    .locator(".saas-app")
    .evaluate((e) => ((e as HTMLElement).style.zoom = "2"));
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
test("五页导航、D22草稿入口、已有RAG/Agent与中文长名布局", async ({ page }) => {
  await page.route("**/api/companies", async (route) => {
    const response = await route.fetch(),
      companies = await response.json();
    companies.find(
      (c: any) => c.company_id === group("midea", 2025).company_id,
    ).name = "美的集团股份有限公司企业长期经营财务研究".repeat(8);
    await route.fulfill({ response, json: companies });
  });
  await open(page);
  await expect(
    page.getByRole("navigation", { name: "产品导航" }).getByRole("link"),
  ).toHaveCount(5);
  for (const width of [1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.getByRole("link", { name: "企业概览", exact: true }).click();
  await expect(page.getByRole("link", { name: "打开已有上传工作台", exact: true })).toHaveAttribute("href", "/legacy");
  await page.getByRole("link", { name: "AI 研究", exact: true }).click();
  await page.getByRole("tab", { name: "原文问答", exact: true }).click();
  await expect(page.getByRole("button", { name: "Agent 有限任务", exact: true })).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const selection = page.getByRole("region", { name: "研究资料选择" });
  await selection.getByLabel(/2025 年报/).check();
  await expect(selection.getByLabel("所选资料摘要")).toContainText("2025 年报");
  await page
    .getByLabel("当前企业")
    .selectOption(group("gree", 2025).company_id);
  await expect(selection.getByLabel("所选资料摘要")).toBeEmpty();
  await page
    .getByLabel("当前企业")
    .selectOption(group("midea", 2025).company_id);
  await page.getByText("兼容工具：原有单文档工作台", { exact: true }).click();
  await page.unroute("**/src/main.tsx*");
  await page.getByRole("link", { name: "打开原有单文档 RAG / Agent / 上传工作台" }).click();
  await expect(page.getByRole("button", { name: "Agent 有限任务", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "RAG 自由问答", exact: true })).toBeVisible();
  await preview(page);
  await page.goBack();
  await page.getByRole("link", { name: "研究报告", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "结构化研究报告" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "生成草稿", exact: true })).toBeDisabled();
  await expect(page.getByText("草稿尚未保存", { exact: false }).first()).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await legacyScreenshot(page, {
    path: "../product/validation/d12-screenshots/reports-not-developed.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "财报资料库", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "准备财报资料", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "打开财务事实核对 →" }),
  ).toHaveCount(2);
});

test("真实来源纠错后自动复验：旧金额、分析、PDF一起撤下", async ({
  page,
  request,
}) => {
  await open(page, "gree");
  await choose(page, "gree");
  const g = group("gree", 2025),
    f = g.facts.find(
      (f: any) => f.metric_key === "revenue" && f.period === 2025,
    );
  await page.locator(`[data-fact-id="${f.fact_id}"]`).click();
  await expect(page.locator("canvas")).toBeVisible({ timeout: 30_000 });
  const response = await request.post(
    `/api/documents/${g.document_id}/binding-corrections`,
    {
      data: {
        expected_attempt: 1,
        metadata: {
          company_id: g.company_id,
          report_year: 2025,
          report_type: "annual",
          basis: "unknown",
          period_start: "2025-01-01",
          period_end: "2025-12-31",
        },
        reason: "D12 isolated simulated correction test",
      },
    },
  );
  expect(response.status()).toBe(200);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.locator(`[data-fact-id="${f.fact_id}"]`)).toHaveCount(0);
  await expect(page.locator("canvas")).toHaveCount(0);
  await expect(
    page.getByText("存在失效来源事实", { exact: false }),
  ).toBeVisible({ timeout: 30_000 });
  await expect(
    page.getByTestId("row-revenue").getByText("-9.89%", { exact: true }),
  ).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await legacyScreenshot(page, {
    path: "../product/validation/d12-screenshots/source-invalidated.png",
    fullPage: true,
  });
});
