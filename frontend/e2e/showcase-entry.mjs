// UI_MOCK boundary check: navigation fills a draft and never submits business work.
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
const origin = process.env.SHOWCASE_ORIGIN || 'http://127.0.0.1:14521';
const out = process.env.SHOWCASE_SCREENSHOTS || '/tmp/findoc-showcase-entry';
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  for (const width of [1440, 1280, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const writes = [];
    page.on('request', request => {
      if (new URL(request.url()).pathname.startsWith('/api/') && request.method() !== 'GET') {
        writes.push(`${request.method()} ${new URL(request.url()).pathname}`);
      }
    });
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname;
      await route.fulfill(path === '/api/companies'
        ? { status: 200, json: [{ company_id: 'entry-sample', name: '入口测试企业', security_code: 'SAMPLE', exchange: 'TEST' }] }
        : { status: 503, json: { detail: 'UI_MOCK intentionally unavailable read service' } });
    });
    const query = new URLSearchParams({ company: 'entry-sample', question: '请先查看现金流原文，不自动执行研究。' });
    await page.goto(`${origin}/conversations?${query}`);
    const input = page.getByRole('textbox', { name: '研究问题', exact: true });
    await input.waitFor();
    if (await input.inputValue() !== query.get('question')) throw Error('draft not preserved');
    if (await page.getByRole('button', { name: '发送', exact: true }).isEnabled()) throw Error('send enabled without explicit conversation scope');
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw Error(`overflow ${width}`);
    await page.screenshot({ path: `${out}/entry-${width}.png`, fullPage: true });
    if (writes.length) throw Error(`navigation issued business writes: ${writes.join(', ')}`);
    console.log(`PASS ${width}: draft filled, source not selected, zero POST/PATCH/DELETE`);
    await page.close();
  }
} finally { await browser.close(); }
