import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
const out = process.env.O03_SCREENSHOTS || "/tmp/findoc-o03-mock";
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
  const mockPng = await p.evaluate(() => {
    const c = document.createElement("canvas");
    c.width = 600;
    c.height = 800;
    const x = c.getContext("2d");
    x.fillStyle = "#fff";
    x.fillRect(0, 0, 600, 800);
    x.fillStyle = "#24364b";
    x.font = "28px sans-serif";
    x.fillText("UI MOCK · 示例原页", 80, 100);
    x.font = "20px sans-serif";
    [
      "示意项目甲      示意数值甲",
      "示意项目乙      示意数值乙",
      "仅用于界面验证，非真实资料",
    ].forEach((v, i) => x.fillText(v, 80, 180 + i * 55));
    return c.toDataURL("image/png").split(",")[1];
  });
  let posts = 0,
    phase = "unknown";
  const errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  await p.route("**/parse-fixture", (r) =>
    r.fulfill({
      contentType: "text/html",
      body: `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><div style="background:#fff0be;text-align:center;padding:8px">UI_MOCK · 候选内容与数据为测试示意</div><div id="root"></div><script type="module">import R from '/@react-refresh';R.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>t=>t;window.__vite_plugin_react_preamble_installed__=true;</script><script type="module">import React from '/node_modules/.vite/deps/react.js';import DOM from '/node_modules/.vite/deps/react-dom_client.js';import {ParseQualityPanel} from '/src/product/parsing/ParseQualityPanel.tsx';import '/src/product/tokens.css';DOM.createRoot(document.getElementById('root')).render(React.createElement('main',{style:{maxWidth:1200,margin:'30px auto',padding:16}},React.createElement(ParseQualityPanel,{documentId:'doc-1',sourceFile:'示例年报.pdf'})));</script></html>`,
    }),
  );
  await p.route("**/api/documents/**", async (r) => {
    const path = new URL(r.request().url()).pathname;
    let data;
    if (path.endsWith("/parse-identity"))
      data = {
        document_id: "doc-1",
        source_revision: "a".repeat(64),
        identity_assessment: "manual_check",
        legacy_source_verified: false,
      };
    else if (path.endsWith("/parse-retry")) {
      posts++;
      const x = r.request().postDataJSON();
      data = {
        operation_id: x.operation_id,
        state: "unknown",
        artifact_id: null,
      };
    } else if (path.includes("/parse-operations/"))
      data = {
        operation_id: path.split("/").at(-1),
        state: phase,
        artifact_id: phase === "unknown" ? null : "artifact-1",
      };
    else if (path.endsWith("/image")) {
      await r.fulfill({
        status: 200,
        contentType: "image/png",
        body: Buffer.from(mockPng, "base64"),
      });
      return;
    } else {
      const lines = [
        "示意项目甲",
        "示意数值甲",
        "示意项目乙",
        "示意数值乙",
        "重复坐标内容",
      ].map((text, i) => ({
        text,
        bbox: [0.1, 0.1 + i * 0.1, 0.4, 0.15 + i * 0.1],
        confidence: 0.9,
      }));
      const cells = lines.map((line, i) => ({
        row: i < 2 || i === 4 ? 0 : 1,
        column: i % 2,
        row_span: null,
        column_span: null,
        text: line.text,
        bbox: line.bbox,
        source_line_index: i,
        confidence: 0.9,
      }));
      data = {
        schema_version: "parse-artifact-v2",
        artifact_id: "artifact-1",
        document_id: "doc-1",
        source_revision: "a".repeat(64),
        source_status: phase === "stale" ? "stale" : "current",
        state: phase === "unknown" || phase === "stale" ? "completed" : phase,
        legacy_source_verified: false,
        identity_assessment: {
          status: "manual_check",
          financial_facts: "not_verified",
        },
        pages_total: phase === "unknown" || phase === "stale" ? 1 : 3,
        pages_processed: 1,
        ocr_pages: 1,
        error_code: null,
        limitations: ["示例页，仅用于 UI 测试"],
        pages: [
          {
            physical_page: 1,
            method: "ocr",
            status: "completed",
            text: lines.map((x) => x.text).join("\n"),
            warnings: ["ocr_transcription_unreviewed"],
            lines,
            tables: [
              {
                table_id: "ocr-layout-candidate",
                quality: "needs_review",
                method: "bbox_line_clustering",
                coordinate_system: "normalized_top_left",
                row_count: 2,
                column_count: 2,
                warning: "整页版面聚类并非表格区域检测，请对照原图。",
                cells,
              },
            ],
          },
        ],
      };
    }
    await r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
  await p.goto("http://127.0.0.1:5180/parse-fixture");
  await p.getByRole("button", { name: "打开预览" }).click();
  await p.getByRole("heading", { name: "版面候选 · 需人工核对" }).waitFor();
  if ((await p.locator("td span").count()) !== 5)
    throw Error("duplicate grid cells lost");
  await p.screenshot({ path: `${out}/grid-${width}.png`, fullPage: true });
  if (await p.evaluate(() => document.documentElement.scrollWidth > innerWidth))
    throw Error("overflow");
  if (posts !== 0) throw Error("GET unexpectedly started OCR");
  await p.getByRole("button", { name: "明确开始新解析" }).click();
  await p.getByRole("button", { name: "只读查询原操作" }).waitFor();
  await p.screenshot({ path: `${out}/unknown-${width}.png`, fullPage: true });
  await p.reload();
  await p.getByRole("button", { name: "只读查询原操作" }).click();
  if (posts !== 1) throw Error("GET replayed OCR");
  phase = "partial";
  await p.getByRole("button", { name: "只读查询原操作" }).click();
  await p.getByText("状态：部分完成", { exact: false }).waitFor();
  await p.screenshot({ path: `${out}/partial-${width}.png`, fullPage: true });
  await p.getByRole("button", { name: "打开预览" }).click();
  await p.getByRole("button", { name: "明确开始新解析" }).click();
  phase = "failed";
  await p.getByRole("button", { name: "只读查询原操作" }).click();
  await p.getByText("状态：失败", { exact: false }).waitFor();
  await p.screenshot({ path: `${out}/failed-${width}.png`, fullPage: true });
  phase = "stale";
  await p.getByLabel("历史产物 ID").fill("artifact-1");
  await p.getByRole("button", { name: "只读查看历史" }).click();
  await p.getByText("历史产物 · 来源已变化").waitFor();
  if (await p.locator(".parse-image img").count())
    throw Error("stale artifact exposed current source image");
  if (await p.getByRole("link", { name: "打开受控 PDF ↗" }).count())
    throw Error("stale artifact exposed current PDF");
  if (errors.length) throw Error(errors.join(";"));
  console.log(
    `PASS O03 mock ${width}: grid collision, unknown reload, partial/failed and stale`,
  );
  await p.close();
}
await b.close();
