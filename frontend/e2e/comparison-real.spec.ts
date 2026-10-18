import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { compactYi } from "../src/product/api.ts";
const stage=process.env.FINDOC_COMPARISON_STAGE || "d13";
const root=readFileSync(`../data/30d-foundation/${stage}-product-runtime-path.txt`,"utf8").trim();
const manifest=JSON.parse(readFileSync(`${root}/manifest.json`,"utf8"));
const gold=JSON.parse(readFileSync("../product/validation/manual-benchmark.json","utf8")).facts;
const metrics: Record<string,string>={revenue:"营业收入",net_profit_parent:"归母净利润",operating_cash_flow:"经营活动现金流量净额"};
const proof: any[]=[];
async function legacyScreenshot(page: Page, options: Parameters<Page["screenshot"]>[0]) {
  if (stage === "d13") await page.screenshot(options);
}
function group(key:string,year:number) {
  return manifest.groups.find((g:any) => g.document_id===manifest.reports.find((r:any)=>r.report_id===`${key}-${year}`).source.document_id);
}
async function open(page:Page,year=2025) {
  await page.route("**/src/main.tsx*",r=>r.fulfill({contentType:"application/javascript",body:"import '/tests/support/d12-entry.tsx'"}));
  await page.goto(`/companies/${group("midea",2025).company_id}/analysis`);
  await page.getByRole("button",{name:"双企业同期间比较",exact:true}).click();
  await page.getByLabel("企业 B",{exact:true}).selectOption(group("gree",2025).company_id);
  await expect(page.getByRole("heading",{name:"明确选择双方报告"})).toBeVisible();
  await page.getByLabel("对比财务年度").selectOption(String(year));
}
async function select(page:Page,reportYear=2025) {
  await page.getByLabel("A 报告来源",{exact:true}).selectOption(group("midea",reportYear).document_id);
  await page.getByLabel("B 报告来源",{exact:true}).selectOption(group("gree",reportYear).document_id);
  for (const m of Object.keys(metrics)) await expect(page.getByTestId(`compare-${m}`)).toContainText("同口径可比");
}
test.afterEach(async ({page})=>page.unrouteAll({behavior:"ignoreErrors"}));
test.afterAll(()=>writeFileSync(`../product/validation/${stage}-product-measurements.json`,JSON.stringify({
  observations:proof,confirmation_kind:"simulated_test",human_acceptance:"pending",runtime:root,
  boundaries:manifest.substitutions,real_reports:4,
},null,2)));
for (const year of [2025,2024]) test(`${year} 同期间三指标、显式报告与两企原PDF证据`,async ({page,request})=>{
  const responses:any[]=[],errors:string[]=[];
  page.on("pageerror",e=>errors.push(e.message));
  page.on("response",async r=>{if(r.url().endsWith("/__test__/company-comparison")&&r.status()===200)responses.push(await r.json());});
  await open(page,year);
  expect(await page.getByLabel("企业 B").locator(`option[value="${group("midea",2025).company_id}"]`).count()).toBe(0);
  expect(responses).toHaveLength(0);
  for(const side of ["A","B"]) expect(await page.getByLabel(`${side} 报告来源`).inputValue()).toBe("");
  await select(page,year);
  const response=responses.findLast(c=>c.rows.every((r:any)=>r.status==="compared"));
  expect(response).toBeTruthy();
  expect(response.formula.absolute_expression).toBe("B - A");
  expect(response.formula.percentage_change_id).toBe("financial_company_relative_signed_base_v1");
  for(const m of Object.keys(metrics)) {
    for(const [side,key] of [["a","midea"],["b","gree"]]) {
      const row=response.rows.find((r:any)=>r.metric_key===m), f=row[side];
      const expected=gold.find((v:any)=>v.document_id===`${key}-${year}`&&v.period===year&&v.metric===m);
      expect(f.value_cny_yuan).toBe(expected.value_cny_yuan);
      expect(f.raw_unit).toBe(key==="midea"?"千元":"元");
      await expect(page.locator(`[data-fact-id="${f.fact_id}"]`)).toContainText(compactYi(f.value_cny_yuan));
      await page.locator(`[data-fact-id="${f.fact_id}"]`).click();
      await expect(page.getByLabel("物理页码")).toHaveValue(String(f.evidence[0].physical_page));
      await expect(page.locator("canvas")).toHaveAttribute("aria-label",`PDF 物理第 ${f.evidence[0].physical_page} 页`);
      await expect(page.locator(".pdf-location")).toContainText("金额区域已核验");
      if(year===2025&&m==="revenue") await legacyScreenshot(page,{path:`../product/validation/d13-screenshots/${side}-2025-pdf.png`});
      await page.getByRole("button",{name:"返回核对",exact:true}).click();
      proof.push({year,side,metric:m,fact_id:f.fact_id,normalized:f.value_cny_yuan,raw:f.raw_value,unit:f.raw_unit,
        evidence_id:f.evidence[0].evidence_id,physical_page:f.evidence[0].physical_page,source_revision:f.source_revision,disclosure_version:f.disclosure_version});
    }
  }
  if(year===2024) {
    await select(page,2025);
    for(const side of ["a","b"]){
      await page.getByTestId("compare-revenue").getByText(`${side.toUpperCase()} · 来源与版本`,{exact:false}).click();
      const picker=page.getByLabel(`${side.toUpperCase()} 营业收入披露版本`,{exact:true});
      expect(await picker.inputValue()).toBe(group(side==="a"?"midea":"gree",2025).facts.find((f:any)=>f.period===2024&&f.metric_key==="revenue").fact_id);
      expect(await picker.locator("option").count()).toBe(3);
      await picker.selectOption("");
      await expect(page.getByTestId("compare-revenue")).toContainText("incomplete");
      await expect(page.getByTestId("compare-revenue").getByText("同口径可比",{exact:true})).toHaveCount(0);
      await picker.selectOption(group(side==="a"?"midea":"gree",2024).facts.find((f:any)=>f.metric_key==="revenue").fact_id);
    }
    await expect(page.getByTestId("compare-revenue")).toContainText("同口径可比");
    proof.push({same_value_different_versions_explicit:true});
  }
  if(year===2025) for(const width of [1440,1280,1024]) {
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    const scroll=page.getByLabel("双企业比较表格滚动区域");
    expect(await scroll.evaluate(e=>e.scrollWidth>e.clientWidth)).toBe(true);
    await page.evaluate(()=>window.scrollTo(0,0));
    await legacyScreenshot(page,{path:`../product/validation/d13-screenshots/comparison-${width}.png`,fullPage:true});
    proof.push({width,whole_page_overflow:false,local_scroll:true});
  }
  const body={schema_version:"financial-company-comparison-v1",company_a_id:response.company_a_id,
    company_b_id:response.company_b_id,period:year,selections:response.rows.map((r:any)=>({metric_key:r.metric_key,...r.selection}))};
  expect((await request.post("/api/analyses/company-comparison",{data:body})).status()).toBe(404);
  expect(errors).toEqual([]);
  proof.push({year,responses,formal_simulation_rejected:true,errors});
});
test("相同数据后台复验稳定；改变来源即时撤销结果；概览首屏KPI",async ({page})=>{
  await open(page);await select(page);
  await page.getByLabel("比较展示单位").selectOption("yuan");
  const original=group("midea",2025).facts.find((f:any)=>f.metric_key==="revenue"&&f.period===2025);
  await page.locator(`[data-fact-id="${original.fact_id}"]`).click();await expect(page.locator("canvas")).toBeVisible();
  const canvas=await page.locator("canvas").elementHandle();
  await page.route("**/financial-facts?**",async route=>{
    const response=await route.fetch(),q=await response.json();q.facts.reverse();q.incidental_metadata="different";
    await route.fulfill({response,json:q});
  });
  const completed=page.waitForResponse(r=>r.url().includes("financial-facts?"));
  await page.evaluate(()=>window.dispatchEvent(new Event("focus")));await completed;
  // The first query response is not the completion of the four-request single-flight refresh.
  await page.waitForLoadState("networkidle");
  await expect(page.getByLabel("A 报告来源")).toHaveValue(group("midea",2025).document_id);
  await expect(page.getByTestId("compare-revenue")).toContainText("同口径可比");
  expect(await canvas?.evaluate(e=>e.isConnected)).toBe(true);
  await page.unroute("**/financial-facts?**");
  await page.route("**/financial-facts?**",async route=>{
    const response=await route.fetch(),q=await response.json();
    for(const f of q.facts)if(f.company_id===group("midea",2025).company_id&&f.period===2025)f.current_valid=false;
    await route.fulfill({response,json:q});
  });
  await page.evaluate(()=>window.dispatchEvent(new Event("focus")));
  await expect(page.getByText("来源发生变化",{exact:false})).toBeVisible();
  await expect(page.locator("canvas")).toHaveCount(0);
  await expect(page.locator(`[data-fact-id="${original.fact_id}"]`)).toHaveCount(0);
  await expect(page.getByTestId("compare-revenue").getByText("同口径可比",{exact:true})).toHaveCount(0);
  await page.unroute("**/financial-facts?**");
  await page.getByRole("link",{name:"企业概览",exact:true}).click();
  const kpi=page.getByTestId("kpi-revenue");await expect(kpi).toBeVisible();
  expect((await kpi.boundingBox())!.y).toBeLessThan(600);
  if (!await page.getByLabel('2025 营业收入披露版本', {exact:true}).isVisible())
    await page.getByText("检查与选择各指标披露版本",{exact:true}).click();
  for(const [m,title]of Object.entries(metrics))await page.getByLabel(`2025 ${title}披露版本`,{exact:true}).selectOption(group("midea",2025).facts.find((f:any)=>f.metric_key===m&&f.period===2025).fact_id);
  await page.getByLabel("展示单位",{exact:true}).selectOption("yi-short");
  await expect(kpi).toContainText(compactYi(original.value_cny_yuan));
  await page.getByText("检查与选择各指标披露版本",{exact:true}).click();
  await legacyScreenshot(page,{path:"../product/validation/d13-screenshots/overview-compact.png",fullPage:true});
  proof.push({stable_poll_preserves_canvas:true,source_change_revokes_comparison:true,kpi_first_screen:true});
});
test("单侧缺项与双方空数据不会补零；其他指标继续比较",async ({page})=>{
  await page.route("**/financial-facts?**",async route=>{
    const response=await route.fetch(),q=await response.json();
    if(route.request().url().includes(group("gree",2025).company_id))q.facts=q.facts.filter((f:any)=>f.metric_key!=="operating_cash_flow");
    await route.fulfill({response,json:q});
  });
  await open(page);await page.getByLabel("A 报告来源").selectOption(group("midea",2025).document_id);
  await page.getByLabel("B 报告来源").selectOption(group("gree",2025).document_id);
  await expect(page.getByTestId("compare-revenue")).toContainText("同口径可比");
  await expect(page.getByTestId("compare-operating_cash_flow")).toContainText("incomplete");
  await legacyScreenshot(page,{path:"../product/validation/d13-screenshots/one-side-missing.png",fullPage:true});
  await page.unroute("**/financial-facts?**");
  await page.route("**/financial-facts?**",async route=>{
    const response=await route.fetch(),q=await response.json();q.facts=[];await route.fulfill({response,json:q});
  });
  await page.reload();await page.getByRole("button",{name:"双企业同期间比较",exact:true}).click();
  await page.getByLabel("企业 B").selectOption(group("gree",2025).company_id);
  await expect(page.getByRole("heading",{name:"明确选择双方报告"})).toBeVisible();
  await page.getByLabel("对比财务年度").selectOption("2025");
  await expect(page.locator(".money-link")).toHaveCount(0);
  await expect(page.getByTestId("compare-revenue")).toContainText("incomplete");
  proof.push({fault_injection:["one-sided missing","both empty"],other_metrics_retained:true});
});
test("A/B公司切换与迟到比较响应不混用旧结果",async ({page})=>{
  await open(page);await select(page);
  let release!:()=>void, seen!:()=>void;
  const gate=new Promise<void>(r=>release=r),start=new Promise<void>(r=>seen=r);
  await page.route("**/__test__/company-comparison",async route=>{
    const response=await route.fetch();seen();await gate;try{await route.fulfill({response});}catch{}
  });
  await page.getByLabel("A 报告来源").selectOption("");await start;
  await page.getByLabel("企业 B").selectOption("");release();
  await expect(page.locator(".money-link")).toHaveCount(0);
  await expect(page.getByRole("heading",{name:"两企业同期间财务比较"})).toHaveCount(0);
  await page.unroute("**/__test__/company-comparison");
  await page.getByLabel("当前企业").selectOption(group("gree",2025).company_id);
  await page.getByRole("button",{name:"双企业同期间比较",exact:true}).click();
  await expect(page.getByLabel("企业 B")).toHaveValue("");
  proof.push({late_response_after_company_switch_ignored:true});
});
test("D12 单企业复验保留年度、指标、单位、披露选择与原PDF", async ({page}) => {
  await open(page);
  await page.getByRole("button",{name:"单企业跨年分析",exact:true}).click();
  for(const [m,title] of Object.entries(metrics)) for(const year of [2024,2025]) {
    await page.getByLabel(`${year} ${title}披露版本`,{exact:true}).selectOption(
      group("midea",year).facts.find((f:any)=>f.metric_key===m&&f.period===year).fact_id);
  }
  await expect(page.getByTestId("row-revenue")).toContainText("12.11%");
  await page.getByLabel("展示单位",{exact:true}).selectOption("yi-short");
  const f=group("midea",2025).facts.find((f:any)=>f.metric_key==="revenue"&&f.period===2025);
  await page.locator(`[data-fact-id="${f.fact_id}"]`).click();
  await expect(page.locator("canvas")).toBeVisible();
  await expect(page.locator('.pdf-location')).toContainText('金额区域已核验');
  const canvas=await page.locator("canvas").elementHandle();
  await page.route("**/financial-facts?**",async route=>{
    const response=await route.fetch(),q=await response.json();q.facts.reverse();q.description="incidental";
    await route.fulfill({response,json:q});
  });
  const read=page.waitForResponse(r=>r.url().includes("financial-facts?"));
  await page.evaluate(()=>window.dispatchEvent(new Event("focus")));await read;
  await expect(page.getByLabel("2025 营业收入披露版本",{exact:true})).toHaveValue(f.fact_id);
  await expect(page.getByLabel("展示单位",{exact:true})).toHaveValue("yi-short");
  await expect(page.getByTestId("row-revenue")).toContainText("12.11%");
  expect(await canvas?.evaluate(e=>e.isConnected)).toBe(true);
  proof.push({single_company_stable_poll_preserves_choices_units_result_pdf:true});
});
test("D13 零基数与负基数限制UI（明确响应注入）",async ({page}) => {
  await page.route("**/__test__/company-comparison",async route=>{
    const response=await route.fetch(),c=await response.json();
    for(const row of c.rows) if(row.status==="compared") {
      row.limitations=[{code:"negative_base",message:"企业 A 为负基数，使用带符号分母；百分比符号不能表示经营改善或恶化。"}];
      if(row.metric_key==="revenue") {row.status="partial";row.percentage_change=null;row.percentage_reason="zero_base";
        row.reasons=[{code:"zero_base",message:"企业 A 为零，相对差异无定义；仅提供 B − A 差额。"}];}
    }
    await route.fulfill({response,json:c});
  });
  await open(page);await page.getByLabel("A 报告来源").selectOption(group("midea",2025).document_id);
  await page.getByLabel("B 报告来源").selectOption(group("gree",2025).document_id);
  await expect(page.getByTestId("compare-revenue")).toContainText("无定义（A 为零）");
  await expect(page.getByTestId("compare-net_profit_parent")).toContainText("不能表示经营改善或恶化");
  await expect(page.getByTestId("compare-revenue")).toContainText("部分可比");
  await legacyScreenshot(page,{path:"../product/validation/d13-screenshots/injected-zero-negative-limits.png",fullPage:true});
  proof.push({ui_response_injection_only:["zero_base","negative_base"],actual_decimal_boundaries:"tests/test_d13_company_comparison.py"});
});
test("真实B来源纠错后联合复验撤销双企差异和PDF",async ({page,request})=>{
  await open(page);await select(page);
  const g=group("gree",2025),f=g.facts.find((f:any)=>f.metric_key==="revenue"&&f.period===2025);
  await page.locator(`[data-fact-id="${f.fact_id}"]`).click();await expect(page.locator("canvas")).toBeVisible();
  const response=await request.post(`/api/documents/${g.document_id}/binding-corrections`,{data:{expected_attempt:1,
    metadata:{company_id:g.company_id,report_year:2025,report_type:"annual",basis:"unknown",period_start:"2025-01-01",period_end:"2025-12-31"},reason:"D13 isolated B source correction"}});
  expect(response.status()).toBe(200);await page.evaluate(()=>window.dispatchEvent(new Event("focus")));
  await expect(page.locator(`[data-fact-id="${f.fact_id}"]`)).toHaveCount(0);await expect(page.locator("canvas")).toHaveCount(0);
  await expect(page.getByTestId("compare-revenue").getByText("同口径可比",{exact:true})).toHaveCount(0);
  await expect(page.getByText("来源发生变化",{exact:false})).toBeVisible();
  await legacyScreenshot(page,{path:"../product/validation/d13-screenshots/source-invalidated.png",fullPage:true});
  proof.push({real_correction:true,old_b_amount_and_both_differences_revoked:true});
});
