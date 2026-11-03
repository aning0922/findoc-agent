// Explicitly invoked by root only. No CLI, .env, browser launch, login or provider setup.
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';

/** api(path, method='GET', body?) -> parsed JSON or throw.
 * api.sourceFixtures maps midea-2024/... to actual document IDs in the current verified generation.
 * api.evidenceTier is a descriptive root-owned label (default unknown), not proof of model usage.
 * Root supplies an authenticated page and shared budget-protected API callback. No retries.
 */
export async function runFixedIntentEval(page, base, api, out) {
  if (!page || new URL(page.url()).origin !== new URL(base).origin || typeof api !== 'function') throw Error('Authenticated same-origin page and root API callback required');
  const dataset = JSON.parse(await readFile(new URL('../../eval/showcase-cases.json', import.meta.url), 'utf8'));
  if (dataset.cases.length !== 15 || new Set(dataset.cases.map(c => c.id)).size !== 15) throw Error('Expected exactly 15 unique fixed cases');
  const fixtures = api.sourceFixtures || {};
  const result = {schema_version:'showcase-fixed-intent-eval-v1', evidence_tier_actual:api.evidenceTier || 'unknown', provider_enabled_intent_requests:0, max_intent_requests:15, results:[]};
  const skip = {
    'E01-03':'Requires a verified prior turn; this intent-only runner does not create paid turns.',
    'E01-08':'Requires isolated injected document fixture; never inject into real sources.',
    'E01-10':'Requires controlled source-revision race.',
    'E01-11':'Requires persisted note plus real BGE two-conversation setup.',
    'E01-12':'Requires deletion fence and real BGE two-conversation setup.',
    'E01-14':'Requires completed verified job and report contract execution.',
    'E01-15':'Requires paired completed single/deep jobs; one intent cannot establish comparison.'
  };
  await mkdir(out, {recursive:true});
  async function persist() { await writeFile(`${out}/fixed-intent-eval.json`,JSON.stringify(result,null,2)); }
  for (const c of dataset.cases) {
    const row = {case_id:c.id, question:c.question, mode:c.mode, status:'skipped', evidence_tier_actual:result.evidence_tier_actual, reason:null, invariants:[], provider_attempts:null, cost_cny:null, cost_status:'root_proxy_only', duration_ms:null};
    result.results.push(row);
    if (skip[c.id]) {row.reason=skip[c.id];await persist();continue;}
    const aliases = c.source_fixture.startsWith('all-four') ? dataset.source_catalog : c.source_fixture.split(';')[0].split('+');
    const documents = aliases.map(alias=>fixtures[alias]);
    if (documents.some(id=>typeof id!=='string'||!id) || new Set(documents).size!==documents.length) {row.reason=`Missing exact current-generation source fixtures: ${aliases.join(',')}`;await persist();continue;}
    let conversation;
    const createOp=randomUUID(); row.conversation_operation_id=createOp;
    try { conversation=await api('/conversations','POST',{operation_id:createOp,document_ids:documents,title:`固定评测 ${c.id}`}); }
    catch {row.status='unknown';row.reason='Conversation setup outcome unknown; no intent sent, no mutation retry.';await persist();continue;}
    if(!conversation?.conversation_id || !Array.isArray(conversation.sources) || conversation.sources.length!==documents.length || !conversation.sources.every(s=>documents.includes(s.document_id))) {row.status='fail';row.reason='Frozen conversation selection mismatch; intent not sent.';await persist();continue;}
    row.conversation_id=conversation.conversation_id;row.source_refs=conversation.sources.map(({document_id,source_revision,company_id})=>({document_id,source_revision,company_id}));
    const op=randomUUID();row.operation_id=op;row.status='unknown';result.provider_enabled_intent_requests++;await persist();const started=Date.now();
    let intent;
    try {intent=await api('/research/intent','POST',{operation_id:op,conversation_id:conversation.conversation_id,text:c.question,requested_mode:c.mode});}
    catch {try {const receipt=await api(`/research/operations/${op}`);if(receipt.operation_id===op&&receipt.state==='completed')intent=receipt.result;}catch { /* UNKNOWN preserved, never retry POST. */ }}
    row.duration_ms=Date.now()-started;
    if(!intent){row.reason='Intent UNKNOWN; original operation retained for read-only recovery.';await persist();continue;}
    row.intent_id=intent.intent_id;row.proposal_origin=intent.proposal_origin;row.provider_error=intent.provider_error;
    const companies=new Set(conversation.sources.map(s=>s.company_id));
    row.invariants=[{name:'intent bound to created conversation',status:intent.conversation_id===conversation.conversation_id?'pass':'fail'},
      {name:'company scope stays frozen',status:Array.isArray(intent.company_ids)&&intent.company_ids.every(id=>companies.has(id))?'pass':'fail'},
      {name:'requested mode retained',status:intent.mode===c.mode?'pass':'fail'},
      {name:'proposal action enum is valid (not execution authorization)',status:Array.isArray(intent.actions)&&intent.actions.every(a=>['read_evidence','read_confirmed_facts','create_task','draft_report','clarify'].includes(a))?'pass':'unknown'},
      ...c.expected_program_invariants.map(name=>({name,status:'unknown',reason:'Intent-only execution does not prove downstream program invariant.'}))];
    row.status=row.invariants.some(v=>v.status==='fail')?'fail':'partial';row.reason='Intent proposal observed only; findings, semantic relevance and required case tier remain unverified.';await persist();
  }
  result.denominators={fixed_cases:15, intent_requests:result.provider_enabled_intent_requests, status_counts:Object.fromEntries(['pass','fail','partial','unknown','skipped','not_run'].map(s=>[s,result.results.filter(r=>r.status===s).length])), required_tier_pass:0};
  await persist();return result;
}
