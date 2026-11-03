// Fixed-baseline positive regression: actual chart + research React, intercepted APIs only.
// The old ee836e6 reproduction and failures remain in M3-integration-review.md.
const assert = require('node:assert/strict');
const { chromium } = require('../frontend/node_modules/playwright');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const net = require('node:net');
const path = require('node:path');
const fs = require('node:fs');

const revision = 'a'.repeat(64);
const hash = 'b'.repeat(64);
const source = {
  kind: 'fast', workspace_id: 'demo', company_id: 'review-company',
  document_id: 'review-document', source_revision: revision, content_sha256: 'c'.repeat(64),
  parser_version: 'synthetic-review', report_year: 2025, attempt: 1,
  report_type: 'annual', basis: 'PRC_GAAP', period_start: '2025-01-01', period_end: '2025-12-31',
  selected_pages: [], identity_status: 'fast_source_verified',
};
const cell = {
  cell_id: 'review-comparative-cell', cell_revision: 1, payload_sha256: hash,
  metric_key: 'revenue', raw_label: '营业收入', raw_decimal: '99', raw_unit: '元',
  normalized_decimal: '99', normalized_unit: 'CNY', statement_kind: 'income_statement',
  time: { kind: 'duration', period_start: '2024-01-01', period_end: '2024-12-31' },
  extraction_status: 'candidate', financial_review: 'unreviewed',
  evidence_refs: [{ document_id: source.document_id, source_revision: revision, physical_page: 1 }],
};
const focus = {
  schema_version: 'financial-point-focus-v1', collection_id: 'review-collection',
  cell_id: cell.cell_id, cell_revision: cell.cell_revision, payload_sha256: hash,
  metric_key: cell.metric_key, time: cell.time, normalized_decimal: cell.normalized_decimal,
  normalized_unit: cell.normalized_unit, source_ref: source, financial_authority: false,
};
const collection = { id: focus.collection_id, collection_id: focus.collection_id,
  source, source_status: 'current', cells: [cell] };
const contextId = '11111111-1111-4111-8111-111111111111';
const answerId = '22222222-2222-4222-8222-222222222222';
const draftId = '33333333-3333-4333-8333-333333333333';
const evidence = { source_ref: source, evidence_id: 'review-evidence', physical_page: 1, text: '比较期间的营业收入原文' };

function html(company) {
  return `<html><div id="root"></div><script type="module">
    import R from '/@react-refresh';R.injectIntoGlobalHook(window);
    window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>t=>t;
    window.__vite_plugin_react_preamble_installed__=true;</script><script type="module">
    import React from '/node_modules/.vite/deps/react.js';
    import DOM from '/node_modules/.vite/deps/react-dom_client.js';
    import {${company ? 'CPlusCompanyEntry' : 'DocumentResearchPanel'}} from
      '/src/product/cplus/${company ? 'profile/CPlusCompanyEntry' : 'research/DocumentResearchPanel'}.tsx';
    DOM.createRoot(document.getElementById('root')).render(React.createElement(
      ${company ? `CPlusCompanyEntry,{companyId:'${source.company_id}',companies:[{company_id:'${source.company_id}',name:'合成测试企业'}]}` : 'DocumentResearchPanel'}));
    </script></html>`;
}

async function setupPage(browserContext, base, { draft, focusOverride } = {}) {
  const page = await browserContext.newPage();
  page.setDefaultTimeout(10000);
  const posts = [], focusGets = [], answerGets = [], errors = [], blockedRequests = [];
  let storedContext, storedAnswer;
  page.on('pageerror', e => errors.push(String(e)));
  // Block all requests outside this owned Vite instance; no proxy can reach a backend.
  await page.route('**/*', route => {
    if (new URL(route.request().url()).origin === base) return route.continue();
    blockedRequests.push(route.request().url());
    return route.abort();
  });
  if (draft) await page.addInitScript(({ draftId, draft }) => {
    sessionStorage.setItem(`findoc:cplus-research:draft:${draftId}`, JSON.stringify(draft));
  }, { draftId, draft });
  await page.route('**/review-cplus-company', r => r.fulfill({ contentType: 'text/html', body: html(true) }));
  await page.route('**/conversations?*', r => r.fulfill({ contentType: 'text/html', body: html(false) }));
  await page.route('**/api/**', route => {
    const request = route.request(), url = new URL(request.url());
    const reply = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    if (request.method() === 'POST') {
      const body = request.postDataJSON(); posts.push({ path: url.pathname, body });
      if (url.pathname === '/api/cplus/financial/trend-projections') return reply({ points: [cell], changes: [] });
      if (url.pathname === '/api/cplus/research/contexts') {
        storedContext = { context_id: contextId, revision: 1, context_sha256: hash,
          selected_sources: body.selected_sources, financial_focus: body.financial_focus };
        return reply({ state: 'completed', result: storedContext });
      }
      if (url.pathname === '/api/cplus/research/answers') {
        assert.equal(body.context_id, storedContext.context_id);
        storedAnswer = { answer_id: answerId, context_id: contextId, state: 'provider_unconfigured',
          question: body.question, interpretation: null, financial_focus: storedContext.financial_focus,
          findings: [{ text: evidence.text, evidence_ref: evidence, transcription_review_status: 'fast_extraction_unreviewed' }] };
        return reply({ state: 'completed', result: storedAnswer });
      }
      if (url.pathname === '/api/research-memories') return reply({ state: 'completed', memory_id: 'review-memory' });
      return reply({ detail: { code: 'unexpected_test_post' } }, 500);
    }
    if (url.pathname === '/api/documents') return reply([{
      document_id: source.document_id, source_file: 'synthetic-2025.pdf', status: 'ready',
      metadata: { company_id: source.company_id, report_year: source.report_year },
    }]);
    if (url.pathname.endsWith('/statements')) return reply({ collections: [collection] });
    if (url.pathname.endsWith('/research-source')) return reply(source);
    if (url.pathname.endsWith('/research-focus')) {
      focusGets.push({ path: url.pathname, query: Object.fromEntries(url.searchParams) });
      return reply(focusOverride || focus);
    }
    if (url.pathname === `/api/cplus/research/answers/${answerId}`) {
      answerGets.push(url.pathname);
      return reply({ ...storedAnswer, historical_snapshot: true, current_source_status: 'stale_or_unavailable' });
    }
    if (url.pathname === '/api/memories') return reply({ schema_version: 'memory-list-v1', items: [], generation: 0 });
    if (url.pathname === '/api/research-memories') return reply({ items: [], memory_generation: 0 });
    if (url.pathname.endsWith('/metadata')) return reply({ company_id: source.company_id, report_year: source.report_year });
    return reply({ items: [], memory_generation: 0 });
  });
  return { page, posts, focusGets, answerGets, errors, blockedRequests };
}

(async () => {
  const server = net.createServer();
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  await new Promise(r => server.close(r));
  const frontend = path.resolve(__dirname, '../frontend'), base = `http://127.0.0.1:${port}`;
  const vite = spawn(process.execPath, [path.join(frontend, 'node_modules/vite/bin/vite.js'),
    '--host', '127.0.0.1', '--port', String(port), '--strictPort'], {
    cwd: frontend, env: { PATH: process.env.PATH, HOME: process.env.HOME, FINDOC_E2E_DISABLE_ENV_FILES: '1' }, stdio: 'ignore',
  });
  let browser;
  try {
    let ready = false;
    for (let i = 0; i < 100; i++) {
      try { if ((await fetch(base)).ok) { ready = true; break; } } catch {}
      await new Promise(r => setTimeout(r, 100));
    }
    assert(ready, 'Owned Vite did not become ready');
    browser = await chromium.launch({ headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
    const ctx = await browser.newContext();
    const positive = await setupPage(ctx, base), { page } = positive;
    await page.goto(`${base}/review-cplus-company`);
    await page.getByRole('button', { name: '三大报表', exact: true }).click();
    await page.getByRole('checkbox', { name: '选择 营业收入 2024-12-31', exact: true }).check();
    await page.getByRole('checkbox', { name: '显示待核对候选观察' }).check();
    await page.getByRole('button', { name: '生成趋势', exact: true }).click();
    await page.getByRole('button', { name: '企业概览', exact: true }).click();
    await page.locator('svg circle[role="button"]').click();
    await page.waitForURL('**/conversations?*');
    const draft = await page.evaluate(() => {
      const id = new URLSearchParams(location.search).get('cplus_draft');
      return JSON.parse(sessionStorage.getItem(`findoc:cplus-research:draft:${id}`));
    });
    assert.deepEqual(draft.point.time, cell.time);
    assert.equal(draft.point.cell_id, cell.cell_id);
    assert.equal(draft.point.payload_sha256, hash);
    assert.deepEqual(draft.documentIds, [source.document_id]);
    assert.deepEqual(draft.sourceRevisions, [revision]);
    assert.match(draft.question, /2024-01-01 至 2024-12-31/);
    await page.getByRole('button', { name: '读取资料身份' }).click();
    await page.getByText('已核验图表焦点：', { exact: false }).waitFor();
    assert.deepEqual(positive.focusGets, [{
      path: `/api/cplus/financial/cells/${cell.cell_id}/research-focus`,
      query: { revision: String(cell.cell_revision), payload_sha256: hash },
    }]);
    await page.getByRole('button', { name: '固定范围，开始研究' }).click();
    assert.match(await page.getByRole('textbox', { name: '研究问题' }).inputValue(), /实际期间 2024-01-01 至 2024-12-31/);
    await page.getByRole('button', { name: '提交研究问题' }).click();
    await page.getByText('模型未配置 · 展示真实检索原文', { exact: true }).waitFor();
    await page.getByText('历史快照：当前来源已变化或无法复验；不能据此继续执行或确认财务。', { exact: true }).waitFor();
    const contextPost = positive.posts.find(p => p.path.endsWith('/contexts'));
    const answerPost = positive.posts.find(p => p.path.endsWith('/answers'));
    assert.deepEqual(contextPost.body.financial_focus, focus);
    assert.deepEqual(contextPost.body.selected_sources, [focus.source_ref]);
    assert.equal(answerPost.body.context_id, contextId);
    assert.equal(answerPost.body.context_sha256, hash);
    assert.match(answerPost.body.question, /2024-01-01 至 2024-12-31/);
    assert.equal(focus.source_ref.report_year, 2025);
    assert.equal(positive.answerGets.length, 1, 'POST receipt must refresh actual answer GET projection');
    await page.getByRole('button', { name: '收藏这条证据' }).click();
    await page.getByText('证据已收藏；可在下方记忆中查询与删除。', { exact: true }).waitFor();
    const favorite = positive.posts.find(p => p.path === '/api/research-memories').body;
    assert.equal(favorite.evidence_id, evidence.evidence_id);
    for (const key of ['artifact_id', 'physical_page', 'source_line_index']) assert.equal(favorite[key], null);
    assert.equal(favorite.source_revision, revision);
    assert.deepEqual(positive.errors, []);
    assert.deepEqual(positive.blockedRequests, []);

    const negatives = [];
    for (const field of ['cell_id', 'cell_revision', 'payload_sha256']) {
      const malformed = structuredClone(draft); delete malformed.point[field];
      const isolated = await browser.newContext();
      const check = await setupPage(isolated, base, { draft: malformed });
      await check.page.goto(`${base}/conversations?cplus_draft=${draftId}&question=${encodeURIComponent(draft.question)}`);
      await check.page.getByRole('button', { name: '读取资料身份' }).click();
      await check.page.getByText('图表点位缺少可核验的单元格身份，请返回原图重新选择。', { exact: true }).waitFor();
      assert.equal(await check.page.getByRole('button', { name: '固定范围，开始研究' }).count(), 0);
      assert.equal(check.focusGets.length, 0);
      assert.equal(check.posts.length, 0);
      assert.deepEqual(check.errors, []);
      negatives.push({ missing_field: field, focus_gets: 0, posts: 0, blocked: true });
      await isolated.close();
    }
    const report = {
      baseline: 'b2b73d5', tier: 'UI_MOCK_ACTUAL_REACT', passed: true,
      flow: 'CPlusCompanyEntry → CPlusCompany360 chart click → session draft → DocumentResearchPanel → focus GET → contexts POST → answers POST/GET → favorite POST',
      report_year: source.report_year, actual_comparative_period: cell.time, draft,
      focus_gets: positive.focusGets, posts: positive.posts, answer_gets: positive.answerGets,
      selected_period_preserved: true, exact_server_focus_preserved: true,
      fast_favorite_ocr_fields_null: true, history_get_refreshed_and_alert_visible: true,
      negative_missing_metadata: negatives, page_errors: positive.errors, blocked_external_requests: positive.blockedRequests,
      provider_calls: 0, financial_confirmations: 0,
    };
    fs.writeFileSync('/tmp/cplus-m3-fixes-ui-verification.json', JSON.stringify(report, null, 2));
    console.log('PASS: actual React chart 2025 report/2024 period keeps exact server focus, source and question; fast favorite and historical GET refresh pass; 3 missing-cell metadata cases block before POST.');
    await ctx.close();
  } finally {
    if (browser) await browser.close();
    if (vite.exitCode === null) { vite.kill('SIGTERM'); await once(vite, 'exit'); }
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
