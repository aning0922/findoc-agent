import { test } from "node:test";
import assert from "node:assert/strict";
import { qaFailureMessage, qaRefusalMessage, researchFailureMessage } from "../src/product/recoveryMessages.ts";
import { reportPersistenceText, reportLimitations, editorDirty } from "../src/product/reportState.ts";
test("known QA failure, evidence refusal and uncertain research execution have separate recovery",()=>{
  assert.match(qaFailureMessage("llm_error"),/失败记录已保存/);
  assert.match(qaFailureMessage("llm_error"),/只读/);
  assert.match(qaFailureMessage("context_budget_error"),/上下文预算不足/);
  assert.match(qaFailureMessage("context_budget_error"),/缩小/);
  assert.doesNotMatch(qaFailureMessage("context_budget_error"),/校验未通过/);
  assert.doesNotMatch(qaFailureMessage("llm_error"),/llm_error/);
  assert.match(qaRefusalMessage("unsupported_table_structure"),/年度与金额列关系/);
  assert.match(qaRefusalMessage("requires_confirmed_financial_analysis"),/确定性分析/);
  assert.match(researchFailureMessage("operating_provider_unknown"),/尚无法确认/);
  assert.match(researchFailureMessage("budget_tool_calls_exhausted"),/预算已耗尽/);
  assert.match(researchFailureMessage("operating_output_invalid"),/研究失败/);
});
test("verified saved versions and current unsaved edits remain distinct without editing snapshots",()=>{
  const limits=["草稿尚未保存；需显式保存", "经营归因未验证", "原 PDF 需复验"];
  assert.doesNotMatch(reportPersistenceText(true),/草稿尚未保存/);
  assert.match(reportPersistenceText(false),/草稿尚未保存/);
  assert.deepEqual(reportLimitations(limits,true),limits.slice(1));
  assert.deepEqual(reportLimitations(limits,false),limits);
  assert.equal(editorDirty("旧标题","旧结论","旧标题",["旧结论"]),false);
  assert.equal(editorDirty("新标题","旧结论","旧标题",["旧结论"]),true);
  assert.equal(editorDirty("","",null,[]),false);
  assert.deepEqual(limits,["草稿尚未保存；需显式保存", "经营归因未验证", "原 PDF 需复验"]);
});
