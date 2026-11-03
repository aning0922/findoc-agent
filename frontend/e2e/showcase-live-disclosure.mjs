import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
const out = process.env.D03_SCREENSHOTS || "/tmp/findoc-d03-mock";
await mkdir(out, { recursive: true });
const b = await chromium.launch({
  headless: true,
  ...(process.env.CHROME_PATH
    ? { executablePath: process.env.CHROME_PATH }
    : {}),
});
for (const width of [1440, 1280, 390]) {
  const p = await b.newPage({ viewport: { width, height: 900 } });
  p.setDefaultTimeout(6000);
  let mode = "success",
    posts = 0,
    release;
  const errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  await p.route("**/disclosure-fixture", (r) =>
    r.fulfill({
      contentType: "text/html",
      body: `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><div style="background:#fff0be;text-align:center;padding:8px">UI_MOCK · 测试目录数据</div><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>t=>t;window.__vite_plugin_react_preamble_installed__=true;</script><script type="module">import React from '/node_modules/.vite/deps/react.js';import DOM from '/node_modules/.vite/deps/react-dom_client.js';import {DisclosurePanel} from '/src/product/disclosures/DisclosurePanel.tsx';import '/src/product/tokens.css';const companies=[{company_id:'a',name:'美的集团',security_code:'000333',exchange:'SZSE'},{company_id:'b',name:'格力电器',security_code:'000651',exchange:'SZSE'}];class App extends React.Component{constructor(p){super(p);this.state={company:'a',count:0};window.switchCompany=()=>this.setState({company:'b'});}render(){return React.createElement('main',{style:{maxWidth:1000,margin:'30px auto',padding:16}},React.createElement(DisclosurePanel,{company:this.state.company,companies,onImported:()=>this.setState({count:this.state.count+1})}),React.createElement('p',{id:'count'},String(this.state.count)),React.createElement('button',null,'上传并绑定年报'));}}DOM.createRoot(document.getElementById('root')).render(React.createElement(App));</script></html>`,
    }),
  );
  await p.route("**/api/disclosures/**", async (r) => {
    const u = new URL(r.request().url()),
      path = u.pathname;
    let status = 200,
      data;
    if (path.endsWith("/search")) {
      if (mode === "late") await new Promise((resolve) => (release = resolve));
      data = {
        schema_version: "disclosure-search-v1",
        source_scope: "verified_demo_catalog",
        items: [
          {
            candidate_id: "c1",
            company_code: "000333",
            company_name: "美的集团",
            title: "美的集团 2025 年年度报告",
            report_year: 2025,
            kind: "annual_full",
            publish_date: null,
            is_amendment: null,
            official_url: "https://static.cninfo.com.cn/fake.pdf",
            provider: "官方目录",
            downloadable: true,
          },
        ],
        limitations: ["仅测试模拟目录"],
        fallback: "手动上传",
      };
    } else if (path.endsWith("/import")) {
      posts++;
      const x = r.request().postDataJSON();
      if (mode === "unknown") {
        status = 409;
        data = {
          schema_version: "disclosure-import-v1",
          operation_id: x.operation_id,
          state: "unknown",
          phase: "uploading",
          error_code: null,
          result: null,
        };
      } else
        data = {
          schema_version: "disclosure-import-v1",
          operation_id: x.operation_id,
          state: "completed",
          phase: "completed",
          error_code: null,
          result: { document_id: "fake" },
        };
    } else {
      const id = path.split("/").at(-1);
      data = {
        schema_version: "disclosure-import-v1",
        operation_id: id,
        state: "completed",
        phase: "completed",
        error_code: null,
        result: { document_id: "fake" },
      };
    }
    await r.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
  await p.goto("http://127.0.0.1:5180/disclosure-fixture");
  await p.getByRole("button", { name: "查询目录" }).click();
  await p.getByText("美的集团 2025 年年度报告").waitFor();
  await p.screenshot({ path: `${out}/d03-${width}.png`, fullPage: true });
  if (await p.evaluate(() => document.documentElement.scrollWidth > innerWidth))
    throw Error("overflow " + width);
  await p.getByRole("button", { name: "明确导入此年报" }).click();
  await p.getByText("已完成上传与企业绑定。", { exact: false }).waitFor();
  await p.screenshot({path:`${out}/success-${width}.png`,fullPage:true});
  if ((await p.locator("#count").innerText()) !== "1")
    throw Error("missing callback");
  mode = "unknown";
  await p.getByRole("button", { name: "明确导入此年报" }).click();
  await p.getByRole("button", { name: "只读查询原操作" }).waitFor();
  await p.screenshot({ path: `${out}/unknown-${width}.png`, fullPage: true });
  await p.reload();
  await p.getByRole("button", { name: "只读查询原操作" }).click();
  await p.getByText("已完成上传与企业绑定。", { exact: false }).waitFor();
  if (posts !== 2) throw Error("POST replay");
  mode = "late";
  await p.getByRole("button", { name: "查询目录" }).click();
  await p.waitForTimeout(100);
  await p.evaluate(() => window.switchCompany());
  await p.getByText("当前绑定企业：格力电器", { exact: false }).waitFor();
  release();
  await p.waitForTimeout(150);
  await p.screenshot({ path: `${out}/switch-${width}.png`, fullPage: true });
  if (await p.getByText("美的集团 2025 年年度报告").count())
    throw Error("stale response");
  if (errors.length) throw Error(errors.join(";"));
  console.log(
    `PASS D03 mock ${width}: success, unknown reload/read-only, switch`,
  );
  await p.close();
}
await b.close();
