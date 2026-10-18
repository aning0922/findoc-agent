import { test, expect } from "@playwright/test";
import { writeFileSync } from "node:fs";

test("已有企业时首页和正式研究页仍能明确建立下一家企业", async ({ page }) => {
  const catalog = await (await page.request.get("/api/companies")).json();
  expect(catalog.length).toBeGreaterThan(0);
  await page.goto("/");
  const entry = page.getByText("目录中没有要研究的企业？建立企业", {
    exact: true,
  });
  await expect(entry).toBeVisible();
  await entry.click();
  await page
    .getByLabel("企业正式名称", { exact: true })
    .fill("UX-P1 合成企业入口回归");
  await page.getByLabel("证券代码", { exact: true }).fill("000998");
  await page
    .getByRole("combobox", { name: "交易所", exact: true })
    .selectOption("SZSE");
  const created = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/companies") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "建立企业并开始研究", exact: true })
    .click();
  const response = await created;
  expect(response.status()).toBe(201);
  await page.waitForURL(/\/research\?/);
  await expect(
    page.getByText("目录中没有要研究的企业？建立企业", { exact: true }),
  ).toBeVisible();
  const refreshed = await (await page.request.get("/api/companies")).json();
  const company = refreshed.find(
    (c: { company_id: string }) =>
      c.company_id === new URL(page.url()).searchParams.get("company"),
  );
  expect(company).toBeTruthy();
  expect(company.security_code).toBe("000998");
  expect(company.name).toBe("UX-P1 合成企业入口回归");
  await page.screenshot({
    path: `${process.env.UX_ARTIFACT_DIR}/next-company-entry.png`,
    fullPage: true,
  });
  writeFileSync(
    `${process.env.UX_ARTIFACT_DIR}/d25-company-entry-proof.json`,
    JSON.stringify(
      {
        synthetic_company: true,
        isolated_test_runtime: true,
        human_acceptances: 0,
        prior_companies: catalog.length,
        company,
        home_creation: true,
        subsequent_research_creation_entry: true,
      },
      null,
      2,
    ),
  );
});
