import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
const base = process.env.SHOWCASE_TEST_URL || "http://127.0.0.1:5180";
const out = process.env.SHOWCASE_TEST_OUTPUT || "/tmp/findoc-m1-mock";
await mkdir(out, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROME_PATH
    ? { executablePath: process.env.CHROME_PATH }
    : {}),
});
const session = {
  schema_version: "demo-session-v1",
  state: "active",
  expires_at: "2030-01-01T00:20:00Z",
  server_now: "2030-01-01T00:00:00Z",
  remaining_seconds: 1200,
  lease_generation: 1,
  seed_version: "fake",
  can_review: false,
  owner_elevated_until: null,
};
for (const width of [1440, 1280, 390]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  let active = false,
    loginId = "",
    claimId = "";
  page.on("pageerror", (e) => console.log("PAGEERROR", e.message));
  page.setDefaultTimeout(5000);
  await page.route("**/fixture", (r) =>
    r.fulfill({
      contentType: "text/html",
      body: `<div id="root"></div><script type="module">import RefreshRuntime from "/@react-refresh"; RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => (type) => type; window.__vite_plugin_react_preamble_installed__ = true;</script><script type="module">import React from '/node_modules/.vite/deps/react.js';import ReactDOM from '/node_modules/.vite/deps/react-dom_client.js';import {DemoGate} from '/src/demo/DemoGate.tsx';import {ShowcaseDashboard} from '/src/product/showcase/ShowcaseDashboard.tsx';ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(DemoGate,{enabled:true},React.createElement(ShowcaseDashboard,{companies:[],company:''})));</script>`,
    }),
  );
  await page.route("**/api/**", async (r) => {
    let path = new URL(r.request().url()).pathname;
    let body = r.request().postDataJSON();
    let data = {};
    let status = 200;
    if (path === "/api/demo/status")
      data = {
        schema_version: "demo-status-v1",
        service_state: "ready",
        ttl_minutes: 20,
        conflict_policy: "wait_only",
      };
    else if (path === "/api/demo/session") {
      if (active) data = session;
      else {
        status = 401;
        data = { detail: { code: "unauthenticated", message: "未登录" } };
      }
    } else if (path === "/api/demo/login") {
      loginId = body.operation_id;
      status = 202;
      data = {
        schema_version: "demo-attempt-v1",
        operation_id: loginId,
        state: "pending",
        reset_id: "fake",
        claimable: false,
      };
    } else if (path.startsWith("/api/demo/operations/"))
      data = {
        schema_version: "demo-attempt-v1",
        operation_id: loginId,
        state: "ready",
        reset_id: "fake",
        claimable: true,
      };
    else if (path === "/api/demo/claim") {
      claimId = body.operation_id;
      if (body.attempt_operation_id !== loginId || claimId === loginId)
        throw Error("claim contract");
      active = true;
      data = session;
    } else if (path === "/api/demo/logout") {
      active = false;
      data = { state: "resetting" };
    } else if (path === "/api/dashboard/overview")
      data = {
        schema_version: "dashboard-overview-v1",
        data_origin: "preset_demo",
        lease_generation: 1,
        snapshot_at: "2030",
        seed_version: "fake",
        kpis: {
          companies: 1,
          reports_ready: 1,
          research_completed: 1,
          reports: 1,
        },
        task_distribution: [{ status: "completed", count: 1 }],
        recent_research: [],
        suggested_questions: [],
        companies: [],
        limitations: ["测试模拟数据"],
      };
    else if (path === "/api/dashboard/charts")
      data = {
        schema_version: "dashboard-charts-v1",
        company_id: "fake",
        metric_key: "revenue",
        unit: "元",
        origin: "illustrative",
        points: [
          {
            period: "2024",
            report_year: 2024,
            value_decimal: "123.45",
            source_revision: "fake",
            document_id: "fake",
            fact_ref: null,
            source_state: "illustrative",
          },
        ],
        comparison: [],
        empty_reason: null,
        limitations: ["测试模拟数据"],
      };
    else {
      status = 500;
      data = { detail: { code: "unknown", message: path } };
    }
    await r.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
  await page.goto(base + "/fixture");
  await page.getByLabel("账号").fill("example");
  await page.getByLabel("密码").fill("example");
  await page.getByRole("button", { name: "进入演示" }).click();
  await page.getByText("研究图表").waitFor();
  await page.getByText("来源：illustrative", { exact: false }).waitFor();
  await page.screenshot({ path: `${out}/mock-${width}.png`, fullPage: true });
  if (
    await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  )
    throw Error(`overflow ${width}`);
  await page.getByRole("button", { name: "退出演示" }).click();
  await page.getByText("欢迎体验 FinDoc").waitFor();
  console.log(`PASS mocked pending/claim/logout and dashboard ${width}`);
  await page.close();
}
await browser.close();
