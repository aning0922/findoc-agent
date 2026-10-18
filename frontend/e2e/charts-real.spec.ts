import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { compactYi, formatDecimal, reference } from "../src/product/api.ts";
import { chartIdentity } from "../src/product/chartData.ts";
const root=readFileSync("../data/30d-foundation/d14-product-runtime-path.txt","utf8").trim();
const manifest=JSON.parse(readFileSync(`${root}/manifest.json`,"utf8"));
const gold=JSON.parse(readFileSync("../product/validation/manual-benchmark.json","utf8")).facts;
const metrics: Record<string,string>={revenue:"营业收入",net_profit_parent:"归母净利润",operating_cash_flow:"经营活动现金流量净额"};
const proof:any[]=[];
function group(key:string,year:number) { return manifest.groups.find((g:any)=>g.document_id===manifest.reports.find((r:any)=>r.report_id===`${key}-${year}`).source.document_id); }
function fact(key:string,reportYear:number,period:number,metric:string) {const g=group(key,reportYear);return {...g.facts.find((f:any)=>f.period===period&&f.metric_key===metric),disclosure_version:g.disclosure_version,confirmation_kind:g.confirmation_kind};}
async function open(page:Page,key="midea") {
  await page.route("**/src/main.tsx*",r=>r.fulfill({contentType:"application/javascript",body:"import '/tests/support/d12-entry.tsx'"}));
  await page.goto(`/companies/${group(key,2025).company_id}/analysis`);
  await expect(page.getByRole("heading",{name:"披露版本与来源",exact:true})).toBeVisible();
}
async function single(page:Page,key="midea",previousReport=2024) {
  for(const [m,title] of Object.entries(metrics))for(const year of [2024,2025])
    await page.getByLabel(`${year} ${title}披露版本`,{exact:true}).selectOption(fact(key,year===2024?previousReport:2025,year,m).fact_id);
  await expect(page.getByTestId("row-revenue")).toContainText(key==="midea"?"12.11%":"-9.89%");
  await expect(page.locator("[data-chart-point]")).toHaveCount(2);
}
async function compare(page:Page,year=2025,reportYear=year) {
  await page.getByRole("button",{name:"双企业同期间比较",exact:true}).click();
  await page.getByLabel("企业 B",{exact:true}).selectOption(group("gree",2025).company_id);
  await expect(page.getByRole("heading",{name:"明确选择双方报告"})).toBeVisible();
  await page.getByLabel("对比财务年度").selectOption(String(year));
  for(const [side,key] of [["A","midea"],["B","gree"]])await page.getByLabel(`${side} 报告来源`,{exact:true}).selectOption(group(key,reportYear).document_id);
  await expect(page.getByTestId("compare-revenue")).toContainText("同口径可比");
  await expect(page.locator("[data-chart-point]")).toHaveCount(2);
}
async function verifyPoint(page:Page,f:any,report:string,mode:string,keyboard=false) {
  const expected=gold.find((v:any)=>v.document_id===report&&v.period===f.period&&v.metric===f.metric_key);
  expect(f.value_cny_yuan).toBe(expected.value_cny_yuan);
  const point=page.locator(`[data-chart-point="${f.fact_id}"]`);
  await expect(point).toHaveAttribute("data-chart-identity",chartIdentity(f));
  await point.hover();
  await expect(page.locator(".chart-tooltip")).toContainText(f.value_cny_yuan);
  await expect(page.locator(".chart-tooltip")).toContainText(f.disclosure_version);
  await expect(page.locator(".chart-tooltip")).toContainText(f.source_revision);
  const evidenceResponse=page.waitForResponse(r=>r.url().includes(`/evidence/${f.evidence[0].evidence_id}`)&&r.status()===200);
  if(keyboard){const link=page.locator(`[data-chart-fact-id="${f.fact_id}"]`);await link.focus();await page.keyboard.press("Enter");}
  else await point.click();
  const e=await (await evidenceResponse).json();
  expect(e.document_id).toBe(f.document_id);expect(e.company_id).toBe(f.company_id);
  expect(e.source_revision).toBe(f.source_revision);expect(e.evidence_id).toBe(f.evidence[0].evidence_id);
  expect(e.physical_page).toBe(f.evidence[0].physical_page);
  await expect(page.getByLabel("物理页码")).toHaveValue(String(f.evidence[0].physical_page));
  await expect(page.locator("canvas")).toHaveAttribute("aria-label",`PDF 物理第 ${f.evidence[0].physical_page} 页`);
  await expect(page.locator(".pdf-location")).toContainText("金额区域已核验");
  if(mode==="comparison"&&f.period===2025&&f.metric_key==="revenue")await page.screenshot({path:`../product/validation/d14-screenshots/${report}-chart-pdf.png`});
  await page.getByRole("button",{name:"收起证据侧栏"}).click();
  proof.push({mode,report,metric:f.metric_key,year:f.period,fact_id:f.fact_id,fact_set_id:f.fact_set_id,
    document_id:f.document_id,source_revision:f.source_revision,disclosure_version:f.disclosure_version,
    content_sha256:f.content_sha256,value_cny_yuan:f.value_cny_yuan,raw_value:f.raw_value,raw_unit:f.raw_unit,
    evidence_id:f.evidence[0].evidence_id,physical_page:f.evidence[0].physical_page,evidence_response:e,keyboard});
}
async function widths(page:Page,mode:string) {
  await page.getByRole("heading",{name:mode==="single"?"年度财务 · 两期对照":"双企业 · 同期间对照"}).scrollIntoViewIfNeeded();
  await page.mouse.move(10,10);
  for(const width of [1440,1280,1024]) {
    await page.setViewportSize({width,height:900});
    await expect(page.locator("[data-chart-point]")).toHaveCount(2);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    const chart=await page.locator(".chart-plot").boundingBox();expect(chart!.width).toBeGreaterThan(400);
    await page.screenshot({path:`../product/validation/d14-screenshots/${mode}-${width}.png`});
    proof.push({mode,width,chart,whole_page_overflow:false});
  }
}
test.afterEach(async({page})=>page.unrouteAll({behavior:"ignoreErrors"}));
test.afterAll(()=>writeFileSync("../product/validation/d14-chart-mappings.json",JSON.stringify({
  confirmation_kind:"simulated_test",human_acceptance:"pending",boundaries:manifest.substitutions,
  reports:manifest.reports,observations:proof,
},null,2)+"\n"));
for(const key of ["midea","gree"])test(`${key} 两年度三指标图点、精确tooltip、PDF及2024披露切换`,async({page})=>{
  const errors:string[]=[],writes:string[]=[],responses:any[]=[];
  page.on("pageerror",e=>errors.push(e.message));
  page.on("request",r=>{if(r.method()==="POST"&&!r.url().endsWith("/__test__/analyses"))writes.push(r.url());});
  page.on("response",async r=>{if(r.url().endsWith("/__test__/analyses")&&r.ok())responses.push(await r.json());});
  await open(page,key);await single(page,key);
  for(const m of Object.keys(metrics)) {
    await page.getByLabel("图表指标",{exact:true}).selectOption(m);
    const a=responses.findLast(r=>r.metric_key===m);
    expect(a).toBeTruthy();await expect(page.locator(".chart-result")).toContainText(`${a.percentage_change}%`);
    await expect(page.locator(".chart-result")).toContainText(formatDecimal(a.absolute_change));
    for(const year of [2024,2025]) {
      const f=fact(key,year,year,m);
      await expect(page.getByTestId(`row-${m}`)).toContainText(formatDecimal(f.value_cny_yuan));
      await verifyPoint(page,f,`${key}-${year}`,"single",m==="operating_cash_flow");
    }
  }
  if(key==="midea") {await page.getByLabel("图表指标",{exact:true}).selectOption("revenue");await widths(page,"single");}
  await single(page,key,2025);
  for(const m of Object.keys(metrics)) {
    await page.getByLabel("图表指标",{exact:true}).selectOption(m);
    const old=fact(key,2024,2024,m),fresh=fact(key,2025,2024,m);
    await expect(page.locator(`[data-chart-point="${old.fact_id}"]`)).toHaveCount(0);
    await verifyPoint(page,fresh,`${key}-2025`,"single-version");
  }
  expect(errors).toEqual([]);expect(writes).toEqual([]);proof.push({key,analysis_responses:responses,readonly_post_paths:writes,errors});
});
for(const year of [2024,2025])test(`${year} A/B图与正式D13结果、双方PDF、三视口`,async({page,request})=>{
  const responses:any[]=[];
  page.on("response",async r=>{if(r.url().endsWith("/__test__/company-comparison")&&r.ok())responses.push(await r.json());});
  await open(page);await compare(page,year);
  const c=responses.findLast(c=>c.rows.every((r:any)=>r.status==="compared"));expect(c).toBeTruthy();
  for(const m of Object.keys(metrics)) {
    await page.getByLabel("图表指标",{exact:true}).selectOption(m);
    const row=c.rows.find((r:any)=>r.metric_key===m);
    await expect(page.locator(".chart-result")).toContainText(row.percentage_change+"%");
    await expect(page.locator(".chart-result")).toContainText(compactYi(row.absolute_change));
    for(const key of ["midea","gree"]) await verifyPoint(page,fact(key,year,year,m),`${key}-${year}`,"comparison");
  }
  if(year===2025){await page.getByLabel("图表指标",{exact:true}).selectOption("revenue");await widths(page,"comparison");}
  if(year===2024) {
    for(const [side,key] of [["A","midea"],["B","gree"]])await page.getByLabel(`${side} 报告来源`).selectOption(group(key,2025).document_id);
    await expect(page.getByTestId("compare-revenue")).toContainText("同口径可比");
    for(const key of ["midea","gree"]) await verifyPoint(page,fact(key,2025,2024,"operating_cash_flow"),`${key}-2025`,"comparison-version");
  }
  const r=c.rows[0];expect((await request.post("/api/analyses/company-comparison",{data:{schema_version:c.schema,
    company_a_id:c.company_a_id,company_b_id:c.company_b_id,period:year,selections:[{metric_key:r.metric_key,...r.selection}]}})).status()).toBe(404);
  proof.push({year,comparison_response:c,formal_rejects_simulation:true});
});
test("正式生产入口隔离模拟图点，零人工接受和事实保存",async({page,request})=>{
  const writes:string[]=[];page.on("request",r=>{if(r.method()==="POST")writes.push(r.url());});
  await page.goto(`/companies/${group("midea",2025).company_id}/analysis`);
  await expect(page.getByText("尚无可用于正式分析的已确认事实")).toBeVisible();
  await expect(page.locator("[data-chart-point]")).toHaveCount(0);
  await page.getByRole("button",{name:"双企业同期间比较",exact:true}).click();
  await page.getByLabel("企业 B").selectOption(group("gree",2025).company_id);
  await expect(page.getByRole("heading",{name:"明确选择双方报告"})).toBeVisible();
  await expect(page.locator("[data-chart-point]")).toHaveCount(0);expect(writes).toEqual([]);
  const c=fact("midea",2025,2025,"revenue"),p=fact("midea",2024,2024,"revenue");
  expect((await request.post("/api/analyses",{data:{schema_version:"financial-analysis-v1",company_id:c.company_id,metric_key:"revenue",current:reference(c),previous:reference(p)}})).status()).toBe(404);
});
test("相同事实复验保持图表DOM、指标和PDF；切换版本撤销旧图及旧PDF",async({page})=>{
  await open(page);await single(page);await page.getByLabel("图表指标",{exact:true}).selectOption("net_profit_parent");
  const f=fact("midea",2024,2024,"net_profit_parent");await page.locator(`[data-chart-point="${f.fact_id}"]`).click();
  await expect(page.locator("canvas")).toBeVisible();
  const chart=await page.locator(".recharts-surface").elementHandle(),canvas=await page.locator("canvas").elementHandle();
  await page.route("**/financial-facts?**",async route=>{const response=await route.fetch(),q=await response.json();q.facts.reverse();q.incidental="changed";await route.fulfill({response,json:q});});
  const read=page.waitForResponse(r=>r.url().includes("financial-facts?"));await page.evaluate(()=>window.dispatchEvent(new Event("focus")));await read;await page.waitForLoadState("networkidle");
  await expect(page.getByLabel("图表指标",{exact:true})).toHaveValue("net_profit_parent");
  expect(await chart?.evaluate(e=>e.isConnected)).toBe(true);expect(await canvas?.evaluate(e=>e.isConnected)).toBe(true);
  await page.getByRole("button",{name:"收起证据侧栏"}).click();
  await page.getByLabel("2024 归母净利润披露版本",{exact:true}).selectOption(fact("midea",2025,2024,"net_profit_parent").fact_id);
  await expect(page.locator(`[data-chart-point="${f.fact_id}"]`)).toHaveCount(0);await expect(page.locator("canvas")).toHaveCount(0);
  await expect(page.locator("[data-chart-point]")).toHaveCount(2);
  proof.push({stable_chart_and_pdf_dom:true,version_change_revokes_point:true});
});
test("缺失、冲突与blocked注入：单侧有效保留，阻断不画可信比较",async({page})=>{
  await page.route("**/financial-facts?**",async route=>{const response=await route.fetch(),q=await response.json();
    if(route.request().url().includes(group("gree",2025).company_id))q.facts=q.facts.filter((f:any)=>f.metric_key!=="operating_cash_flow");
    q.conflicting_periods=["injected conflict, explicit version required"];await route.fulfill({response,json:q});});
  await open(page);await expect(page.locator("[data-chart-point]")).toHaveCount(0);await compare(page);
  await page.getByLabel("图表指标",{exact:true}).selectOption("operating_cash_flow");
  await expect(page.locator("[data-chart-point]")).toHaveCount(1);await expect(page.locator(".chart-result")).toContainText("incomplete");
  await page.locator(".financial-chart").scrollIntoViewIfNeeded();
  await page.screenshot({path:"../product/validation/d14-screenshots/incomplete.png"});
  await page.route("**/__test__/company-comparison",async route=>{const response=await route.fetch(),c=await response.json();
    for(const r of c.rows){r.status="blocked";r.a=null;r.b=null;r.absolute_change=null;r.percentage_change=null;r.reasons=[{code:"injected_conflict",message:"合成口径冲突"}];}await route.fulfill({response,json:c});});
  await page.getByLabel("A 报告来源").selectOption("");await page.getByLabel("A 报告来源").selectOption(group("midea",2025).document_id);
  await expect(page.locator(".chart-result")).toContainText("不可比较");await expect(page.locator("[data-chart-point]")).toHaveCount(0);
  await expect(page.locator("[data-chart-fact-id]")).toHaveCount(0);
  proof.push({injection_only:true,missing_one_side:true,conflict_requires_selection:true,blocked_no_chart:true});
});
test("迟到比较与事实响应不能在切换企业后复活旧图",async({page})=>{
  await open(page);await compare(page);
  let release!:()=>void,seen!:()=>void;const gate=new Promise<void>(r=>release=r),start=new Promise<void>(r=>seen=r);
  await page.route("**/__test__/company-comparison",async route=>{const response=await route.fetch();seen();await gate;try{await route.fulfill({response});}catch{}});
  await page.getByLabel("A 报告来源").selectOption("");await start;
  await expect(page.locator("[data-chart-point]")).toHaveCount(0);
  await page.getByLabel("企业 B").selectOption("");release();await page.unrouteAll({behavior:"ignoreErrors"});
  await expect(page.locator("[data-chart-point]")).toHaveCount(0);
  let releaseFacts!:()=>void,seenFacts!:()=>void;const gateFacts=new Promise<void>(r=>releaseFacts=r),startFacts=new Promise<void>(r=>seenFacts=r);
  await page.route("**/financial-facts?**",async route=>{const response=await route.fetch();seenFacts();await gateFacts;try{await route.fulfill({response});}catch{}});
  await page.getByLabel("企业 B").selectOption(group("gree",2025).company_id);await startFacts;
  await page.getByLabel("企业 B").selectOption("");releaseFacts();await page.unrouteAll({behavior:"ignoreErrors"});
  await expect(page.locator("[data-chart-point]")).toHaveCount(0);
  proof.push({late_comparison_and_facts_ignored:true});
});
test("迟到单企分析在年度切换后不复活；网络错误撤图",async({page})=>{
  await open(page);await single(page);
  let release!:()=>void,seen!:()=>void;const gate=new Promise<void>(r=>release=r),start=new Promise<void>(r=>seen=r);
  await page.route("**/__test__/analyses",async route=>{const response=await route.fetch();seen();await gate;try{await route.fulfill({response});}catch{}});
  await page.getByLabel("2024 营业收入披露版本",{exact:true}).selectOption(fact("midea",2025,2024,"revenue").fact_id);await start;
  await expect(page.locator("[data-chart-point]")).toHaveCount(0);
  await page.getByLabel("本期年度",{exact:true}).selectOption("2024");release();await page.unrouteAll({behavior:"ignoreErrors"});
  await expect(page.locator("[data-chart-point]")).toHaveCount(0);
  await page.getByLabel("本期年度",{exact:true}).selectOption("2025");await expect(page.locator("[data-chart-point]")).toHaveCount(2);
  await page.route("**/financial-facts?**",r=>r.abort());await page.evaluate(()=>window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("heading",{name:"数据或来源不可用"})).toBeVisible();await expect(page.locator("[data-chart-point]")).toHaveCount(0);
  proof.push({late_single_analysis_ignored:true,read_error_clears_chart:true});
});
test("明确合成边界：正负方向、零点、极大和微小Decimal安全几何",async({page})=>{
  await page.route("**/src/main.tsx*",r=>r.fulfill({contentType:"application/javascript",body:"import '/tests/support/d14-chart-boundaries.tsx'"}));
  await page.goto("/companies/synthetic/analysis");
  await expect(page.locator("[data-chart-point]")).toHaveCount(2);
  const baseline=Number(await page.locator(".recharts-reference-line line").getAttribute("y1"));
  expect(Number(await page.locator('[data-chart-point="synthetic-0"]').getAttribute("y"))).toBeGreaterThanOrEqual(baseline-1);
  expect(Number(await page.locator('[data-chart-point="synthetic-1"]').getAttribute("y"))).toBeLessThan(baseline);
  await page.getByRole("button",{name:"零与负数",exact:true}).click();
  await expect(page.locator('circle[data-chart-point="synthetic-0"]')).toHaveCount(1);
  await page.locator('circle[data-chart-point="synthetic-0"]').hover();await expect(page.locator(".chart-tooltip")).toContainText("0.00 元");
  await page.getByRole("button",{name:"极大与小数",exact:true}).click();
  await expect(page.locator("[data-chart-point]")).toHaveCount(1);await expect(page.locator(".chart-caption")).toContainText("10^399 元");
  await expect(page.getByText("金额低于当前绘图分辨率",{exact:false})).toBeVisible();
  await page.locator('[data-chart-point="synthetic-0"]').hover();await expect(page.locator(".chart-tooltip")).toContainText("9".repeat(400)+".123456789");
  await page.getByRole("button",{name:"微小金额",exact:true}).click();await expect(page.locator("[data-chart-point]")).toHaveCount(2);
  await expect(page.locator(".chart-caption")).toContainText("10^-21 元");
  expect(await page.locator(".recharts-surface").evaluate(e=>!/(NaN|Infinity)/.test(e.outerHTML))).toBe(true);
  await page.screenshot({path:"../product/validation/d14-screenshots/synthetic-small-negative.png"});
  proof.push({synthetic_only:true,negative_direction:true,zero_circle:true,huge_decimal_preserved:true,tiny_decimal:true,no_nonfinite_geometry:true});
});
// Genuine correction runs last, in this suite's own disposable database.
test("真实来源纠错联合撤销图点、表格及已打开的PDF",async({page,request})=>{
  await open(page);await compare(page);
  const g=group("gree",2025),f=fact("gree",2025,2025,"revenue");
  await page.locator(`[data-chart-point="${f.fact_id}"]`).click();await expect(page.locator("canvas")).toBeVisible();
  expect((await request.post(`/api/documents/${g.document_id}/binding-corrections`,{data:{expected_attempt:1,
    metadata:{company_id:g.company_id,report_year:2025,report_type:"annual",basis:"unknown",period_start:"2025-01-01",period_end:"2025-12-31"},reason:"D14 isolated source invalidation"}})).status()).toBe(200);
  await page.evaluate(()=>window.dispatchEvent(new Event("focus")));
  await expect(page.locator(`[data-chart-point="${f.fact_id}"]`)).toHaveCount(0);
  await expect(page.locator(`[data-chart-fact-id="${f.fact_id}"]`)).toHaveCount(0);
  await expect(page.locator(`[data-fact-id="${f.fact_id}"]`)).toHaveCount(0);await expect(page.locator("canvas")).toHaveCount(0);
  await expect(page.getByTestId("compare-revenue").getByText("同口径可比",{exact:true})).toHaveCount(0);
  proof.push({real_source_correction:true,revoked_chart_table_pdf:true});
});
