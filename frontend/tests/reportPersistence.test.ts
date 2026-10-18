import test from 'node:test';
import assert from 'node:assert/strict';
import { validateReport } from '../src/product/reportPersistence.ts';
import type { ReportDetail } from '../src/product/reportPersistence.ts';
function value(): ReportDetail {
  return { schema_version:'report-detail-v1', payload_sha256:'a'.repeat(64), current_revision:2, current_eligibility:{status:'current_at_read',reason:null}, report:{schema_version:'report-revision-v1',report_id:'id',revision:1,parent_revision:null,operation_id:'op',created_at:'today',persisted:true,editor_revision:{title:'用户标题',conclusions:['断言'],origin:'user_edit',validation_status:'pending_semantic_review',verified_operating_attribution:false,qualification_limit:'user_assertions_unverified'},trusted_snapshot:{schema_version:'report-draft-v1',task_id:'task',task_revision:4,persisted:false,status:'simulated_draft',test_mode:'simulated_test',watermark:'simulated_test',financial_facts:Array(6).fill({}),financial_analysis:Array(3).fill({}),model_interpretations:[]}}} as unknown as ReportDetail;
}
test('D23 saved simulation remains isolated and never promoted by outer persistence',()=>{
  assert.equal(validateReport(value(),true).report.persisted,true);
  assert.throws(()=>validateReport(value(),false));
  const edited=value();edited.report.trusted_snapshot.watermark=null;assert.throws(()=>validateReport(edited,true));
});
test('D23 editor assertions cannot be relabelled verified or merged into trusted snapshots',()=>{
  for(const change of [{origin:'D10'},{validation_status:'verified_snapshot'},{verified_operating_attribution:true},{qualification_limit:'qualified'}]) {
    const edited=value();Object.assign(edited.report.editor_revision,change);assert.throws(()=>validateReport(edited,true));
  }
});
test('D23 historical parent, persisted schema and digest identity fail closed',()=>{
  for(const change of [{schema_version:'unknown'},{revision:0},{parent_revision:1},{persisted:false}]) {
    const edited=value();Object.assign(edited.report,change);assert.throws(()=>validateReport(edited,true));
  }
  const damaged=value();damaged.payload_sha256='bad';assert.throws(()=>validateReport(damaged,true));
});

import { assertSavedOwner } from '../src/product/reportState.ts';
test('saved response cannot attach A to B draft or a different task/report revision',()=>{
  const saved=value(), draft=saved.report.trusted_snapshot;
  assert.doesNotThrow(()=>assertSavedOwner(saved,draft));
  assert.throws(()=>assertSavedOwner(saved,{...draft,task_id:'B'}));
  assert.throws(()=>assertSavedOwner(saved,{...draft,task_revision:5}));
  saved.current_revision=1;
  const next=value();next.report.revision=2;next.report.parent_revision=1;
  assert.doesNotThrow(()=>assertSavedOwner(next,draft,saved));
  next.report.report_id='other';assert.throws(()=>assertSavedOwner(next,draft,saved));
});
