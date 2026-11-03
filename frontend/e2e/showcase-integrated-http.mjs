// Actual product entry + Vite proxy + real child runtime, no request interception.
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
const base = process.env.DEMO_CHECK_ORIGIN;
const output = process.env.DEMO_CHECK_OUTPUT;
if (!base || !output) throw Error('Isolated runner configuration required');
await mkdir(output, { recursive: true });
const launches = await Promise.all([chromium.launch({ headless: true }), chromium.launch({ headless: true })]);
const assert = (value, message) => { if (!value) throw Error(message); };
const errors = [];
try {
  const pages = await Promise.all(launches.map(b => b.newPage({ viewport: { width: 1440, height: 1000 } })));
  for (const page of pages) { page.setDefaultTimeout(45000); page.on('pageerror', e => errors.push(e.message)); }
  const [a, b] = pages;
  async function login(page) {
    await page.goto(base);
    await page.getByLabel('账号', { exact: true }).fill(process.env.DEMO_CHECK_USERNAME);
    await page.getByLabel('密码', { exact: true }).fill(process.env.DEMO_CHECK_PASSWORD);
    await page.getByRole('button', { name: '进入演示', exact: true }).click();
  }
  await a.goto(base);
  await a.getByRole('button', { name: '进入演示', exact: true }).waitFor();
  assert(await a.locator('.demo-story h1').evaluate(el => getComputedStyle(el).color) === 'rgb(255, 255, 255)',
    'actual global CSS preserves login cover contrast');
  for (const width of [1440, 1280, 390]) {
    await a.setViewportSize({ width, height: 1000 });
    await a.screenshot({ path: `${output}/login-${width}.png`, fullPage: true });
    assert(await a.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `login overflow ${width}`);
  }
  await a.setViewportSize({ width: 1440, height: 1000 });
  await login(a);
  await a.getByRole('heading', { name: '研究概览', exact: true }).waitFor();
  const initial = await a.evaluate(async () => (await fetch('/api/demo/session')).json());
  assert(initial.lease_generation >= 1 && initial.can_review === false, 'shared login grants no review authority');
  const counts = await a.evaluate(async () => (await fetch('/api/dashboard/overview')).json());
  assert(counts.kpis.companies === Number(process.env.DEMO_CHECK_EXPECTED_COMPANIES || 1) && counts.kpis.reports_ready === Number(process.env.DEMO_CHECK_EXPECTED_READY || 0), 'pinned seed overview inventory');
  async function inventory(page) {
    return page.evaluate(async scanId => ({
      overview: await (await fetch('/api/dashboard/overview')).json(),
      reports: await (await fetch('/api/showcase-archive/items?kind=report')).json(),
      jobs: await (await fetch('/api/showcase-archive/items?kind=job')).json(),
      memories: await (await fetch('/api/research-memories')).json(),
      conversations: await (await fetch('/api/conversations')).json(),
      ocr: scanId ? await (await fetch(`/api/documents/${scanId}/parse-quality`)).json() : null,
    }), process.env.DEMO_CHECK_OCR_DOCUMENT_ID || '');
  }
  const pinned = await inventory(a);
  if (pinned.ocr) assert(pinned.ocr.source_status === 'current' && pinned.ocr.pages[0].lines.length === 68, 'seed OCR artifact remains real/current');
  assert(await a.locator('.sd-hero h1').evaluate(el => getComputedStyle(el).color) === 'rgb(255, 255, 255)',
    'actual product global CSS preserves hero contrast');
  await a.evaluate(() => sessionStorage.setItem('findoc:conversation-operations:v1', 'UNKNOWN-SAME-LEASE-CHECK'));
  await a.reload();
  await a.getByRole('heading', { name: '研究概览', exact: true }).waitFor();
  assert(await a.evaluate(() => sessionStorage.getItem('findoc:conversation-operations:v1')) === 'UNKNOWN-SAME-LEASE-CHECK',
    'same verified lease hard reload preserves unknown operation hint');
  for (const width of [1440, 1280, 390]) {
    await a.setViewportSize({ width, height: 1000 });
    await a.screenshot({ path: `${output}/home-${width}.png`, fullPage: true });
    assert(await a.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `home overflow ${width}`);
  }
  await a.getByLabel('界面示意数据', { exact: true }).check();
  await a.locator('.showcase-dashboard .recharts-line').waitFor();
  for (const width of [1440, 390]) {
    await a.setViewportSize({ width, height: 1000 });
    await a.screenshot({ path: `${output}/home-illustrative-${width}.png`, fullPage: true });
  }
  await a.getByLabel('界面示意数据', { exact: true }).uncheck();
  await a.setViewportSize({ width: 1440, height: 1000 });
  // V1.2 mutation body has no operation_id; bootstrap must add the gateway envelope.
  const dirty = await a.evaluate(async () => {
    const r = await fetch('/api/companies', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: '复位验证临时企业', security_code: 'RESET-CHECK', exchange: 'DEMO' }) });
    return { status: r.status, data: await r.json() };
  });
  assert(dirty.status === 201 && dirty.data.company_id, 'legacy mutation envelope reaches real runtime');
  if (Number(process.env.DEMO_CHECK_EXPECTED_READY || 0) > 0) {
    await a.evaluate(async () => {
      const post = async (path, body) => { const response = await fetch('/api'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!response.ok)throw Error('dirty seed write failed');return response.json(); };
      const sources = await (await fetch('/api/research/sources')).json();
      await post('/conversations',{operation_id:crypto.randomUUID(),document_ids:[sources.documents.find(d=>d.selectable).document_id]});
      await post('/research-memories',{operation_id:crypto.randomUUID(),type:'note',text:'复位隔离测试临时笔记；不是财务确认。',confirmed:true});
    });
  }
  await login(b);
  await b.getByRole('heading', { name: '演示空间正在使用', exact: true }).waitFor();
  assert(await b.getByRole('button', { name: '确认接管', exact: true }).isDisabled(), 'takeover requires explicit confirmation');
  await b.getByLabel('共享演示密码', { exact: true }).fill(process.env.DEMO_CHECK_PASSWORD);
  await b.getByLabel('所有者口令', { exact: true }).fill(process.env.DEMO_CHECK_OWNER_PASSWORD);
  await b.getByLabel('我确认结束当前体验并重置演示环境').check();
  await b.getByRole('button', { name: '确认接管', exact: true }).click();
  await b.getByRole('heading', { name: '研究概览', exact: true }).waitFor();
  const after = await b.evaluate(async () => ({ session: await (await fetch('/api/demo/session')).json(),
    companies: await (await fetch('/api/companies')).json() }));
  assert(after.session.lease_generation > initial.lease_generation && after.companies.length === Number(process.env.DEMO_CHECK_EXPECTED_COMPANIES || 1),
    'takeover switches generation and restores seed');
  const restored = await inventory(b);
  assert(restored.overview.kpis.reports === pinned.overview.kpis.reports && restored.overview.kpis.research_completed === pinned.overview.kpis.research_completed, 'historical KPI restored');
  assert(restored.memories.items.length === pinned.memories.items.length && restored.conversations.items.length === pinned.conversations.items.length, 'visitor notes/conversations removed');
  assert(JSON.stringify(restored.reports.items.map(x=>[x.archive_id,x.revision,x.current_source_status])) === JSON.stringify(pinned.reports.items.map(x=>[x.archive_id,x.revision,x.current_source_status])), 'preset reports and source state restored');
  if (pinned.ocr) assert(restored.ocr.artifact_id === pinned.ocr.artifact_id && restored.ocr.output_sha256 === pinned.ocr.output_sha256, 'same OCR output restored without new engine execution');
  assert(!after.companies.some(c => c.company_id === dirty.data.company_id), 'visitor mutation gone after reset');
  assert(await a.evaluate(async () => (await fetch('/api/companies')).status) === 401, 'old browser HTTP rejected');
  await a.getByRole('button', { name: '进入演示', exact: true }).waitFor({ timeout: 15000 });
  assert(await a.getByRole('heading', { name: '研究概览', exact: true }).count() === 0, 'revoked browser unmounts business');
  await a.screenshot({ path: `${output}/old-visitor-revoked.png`, fullPage: true });
  await b.getByRole('button', { name: '退出演示', exact: true }).click();
  await b.getByRole('button', { name: '进入演示', exact: true }).waitFor();
  const deadline = Date.now() + 30000;
  let logoutReady = false;
  while (Date.now() < deadline) {
    const status = await b.evaluate(async () => (await fetch('/api/demo/status')).json());
    if (status.service_state === 'ready') { logoutReady = true; break; }
    assert(status.service_state !== 'degraded', 'logout reset failed closed');
    await new Promise(r => setTimeout(r, 200));
  }
  assert(logoutReady, 'logout reset reached ready within budget');
  assert(errors.length === 0, `browser runtime errors: ${errors.join('; ')}`);
  const result = { evidence: 'REAL_CHROMIUM_TWO_PROCESSES_REAL_HTTP_REAL_BGE_MILVUS_PINNED_SEED',
    checks: ['three-width login/home no overflow', 'pending cookie via Vite /api', 'legacy mutation envelope',
      'same verified lease hard reload preserves UNKNOWN hint', 'actual CSS hero contrast', 'explicit illustrative chart route',
      'second browser conflict and explicit owner takeover', 'new generation restores seed', 'old browser HTTP401 and UI unmount', 'logout resets'],
    first_generation: initial.lease_generation, next_generation: after.session.lease_generation,
    llm_calls: 0, real_pdfs: Number(process.env.DEMO_CHECK_EXPECTED_READY || 0), seed_inventory: {kpis:pinned.overview.kpis, archived_report_revisions:pinned.reports.items.length, archived_jobs:pinned.jobs.items.length, memories:pinned.memories.items.length, conversations:pinned.conversations.items.length, ocr_lines:pinned.ocr?.pages[0].lines.length ?? 0}, human_financial_approvals: 0, browser_errors: errors };
  await writeFile(`${output}/browser-result.json`, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} finally { await Promise.all(launches.map(b => b.close())); }
