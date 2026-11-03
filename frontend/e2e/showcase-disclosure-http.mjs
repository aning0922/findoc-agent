// Real official download + real PDF parser/BGE/Milvus through the actual demo UI.
import { chromium } from 'playwright';
import { writeFile } from 'node:fs/promises';
const base = process.env.DEMO_CHECK_ORIGIN, output = process.env.DEMO_CHECK_OUTPUT;
const assert = (x, message) => { if (!x) throw Error(message); };
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(45000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(base);
  await page.getByRole('button', { name: '进入演示', exact: true }).waitFor();
  assert(await page.locator('.demo-story h1').evaluate(el => getComputedStyle(el).color) === 'rgb(255, 255, 255)', 'cover contrast');
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.screenshot({ path: `${output}/login-${width}.png`, fullPage: true });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByLabel('账号', { exact: true }).fill(process.env.DEMO_CHECK_USERNAME);
  await page.getByLabel('密码', { exact: true }).fill(process.env.DEMO_CHECK_PASSWORD);
  await page.getByRole('button', { name: '进入演示', exact: true }).click();
  await page.getByRole('heading', { name: '研究概览', exact: true }).waitFor();
  await page.getByRole('link', { name: '企业与资料', exact: true }).click();
  await page.getByText('目录中没有要研究的企业？建立企业', { exact: true }).click();
  await page.getByLabel('企业正式名称', { exact: true }).fill('珠海格力电器股份有限公司');
  await page.getByLabel('证券代码', { exact: true }).fill('000651');
  await page.getByLabel('交易所', { exact: true }).selectOption('SZSE');
  await page.getByRole('button', { name: '建立企业并开始研究', exact: true }).click();
  await page.waitForURL(url => url.pathname === '/research' && !!url.searchParams.get('company'));
  const company = await page.evaluate(async () => {
    const id = new URL(location.href).searchParams.get('company');
    return (await fetch(`/api/companies/${encodeURIComponent(id)}`)).json();
  });
  assert(company.company_id && company.security_code === '000651', 'company creation');
  await page.goto(`${base}/companies/${encodeURIComponent(company.company_id)}/documents`);
  await page.getByRole('heading', { name: '查找企业年报', exact: true }).waitFor();
  await page.getByLabel('报告年度（可选）', { exact: true }).fill('2025');
  await page.getByRole('button', { name: '查询目录', exact: true }).click();
  await page.getByRole('button', { name: '明确导入此年报', exact: true }).waitFor();
  for (const width of [1440, 1280, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.screenshot({ path: `${output}/catalog-${width}.png`, fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `catalog overflow ${width}`);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  const started = Date.now();
  const receipt = page.waitForResponse(r => r.url().endsWith('/api/disclosures/import') && r.request().method() === 'POST', { timeout: 90000 });
  await page.getByRole('button', { name: '明确导入此年报', exact: true }).click();
  const response = await receipt, imported = await response.json();
  assert(response.ok() && imported.state === 'completed', 'real official import completed');
  const documentId = imported.result.document_id;
  assert(imported.result.disclosure_import.sha256 === '7cc972f2d199e2ec3797cc5da479e8268afa59b77875770de3bcd3648242fb8c', 'official SHA');
  await page.getByText('已完成上传与企业绑定。解析状态请在资料目录另行查看；这不代表财务数据已确认。', { exact: true }).waitFor();
  let record;
  const deadline = Date.now() + 240000;
  while (Date.now() < deadline) {
    record = await page.evaluate(async id => (await fetch(`/api/documents/${id}`)).json(), documentId);
    if (record.status === 'ready') break;
    assert(record.status !== 'failed', `document processing failed: ${record.error_code}`);
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  assert(record.status === 'ready', 'real BGE/Milvus indexing reached READY within budget');
  const source = await page.evaluate(async id => (await fetch(`/api/documents/${id}/source`)).json(), documentId);
  assert(source.physical_pages === 219 && source.report_year === 2025 && source.assessment.financial_facts === 'not_verified', 'source identity and no financial approval');
  await page.getByRole('button', { name: '刷新资料与绑定（只读）', exact: true }).click();
  await page.getByText('PDF 处理就绪', { exact: true }).waitFor();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.screenshot({ path: `${output}/import-ready-${width}.png`, fullPage: true });
  }
  assert(errors.length === 0, `browser errors: ${errors.join('; ')}`);
  const result = { evidence: 'REAL_CHROMIUM_UI_OFFICIAL_HTTP_REAL_FAST_PARSE_BGE_MILVUS',
    document_id: documentId, pdf_sha256: source.content_sha256, physical_pages: source.physical_pages,
    source_revision: source.source_revision, status: record.status, elapsed_seconds: (Date.now() - started) / 1000,
    llm_calls: 0, human_financial_approvals: 0, browser_errors: errors,
    limitations: ['verified demo catalog only', 'publish date/amendment unknown', 'financial facts not verified'] };
  await writeFile(`${output}/browser-result.json`, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} finally { await browser.close(); }
