import test from "node:test";
import assert from "node:assert/strict";
import { chartData, chartIdentity } from "../src/product/chartData.ts";
import { productionAccess } from "../src/product/api.ts";
import type { Fact } from "../src/product/api.ts";
const f = { fact_id:"f",fact_set_id:"s",source_revision:"source",disclosure_version:"version",
  value_cny_yuan:"9007199254740993.005",current_valid:true,production_calculable:true,
  confirmation_kind:"local_operator",calculable:true,confirmation_status:"confirmed",integrity:"verified" } as Fact;
const slots = (facts: (Fact | null)[]) => facts.map((fact,i) => ({label:String(i),company:"synthetic",fact}));
test("render approximation preserves original Decimal object and exact identity", () => {
  const {points,scale} = chartData(slots([f]),productionAccess);
  assert.equal(points[0].fact,f);assert.equal(f.value_cny_yuan,"9007199254740993.005");
  assert.equal(scale,15);assert.ok(Number.isFinite(points[0].coordinate));
  for(const field of ["fact_id","fact_set_id","source_revision","disclosure_version"])
    assert.notEqual(chartIdentity(f),chartIdentity({...f,[field]:"different"}));
});
test("negative, zero and high precision decimal stay distinct from missing", () => {
  const {points} = chartData(slots(["-123456789.123456789","0","0.00000000001"].map((v,i) => ({...f,fact_id:String(i),value_cny_yuan:v}))),productionAccess);
  assert.ok(points[0].coordinate! < 0);assert.equal(points[1].coordinate,0);
  assert.equal(points[2].coordinate,null);assert.match(points[2].reason,/分辨率/);
  assert.equal(chartData(slots([null]),productionAccess).points[0].coordinate,null);
});
test("huge and tiny numbers cannot cause Infinity, NaN or silent underflow to zero", () => {
  for(const value of ["9".repeat(10000), "-"+"9".repeat(400), "0."+"0".repeat(1000)+"123456789"]){
    const {points} = chartData(slots([{...f,value_cny_yuan:value}]),productionAccess);
    assert.ok(Number.isFinite(points[0].coordinate));assert.notEqual(points[0].coordinate,0);
    assert.equal(points[0].fact?.value_cny_yuan,value);
  }
  for(const value of ["NaN","Infinity","1e999","", "--1"])
    assert.equal(chartData(slots([{...f,value_cny_yuan:value}]),productionAccess).points[0].coordinate,null);
});
test("production refuses simulated, unconfirmed, invalid and duplicate facts", () => {
  for(const patch of [{confirmation_kind:"simulated_test"},{current_valid:false},{production_calculable:false},
    {confirmation_status:"candidate"},{integrity:"conflict"}]) {
    const p=chartData(slots([{...f,...patch}]),productionAccess).points[0];
    assert.equal(p.fact,null);assert.equal(p.coordinate,null);
  }
  assert.equal(chartData(slots([f,f]),productionAccess).points[1].coordinate,null);
});
test("multiple real annual slots extend without fabricated points or interpolation", () => {
  const series = [2023,2024,2025,2026].map((period,i) => i===1 ? null : {...f,period,fact_id:String(period)});
  const {points} = chartData(slots(series),productionAccess);
  assert.equal(points.length,4);assert.equal(points[1].coordinate,null);
  assert.equal(points.filter(p => p.coordinate !== null).length,3);
});
