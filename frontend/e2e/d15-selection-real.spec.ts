import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
const root = readFileSync("../data/30d-foundation/d15-product-runtime-path.txt", "utf8").trim();
const manifest = JSON.parse(readFileSync(`${root}/manifest.json`, "utf8"));
const midea = manifest.reports.find((r: any) => r.report_id === "midea-2025").source.company_id;
const gree = manifest.reports.find((r: any) => r.report_id === "gree-2025").source.company_id;

test("four real sources: explicit scope, zero automatic research and company reset", async ({ page }) => {
  const posts: string[] = [];
  page.on("request", r => { if (r.method() === "POST") posts.push(r.url()); });
  await page.goto(`/research?company=${midea}`);
  const panel = page.getByRole("region", { name: "研究资料选择" });
  await expect(panel.getByLabel(/美的集团股份有限公司 · 2025/)).toBeEnabled({ timeout: 60_000 });
  await expect(panel.getByRole("button", { name: "核验所选范围" })).toBeDisabled();
  await panel.getByLabel(/美的集团股份有限公司 · 2025/).check();
  await expect(panel.getByText("已选择 1 / 4 份")).toBeVisible();
  expect(posts).toEqual([]);
  await panel.getByRole("button", { name: "核验所选范围" }).click();
  await expect(panel.getByText(/已核验 1 份资料/)).toBeVisible({ timeout: 60_000 });
  await panel.getByLabel(/显示全部企业/).check();
  await expect(panel.getByText("已选择 0 / 4 份")).toBeVisible();
  for (const company of ["美的集团股份有限公司", "珠海格力电器股份有限公司"])
    for (const year of [2024, 2025]) await panel.getByLabel(new RegExp(`${company} · ${year}`)).check();
  await panel.getByRole("button", { name: "核验所选范围" }).click();
  await expect(panel.getByText(/已核验 4 份资料/)).toBeVisible({ timeout: 60_000 });
  for (const width of [1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(panel.getByRole("button", { name: "核验所选范围" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `../product/validation/d15-product-screenshots/selection-${width}.png`, fullPage: false });
  }
  await page.getByRole("combobox", { name: "当前企业" }).selectOption(gree);
  await expect(panel.getByText("已选择 0 / 4 份")).toBeVisible({ timeout: 60_000 });
  await expect(panel.getByRole("button", { name: "核验所选范围" })).toBeDisabled();
  expect(posts.length).toBe(2);
  expect(posts.every(p => p.endsWith("/research/selections/prepare"))).toBe(true);
});

test("failed source options disabled and preparation failure clears stale selection", async ({ page }) => {
  await page.route("**/api/research/sources", async route => {
    const r = await route.fetch(); const body = await r.json();
    const rows = body.documents.filter((d: any) => d.company_id === midea);
    rows[0].selectable = false; rows[0].reason = "source_changed";
    rows[0].status = "failed";
    await route.fulfill({ json: body });
  });
  await page.goto(`/research?company=${midea}`);
  const panel = page.getByRole("region", { name: "研究资料选择" });
  await expect(panel.getByLabel(/不可选择/)).toBeDisabled({ timeout: 60_000 });
  await panel.locator('input[type="checkbox"]:enabled').last().check();
  await page.route("**/api/research/selections/prepare", route => route.fulfill({ status: 409, json: { detail: "source_changed" } }));
  await panel.getByRole("button", { name: "核验所选范围" }).click();
  await expect(panel.getByText(/所选范围已失效或核验失败/)).toBeVisible();
  await expect(panel.getByRole("button", { name: "核验所选范围" })).toBeDisabled();
});

test("late preparation after company switch cannot revive old scope", async ({ page }) => {
  let release!: () => void;
  const waiting = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/research/selections/prepare", async route => {
    const response = await route.fetch(); await waiting; await route.fulfill({ response }).catch(() => {});
  });
  await page.goto(`/research?company=${midea}`);
  const panel = page.getByRole("region", { name: "研究资料选择" });
  await expect(panel.getByLabel(/美的集团股份有限公司 · 2025/)).toBeEnabled({ timeout: 60_000 });
  await panel.getByLabel(/美的集团股份有限公司 · 2025/).check();
  await panel.getByRole("button", { name: "核验所选范围" }).click();
  await page.getByRole("combobox", { name: "当前企业" }).selectOption(gree);
  release();
  await expect(panel.getByText("已选择 0 / 4 份")).toBeVisible({ timeout: 60_000 });
  await expect(panel.getByText(/已核验 1 份资料/)).toHaveCount(0);
  await page.unrouteAll({ behavior: "ignoreErrors" });
});
