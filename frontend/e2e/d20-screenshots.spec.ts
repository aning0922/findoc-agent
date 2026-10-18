import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { harness, current, out, record } from "./d20-helpers.ts";
test("仅GET打开仍有效的2024双企分析，三指标结果与D8原PDF截图", async ({
  page,
}) => {
  await harness(page);
  const t = JSON.parse(readFileSync(`${out}/resumed-tasks.json`, "utf8"))[2];
  let posts = 0;
  page.on("request", (r) => {
    if (r.method() === "POST") posts++;
  });
  await current(page, t);
  await expect(page.locator(".operating-result")).toHaveCount(3, {
    timeout: 60000,
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page
    .getByRole("region", { name: "确定性分析结果" })
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: `${out}/workbench-comparison-results-1440.png`,
  });
  await page
    .locator('[data-testid^="slot-"]')
    .first()
    .getByRole("button", { name: "查看原 PDF" })
    .click();
  await expect(page.locator(".pdf-location")).toContainText("金额区域已核验", {
    timeout: 60000,
  });
  await page.screenshot({ path: `${out}/workbench-fact-pdf-1440.png` });
  expect(posts).toBe(0);
  record("results-read-proof", {
    task_id: t.task_id,
    revision: t.revision,
    post_count: posts,
    simulated_test: true,
    all_three_results_visible: true,
    real_d8_pdf: true,
  });
});
