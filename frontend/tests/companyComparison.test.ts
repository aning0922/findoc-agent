import test from "node:test";
import assert from "node:assert/strict";
import { factsIdentity, compactYi, comparisonBody, reference, validateComparison, productionAccess } from "../src/product/api.ts";
import type { Fact, FactQuery, Comparison } from "../src/product/api.ts";
const f={company_id:"a",fact_id:"af",fact_set_id:"as",period:2025,metric_key:"revenue",
  source_revision:"1".repeat(64),disclosure_version:`disclosure-v1:${"2".repeat(64)}`,
  document_id:"ad",value_cny_yuan:"456451731000",raw_value:"456,451,731",raw_unit:"千元",
  current_valid:true,calculable:true,production_calculable:true,confirmation_kind:"local_operator",
  integrity:"verified",confirmation_status:"confirmed",evidence:[{evidence_id:"e",physical_page:2}],
  basis_evidence:[{evidence_id:"basis",physical_page:3}]} as Fact;
const b={...f,company_id:"b",fact_id:"bf",fact_set_id:"bs",document_id:"bd",value_cny_yuan:"170447058533.57"};
const q={facts:[f,b]} as FactQuery;
const selections=[{metric_key:"revenue",a:f,b}];
const result={schema:"financial-company-comparison-v1",company_a_id:"a",company_b_id:"b",period:2025,
  production_calculable:true,confirmation_kind:"local_operator",automatic_selection:false,
  formula:{absolute_change_id:"financial_absolute_change_v1",percentage_change_id:"financial_company_relative_signed_base_v1",
    version:"1",base:"company_a",absolute_expression:"B - A",percentage_expression:"(B - A) / A * 100"},
  rows:[{metric_key:"revenue",selection:{a:reference(f),b:reference(b)},a:f,b,status:"compared",
    absolute_change:"-286004672466.43",percentage_change:"-62.66",percentage_reason:null,reasons:[],limitations:[]}] } as Comparison;
test("identity ignores ordering and metadata, retains source and fact validity",()=>{
  assert.equal(factsIdentity(q),factsIdentity({...q,facts:[{...b,irrelevant:"changed"} as Fact,f]}));
  for(const change of [{source_revision:"3".repeat(64)},{disclosure_version:"other"},{current_valid:false},
      {value_cny_yuan:"0"},{integrity:"bad"},{evidence:[{evidence_id:"other",physical_page:3}]}])
    assert.notEqual(factsIdentity(q),factsIdentity({...q,facts:[{...f,...change} as Fact,b]}));
});
test("short yi display is explicitly approximate and decimal strings stay exact",()=>{
  assert.equal(compactYi("456451731000"),"≈ 4,564.5173");
  assert.equal(compactYi("170447058533.57"),"≈ 1,704.4705");
  assert.equal(compactYi("9007199254740993.005"),"≈ 90,071,992.5474");
  assert.equal(b.value_cny_yuan,"170447058533.57");
});
test("request submits only explicit IDs, metrics and period",()=>{
  const body=comparisonBody("a","b",2025,selections);
  assert.deepEqual(Object.keys(body.selections[0].a!).sort(),["disclosure_version","fact_id","fact_set_id","period","source_revision"]);
  assert.equal(JSON.stringify(body).includes("value_cny_yuan"),false);
});
test("comparison contract rejects swapped companies, late selections, wrong formulas and simulated production",()=>{
  assert.equal(validateComparison(result,"a","b",2025,selections,productionAccess),result);
  for(const value of [{...result,company_a_id:"b"},{...result,period:2024},
    {...result,formula:{...result.formula,base:"company_b"}},
    {...result,production_calculable:false,confirmation_kind:"simulated_test"},
    {...result,rows:[{...result.rows[0],b:{...b,value_cny_yuan:"0"}}]},
    {...result,rows:[result.rows[0],result.rows[0]]}])
    assert.throws(()=>validateComparison(value as Comparison,"a","b",2025,selections,productionAccess));
});
test("zero base remains partial and incomplete never contains formal differences",()=>{
  const partial={...result,rows:[{...result.rows[0],status:"partial",percentage_change:null,percentage_reason:"zero_base"}]} as Comparison;
  assert.equal(validateComparison(partial,"a","b",2025,selections,productionAccess),partial);
  assert.throws(()=>validateComparison({...partial,rows:[{...partial.rows[0],percentage_change:"0"}]},"a","b",2025,selections,productionAccess));
  const empty={...result,rows:[{...result.rows[0],status:"incomplete",a:null,b:null,absolute_change:null,percentage_change:null}]} as Comparison;
  assert.equal(validateComparison(empty,"a","b",2025,selections,productionAccess),empty);
  assert.throws(()=>validateComparison({...empty,rows:[{...empty.rows[0],absolute_change:"0"}]},"a","b",2025,selections,productionAccess));
});
