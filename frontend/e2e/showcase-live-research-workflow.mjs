import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
const out = process.env.A03_SCREENSHOTS || "/tmp/findoc-a03-workflow";
await mkdir(out, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROME_PATH
    ? { executablePath: process.env.CHROME_PATH }
    : {}),
});
const cid = "11111111-1111-4111-8111-111111111111",
  cid2 = "22222222-2222-4222-8222-222222222222",
  iid = "33333333-3333-4333-8333-333333333333",
  pid = "44444444-4444-4444-8444-444444444444",
  jid = "55555555-5555-4555-8555-555555555555",
  did = "66666666-6666-4666-8666-666666666666",
  rid = "77777777-7777-4777-8777-777777777777",
  fid = "88888888-8888-4888-8888-888888888888",
  h = "a".repeat(64);
for (const width of [1440, 1280, 390]) {
  const p = await browser.newPage({ viewport: { width, height: 950 } });
  p.setDefaultTimeout(6000);
  let abortNext = "",
    late = false,
    release,
    posts = 0,
    history = [];
  const operations = new Map(),
    errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  const intent = {
    schema_version: "intent-v2",
    intent_id: iid,
    conversation_id: cid,
    mode: "deep",
    goal: "分析现金流",
    company_ids: ["sample"],
    periods: [2024, 2025],
    metric_keys: ["operating_cash_flow"],
    clarifying_question: null,
    requires_confirmed_facts: true,
    scope: { scope_hash: h },
    provider_error: null,
  };
  const plan = {
    schema_version: "research-plan-v2",
    plan_id: pid,
    intent_id: iid,
    conversation_id: cid,
    mode: "deep",
    goal: intent.goal,
    revision: 1,
    plan_sha256: h,
    company_ids: intent.company_ids,
    periods: intent.periods,
    metric_keys: intent.metric_keys,
    roles: ["evidence", "finance"],
    limits: { model_attempts: 10 },
    scope: { scope_hash: h },
    provider_error: null,
  };
  const finding = {
    schema_version: "research-finding-v2",
    finding_id: fid,
    kind: "model_interpretation",
    text: "示意解读：变化待核实",
    origin: "model_draft",
    source_status: "not_applicable",
    financial_refs: [],
    evidence_refs: [{ document_id: "id-only" }],
    numeric_claim_status: "numeric_claim_unverified",
  };
  const queued = {
    schema_version: "showcase-job-v2",
    job_id: jid,
    plan_id: pid,
    conversation_id: cid,
    mode: "deep",
    state: "queued",
  };
  const done = {
    ...queued,
    scope: { scope_hash: h },
    state: "completed",
    created_at: "2026-01-01",
    steps: [
      { agent_id: "evidence", state: "completed", tools: ["read_evidence"] },
    ],
    usage: {
      attempts: 2,
      tools: 1,
      unknown_attempts: 0,
      provider_tokens_actual: null,
    },
    result: {
      schema_version: "showcase-research-result-v2",
      job_id: jid,
      mode: "deep",
      scope_hash: h,
      data_origin: "fake",
      findings: [
        finding,
        {
          schema_version: "research-finding-v2",
          finding_id: "99999999-9999-4999-8999-999999999999",
          kind: "unresolved_question",
          text: "缺少事实",
          unresolved_question: "请核对来源",
          origin: "system",
          source_status: "unresolved",
          financial_refs: [],
          evidence_refs: [],
          actions: [
            {
              kind: "review_sources",
              label: "核对来源",
              href: "/research?mode=operating",
            },
          ],
        },
      ],
      limitations: ["示意"],
    },
  };
  await p.route("**/research-flow", (r) =>
    r.fulfill({
      contentType: "text/html",
      body: `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><div style="background:#fff0be;text-align:center;padding:8px">UI_MOCK · 无真实模型/财务调用</div><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>t=>t;window.__vite_plugin_react_preamble_installed__=true;</script><script type="module">import React from '/node_modules/.vite/deps/react.js';import DOM from '/node_modules/.vite/deps/react-dom_client.js';import {ShowcaseResearchPanel} from '/src/product/showcaseResearch/ShowcaseResearchPanel.tsx';import '/src/product/tokens.css';class App extends React.Component{constructor(p){super(p);this.state={cid:'${cid}'};window.switchConversation=()=>this.setState({cid:'${cid2}'});}render(){return React.createElement('main',{style:{maxWidth:1000,margin:'30px auto',padding:16}},React.createElement(ShowcaseResearchPanel,{conversationId:this.state.cid,initialQuestion:'分析现金流'}));}}DOM.createRoot(document.getElementById('root')).render(React.createElement(App));</script></html>`,
    }),
  );
  await p.route("**/api/**", async (r) => {
    const u = new URL(r.request().url()),
      path = u.pathname,
      method = r.request().method(),
      body = r.request().postDataJSON();
    let data;
    if (method === "POST") {
      posts++;
      if (!body.operation_id) throw Error("missing operation UUID");
      if (path === "/api/research/intent") {
        if (body.requested_mode !== "deep" || body.conversation_id !== cid)
          throw Error("mode mismatch");
        data = intent;
        operations.set(body.operation_id, data);
      } else if (path === "/api/synthesis/plans") {
        if (body.intent_id !== iid) throw Error("intent mismatch");
        data = plan;
        operations.set(body.operation_id, data);
      } else if (path === "/api/deep-research/jobs") {
        if (
          body.approved_plan_id !== pid ||
          body.approved_plan_sha256 !== h ||
          body.confirmed !== true ||
          Object.hasOwn(body, "scope")
        )
          throw Error("plan authority");
        data = queued;
        history = [done];
        operations.set(body.operation_id, data);
      } else if (path === "/api/research/handoffs") {
        data = {
          schema_version: "research-handoff-v2",
          intent_id: iid,
          task_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          automatic_confirmation: false,
          automatic_resume: false,
        };
        operations.set(body.operation_id, data);
      } else if (path === "/api/showcase-reports/drafts") {
        data = {
          draft_id: did,
          snapshot: {
            schema_version: "verified-report-job-v2",
            job_id: jid,
            state: "completed",
            data_origin: "fake",
            workspace_id: "demo",
            findings: [],
          },
        };
        operations.set(body.operation_id, data);
      } else if (path === "/api/showcase-reports") {
        if (body.draft_id !== did || Object.hasOwn(body, "findings"))
          throw Error("report input");
        data = {
          schema_version: "showcase-report-v2",
          report_id: rid,
          revision: 1,
          snapshot: {
            schema_version: "verified-report-job-v2",
            job_id: jid,
            state: "completed",
            data_origin: "fake",
            workspace_id: "demo",
            findings: [],
          },
          title: body.title,
        };
        operations.set(body.operation_id, data);
      } else throw Error("unexpected POST " + path);
      if (abortNext === path) {
        abortNext = "";
        await r.abort();
        return;
      }
    } else if (path.includes("/research/conversations/"))
      data = { conversation_id: path.split("/").at(-2), items: [] };
    else if (path.endsWith("/jobs"))
      data = { schema_version: "showcase-job-list-v2", items: history };
    else if (path.endsWith("/events")) {
      if (late) await new Promise((resolve) => (release = resolve));
      data = {
        schema_version: "execution-events-v1",
        job_id: jid,
        events: ["准备来源", "核对引用", "已保存结论"].map((label, i) => ({
          schema_version: "execution-event-v1",
          job_id: jid,
          event_seq: i + 1,
          event_type: "phase",
          label,
          state: "completed",
          agent_id: "controller",
          public_summary: label,
        })),
        next_after_seq: 3,
      };
    } else if (path.endsWith("/jobs/" + jid)) data = done;
    else if (path.includes("/operations/")) {
      const id = path.split("/").at(-1);
      data = {
        operation_id: id,
        state: "completed",
        result: operations.get(id),
        error_code: null,
      };
    } else if (path === "/api/research/intents/" + iid) data = intent;
    else if (path === "/api/synthesis/plans/" + pid) data = plan;
    else throw Error("unexpected GET " + path);
    await r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
  await p.goto("http://127.0.0.1:5180/research-flow");
  await p.getByRole("button", { name: /深度研究/ }).click();
  await p.getByRole("button", { name: "明确解析意图" }).click();
  await p.getByRole("heading", { name: "研究提案" }).waitFor();
  await p.getByRole("button", { name: "明确准备财务核对任务" }).click();
  await p.getByRole("link", { name: "进入研究任务，由真人核对 →" }).waitFor();
  if (await p.getByRole("button", { name: "明确准备财务核对任务" }).isEnabled())
    throw Error("duplicate handoff enabled");
  await p.getByRole("button", { name: "明确准备研究计划" }).click();
  await p.getByRole("heading", { name: "研究计划" }).waitFor();
  if (await p.getByRole("button", { name: "确认并开始研究" }).isEnabled())
    throw Error("plan not confirmed");
  await p.getByLabel("我已阅读并确认此计划").check();
  await p.getByRole("button", { name: "确认并开始研究" }).click();
  await p.getByText("已保存结论", { exact: false }).waitFor();
  await p.getByText("数字陈述未核实").waitFor();
  await p.getByText("来源暂不可定位", { exact: false }).waitFor();
  await p.getByRole("link", { name: "核对来源 →" }).waitFor();
  await p.screenshot({ path: `${out}/workflow-${width}.png`, fullPage: true });
  if (await p.evaluate(() => document.documentElement.scrollWidth > innerWidth))
    throw Error("overflow");
  await p.getByRole("button", { name: "准备报告草稿" }).click();
  await p.getByLabel("报告标题").fill("模拟研究报告");
  await p.getByRole("button", { name: "明确创建报告" }).click();
  await p.getByRole("link", { name: "打开报告版本 1 ↗" }).waitFor();
  abortNext = "/api/research/intent";
  await p.getByRole("button", { name: "明确解析意图" }).click();
  await p.getByRole("button", { name: "只读查询原操作" }).waitFor();
  await p.reload();
  await p.getByRole("button", { name: /深度研究/ }).click();
  const before = posts;
  await p.getByRole("button", { name: "只读查询原操作" }).click();
  await p.getByRole("heading", { name: "研究提案" }).waitFor();
  if (posts !== before) throw Error("UNKNOWN replay");
  abortNext = "/api/synthesis/plans";
  await p.getByRole("button", { name: "明确准备研究计划" }).click();
  await p.getByRole("button", { name: "只读查询原操作" }).waitFor();
  await p.reload();
  await p.getByRole("button", { name: /深度研究/ }).click();
  let count = posts;
  await p.getByRole("button", { name: "只读查询原操作" }).click();
  await p.getByRole("heading", { name: "研究计划" }).waitFor();
  if (posts !== count) throw Error("plan replay");
  abortNext = "/api/deep-research/jobs";
  await p.getByLabel("我已阅读并确认此计划").check();
  await p.getByRole("button", { name: "确认并开始研究" }).click();
  await p.getByRole("button", { name: "只读查询原操作" }).waitFor();
  await p.reload();
  await p.getByRole("button", { name: /深度研究/ }).click();
  count = posts;
  await p.getByRole("button", { name: "只读查询原操作" }).click();
  await p.getByText("已保存结论", { exact: false }).waitFor();
  if (posts !== count) throw Error("job replay");
  abortNext = "/api/showcase-reports/drafts";
  await p.getByRole("button", { name: "准备报告草稿" }).click();
  await p.getByRole("button", { name: "只读查询原操作" }).waitFor();
  await p.reload();
  await p.getByRole("button", { name: /深度研究/ }).click();
  count = posts;
  await p.getByRole("button", { name: "只读查询原操作" }).click();
  await p.getByLabel("报告标题").waitFor();
  if (posts !== count) throw Error("draft replay");
  abortNext = "/api/showcase-reports";
  await p.getByLabel("报告标题").fill("模拟报告");
  await p.getByRole("button", { name: "明确创建报告" }).click();
  await p.getByRole("button", { name: "只读查询原操作" }).waitFor();
  await p.reload();
  await p.getByRole("button", { name: /深度研究/ }).click();
  count = posts;
  await p.getByRole("button", { name: "只读查询原操作" }).click();
  await p.getByRole("link", { name: "打开报告版本 1 ↗" }).waitFor();
  if (posts !== count) throw Error("report replay");
  await p.getByRole("button", { name: "明确解析意图" }).click();
  await p.getByRole("heading", { name: "研究提案" }).waitFor();
  await p.getByRole("button", { name: "明确准备研究计划" }).click();
  await p.getByLabel("我已阅读并确认此计划").check();
  late = true;
  await p.getByRole("button", { name: "确认并开始研究" }).click();
  await p.waitForFunction(() => true);
  for (let i = 0; i < 30 && !release; i++) await p.waitForTimeout(50);
  if (!release) throw Error("event was not requested");
  await p.evaluate(() => window.switchConversation());
  release();
  await p.waitForTimeout(150);
  if (await p.getByText("已保存结论", { exact: false }).count())
    throw Error("late event leaked");
  if (errors.length) throw Error(errors.join(";"));
  console.log(
    `PASS A03 workflow ${width}: plan, job, events, fake report, all UNKNOWN paths, CID fence`,
  );
  await p.close();
}
await browser.close();
