import { chromium } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
import assert from 'node:assert/strict';
const dir=process.argv[2];
const proof=JSON.parse(readFileSync(join(dir,'proof.json'),'utf8'));
const browser=await chromium.launch();
const page=await browser.newPage({viewport:{width:1280,height:900}});
const records=[];
try {
  for(const [index,c] of proof.cases.entries()) for(const revision of [1,2]) {
    const file=join(dir,`reader-${index}-v${revision}.html`);
    await page.goto(pathToFileURL(file).href);
    assert.equal(await page.locator('tbody tr').count(),6);
    const audit=JSON.parse(await page.locator('pre code').last().innerText());
    assert.deepEqual(audit,c.versions[revision-1].report);
    const headings=await page.locator('h2').allTextContents();
    assert.equal(headings.length,10);
    const hrefs=await page.locator('a').evaluateAll(links=>links.map(a=>a.getAttribute('href')));
    assert(hrefs.every(h=>h.startsWith('/api/documents/')&&h.includes('source_revision=')&&h.includes('#page=')));
    for(const f of c.facts) for(const key of ['raw_value','raw_unit','value_cny_yuan']) assert((await page.locator('table').innerText()).includes(f[key]));
    if(index===0&&revision===1)await page.screenshot({path:join(dir,'markdown-reader.png')});
    records.push({case:c.title,revision,reader_file:file,financial_rows:6,audit_equal:true,links_safe:true,chinese_amounts_units:true});
  }
  writeFileSync(join(dir,'markdown-reader-results.json'),JSON.stringify({actualChromiumReader:true,records},null,2));
} finally {await browser.close();}
console.log(JSON.stringify({actualChromiumReader:true,versions:records.length,passed:true}));
