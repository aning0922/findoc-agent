import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { randomUUID, createHash } from "node:crypto";
import {
  harness,
  open,
  current,
  tasks,
  accept,
  reports,
  record,
  out,
  report,
  configure,
  create,
} from "./d20-helpers.ts";
let resumed: any[] = [];
test("新进程与新浏览器仅GET恢复真实等待，历史读回不消费预算", async ({
  page,
  request,
}) => {
  await harness(page);
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST") posts++;
  });
  await current(page, tasks()[0]);
  await expect(
    page.getByRole("button", { name: "刷新 revision 并恢复研究" }),
  ).toBeDisabled();
  await page.reload();
  await expect(
    page.getByRole("region", { name: "当前经营研究任务" }),
  ).toContainText("等待人工确认");
  expect(posts).toBe(0);
  for (const t of tasks()) {
    const r = await request.get(`/api/research/tasks/${t.task_id}`);
    expect(r.status()).toBe(200);
    const value = await r.json();
    expect(value.budget.used).toEqual(t.budget.used);
    expect(value.revision).toBe(t.revision);
  }
  record("restart-proof", {
    fresh_server: true,
    new_browser: true,
    get_only: true,
    post_count: posts,
    tasks: tasks().map((t) => t.task_id),
  });
});
test("既有D9/D10模拟接受与事实入库，六事实ID显式恢复两个模板，PDF与服务预算", async ({
  page,
  request,
}) => {
  await harness(page);
  const groups = [];
  for (const r of reports) groups.push(await accept(page, r));
  record("simulated-groups", groups);
  for (const t of tasks()) {
    await current(page, t);
    const button = page.getByRole("button", {
      name: "刷新 revision 并恢复研究",
    });
    await expect(button).toBeEnabled({ timeout: 60000 });
    let payload: any;
    page.once("request", () => {});
    const response = page.waitForResponse(
      (r) =>
        r.url().endsWith(`/${t.task_id}/resume`) &&
        r.request().method() === "POST",
    );
    await button.dblclick();
    const r = await response;
    payload = r.request().postDataJSON();
    const v = await r.json();
    expect(r.status()).toBe(200);
    expect(payload.facts).toHaveLength(6);
    expect(payload.expected_revision).toBe(t.revision);
    expect(
      payload.facts.every(
        (f: any) =>
          Object.keys(f).sort().join(",") ===
          "fact_id,fact_set_id,metric_key,side",
      ),
    ).toBe(true);
    expect(v.status).toBe("collecting_explanation");
    const gold = JSON.parse(
      readFileSync("../product/validation/manual-benchmark.json", "utf8"),
    ).facts;
    for (const a of v.snapshot.analysis_results) {
      const fs = a.current
        ? [a.current, a.previous]
        : a.rows.flatMap((r: any) => [r.a, r.b]);
      for (const f of fs) {
        const original = reports.find(
          (r) => r.source.document_id === f.document_id,
        )!.report_id;
        const expected = gold.find(
          (g: any) =>
            g.document_id === original &&
            g.period === f.period &&
            g.metric === f.metric_key,
        );
        expect(f.value_cny_yuan).toBe(expected.value_cny_yuan);
        expect(f.raw_value).toBe(expected.raw_value);
      }
    }
    expect(v.budget.used).toEqual({
      steps: 30,
      tool_calls: 24,
      model_calls: 0,
      retrieval_total: 12,
    });
    await expect(page.locator(".operating-result")).toHaveCount(3, {
      timeout: 60000,
    });
    await expect(
      page.getByRole("region", { name: "当前经营研究任务" }),
    ).toContainText("研究解释待完成");
    expect(await page.getByText("最终完成", { exact: true }).count()).toBe(0);
    const replay = await request.post(
      `/api/research/tasks/${t.task_id}/resume`,
      { data: payload },
    );
    expect(await replay.json()).toEqual(v);
    const stale = await request.post(
      `/api/research/tasks/${t.task_id}/resume`,
      { data: { ...payload, operation_id: randomUUID() } },
    );
    expect(stale.status()).toBe(409);
    expect((await stale.json()).error_code).toBe("task_revision_conflict");
    const slots = page.locator('[data-testid^="slot-"]');
    for (let i = 0; i < 6; i++)
      await expect(slots.nth(i)).toContainText("已核准有效事实 ID");
    const f = groups
      .flatMap((g) => g.facts)
      .find((f) => f.fact_id === v.active_input.first.choices[0].fact_id);
    const pdf = await request.get(
      `/api/documents/${f.document_id}/file?company_id=${f.company_id}&source_revision=${f.source_revision}`,
    );
    expect(pdf.status()).toBe(200);
    expect(
      createHash("sha256")
        .update(await pdf.body())
        .digest("hex"),
    ).toBe(f.content_sha256);
    await slots.first().getByRole("button", { name: "查看原 PDF" }).click();
    await expect(page.locator("canvas")).toBeVisible({ timeout: 60000 });
    await expect(page.locator(".pdf-location")).toContainText("金额区域已核验");
    await page.getByRole("button", { name: "收起证据侧栏" }).click();
    if (resumed.length === 0)
      for (const width of [1440, 1280, 1024]) {
        await page.setViewportSize({ width, height: 900 });
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        await page
          .getByRole("region", { name: "当前经营研究任务" })
          .scrollIntoViewIfNeeded();
        await page.screenshot({
          path: `${out}/workbench-analysis-${width}.png`,
        });
      }
    resumed.push(v);
  }
  record("resumed-tasks", resumed);
  record("resume-proof", {
    templates: resumed.map((t) => t.input.template),
    simulated_test: true,
    human_acceptance: "pending",
    explicit_d9_d10_ui: true,
    model_calls: 0,
    retrieval: "empty controlled substitute",
    final_content: null,
  });
});
test("正式UI及正式D19准入拒绝simulated_test，历史GET零执行不变", async ({
  page,
  request,
}) => {
  const t = JSON.parse(readFileSync(`${out}/resumed-tasks.json`, "utf8"))[2];
  await current(page, t);
  await expect(page.locator(".operating-result")).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "六项事实准备状态" }),
  ).toContainText("旧分析及 PDF 引用已撤下", { timeout: 60000 });
  const r = await request.post("/api/__test__/production/research/tasks", {
    data: { operation_id: randomUUID(), input: t.active_input },
  });
  expect(r.status()).toBe(200);
  const v = await r.json();
  expect(v.status).toBe("awaiting_human_confirmation");
  expect(v.snapshot.analysis_results).toEqual([]);
  const attempted = await request.post(
    `/api/__test__/production/research/tasks/${v.task_id}/resume`,
    {
      data: {
        operation_id: randomUUID(),
        expected_revision: v.revision,
        facts: ["first", "second"].flatMap((side) =>
          t.active_input[side].choices.map((c: any) => ({
            side,
            metric_key: c.metric_key,
            fact_set_id: c.fact_set_id,
            fact_id: c.fact_id,
          })),
        ),
      },
    },
  );
  expect(attempted.status()).toBe(409);
  const rejected = await attempted.json();
  expect(rejected.status).toBe("refused");
  expect(rejected.snapshot.analysis_results).toEqual([]);
  record("production-refusal", {
    create_status: v.status,
    resume_status: rejected.status,
    error_code: rejected.error_code,
    test_facts_rejected: true,
  });
  const pending = await request.post(
    "/api/__test__/production/research/tasks",
    {
      data: { operation_id: randomUUID(), input: tasks()[0].input },
    },
  );
  expect(pending.status()).toBe(200);
  const waiting = await pending.json();
  expect(waiting.status).toBe("awaiting_human_confirmation");
  expect(waiting.snapshot.test_mode).toBeNull();
  await current(page, waiting);
  await expect(
    page.getByRole("button", { name: "刷新 revision 并恢复研究" }),
  ).toBeDisabled();
  await expect(page.getByLabel("first 期间")).toContainText("2025");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.evaluate(() => scrollTo(0, 0));
  await expect(
    page.getByRole("region", { name: "当前任务摘要" }),
  ).toBeInViewport();
  await page.screenshot({
    path: `${out}/workbench-production-waiting-1440.png`,
  });
  record("production-waiting", {
    task_id: waiting.task_id,
    revision: waiting.revision,
    status: waiting.status,
    test_mode: waiting.snapshot.test_mode,
    model_calls: waiting.budget.used.model_calls,
  });
});
test("真实创建响应丢失：按operation GET恢复，404和重开不重放POST", async ({
  page,
}) => {
  await harness(page);
  await open(page);
  await configure(page);
  let posts = 0,
    op = "";
  await page.route("**/api/research/tasks", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    posts++;
    op = route.request().postDataJSON().operation_id;
    await route.fetch();
    await route.abort("failed");
  });
  await page
    .getByRole("button", { name: "创建服务端研究任务", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("网络响应未知", {
    timeout: 60000,
  });
  expect(posts).toBe(1);
  await page.reload();
  await expect(
    page.getByRole("region", { name: "当前经营研究任务" }),
  ).toContainText("等待人工确认");
  expect(posts).toBe(1);
  await page.route(`**/by-operation/${op}`, (route) =>
    route.fulfill({ status: 404, json: { error_code: "resource_not_found" } }),
  );
  await page.getByText("已保存任务身份", { exact: true }).click();
  await page.getByRole("button", { name: "按操作 ID 只读查询" }).click();
  await expect(
    page.getByRole("button", { name: "结束查询，允许显式新建" }),
  ).toBeVisible();
  expect(posts).toBe(1);
  record("unknown-proof", {
    post_count: posts,
    operation_id: op,
    real_post_response_lost: true,
    get_404_no_replay: true,
  });
});
test("真实恢复响应丢失只读恢复，历史使用服务端分页且GET不消耗预算", async ({
  page,
  request,
}) => {
  await harness(page);
  await open(page);
  await configure(page);
  const t = await create(page);
  const button = page.getByRole("button", { name: "刷新 revision 并恢复研究" });
  await expect(button).toBeEnabled({ timeout: 60000 });
  let posts = 0,
    op = "";
  await page.route("**/api/research/tasks/*/resume", async (route) => {
    posts++;
    op = route.request().postDataJSON().operation_id;
    await route.fetch();
    await route.abort("failed");
  });
  await button.dblclick();
  await expect(page.getByRole("alert")).toContainText("网络响应未知", {
    timeout: 60000,
  });
  await page.getByRole("button", { name: "按操作 ID 只读查询" }).click();
  await expect(page.locator(".operating-result")).toHaveCount(3, {
    timeout: 60000,
  });
  expect(posts).toBe(1);
  let readPosts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST") readPosts++;
  });
  const before = (
    await (await request.get(`/api/research/tasks/${t.task_id}`)).json()
  ).budget;
  const list = page.getByRole("complementary", { name: "经营研究历史" });
  await list.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(
    list.getByRole("button", { name: "读取下一页历史" }),
  ).toBeVisible();
  await list.getByRole("button", { name: "读取下一页历史" }).click();
  const after = (
    await (await request.get(`/api/research/tasks/${t.task_id}`)).json()
  ).budget;
  expect(after).toEqual(before);
  expect(readPosts).toBe(0);
  record("resume-unknown-history-proof", {
    task_id: t.task_id,
    operation_id: op,
    resume_post_count: posts,
    read_post_count: readPosts,
    budget_unchanged: true,
    real_server_pagination: true,
  });
});
test("无财报空状态不生成版本、事实或任务", async ({ page }) => {
  await harness(page);
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST") posts++;
  });
  await page.route("**/api/research/sources", (route) =>
    route.fulfill({
      json: {
        schema_version: "research-source-options-v1",
        max_selected_documents: 4,
        documents: [],
      },
    }),
  );
  await open(page);
  await expect(
    page.getByText("无可用财报，请在资料库上传并核准来源。").first(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "创建服务端研究任务", exact: true }),
  ).toBeDisabled();
  expect(posts).toBe(0);
  record("empty-proof", { controlled_empty_catalog: true, post_count: posts });
});
test("迟到历史、旧revision、企业和模板切换不能恢复旧结果", async ({ page }) => {
  await harness(page);
  const values = JSON.parse(readFileSync(`${out}/resumed-tasks.json`, "utf8")),
    t = values[0];
  await current(page, t);
  await expect(page.locator(".operating-result")).toHaveCount(3, {
    timeout: 60000,
  });
  let release!: () => void;
  const wait = new Promise<void>((resolve) => (release = resolve));
  await page.route(`**/api/research/tasks/${t.task_id}`, async (route) => {
    const response = await route.fetch();
    await wait;
    await route.fulfill({ response }).catch(() => {});
  });
  await page.getByRole("button", { name: "刷新当前任务" }).click();
  await page.getByRole("button", { name: /两企业同期间比较/ }).click();
  release();
  await expect(page.locator(".operating-result")).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "当前经营研究任务" }),
  ).toHaveCount(0);
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await harness(page);
  await page.route(`**/api/research/tasks/${t.task_id}`, (route) =>
    route.fulfill({ json: { ...t, revision: t.revision - 1 } }),
  );
  await current(page, t, false);
  await expect(page.getByRole("alert")).toContainText("迟到的旧 revision");
  await expect(page.locator(".operating-result")).toHaveCount(0);
  await page
    .getByRole("combobox", { name: "当前企业" })
    .selectOption(report("gree").source.company_id);
  await expect(page.locator(".operating-result")).toHaveCount(0);
  record("ownership-proof", {
    late_response_ignored: true,
    stale_revision_rejected: true,
    template_and_company_switch_clear: true,
  });
});
test("202执行未知、409/503业务终态、操作冲突、预算耗尽与中断（明确响应注入）", async ({
  page,
}) => {
  await harness(page);
  const t = JSON.parse(readFileSync(`${out}/resumed-tasks.json`, "utf8"))[0];
  for (const [http, status, error] of [
    [202, "analyzing", null],
    [409, "refused", "selection_mismatch"],
    [503, "failed", "budget_tool_calls_exhausted"],
    [503, "failed", "interrupted_unknown_execution"],
  ] as const) {
    const v = {
      ...t,
      status,
      execution_status: http === 202 ? "running" : "idle",
      error_code: error,
      snapshot: null,
      waiting_checkpoint: false,
    };
    await page.route(`**/api/research/tasks/${t.task_id}`, (route) =>
      route.fulfill({ status: http, json: v }),
    );
    await current(page, v);
    await expect(page.locator(".operating-result")).toHaveCount(0);
    await expect(
      page.getByRole("region", { name: "当前经营研究任务" }),
    ).toContainText(
      http === 202
        ? "执行中 / 结果等待读回"
        : status === "refused"
          ? "研究被拒绝"
          : "任务失败",
    );
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await harness(page);
  }
  await page.route(`**/api/research/tasks/${t.task_id}`, (route) =>
    route.fulfill({
      status: 409,
      json: { error_code: "operation_request_conflict" },
    }),
  );
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
    { company: report("midea").source.company_id, t },
  );
  await open(page);
  await expect(page.getByRole("alert")).toContainText("操作 ID 冲突");
  record("injected-states", {
    response_injection_only: [
      202,
      409,
      503,
      "selection_mismatch",
      "budget_tool_calls_exhausted",
      "interrupted_unknown_execution",
      "operation_request_conflict",
    ],
  });
});
test("真实凭证撤销与真实来源纠错，已保存分析不可作为当前结果", async ({
  page,
  request,
}) => {
  await harness(page);
  const values = JSON.parse(readFileSync(`${out}/resumed-tasks.json`, "utf8")),
    groups = JSON.parse(readFileSync(`${out}/simulated-groups.json`, "utf8"));
  await current(page, values[0]);
  await expect(page.locator(".operating-result")).toHaveCount(3, {
    timeout: 60000,
  });
  const g = groups.find(
      (g: any) => g.document_id === report("midea", 2025).source.document_id,
    ),
    r = await request.post(
      `/api/financial-facts/acceptances/${g.fact_set_id}/revoke`,
      { data: { reason: "D20 isolated simulated receipt revocation" } },
    );
  expect(r.status()).toBe(200);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.locator(".operating-result")).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "六项事实准备状态" }),
  ).toContainText("旧分析及 PDF 引用已撤下", { timeout: 60000 });
  await current(page, values[1]);
  await expect(page.locator(".operating-result")).toHaveCount(3, {
    timeout: 60000,
  });
  const s = report("gree", 2025).source;
  const correction = await request.post(
    `/api/documents/${s.document_id}/binding-corrections`,
    {
      data: {
        expected_attempt: s.attempt,
        metadata: {
          company_id: s.company_id,
          report_year: 2025,
          report_type: "annual",
          basis: "unknown",
          period_start: "2025-01-01",
          period_end: "2025-12-31",
        },
        reason: "D20 isolated source correction",
      },
    },
  );
  expect(correction.status()).toBe(200);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.locator(".operating-result")).toHaveCount(0);
  await expect(page.locator("canvas")).toHaveCount(0);
  record("invalidated-proof", {
    real_revocation: true,
    real_source_correction: true,
    old_amounts_and_pdf_removed: true,
  });
});
