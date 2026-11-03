import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
const out = process.env.A03_SCREENSHOTS || "/tmp/findoc-a03-shell";
await mkdir(out, { recursive: true });
const b = await chromium.launch({
  headless: true,
  ...(process.env.CHROME_PATH
    ? { executablePath: process.env.CHROME_PATH }
    : {}),
});
for (const width of [1440, 1280, 390]) {
  const p = await b.newPage({ viewport: { width, height: 900 } });
  let release,
    posts = 0;
  const errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  await p.route("**/research-fixture", (r) =>
    r.fulfill({
      contentType: "text/html",
      body: `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><div style="background:#fff0be;text-align:center;padding:8px">UI_MOCK · 假接口，无真实模型调用</div><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>t=>t;window.__vite_plugin_react_preamble_installed__=true;</script><script type="module">import React from '/node_modules/.vite/deps/react.js';import DOM from '/node_modules/.vite/deps/react-dom_client.js';import {ShowcaseResearchPanel} from '/src/product/showcaseResearch/ShowcaseResearchPanel.tsx';import '/src/product/tokens.css';const a='11111111-1111-4111-8111-111111111111',b='22222222-2222-4222-8222-222222222222';class App extends React.Component{constructor(p){super(p);this.state={cid:a};window.switchConversation=()=>this.setState({cid:b});}render(){return React.createElement('main',{style:{maxWidth:1000,margin:'30px auto',padding:16}},React.createElement(ShowcaseResearchPanel,{conversationId:this.state.cid,initialQuestion:'分析现金流',onModeChange:m=>window.currentMode=m}));}}DOM.createRoot(document.getElementById('root')).render(React.createElement(App));</script></html>`,
    }),
  );
  await p.route("**/api/**", async (r) => {
    if (r.request().method() !== "GET") {
      posts++;
      await r.abort();
      return;
    }
    const cid = new URL(r.request().url()).pathname.split("/").at(-2);
    if (cid.startsWith("1111") && release === undefined)
      await new Promise((resolve) => (release = resolve));
    await r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        conversation_id: cid,
        items: cid.startsWith("1111")
          ? [
              {
                intent_id: "33333333-3333-4333-8333-333333333333",
                task_id: "44444444-4444-4444-8444-444444444444",
                state: "completed",
              },
            ]
          : [],
      }),
    });
  });
  await p.goto("http://127.0.0.1:5180/research-fixture");
  await p.getByRole("button", { name: /综合研究/ }).click();
  await p.getByLabel("研究问题").fill("旧会话问题");
  await p.screenshot({ path: `${out}/shell-${width}.png`, fullPage: true });
  if (await p.evaluate(() => document.documentElement.scrollWidth > innerWidth))
    throw Error("overflow");
  await p.evaluate(() => window.switchConversation());
  await p.getByText("当前会话暂无可读取的关联任务。").waitFor();
  release();
  await p.waitForTimeout(150);
  if (await p.getByText("已关联任务").count()) throw Error("stale links");
  await p.getByRole("button", { name: /深度研究/ }).click();
  if ((await p.getByLabel("研究问题").inputValue()) !== "分析现金流")
    throw Error("stale draft");
  if (await p.getByRole("button", { name: "意图解析暂不可用" }).isEnabled())
    throw Error("unfrozen endpoint enabled");
  if (posts || errors.length) throw Error(errors.join(";") || "mutation");
  console.log(`PASS A03 shell ${width}: mode/CID and stale response`);
  await p.close();
}
await b.close();
