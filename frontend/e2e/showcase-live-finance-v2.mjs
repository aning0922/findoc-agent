import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
const out = process.env.F03_SCREENSHOTS || "/tmp/findoc-f03-mock";
await mkdir(out, { recursive: true });
const b = await chromium.launch({
  headless: true,
  ...(process.env.CHROME_PATH
    ? { executablePath: process.env.CHROME_PATH }
    : {}),
});
const ids = [
  "11111111-1111-4111-8111-111111111111",
  "22222222-2222-4222-8222-222222222222",
];
for (const width of [1440, 1280, 390]) {
  const p = await b.newPage({ viewport: { width, height: 950 } });
  p.setDefaultTimeout(6500);
  let state = "candidate",
    unknown = false,
    authorized = true,
    posts = 0,
    confirmPosts = 0;
  const errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  const metrics = () =>
    ids.map((id, i) => ({
      schema_version: "extended-metric-v2",
      metric_id: id,
      company_id: "c",
      document_id: "doc",
      source_revision: "a".repeat(64),
      report_year: 2025,
      period: 2024,
      period_kind: "instant",
      scope: "consolidated",
      basis: "PRC_GAAP",
      as_of_date: "2024-12-31",
      metric_key: i ? "total_liabilities" : "total_assets",
      value_decimal:
        state === "unavailable"
          ? null
          : i
            ? "24000000000.50"
            : "60000000000.25",
      unit: "CNY_YUAN",
      status: state === "unavailable" ? "unsupported" : state,
      source_status: state === "unavailable" ? "unavailable" : "current_valid",
      confirmation_ref:
        state === "confirmed"
          ? {
              receipt_id: "44444444-4444-4444-8444-444444444444",
              confirmation_kind: "local_operator",
            }
          : null,
      evidence_refs: [{ physical_page: 9, text: "UI_MOCK 原文" }],
      unsupported_reasons: state === "unavailable" ? ["source_changed"] : [],
    }));
  await p.route("**/finance-fixture", (r) =>
    r.fulfill({
      contentType: "text/html",
      body: `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><div style="background:#fff0be;text-align:center;padding:8px">UI_MOCK · 模拟财务核对，不产生真实回执</div><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>t=>t;window.__vite_plugin_react_preamble_installed__=true;</script><script type="module">import React from '/node_modules/.vite/deps/react.js';import DOM from '/node_modules/.vite/deps/react-dom_client.js';import {ExtendedFinancePanel} from '/src/product/financeV2/ExtendedFinancePanel.tsx';import '/src/product/tokens.css';DOM.createRoot(document.getElementById('root')).render(React.createElement('main',{style:{maxWidth:1200,margin:'30px auto',padding:16}},React.createElement(ExtendedFinancePanel,{company:{company_id:'c',name:'示意企业',security_code:'000000',exchange:'SZSE'}})));</script></html>`,
    }),
  );
  await p.route("**/api/**", async (r) => {
    const path = new URL(r.request().url()).pathname,
      body = r.request().postDataJSON();
    let data;
    if (path === "/api/documents")
      data = [
        { document_id: "doc", source_file: "示例年报.pdf", status: "ready" },
      ];
    else if (path.endsWith("/metadata"))
      data = {
        company_id: "c",
        report_year: 2025,
        report_type: "annual",
        basis: "PRC_GAAP",
        period_start: "2025-01-01",
        period_end: "2025-12-31",
      };
    else if (path.endsWith("/source"))
      data = {
        company_id: "c",
        document_id: "doc",
        source_revision: "a".repeat(64),
        content_sha256: "b".repeat(64),
        attempt: 1,
        physical_pages: 20,
        parser_version: "mock",
        report_year: 2025,
        metadata_status: "bound",
      };
    else if (path.endsWith("/extended-metrics"))
      data = {
        schema_version: "extended-metric-list-v2",
        company_id: "c",
        metrics: metrics(),
        limitations: [],
      };
    else if (path === "/api/demo/session")
      data = {
        schema_version: "demo-session-v1",
        state: "active",
        can_review: authorized,
        lease_generation: 1,
        remaining_seconds: 1200,
        server_now: "2030-01-01T00:00:00Z",
        expires_at: "2030-01-01T00:20:00Z",
        owner_elevated_until: "2030-01-01T00:05:00Z",
      };
    else if (path.includes("/extended-operations/"))
      data = {
        operation_id: path.split("/").at(-1),
        state: "completed",
        historical_snapshot: true,
        result: { schema_version: "extended-confirmation-v2" },
      };
    else {
      posts++;
      if (body && "value_decimal" in body)
        throw Error("client amount submitted");
      if (path.endsWith("/collect")) {
        if (unknown) {
          await r.abort();
          return;
        }
        data = {
          schema_version: "extended-metric-collection-v2",
          metrics: metrics(),
          limitations: [],
        };
      } else if (path.endsWith("/extended-reviews"))
        data = {
          schema_version: "extended-review-v2",
          review_id: "33333333-3333-4333-8333-333333333333",
          review_sha256: "c".repeat(64),
          acceptable: true,
          metrics: metrics(),
        };
      else if (path.endsWith("/extended-confirmations")) {
        confirmPosts++;
        state = "confirmed";
        data = {
          schema_version: "extended-confirmation-v2",
          review_id: body.review_id,
          review_sha256: body.review_sha256,
          metric_refs: ids,
          receipt_id: "44444444-4444-4444-8444-444444444444",
          confirmation_kind: "local_operator",
        };
      } else
        data = {
          ...metrics()[0],
          metric_key: "debt_asset_ratio",
          unit: "PERCENT",
          input_refs: ids,
          value_decimal: "40.000000",
        };
    }
    await r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
  await p.goto(`${process.env.F03_TEST_URL || "http://127.0.0.1:5180"}/finance-fixture`);
  await p.getByLabel("明确选择已就绪年报").selectOption("doc");
  await p.getByRole("button", { name: "读取所选来源" }).click();
  await p.getByRole("button", { name: "明确收集资产负债候选" }).click();
  await p.getByText("操作已返回，正在只读重新核验当前指标。").waitFor();
  await p.screenshot({ path: `${out}/candidate-${width}.png`, fullPage: true });
  if (await p.locator(".recharts-wrapper").count())
    throw Error("candidate chart");
  for (const name of ["总资产", "总负债"])
    await p.getByLabel(`选择 ${name} 2024-12-31`).check();
  await p.getByRole("button", { name: "准备两项核对快照" }).click();
  await p.getByRole("heading", { name: "真人核对快照 · 尚未接受" }).waitFor();
  if (await p.getByRole("button", { name: "真人明确接受 v2 核对" }).isEnabled())
    throw Error("confirmation without owner/checkbox");
  await p.getByRole("button", { name: "只读检查真人授权" }).click();
  await p.getByLabel("我已对照原文核对", { exact: false }).first().check();
  await p.getByLabel("我已对照原文核对", { exact: false }).nth(1).check();
  await p.getByRole("button", { name: "真人明确接受 v2 核对" }).click();
  await p.locator(".recharts-wrapper").first().waitFor();
  await p.screenshot({ path: `${out}/confirmed-${width}.png`, fullPage: true });
  await p.getByLabel("选择 总资产 2024-12-31").check();
  await p.getByLabel("选择 总负债 2024-12-31").check();
  await p.getByRole("button", { name: "请求服务端计算资产负债率" }).click();
  await p
    .getByText("40.000000%（服务端保存的分析快照，非当前资格凭据）")
    .waitFor();
  authorized = false;
  const beforeDenied = posts;
  await p.getByRole("button", { name: "真人撤销此 v2 核对" }).first().click();
  await p
    .getByText("请先使用页面上方的所有者授权入口；财务接受须由真人操作。")
    .waitFor();
  if (posts !== beforeDenied || (await p.locator(".recharts-wrapper").count()))
    throw Error("authorization failure retained chart or wrote");
  authorized = true;
  state = "unavailable";
  await p.getByRole("button", { name: "只读核验指标" }).click();
  await p.getByText("不支持／来源失效").first().waitFor();
  if (await p.locator(".recharts-wrapper").count())
    throw Error("stale chart retained");
  state = "candidate";
  unknown = true;
  await p.getByRole("button", { name: "明确收集资产负债候选" }).click();
  await p.getByRole("button", { name: "只读查询原操作" }).waitFor();
  const before = posts;
  await p.screenshot({ path: `${out}/unknown-${width}.png`, fullPage: true });
  await p.reload();
  await p.getByRole("button", { name: "只读查询原操作" }).click();
  await p.getByText("历史操作已读回，当前资格以重新查询的指标为准。").waitFor();
  if (posts !== before || confirmPosts !== 1) throw Error("operation replay");
  if (await p.locator(".recharts-wrapper").count())
    throw Error("history snapshot treated as authority");
  if (await p.evaluate(() => document.documentElement.scrollWidth > innerWidth))
    throw Error("overflow");
  if (errors.length) throw Error(errors.join(";"));
  console.log(
    `PASS F03 fake ${width}: candidate/review/simulated confirm/stale/UNKNOWN`,
  );
  await p.close();
}
await b.close();
