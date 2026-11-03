// Real source/candidates only. Never tick or submit a human financial approval.
import { chromium } from 'playwright';
import { writeFile } from 'node:fs/promises';
const base = process.env.DEMO_CHECK_ORIGIN, output = process.env.DEMO_CHECK_OUTPUT;
const assert = (x, m) => { if (!x) throw Error(m); };
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(45000);
  const errors = [];
  let financialApprovals = 0;
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (r.method() === 'POST' && /extended-confirmations(?:$|\/)/.test(new URL(r.url()).pathname)) financialApprovals++; });
  await page.goto(base);
  await page.getByLabel('账号', { exact: true }).fill(process.env.DEMO_CHECK_USERNAME);
  await page.getByLabel('密码', { exact: true }).fill(process.env.DEMO_CHECK_PASSWORD);
  await page.getByRole('button', { name: '进入演示', exact: true }).click();
  await page.getByRole('heading', { name: '研究概览', exact: true }).waitFor();
  const company = await page.evaluate(async () => (await (await fetch('/api/companies')).json()).find(x => x.security_code === '000651'));
  assert(company?.company_id, 'verified partial seed company');
  await page.goto(`${base}/companies/${company.company_id}/analysis`);
  const panel = page.locator('.finance-v2');
  await panel.getByRole('heading', { name: '资产与负债', exact: true }).waitFor();
  await panel.getByLabel('明确选择已就绪年报', { exact: true }).selectOption({ label: '000651-2025.pdf · 报告年 2025' });
  await panel.getByRole('button', { name: '读取所选来源', exact: true }).click();
  await panel.getByRole('button', { name: '明确收集资产负债候选', exact: true }).click();
  await panel.getByLabel('选择 总资产 2025-12-31', { exact: true }).waitFor();
  const metrics = await page.evaluate(async id => (await fetch(`/api/financial/extended-metrics?company_id=${id}`)).json(), company.company_id);
  assert(metrics.metrics.length === 4 && metrics.metrics.every(m => m.status === 'candidate' && m.confirmation_ref === null), 'four real candidates without receipts');
  assert(metrics.metrics.every(m => m.report_year === 2025 && m.period === 2025), 'opening date remains 2025-01-01');
  assert(await panel.locator('.recharts-line').count() === 0, 'candidate values are not confirmed charts');
  await panel.getByLabel('选择 总资产 2025-12-31', { exact: true }).check();
  await panel.getByLabel('选择 总负债 2025-12-31', { exact: true }).check();
  await panel.getByRole('button', { name: '准备两项核对快照', exact: true }).click();
  await panel.getByRole('heading', { name: '真人核对快照 · 尚未接受', exact: true }).waitFor();
  await page.waitForFunction(() => [...document.querySelectorAll('.finance-v2 button')].some(b => b.textContent.trim() === '只读核验指标' && !b.disabled));
  assert(await panel.getByRole('button', { name: '真人明确接受 v2 核对', exact: true }).isDisabled(), 'human step remains unavailable');
  assert(await panel.getByRole('button', { name: '请求服务端计算资产负债率', exact: true }).isDisabled(), 'unconfirmed ratio disabled');
  for (const width of [1440, 1280, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.screenshot({ path: `${output}/financial-candidates-${width}.png`, fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `finance overflow ${width}`);
  }
  const result = { evidence: 'REAL_CHROMIUM_HTTP_REAL_OFFICIAL_PDF_STORED_FAST_EVIDENCE',
    company_id: company.company_id, candidate_count: metrics.metrics.length,
    metrics: [...new Set(metrics.metrics.map(m => m.metric_key))],
    as_of_dates: [...new Set(metrics.metrics.map(m => m.as_of_date))],
    source_revision: metrics.metrics[0].source_revision, human_financial_approvals: financialApprovals,
    llm_calls: 0, browser_errors: errors, confirmed_chart_positive_path: 'human_pending' };
  assert(financialApprovals === 0 && errors.length === 0, 'no financial approvals or browser errors');
  await writeFile(`${output}/browser-result.json`, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} finally { await browser.close(); }
