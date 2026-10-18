import { test, expect, type Page } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
const out = process.env.D29_ARTIFACT_DIR!;
const isBefore = process.env.D29_BEFORE === '1';
const manifest = JSON.parse(readFileSync(`${out}/manifest.json`, 'utf8'));
const tasks = manifest.tasks;
const watches = new WeakMap<Page, any[]>();
const dbStates = new Map<string, any>();
const pendingReads = new WeakMap<Page, Promise<void>[]>();
function url(t: any, section = 'operating', hash = '') {
  return `/research?${new URLSearchParams({ company: t.input.first.company_id, mode: 'operating', task: t.task_id, section })}${hash}`;
}
function watch(page: Page) {
  const known = watches.get(page); if (known) return known;
  const requests: any[] = []; watches.set(page, requests);
  const reads: Promise<void>[] = []; pendingReads.set(page, reads);
  page.on('response', response => {
    const r = response.request(), path = new URL(r.url()).pathname;
    const row = [...requests].reverse().find(row => row.url === r.url() && row.status === undefined);
    if (!row) return;
    row.status = response.status();
    if (/\/source$|\/financial-facts$|\/research\/tasks\/[^/]+$/.test(path)) reads.push((async () => {
      try {
        const value = await response.json();
        if (value.detail) row.detail = value.detail;
        if (value.source_revision) row.source = value;
        if (value.facts) row.facts = value.facts.map((f: any) => ({ company_id: f.company_id, document_id: f.document_id, source_revision: f.source_revision, disclosure_version: f.disclosure_version, fact_set_id: f.fact_set_id, fact_id: f.fact_id, period: f.period, metric_key: f.metric_key, current_valid: f.current_valid, invalid_reason: f.invalid_reason }));
        if (value.task_id) row.identity = { task_id: value.task_id, operation_id: value.operation_id, revision: value.revision, status: value.status, active_input: value.active_input, budget: value.budget };
      } catch { row.unparseable = true; }
    })());
  });
  page.on('requestfailed', r => { const row = [...requests].reverse().find(row => row.url === r.url() && row.status === undefined); if (row) row.failure = r.failure()?.errorText; });
  page.on('request', r => { if (r.url().includes('/api/')) requests.push({ url: r.url(), method: r.method(), path: new URL(r.url()).pathname, query: new URL(r.url()).search, body: r.postData() }); });
  return requests;
}
async function shot(page: Page, label: string) {
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    await page.screenshot({ path: `${out}/${label}-${width}.png` });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
}
async function record(page: Page, name: string, requests: any[], t: any) {
  await Promise.allSettled(pendingReads.get(page) || []);
  const read = await (await page.request.get(`/api/research/tasks/${t.task_id}`)).json();
  writeFileSync(`${out}/${name}.json`, JSON.stringify({ requests, original: t, readback: read, text: await page.locator('main').innerText() }, null, 2));
  expect(read.task_id).toBe(t.task_id); expect(read.operation_id).toBe(t.operation_id);
  expect(read.revision).toBe(t.revision); expect(read.budget).toEqual(t.budget);
  expect(read.active_input).toEqual(t.active_input);
  expect(requests.filter(r => r.method !== 'GET')).toEqual([]);
}
test.beforeEach(async ({ page }, info) => {
  watch(page);
  dbStates.set(info.title, await (await page.request.get('/api/__test__/d29-readonly-state')).json());
  await page.route('**/src/main.tsx*', r => r.fulfill({ contentType: 'text/javascript', body: 'import "/tests/support/d20-entry.tsx";' }));
});

test.afterEach(async ({ page }, info) => {
  await Promise.allSettled(pendingReads.get(page) || []);
  const after = await (await page.request.get('/api/__test__/d29-readonly-state')).json();
  const before = dbStates.get(info.title);
  const changed = Object.keys(before).filter(key => before[key] !== after[key]);
  const label = info.title.replace(/[^a-zA-Z0-9]+/g, '-').slice(0, 150);
  writeFileSync(`${out}/${label}-audit.json`, JSON.stringify({ title: info.title, status: info.status, before, after, changed, requests: watches.get(page), text: await page.locator('main').innerText().catch(() => '') }, null, 2));
  if (info.title.includes('real source_changed')) {
    expect(changed.filter(name => !['document_sources', 'documents', 'report_binding_corrections'].includes(name))).toEqual([]);
  } else expect(changed).toEqual([]);
  expect((watches.get(page) || []).filter(r => r.method !== 'GET')).toEqual([]);
});

test('D29-B baseline source 503 suspends eligibility without declaring invalidation and GET restores identity', async ({ page }) => {
  const t = tasks.completed, requests = watch(page);
  await page.route('**/api/documents/*/source?*', r => r.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'source_temporarily_unavailable', message: 'temporary source outage' } }) }));
  await page.goto(url(t));
  await expect(page.getByRole('region', { name: '研究阶段与下一步' })).toBeVisible();
  await expect(page.locator('.operating-alert').filter({ hasText: 'temporary source outage' })).toBeVisible();
  await shot(page, 'source-503');
  await record(page, 'source-503-before-recovery', requests, t);
  await expect(page.getByRole('region', { name: '研究阶段与下一步' })).toContainText('暂时无法核验');
  await expect(page.locator('main')).not.toContainText('已核准数字 · 合并口径');
  await expect(page.locator('.result-exact')).toHaveCount(0);
  await page.unroute('**/api/documents/*/source?*');
  await page.getByRole('button', { name: '重新核验（只读）', exact: true }).click();
  await expect(page.locator('.result-exact')).toHaveCount(3);
  await record(page, 'source-503-recovered', requests, t);
  await shot(page, 'source-503-recovered');
});

test('D29-B baseline visible chapters have real targets and keyboard focus', async ({ page }) => {
  const t = tasks.waiting, requests = watch(page);
  await page.goto(url(t, 'sources'));
  await expect(page.locator('#research-facts')).toBeAttached();
  await expect(page.getByRole('navigation', { name: '任务章节' })).toBeVisible();
  await shot(page, 'sources-navigation');
  const links = page.getByRole('navigation', { name: '任务章节' }).getByRole('link');
  for (const link of await links.all()) {
    const href = await link.getAttribute('href');
    // Check the rendered target before clicking; avoid confusing loading with an absent chapter.
    expect(await page.locator(href!).count(), `rendered target for ${href}`).toBe(1);
    await link.focus(); await page.keyboard.press('Enter');
    const hash = new URL(page.url()).hash;
    const target = page.locator(hash);
    await expect(target, `target for ${href}`).toHaveCount(1);
    await expect(target).toBeFocused();
  }
  await record(page, 'navigation-baseline', requests, t);
});

const sections = ['sources', 'financial', 'operating'];
const scenarios = ['source-503', 'source-network', 'facts-503', 'invalid-json', 'invalid-contract', 'source-not-ready', 'source-timeout'];
async function inject(page: Page, scenario: string) {
  const pattern = scenario === 'facts-503' ? '**/api/financial-facts?*' : '**/api/documents/*/source?*';
  await page.route(pattern, async r => {
    if (scenario === 'source-not-ready') return r.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'source_not_ready' }) });
    if (scenario === 'source-network') return r.abort('connectionfailed');
    if (scenario === 'source-timeout') { await new Promise(resolve => setTimeout(resolve, 18000)); return r.abort('timedout').catch(() => {}); }
    if (scenario === 'invalid-json') return r.fulfill({ status: 200, contentType: 'application/json', body: '<invalid response>' });
    if (scenario === 'invalid-contract') return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ source_revision: 'b'.repeat(64) }) });
    return r.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'source_temporarily_unavailable', message: 'temporary read outage' } }) });
  });
  return pattern;
}
for (const section of sections) for (const scenario of scenarios) {
  if (scenario === 'source-timeout' && section !== 'operating') continue;
  test(`D29-B completed ${section} ${scenario} retains identities and recovers by GET`, async ({ page }) => {
    const t = tasks.completed, requests = watch(page), pattern = await inject(page, scenario);
    await page.goto(url(t, section));
    await expect(page.locator('[data-verification-state]')).toHaveAttribute('data-verification-state', 'unavailable', { timeout: 22000 });
    await expect(page.locator('.context-state')).toContainText('暂时无法核验');
    await expect(page.getByRole('region', { name: '研究阶段与下一步' }).getByRole('heading', { level: 2 })).toContainText('暂时无法核验');
    await expect(page.locator('.result-exact,.confirmed-amount')).toHaveCount(0);
    await expect(page.getByRole('button', { name: '核对新来源并新建研究', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '复核并继续研究', exact: true })).toHaveCount(0);
    await expect(page.locator('main')).not.toContainText('已核准数字 · 合并口径');
    if (scenario === 'source-503' || scenario === 'source-network') await shot(page, `${section}-${scenario}`);
    await record(page, `${section}-${scenario}-unavailable`, requests, t);
    await page.unroute(pattern);
    const taskRead = page.waitForResponse(r => new URL(r.url()).pathname === `/api/research/tasks/${t.task_id}` && r.request().method() === 'GET');
    await page.getByRole('button', { name: '重新核验（只读）', exact: true }).click();
    await taskRead;
    await expect(page.locator('[data-verification-state]')).toHaveAttribute('data-verification-state', 'current');
    if (section === 'sources') {
      await page.getByRole('button', { name: '查看全部六项', exact: true }).click();
      await expect(page.locator('.confirmed-amount')).toHaveCount(6);
    } else await expect(page.locator('.result-exact')).toHaveCount(3);
    await record(page, `${section}-${scenario}-recovered`, requests, t);
  });
}
for (const status of ['waiting', 'failed']) for (const section of sections) {
  test(`D29-B ${status} ${section} unavailable state stays consistent`, async ({ page }) => {
    const t = tasks[status], requests = watch(page), pattern = await inject(page, 'source-503');
    await page.goto(url(t, section));
    await expect(page.locator('[data-verification-state]')).toHaveAttribute('data-verification-state', 'unavailable');
    await expect(page.locator('.context-state')).toContainText('暂时无法核验');
    await expect(page.locator('.confirmed-amount')).toHaveCount(0);
    await page.unroute(pattern);
    await page.getByRole('button', { name: '重新核验（只读）', exact: true }).click();
    await expect(page.locator('[data-verification-state]')).toHaveAttribute('data-verification-state', 'current');
    if (status === 'failed') await expect(page.getByRole('region', { name: '研究阶段与下一步' })).toContainText('本次研究未取得有效结果');
    await record(page, `${status}-${section}-same-identity`, requests, t);
  });
}
for (const status of ['waiting', 'completed', 'failed']) for (const section of sections) {
  test(`D29-B navigation ${status} ${section} local targets refresh back forward and cross-page focus`, async ({ page }) => {
    const t = tasks[status], requests = watch(page);
    await page.goto(url(t, section));
    await expect(page.locator('[data-verification-state]')).toHaveAttribute('data-verification-state', 'current');
    const nav = page.getByRole('navigation', { name: '任务章节' });
    const targets = await nav.getByRole('link').evaluateAll(elements => elements.map(e => e.getAttribute('href')!));
    for (const hash of targets) {
      expect(await page.locator(hash).count(), `${status}/${section}/${hash}`).toBe(1);
      await nav.locator(`a[href="${hash}"]`).focus(); await page.keyboard.press('Enter');
      await expect(page.locator(hash)).toBeVisible();
      await expect(page.locator(hash)).toBeFocused();
      expect(new URL(page.url()).searchParams.get('task')).toBe(t.task_id);
      await page.reload(); await expect(page.locator(hash)).toBeFocused();
    }
    if (targets.length > 1) {
      await page.goBack(); await expect(page.locator(targets[targets.length - 2])).toBeFocused();
      await page.goForward(); await expect(page.locator(targets[targets.length - 1])).toBeFocused();
    }
    await page.getByRole('navigation', { name: '当前研究功能' }).getByRole('link', { name: '财务分析', exact: true }).click();
    expect(new URL(page.url()).searchParams.get('task')).toBe(t.task_id);
    expect(new URL(page.url()).searchParams.get('section')).toBe('financial');
    await expect(page.locator('#research-results')).toBeFocused();
    await page.getByRole('navigation', { name: '当前研究功能' }).getByRole('link', { name: '资料与核对', exact: true }).click();
    await expect(page.locator('#research-facts')).toBeFocused();
    await page.goBack(); await expect(page.locator('#research-results')).toBeFocused();
    await page.goForward(); await expect(page.locator('#research-facts')).toBeFocused();
    if (status === 'completed') await shot(page, `navigation-${status}-${section}`);
    await record(page, `navigation-${status}-${section}`, requests, t);
  });
}

test('D29-B checking suspends old amounts and task GET failure preserves displayed identity', async ({ page }) => {
  const t = tasks.completed, requests = watch(page);
  await page.goto(url(t, 'financial'));
  await expect(page.locator('.result-exact')).toHaveCount(3);
  await page.route(`**/api/research/tasks/${t.task_id}`, async r => {
    await new Promise(resolve => setTimeout(resolve, 1200));
    return r.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
  });
  await page.getByRole('button', { name: '刷新状态（只读）', exact: true }).click();
  await expect(page.locator('[data-verification-state]')).toHaveAttribute('data-verification-state', 'checking');
  await expect(page.locator('.result-exact')).toHaveCount(0);
  await expect(page.locator('[data-verification-state]')).toHaveAttribute('data-verification-state', 'unavailable');
  await expect(page.getByRole('region', { name: '研究上下文' })).toHaveAttribute('data-task-id', t.task_id);
  await page.unroute(`**/api/research/tasks/${t.task_id}`);
  await page.getByRole('button', { name: '重新核验（只读）', exact: true }).click();
  await expect(page.locator('.result-exact')).toHaveCount(3);
  await record(page, 'task-get-failure-recovery', requests, t);
});

// Last: a real binding correction in the disposable database invalidates the pinned source.
// It is an explicit test fault, separate from the UI's read-only actions.
test('D29-B baseline real source_changed blocks every route and keeps original task facts', async ({ page }) => {
  const t = tasks.completed, requests = watch(page), source = manifest.reports.find((r: any) => r.report_id === 'midea-2024').source;
  await page.goto(url(t, 'financial'));
  await expect(page.locator('.result-exact')).toHaveCount(3);
  await shot(page, 'real-source-before');
  const correction = await page.request.post(`/api/documents/${source.document_id}/binding-corrections`, { data: {
    expected_attempt: source.attempt, metadata: { company_id: source.company_id, report_year: 2024, report_type: 'annual', basis: 'unknown', period_start: '2024-01-01', period_end: '2024-12-31' }, reason: 'D29-B disposable source_changed fault' } });
  expect(correction.status()).toBe(200);
  for (const status of ['completed', 'waiting', 'failed']) for (const section of sections) {
    const t = tasks[status];
    await page.goto(url(t, section));
    if (!isBefore) await expect(page.locator('[data-verification-state]')).toHaveAttribute('data-verification-state', 'invalidated');
    await expect(page.locator('.context-state')).toContainText('已失效');
    await expect(page.getByRole('button', { name: '核对新来源并新建研究', exact: true })).toBeVisible();
    await expect(page.locator('.result-exact,.confirmed-amount')).toHaveCount(0);
    await expect(page.locator('canvas')).toHaveCount(0);
    await shot(page, `real-source-changed-${status}-${section}`);
    await page.getByRole('button', { name: '刷新状态（只读）', exact: true }).click();
    if (!isBefore) await expect(page.locator('[data-verification-state]')).toHaveAttribute('data-verification-state', 'invalidated');
    await record(page, `real-source-changed-${status}-${section}`, requests, t);
  }
});
