import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { harness, current, out, record, metrics } from "./d20-helpers.ts";
test("D10真实invalid_reason逐槽展示撤销，历史事实失去资格时不发布金额或PDF", async ({
  page,
}) => {
  await harness(page);
  const task = JSON.parse(readFileSync(`${out}/resumed-tasks.json`, "utf8"))[0];
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST") posts++;
  });
  await current(page, task);
  for (const metric of metrics)
    await expect(page.getByTestId(`slot-first:${metric}`)).toContainText(
      "确认凭证已撤销",
      { timeout: 60000 },
    );
  await expect(page.locator(".operating-result")).toHaveCount(0);
  await expect(page.locator("canvas")).toHaveCount(0);
  expect(posts).toBe(0);
  record("invalid-reason-proof", {
    task_id: task.task_id,
    d10_reason: "acceptance_revoked",
    all_three_revoked_slots_show_reason: true,
    old_amounts_and_pdf_absent: true,
    post_count: posts,
  });
});
