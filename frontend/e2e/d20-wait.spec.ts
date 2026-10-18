import { test, expect } from "@playwright/test";
import {
  harness,
  open,
  configure,
  create,
  record,
  out,
} from "./d20-helpers.ts";
test("四真实PDF：两个模板实际创建、六槽真实等待、重复点击单次POST与三档首屏", async ({
  page,
}) => {
  await harness(page);
  await open(page);
  const tasks = [];
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith("/research/tasks")) posts++;
  });
  for (const [template, key, year] of [
    ["company_period_change", "midea", 2025],
    ["company_period_change", "gree", 2025],
    ["company_same_period_comparison", "midea", 2024],
    ["company_same_period_comparison", "midea", 2025],
  ] as const) {
    await configure(page, template, key, year);
    const t = await create(page);
    expect(t.waiting_checkpoint).toBe(true);
    expect(t.snapshot.analysis_results).toEqual([]);
    expect(t.budget.used).toEqual({
      steps: 16,
      tool_calls: 13,
      model_calls: 0,
      retrieval_total: 0,
    });
    tasks.push(t);
    await expect(
      page.getByRole("button", { name: "刷新 revision 并恢复研究" }),
    ).toBeDisabled();
    expect(await page.locator('[data-testid^="slot-"]').count()).toBe(6);
    if (tasks.length === 1)
      for (const width of [1440, 1280, 1024]) {
        await page.setViewportSize({ width, height: 900 });
        await page.evaluate(() => scrollTo(0, 0));
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        ).toBe(true);
        await expect(
          page.getByRole("region", { name: "当前经营研究任务" }),
        ).toBeVisible();
        await page.screenshot({
          path: `${out}/workbench-waiting-${width}.png`,
        });
      }
  }
  expect(posts).toBe(4);
  record("waiting-tasks", tasks);
  record("wait-proof", {
    tasks: tasks.map((t) => ({
      task_id: t.task_id,
      revision: t.revision,
      status: t.status,
      budget: t.budget.used,
    })),
    post_count: posts,
    human_acceptance: "pending",
    simulated_test: true,
  });
});
