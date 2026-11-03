import { chromium } from "playwright";
import { mkdir, readFile } from "node:fs/promises";
const base = process.env.SHOWCASE_TEST_URL || "http://127.0.0.1:5180";
const out = process.env.SHOWCASE_TEST_OUTPUT || "/tmp/findoc-m1-final";
await mkdir(out, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROME_PATH
    ? { executablePath: process.env.CHROME_PATH }
    : {}),
});
const assert = (x, m) => {
  if (!x) throw Error(m);
};
const tokens = process.env.SHOWCASE_TOKENS
  ? await readFile(process.env.SHOWCASE_TOKENS, "utf8")
  : "";
const overview = {
  schema_version: "dashboard-overview-v1",
  data_origin: "local_runtime",
  lease_generation: 1,
  snapshot_at: "2030-01-01",
  seed_version: "test",
  kpis: { companies: 2, reports_ready: 6, research_completed: 6, reports: 4 },
  task_distribution: [
    { status: "completed", count: 6 },
    { status: "running", count: 2 },
    { status: "waiting", count: 1 },
  ],
  recent_research: [
    {
      id: "one",
      title: "现金流变化分析",
      status: "completed",
      href: "/research?task=one",
      origin: "preset_demo",
      review_status: "source_recheck_required",
    },
    {
      id: "two",
      title: "年度经营表现梳理",
      status: "running",
      href: "/research?task=two",
      origin: "preset_demo",
      review_status: "source_recheck_required",
    },
  ],
  suggested_questions: [
    "近三年现金流有什么变化？",
    "哪些经营风险值得关注？",
    "帮我梳理年度经营表现",
  ].map((text, i) => ({
    id: String(i),
    text,
    href: "/conversations?question=" + encodeURIComponent(text),
  })),
  companies: [
    { company_id: "fake", name: "虚构企业 A", security_code: "示意 A" },
    { company_id: "fake-b", name: "虚构企业 B", security_code: "示意 B" },
  ],
  limitations: ["UI_MOCK：仅测试示意数据，不是真实财报"],
};
async function fixture(width, mode = "normal") {
  const page = await browser.newPage({ viewport: { width, height: 950 } });
  page.setDefaultTimeout(7000);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let active = false,
    operation = "",
    gets = 0,
    release;
  let mutations = 0;
  const session = (gen = 1) => ({
    schema_version: "demo-session-v1",
    state: "active",
    expires_at: "2030-01-01T00:20:00Z",
    server_now: "2030-01-01T00:00:00Z",
    remaining_seconds: mode === "expiry" ? 1 : 1200,
    lease_generation: gen,
    seed_version: "test",
    can_review: gen === 2,
    owner_elevated_until: null,
  });
  await page.route("**/fixture", (r) =>
    r.fulfill({
      contentType: "text/html",
      body: `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0"><div id="root"></div><script type="module">import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>(type)=>type;window.__vite_plugin_react_preamble_installed__=true;</script><script type="module">import React from '/node_modules/.vite/deps/react.js';import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';import {DemoGate} from '/src/demo/DemoGate.tsx';import {ShowcaseDashboard} from '/src/product/showcase/ShowcaseDashboard.tsx';import {AppShell} from '/src/product/AppShell.tsx';import '/src/product/tokens.css';import '/src/product/shell.css';import '/src/product/product.css';import '/src/product/foundation.css';const style=document.createElement('style');style.textContent=${JSON.stringify(tokens)};document.head.append(style);function App(){return React.createElement(React.Fragment,null,React.createElement('div',{style:{background:'#fff0be',textAlign:'center',fontSize:12,padding:8}},'UI_MOCK · 全部为测试示意数据，不是真实财报'),React.createElement(DemoGate,{enabled:true},React.createElement(AppShell,{page:'home',company:'',companies:[],navigate:()=>{}},React.createElement(ShowcaseDashboard,{companies:[],company:''}))));}ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App));</script></body></html>`,
    }),
  );
  await page.route("**/api/**", async (r) => {
    const path = new URL(r.request().url()).pathname;
    const body = r.request().postDataJSON();
    let status = 200,
      data = {};
    if (path === "/api/demo/status")
      data = {
        schema_version: "demo-status-v1",
        service_state: "ready",
        ttl_minutes: 20,
        conflict_policy: "takeover_enabled",
      };
    else if (path === "/api/demo/session") {
      gets++;
      if (mode === "late" && gets === 2) {
        await new Promise((resolve) => (release = resolve));
        data = session(1);
      } else if (!active || (mode === "expiry" && gets > 1)) {
        status = 401;
        data = {
          detail: {
            code: active ? "expired" : "unauthenticated",
            message: active ? "演示会话已到期" : "请登录演示",
          },
        };
      } else data = session(mode === "late" && gets >= 3 ? 2 : 1);
    } else if (path === "/api/demo/login") {
      mutations++;
      operation = body.operation_id;
      status = 202;
      data = {
        schema_version: "demo-attempt-v1",
        operation_id: operation,
        state: "pending",
        reset_id: "fake",
        claimable: false,
      };
    } else if (path.startsWith("/api/demo/operations/"))
      data = {
        schema_version: "demo-attempt-v1",
        operation_id: operation,
        state: "ready",
        reset_id: "fake",
        claimable: true,
      };
    else if (path === "/api/demo/claim") {
      mutations++;
      assert(
        body.operation_id !== operation &&
          body.attempt_operation_id === operation,
        "claim identity",
      );
      active = true;
      if (mode === "claim-unknown") {
        await r.abort();
        return;
      }
      data = session();
    } else if (path === "/api/demo/owner-authorize")
      data = { can_review: true, owner_elevated_until: "2030-01-01T00:05:00Z" };
    else if (path === "/api/demo/logout") {
      active = false;
      data = { state: "resetting" };
    } else if (path === "/api/dashboard/overview")
      data =
        mode === "schema"
          ? { ...overview, kpis: { companies: "invalid" } }
          : overview;
    else if (path === "/api/dashboard/charts") {
      let q = new URL(r.request().url()).searchParams;
      const sample = q.get("sample_mode") === "true";
      data = {
        schema_version: "dashboard-charts-v1",
        company_id: sample ? "illustrative-company-a" : q.get("company_id"),
        metric_key: q.get("metric_key"),
        unit: "CNY_YUAN",
        origin: sample ? "illustrative" : "confirmed_financial",
        points: [32000000000, 37500000000, 42400000000].map((v, i) => ({
          period: 2022 + i,
          report_year: 2023 + i,
          value_decimal: String(v),
          source_revision: sample ? null : "fake",
          document_id: sample ? null : "fake",
          source_state: sample ? "illustrative" : "current",
          ...(!sample
            ? {
                fact_ref: {
                  period: 2022 + i,
                  fact_set_id: "fake",
                  fact_id: "fake",
                  receipt_id: "fake",
                  disclosure_version: "fake",
                  source_revision: "fake",
                },
              }
            : {}),
        })),
        comparison: [],
        empty_reason: null,
        limitations: ["测试示意数据"],
      };
    } else {
      status = 500;
      data = { detail: { code: "unhandled", message: path } };
    }
    if (mode === "chart-schema" && path === "/api/dashboard/charts")
      data.points[0].value_decimal = "invalid";
    await r.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
  await page.goto(base + "/fixture");
  await page.getByText("欢迎体验 FinDoc").waitFor();
  return {
    page,
    errors,
    login: async () => {
      await page.getByLabel("账号", { exact: true }).fill("test");
      await page.getByLabel("密码", { exact: true }).fill("test");
      await page.getByRole("button", { name: "进入演示", exact: true }).click();
    },
    release: () => release?.(),
    hasRelease: () => !!release,
    gets: () => gets,
    mutations: () => mutations,
  };
}
for (const width of [1440, 1280, 390]) {
  const t = await fixture(width);
  const p = t.page;
  await p.screenshot({ path: `${out}/login-${width}.png`, fullPage: true });
  await t.login();
  await p.getByRole("heading", { name: "财务趋势", exact: true }).waitFor();
  await p.locator(".sd-card .recharts-wrapper").first().waitFor();
  await p.screenshot({ path: `${out}/home-${width}.png`, fullPage: true });
  assert(
    !(await p.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    )),
    `overflow ${width}`,
  );
  await p.getByLabel("财务指标").selectOption("operating_cash_flow");
  await p.getByRole("button", { name: "退出演示" }).click();
  await p.getByText("欢迎体验 FinDoc").waitFor();
  assert(!t.errors.length, t.errors.join(";"));
  console.log(`PASS visual shell/login/dashboard/metric/logout ${width}`);
  await p.close();
}
{
  const t = await fixture(1280, "schema");
  await t.login();
  await t.page
    .getByRole("alert")
    .filter({ hasText: "概览数据格式无效" })
    .waitFor();
  assert(
    (await t.page.locator(".sd-kpis").count()) === 0,
    "invalid schema exposed kpis",
  );
  console.log("PASS invalid overview rejected");
  await t.page.close();
}
{
  const t = await fixture(1280, "chart-schema");
  await t.login();
  await t.page
    .getByRole("alert")
    .filter({ hasText: "图表数据身份或格式无效" })
    .first()
    .waitFor();
  assert(
    (await t.page.locator(".recharts-line").count()) === 0,
    "invalid point silently rendered",
  );
  console.log("PASS invalid Decimal rejects complete chart");
  await t.page.close();
}
{
  const t = await fixture(1280, "expiry");
  await t.login();
  await t.page.getByText("演示会话已到期", { exact: true }).waitFor();
  assert(
    (await t.page.locator(".showcase-dashboard").count()) === 0,
    "expired dashboard retained",
  );
  assert(t.gets() >= 2, "expiry missing GET verification");
  console.log("PASS expiry immediate unmount and server verification");
  await t.page.close();
}
{
  const t = await fixture(1280, "late");
  await t.login();
  await t.page.locator(".showcase-dashboard").waitFor();
  await t.page.waitForFunction(() => true);
  await new Promise((resolve) => setTimeout(resolve, 10500));
  assert(t.hasRelease(), "old refresh not held");
  await t.page.getByText("所有者授权", { exact: true }).click();
  await t.page.getByLabel("所有者口令").fill("test");
  await t.page
    .getByRole("button", { name: "授权人工核对", exact: true })
    .click();
  await t.page.getByText("已授权人工核对", { exact: false }).first().waitFor();
  t.release();
  await t.page.waitForTimeout(300);
  assert(
    (await t.page.getByText("已授权人工核对", { exact: false }).count()) > 0,
    "late response overwrote newer generation",
  );
  await t.page.getByRole("button", { name: "退出演示" }).click();
  assert(
    (await t.page.locator(".showcase-dashboard").count()) === 0,
    "old generation remounted",
  );
  console.log("PASS older refresh cannot replace newer session");
  await t.page.close();
}
{
  const t = await fixture(1280, "claim-unknown");
  await t.login();
  await t.page.getByRole("button", { name: "查询本次申请" }).waitFor();
  assert(t.mutations() === 2, "claim automatically replayed");
  await t.page.getByRole("button", { name: "查询本次申请" }).click();
  await t.page.locator(".showcase-dashboard").waitFor();
  assert(t.mutations() === 2, "read-only query posted new operation");
  console.log("PASS unknown claim retained and recovered through GET only");
  await t.page.close();
}
await browser.close();
