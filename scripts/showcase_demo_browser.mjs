/** Chromium -> actual Vite /api proxy -> controller -> real child (FAKE engine).
 * Protocol verification only, not L04 UI acceptance or real financial evidence.
 */
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const frontendRoot = process.env.DEMO_CHECK_FRONTEND_ROOT;
const { chromium } = await import(pathToFileURL(path.join(frontendRoot, 'node_modules/@playwright/test/index.mjs')).href);
const origin = process.env.DEMO_CHECK_ORIGIN;
const credentials = { username: process.env.DEMO_CHECK_USERNAME, password: process.env.DEMO_CHECK_PASSWORD };
const owner = process.env.DEMO_CHECK_OWNER_PASSWORD;
const browser = await chromium.launch({ headless: true });
const checks = [];
const a = await browser.newContext();
const b = await browser.newContext();
const pageA = await a.newPage();
const pageB = await b.newPage();
const operation = () => crypto.randomUUID();

async function api(page, method, route, body) {
  return await page.evaluate(async ({ method, route, body }) => {
    const response = await fetch('/api' + route, { method, headers: body ? { 'Content-Type': 'application/json' } : {},
      ...(body ? { body: JSON.stringify(body) } : {}) });
    return { status: response.status, body: await response.json() };
  }, { method, route, body });
}
async function claim(page, result) {
  assert.equal(result.status, 202);
  assert.equal(result.body.schema_version, 'demo-attempt-v1');
  let progress;
  for (let i = 0; i < 300; i++) {
    progress = await api(page, 'GET', '/demo/operations/' + result.body.operation_id);
    assert.equal(progress.status, 200);
    if (progress.body.claimable) break;
    assert.notEqual(progress.body.state, 'failed');
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  assert.equal(progress.body.state, 'ready');
  const response = await api(page, 'POST', '/demo/claim', {
    operation_id: operation(), attempt_operation_id: result.body.operation_id,
  });
  assert.equal(response.status, 200, JSON.stringify(response.body));
  return response.body;
}
try {
  await Promise.all([pageA.goto(origin), pageB.goto(origin)]);
  const publicStatus = await api(pageB, 'GET', '/demo/status');
  assert.deepEqual(Object.keys(publicStatus.body).sort(), ['conflict_policy', 'schema_version', 'service_state', 'ttl_minutes']);
  assert.equal((await api(pageB, 'GET', '/documents/x/file')).status, 401);
  const bad = await api(pageB, 'POST', '/demo/login', { ...credentials, password: 'intentionally-invalid', operation_id: operation() });
  assert.equal(bad.status, 401);
  assert.deepEqual(Object.keys(bad.body.detail).sort(), ['code', 'message']);
  const pending = await api(pageA, 'POST', '/demo/login', { ...credentials, operation_id: operation() });
  const pendingCookie = (await a.cookies()).find(cookie => cookie.name === 'findoc_demo_pending');
  assert.equal(pendingCookie.path, '/');
  assert.equal(pendingCookie.httpOnly, true);
  assert.equal(pendingCookie.sameSite, 'Strict');
  // Both GET operations and POST claim use /api/demo, exercising browser cookie path matching.
  const sessionA = await claim(pageA, pending);
  assert.equal((await a.cookies()).find(cookie => cookie.name === 'findoc_demo').httpOnly, true);
  const same = await api(pageA, 'POST', '/demo/login', { ...credentials, operation_id: operation() });
  assert.equal(same.status, 200);
  assert.equal(same.body.expires_at, sessionA.expires_at);
  assert.equal((await api(pageB, 'POST', '/demo/login', { ...credentials, operation_id: operation() })).status, 423);
  checks.push('PASS browser /api pending-cookie path + claim + wrong credentials + conflict + absolute TTL');

  assert.equal((await api(pageA, 'GET', '/companies')).body.length, 1);
  const create = { operation_id: operation(), name: 'FAKE visitor company', security_code: 'VISITOR', exchange: 'DEMO' };
  const firstWrite = await api(pageA, 'POST', '/companies', create);
  assert.equal(firstWrite.status, 200);
  assert.deepEqual((await api(pageA, 'POST', '/companies', create)).body, firstWrite.body);
  assert.equal((await api(pageA, 'GET', '/companies')).body.length, 2);
  assert.equal((await api(pageA, 'POST', '/financial-facts/persisted', { operation_id: operation() })).status, 403);
  checks.push('PASS generation SQLite mutation + replay + step-up gate');

  await pageA.evaluate(() => {
    window.__latePDF = fetch('/api/documents/fake/file?delay=3').then(async response => ({ status: response.status, text: await response.text() }));
    window.__events = '';
    window.__stream = fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ operation_id: crypto.randomUUID(), delay: 8 }) }).then(async response => {
        const reader = response.body.getReader();
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            window.__events += new TextDecoder().decode(value);
          }
        } catch { /* cancellation/forced old-process exit can terminate the connection */ }
      });
  });
  await pageA.waitForFunction(() => window.__events.includes('FAKE-start-generation-'));
  const takeover = await api(pageB, 'POST', '/demo/takeover', { ...credentials, operation_id: operation(),
    owner_password: owner, confirm: true, expected_generation: sessionA.lease_generation });
  const sessionB = await claim(pageB, takeover);
  assert.ok(sessionB.lease_generation > sessionA.lease_generation);
  const latePDF = await pageA.evaluate(() => window.__latePDF);
  assert.ok([401, 503].includes(latePDF.status), JSON.stringify(latePDF));
  assert.ok(!latePDF.text.includes('%PDF-FAKE'));
  await pageA.evaluate(() => window.__stream);
  const events = await pageA.evaluate(() => window.__events);
  assert.ok(events.includes('FAKE-start-generation-'));
  assert.ok(!events.includes('FAKE-late-generation-'));
  assert.equal((await api(pageA, 'GET', '/companies')).status, 401);
  assert.equal((await api(pageB, 'GET', '/companies')).body.length, 1);
  const grant = await api(pageB, 'POST', '/demo/owner-authorize', { operation_id: operation(), owner_password: owner, confirm: true });
  assert.equal(grant.body.can_review, true);
  assert.equal((await api(pageB, 'GET', '/demo/session')).body.can_review, true);
  checks.push('PASS real HTTP old PDF discarded + SSE disconnected + old process retired + seed count restored');

  assert.equal((await api(pageB, 'POST', '/demo/logout', { operation_id: operation() })).status, 200);
  assert.ok(!(await b.cookies()).some(cookie => cookie.name.startsWith('findoc_demo')));
  assert.equal((await api(pageB, 'GET', '/companies')).status, 401);
  let status;
  for (let i = 0; i < 300; i++) {
    status = await api(pageB, 'GET', '/demo/status');
    if (status.body.service_state === 'ready') break;
    assert.notEqual(status.body.service_state, 'degraded');
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  assert.equal(status.body.service_state, 'ready');
  const final = await claim(pageA, await api(pageA, 'POST', '/demo/login', { ...credentials, operation_id: operation() }));
  assert.ok(final.lease_generation > sessionB.lease_generation);
  assert.equal((await api(pageA, 'GET', '/companies')).body.length, 1);
  checks.push('PASS logout clears both / cookies + reset + next fresh lease');
  console.log(JSON.stringify({ engine: 'FAKE', evidence: 'BROWSER_FAKE', transport: 'Chromium → Vite /api → controller → OS child', checks }));
} finally {
  await browser.close();
}
