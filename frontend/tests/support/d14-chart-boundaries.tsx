// Playwright-only synthetic render fixture. Never imported by the production entry.
import { createRoot } from "react-dom/client";
import { useState } from "react";
import FinancialChart from "../../src/product/FinancialChart.tsx";
import type { DataAccess, Fact } from "../../src/product/api.ts";
import "../../src/product/tokens.css";
import "../../src/product/product.css";
const access = { eligible: (f: Fact) => f.confirmation_kind === "simulated_test" && f.current_valid } as DataAccess;
function Boundary() {
  const [values,setValues]=useState(["-123456789.123456789", "100000000.005"]);
  const [opened,setOpened]=useState("");
  const facts=values.map((value,i)=>({fact_id:`synthetic-${i}`,fact_set_id:"synthetic-set",source_revision:"synthetic-source",
    disclosure_version:"synthetic-version",company_id:"synthetic-company",period:2024+i,metric_key:"revenue",
    value_cny_yuan:value,raw_value:value,raw_unit:"元",confirmation_kind:"simulated_test",production_calculable:false,
    current_valid:true,evidence:[{physical_page:1,evidence_id:"synthetic-evidence-not-a-real-pdf"}]} as Fact));
  return <main className="findoc-app" style={{padding:32}}><h1>明确合成事实 · simulated_test · 无真实PDF</h1>
    <button onClick={()=>setValues(["0.00","-123456789.123456789"])}>零与负数</button>
    <button onClick={()=>setValues(["9".repeat(400)+".123456789", "0.000000000000000000001"])}>极大与小数</button>
    <button onClick={()=>setValues(["0.000000000000000000001", "-0.000000000000000000002"])}>微小金额</button>
    <FinancialChart title="合成边界渲染" access={access} open={f=>setOpened(f.fact_id)} display={f=>f.value_cny_yuan+" 元"}
      metrics={[{metric:"revenue",message:"合成渲染测试，无业务计算，无四份年报结论。",slots:facts.map((f,i)=>({label:String(f.period),company:`合成企业 ${i}`,fact:f}))}]} />
    <output>{opened}</output>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Boundary/>);
