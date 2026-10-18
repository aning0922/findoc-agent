import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const proof = JSON.parse(readFileSync(process.env.D22_REPORT_PROOF!, "utf8"));
for (const width of [1024, 1280, 1440]) {
    for (const c of proof.cases) {
        test(`D22 ${c.title} ${c.task_id} ${width}`, async ({ page }) => {
            await page.setViewportSize({ width, height: 900 });
            await page.route("**/src/main.tsx*", route => route.fulfill({ contentType: "text/javascript", body: 'import "/tests/support/d20-entry.tsx";' }));
            const posts: string[] = [];
            page.on("request", r => { if (r.method() === "POST")
                posts.push(r.url()); });
            await page.goto(`/reports?company=${c.facts[0].company_id}`);
            await page.getByText("从已完成研究整理报告草稿", { exact: true }).click();
            await page.getByLabel("选择已完成研究").selectOption(c.task_id);
            expect(posts).toHaveLength(0);
            await page.getByRole("button", { name: "生成草稿", exact: true }).click();
            const report = page.getByRole("article", { name: "报告草稿预览" });
            await expect(report).toBeVisible();
            await expect(report.getByRole("heading", { name: c.title, exact: true })).toBeVisible();
            await expect(report).toContainText("simulated_test");
            await expect(report).toContainText("草稿尚未保存");
            for (const f of c.facts) {
                await expect(report.locator(`[data-fact-id="${f.fact_id}"] data`)).toHaveAttribute('value', f.value_cny_yuan); await expect(report.locator(`[data-fact-id="${f.fact_id}"] data`)).toHaveText(f.value_cny_yuan.replace(/\B(?=(\d{3})+(?!\d))/g, ','));
                await expect(report).toContainText(`${f.raw_value} ${f.raw_unit}`);
            }
            for (const a of c.analysis) {
                await expect(report.getByRole('region', { name: '财务变化表，可横向滚动' }).locator(`data[value="${a.absolute_change}"]`)).toHaveCount(1);
                await expect(report).toContainText(a.percentage_change + '%');
            }
            await expect(report).toContainText(c.template === "company_period_change" ? "同比" : "以 A 为基准的相对差异");
            await expect(report).toContainText("待人工语义复核");
            expect(posts).toHaveLength(1);
            expect(posts[0]).toContain('/reports/drafts');
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.screenshot({ path: `${process.env.D22_ARTIFACT_DIR}/${c.task_id}-${width}.png`, fullPage: true });
            await report.getByRole("button", { name: /原 PDF · 物理/ }).first().click();
            const pdf = page.getByRole('dialog', { name: '原 PDF · 财务事实' });
            await expect(pdf.locator('canvas')).toBeVisible({ timeout: 30000 });
            await page.keyboard.press('Escape');
            await page.reload();
            await expect(page.getByRole("article", { name: "报告草稿预览" })).toHaveCount(0);
            expect(posts).toHaveLength(1);
        });
    }
}
test('D22 late response, failure and production simulation guard', async ({ page }) => {
    await page.route("**/src/main.tsx*", r => r.fulfill({ contentType: "text/javascript", body: 'import "/tests/support/d20-entry.tsx";' }));
    await page.goto('/reports'); await page.getByText('从已完成研究整理报告草稿', { exact: true }).click();
    await page.getByLabel("选择已完成研究").selectOption(proof.cases[0].task_id);
    await page.route('**/api/reports/drafts', async (route) => { await new Promise(r => setTimeout(r, 500)); const response = await route.fetch(); await route.fulfill({ response }); });
    await page.getByRole('button', { name: '生成草稿', exact: true }).click();
    await page.getByLabel("选择已完成研究").selectOption(proof.cases[1].task_id);
    await page.waitForTimeout(800);
    await expect(page.getByRole('article', { name: '报告草稿预览' })).toHaveCount(0);
    await page.unroute('**/api/reports/drafts');
    await page.route('**/api/reports/drafts', r => r.fulfill({ status: 409, json: { error_code: 'source_changed' } }));
    await page.getByRole('button', { name: '生成草稿', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('草稿生成失败');
    await page.unroute('**/api/reports/drafts');
    await page.unroute('**/src/main.tsx*');
    await page.goto('/reports'); await page.getByText('从已完成研究整理报告草稿', { exact: true }).click();
    await page.getByLabel("选择已完成研究").selectOption(proof.cases[0].task_id);
    await page.getByRole('button', { name: '生成草稿', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('报告结构或研究身份不一致');
    await expect(page.getByRole('article', { name: '报告草稿预览' })).toHaveCount(0);
});
test('D22 current draft is revoked after actual D10 acceptance withdrawal', async ({ page }) => {
    const { execFileSync } = await import('node:child_process');
    await page.route("**/src/main.tsx*", r => r.fulfill({ contentType: "text/javascript", body: 'import "/tests/support/d20-entry.tsx";' }));
    await page.goto('/reports'); await page.getByText('从已完成研究整理报告草稿', { exact: true }).click();
    const c = proof.cases[0];
    await page.getByLabel("选择已完成研究").selectOption(c.task_id);
    await page.getByRole('button', { name: '生成草稿', exact: true }).click();
    await expect(page.getByRole('article', { name: '报告草稿预览' })).toBeVisible();
    execFileSync(process.env.D22_PYTHON!, ['-c', 'import sys;from pathlib import Path;from app.agent.sqlite_financial_facts import SQLiteRevenueConfirmationRepository;r=SQLiteRevenueConfirmationRepository(Path(sys.argv[1])/"documents.db",initialize=False);r.revoke_financial_receipt(workspace_id="demo",receipt_id=sys.argv[2],confirmation_kind="simulated_test",reason="D22 isolated browser revocation")', proof.runtime_root, c.facts[0].receipt_id], { cwd: process.env.D22_PRODUCT_ROOT });
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await expect(page.getByRole('alert')).toContainText('当前草稿资格已撤销');
    await expect(page.getByRole('article', { name: '报告草稿预览' })).toHaveCount(0);
});
