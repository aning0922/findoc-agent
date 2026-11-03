// Actual UI + public gateway + real local Vision on a labelled derived scan.
import { chromium } from 'playwright';
import { readFile, writeFile } from 'node:fs/promises';
const base = process.env.DEMO_CHECK_ORIGIN, output = process.env.DEMO_CHECK_OUTPUT;
const assert = (x, m) => { if (!x) throw Error(m); };
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(45000);
  const errors = [];
  let parsePosts = 0;
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (r.method() === 'POST' && r.url().includes('/parse-retry')) parsePosts++; });
  await page.goto(base);
  await page.getByLabel('账号', { exact: true }).fill(process.env.DEMO_CHECK_USERNAME);
  await page.getByLabel('密码', { exact: true }).fill(process.env.DEMO_CHECK_PASSWORD);
  await page.getByRole('button', { name: '进入演示', exact: true }).click();
  await page.getByRole('heading', { name: '研究概览', exact: true }).waitFor();
  await page.getByRole('link', { name: '企业与资料', exact: true }).click();
  await page.getByText('目录中没有要研究的企业？建立企业', { exact: true }).click();
  await page.getByLabel('企业正式名称', { exact: true }).fill('美的集团股份有限公司');
  await page.getByLabel('证券代码', { exact: true }).fill('000333');
  await page.getByLabel('交易所', { exact: true }).selectOption('SZSE');
  await page.getByRole('button', { name: '建立企业并开始研究', exact: true }).click();
  await page.waitForURL(u => u.pathname === '/research' && !!u.searchParams.get('company'));
  const company = new URL(page.url()).searchParams.get('company');
  await page.goto(`${base}/companies/${company}/documents`);
  await page.getByRole('button', { name: '上传并绑定年报', exact: true }).click();
  await page.getByLabel('报告年度', { exact: true }).fill('2025');
  await page.getByLabel('PDF 文件', { exact: true }).setInputFiles({
    name: '美的2025_公开年报第9页_派生扫描示例.pdf', mimeType: 'application/pdf', buffer: await readFile(process.env.DEMO_CHECK_SCAN_PATH),
  });
  // This binds metadata in an isolated test, not a financial fact ACCEPT/SAVE.
  await page.getByLabel('核对上传绑定', { exact: true }).check();
  const uploadResponse = page.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/api/report-documents'));
  await page.getByRole('button', { name: '提交 PDF 并绑定', exact: true }).click();
  const upload = await (await uploadResponse).json();
  assert(upload.document_id && upload.assessment.financial_facts === 'not_verified', 'metadata only; no financial approval');
  const panel = page.getByRole('region', { name: '解析质量', exact: true });
  await panel.getByRole('button', { name: '打开预览', exact: true }).click();
  await panel.getByText('尚无可读取的当前完整产物，可明确开始新解析。', { exact: true }).waitFor();
  assert(parsePosts === 0, 'GET preview does not run OCR');
  const parsedResponse = page.waitForResponse(r => r.request().method() === 'POST' && r.url().includes('/parse-retry'));
  await panel.getByRole('button', { name: '明确开始新解析', exact: true }).click();
  const parsed = await (await parsedResponse).json();
  assert(parsed.state === 'completed' && parsed.artifact_id, 'actual OCR completed');
  await panel.getByText('解析完成；转录和版面仍需人工核对。', { exact: true }).waitFor();
  const artifact = await page.evaluate(async ids => (await fetch(`/api/documents/${ids.doc}/parse-quality?artifact_id=${ids.art}`)).json(),
    { doc: upload.document_id, art: parsed.artifact_id });
  assert(artifact.engine.name.includes('Vision') && artifact.ocr_pages === 1 && artifact.pages_processed === 1, 'real Vision engine identity');
  assert(artifact.content_sha256 === '175235d1122aec489a6c943ec8c1f8f9fcb5ffdd0e75f938f5ce6080c8ed163a', 'derived scan original SHA');
  const first = artifact.pages[0], grid = first.tables[0];
  assert(first.lines.length > 20 && grid.cells.length > 20 && grid.quality === 'needs_review', 'real candidate grid');
  assert(artifact.legacy_source_verified === false && artifact.identity_assessment.financial_facts === 'not_verified', 'no legacy/financial promotion');
  await panel.locator('img').scrollIntoViewIfNeeded();
  await panel.locator('img').evaluate(img => img.decode());
  assert(await panel.locator('td span').count() === grid.cells.length, 'every actual OCR cell is visible without merging');
  for (const width of [1440, 1280, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.screenshot({ path: `${output}/ocr-${width}.png`, fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `OCR overflow ${width}`);
  }
  await page.reload();
  const restored = page.getByRole('region', { name: '解析质量', exact: true });
  await restored.getByRole('button', { name: '打开预览', exact: true }).click();
  await restored.getByText('已读取当前完整解析产物。', { exact: true }).waitFor();
  assert(parsePosts === 1, 'reload reads saved artifact without rerunning OCR');
  assert(errors.length === 0, `browser errors: ${errors.join('; ')}`);
  const result = { evidence: 'REAL_CHROMIUM_HTTP_REAL_APPLE_VISION_DERIVED_SCAN', document_id: upload.document_id,
    artifact_id: artifact.artifact_id, input_sha256: artifact.content_sha256, output_sha256: artifact.output_sha256,
    engine: artifact.engine, lines: first.lines.length, candidate_cells: grid.cells.length,
    candidate_rows: grid.row_count, candidate_columns: grid.column_count, parse_posts: parsePosts,
    llm_calls: 0, human_financial_approvals: 0, legacy_source_verified: false,
    limitations: ['derived raster scan of public Midea page 9, not a native scanned filing', 'OCR and layout unreviewed', 'no legacy identity/financial approval'] };
  await writeFile(`${output}/browser-result.json`, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} finally { await browser.close(); }
